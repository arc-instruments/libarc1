import os.path
import serial
import time
import functools
import inspect, importlib, pkgutil
import threading
import numpy as np
import glob
import json
import struct
from queue import Queue
from enum import IntEnum
from dataclasses import dataclass
from collections import namedtuple, deque

from .packets import INIT, INIT_ACK, SELECT, READ_ONE
from .packets import PULSEREAD_ONE, READ_ALL, SET_VREAD
from . import modules
from .modules.readops import ReadAll, ReadMasked, Retention
from .log import LOG


class READ_MODE(IntEnum):
    """ Read mode for ArC1 read-out operations. """

    CLASSIC = 0
    """ Linear resistor mode """
    TIA = 1
    """ Use 2-point transimpedance amplifier """
    TIA4P = 2
    """ Use 4-point transimpedance amplifier (V>0) """
    TIA4P_NEG = 3
    """ Use 4-point transimpedance amplifier (V<0) """


class SESSION(IntEnum):
    """ Session type configuration. """

    LOCAL = 0
    """ Direct access to crossbar; either package or headers """
    EXTERNAL_BNC = 1
    """ Use external BNC connectors to interface devices """
    BNC_TO_LOCAL = 2
    """ Measurement capabilities disabled; ArC1 works as a switch matrix """
    OFFLINE = 3
    """ All capabilities disabled """


class SNEAKPATH_LIMIT(IntEnum):
    """ Sneak path limitation policies """

    ONE_THIRD = 0
    """ Apply 1/3 of the active read voltage to the inactive lines """
    ONE_HALF = 1
    """ Apply 1/2 of the active read voltage to the inactive lines """
    FLOAT = 2
    """ Leave inactive lines floating """


class SERIES_RES(IntEnum):
    """ Serier resistance for overcurrent protection """

    R1K = 1
    """ 1k Series Resistance """
    R10K = 2
    """ 10k Series Resistance """
    R100K = 3
    """ 100k Series Resistance """
    R1M = 4
    """ 1M Series Resistance """
    R0 = 7
    """ No series resistance """


@dataclass
class ArC1Conf:
    """
    This is a data class defining the configuration of ArC1. It can be passed
    as an argument when connecting to the board.

    >>> from libarc1 import ArC1, ArC1Conf
    >>> conf = ArC1Conf()
    >>> # set read cycles to 50
    >>> conf.read_cycles = 50
    >>> arc1 = ArC1('/dev/ttyACM0', config=conf)
    """

    read_cycles: int = 30
    """ Number of read cycles per read-out operation """
    words: int = 32
    """ Number of wordlines in connected crossbar; min: 1, max: 32 """
    bits: int = 32
    """ Number of bitlines in connected crossbar; min: 1, max: 32 """
    read_mode: int = READ_MODE.TIA4P
    """ Method use for readouts; see `libarc1.arc.READ_MODE` """
    session_type: int = SESSION.LOCAL
    """ Type of session; see `libarc1.arc.SESSION` """
    sneak_path: int = SNEAKPATH_LIMIT.ONE_THIRD
    """ Method of sneak path limitation; see `libarc1.arc.SNEAKPATH_LIMIT` """
    Vread: float = 0.5
    """ Read-out voltage """
    write_delay: float = 0.001
    """
    Minimum delay between consecutive write operations. **CAUTION**: Using
    values < 0.5 ms will probably lead to dropped packets.
    """


class ConnectionError(Exception):
    """ Error used to indicate connectivity issues """

    def __init__(self, message=""):
        self.message = message


class OperationInProgress(Exception):
    """ Error used to indicate that an existin operation is in progress """

    def __init__(self, op_name=""):
        if op_name == "":
            self.message = "An operation is in progress"
        else:
            self.message = "%s operation is in progress" % op_name


class ArC1():
    """
    Main class for interacting with ArC1. It encapsulates the connection to the
    tool, provides basic operations (select, read, write, retention, etc.).
    Units are **always** in SI (Volts for voltage, seconds for durations, etc.)

    Arguments
    ---------
    Except for the ``port`` and maybe ``config`` you shouldn't need to define
    any more arguments. The defaults are always compatible with the latest
    firmware of the board.

    * ``port``: A serial port to connect to. This follows the naming convention
      used by the operating system; for instance ``COM1`` on Windows,
      ``/dev/ttyACM0`` on Linux, etc.
    * ``baud``: Baud rate of the serial port connection
    * ``parity``: Parity of the serial port connection. Defaults to even parity
    * ``stop``: Number of stop bits.
    * ``config``: ArC1 configuration; see `libarc1.arc.ArC1Conf`
    """

    def __init__(self, port, baud=921600, parity=serial.PARITY_EVEN,
            stop=serial.STOPBITS_ONE, config=ArC1Conf(), _buffer_impl='queue'):

        # There are two implementations for the internal buffer
        # queue and deque. Deque is faster and atomic for some functions but
        # otherwise not thread-safe. Queue is slower but thread-safe. By
        # default we're using the conservative approach (Queue). Regardless
        # the impl, buffers have three funcs: _add_to_buffer, _get_from_buffer
        # and _items_in_buffer.
        if _buffer_impl == 'queue':
            self._buffer = Queue()
            self.add_to_buffer = self._buffer.put
            self._get_from_buffer = self._buffer.get
            self._items_in_buffer = self._buffer.qsize
        elif _buffer_impl == 'deque':
            self._buffer = deque()
            self.add_to_buffer = self._buffer.appendleft
            def __deque_get():
                while True:
                    # block until something is in the queue
                    if len(self._buffer) != 0:
                        return self._buffer.pop()
            self._get_from_buffer = __deque_get
            self._items_in_buffer = lambda: len(self._buffer)
        else:
            raise ValueError("Invalid buffer implementation %s" % _buffer_impl)

        # lock for write ops
        self.lock  = threading.Lock()
        self._port = None
        self._config = config

        # Ensure that TIA4P_NEG is enabled if Vread < 0.0
        Vread = self._config.Vread
        read_mode = self._config.read_mode

        if Vread < 0.0 and read_mode == READ_MODE.TIA4P:
            self._config.read_mode = READ_MODE.TIA4P_NEG

        self.initialise(port, baud, parity, stop)

        # active operation (this is typically a thread)
        self._operation = None

        time.sleep(1)

        # load everything from `libarc.modules`
        self.modules = {}
        self._load_builtin_modules()

        LOG.debug(self._config)

    def _load_builtin_modules(self):
        """
        Load all non-package modules found under `libarc1.modules`.
        """
        for loader, modname, is_pkg in pkgutil.walk_packages(modules.__path__):
            if is_pkg:
                continue
            # import modules so that we can inspect its members
            mod = importlib.import_module(".".join((modules.__name__, modname)))
            # and find all classes that are subclasses of `modules.Module`
            for _, kls in inspect.getmembers(mod, inspect.isclass):
                if issubclass(kls, modules.Module) and kls is not modules.Module:
                    self.register_module(kls)

    @property
    def config(self):
        """
        Returns the active configuration. This cannot be changed without
        reinitialising the instrument. See `libarc1.arc.ArC1.initialise`.
        """
        return self._config

    def register_module(self, mod):
        """
        Register module ``mod``. Note that if a module with the same tag exists
        it will be overwritten. Module *must* be a subclass of
        `libarc1.modules.Module`.
        """
        if not issubclass(mod, modules.Module):
            raise ValueError("Invalid module type; must subclass `libarc.modules.Module`")

        self.modules[mod.tag] = mod

    @staticmethod
    def _import_predicate(mod):
        return inspect.isclass(mod) and \
                issubclass(mod, modules.Module) and \
                mod is not modules.Module

    def _open_modules_from_file(self, path):
        """
        Load and return modules found on the python file specified. Note that
        if filename contains any more dots ('.') other than the one separating
        the filename from the suffix they will be converted to '_'.
        """

        # take the basename from path and replace any dots before the .py
        # suffix with '_'
        modname = os.path.splitext(os.path.basename(path))[0].replace(".", "_")
        modfile = importlib.machinery.SourceFileLoader(modname, path).load_module()

        mods = inspect.getmembers(modfile, ArC1._import_predicate)

        return [m[1] for m in mods]

    def _open_modules_from_folder(self, path):
        """
        Same as `libarc1.arc.ArC1.open_modules_from_file` but instead of a
        single file load all modules found in python source files under
        specified ``path``.
        """
        if not os.path.isdir(path):
            raise ValueError("%s is not a folder" % path)

        mods = []

        files = glob.glob(os.path.join(path, '*.py'))
        for f in files:
            mods.extend(self._open_modules_from_file(f))

        return mods

    def register_modules_from_file(self, path):
        """
        Load modules from file into the internal module list. File must be
        ending in ``.py``.
        """
        for mod in self._open_modules_from_file(path):
            self.modules[mod.tag] = mod

    def register_modules_from_folder(self, path):
        """
        Load and register all modules from python files found under folder
        ``path``.
        """
        for mod in self._open_modules_from_folder(path):
            self.modules[mod.tag] = mod

    def read_floats(self, how_many):
        """
        Reads a number of floating point numbers from the serial port. This
        is a blocking operation.
        """
        #while self._port.inWaiting() < how_many * 4:
        #   pass
        # values = self._port.read(how_many * 4)
        # return np.frombuffer(memoryview(values), dtype=np.float32)
        return np.frombuffer(self.read_bytes(how_many * 4), dtype=np.float32)

    def read_bytes(self, how_many):
        """
        Reads a number of bytes from the serial port. This is a blocking
        operation.
        """
        values = self._port.read(size=how_many)
        return memoryview(values)

    def update_Vread(self, val):
        """
        Updates the current read-out voltage. Absolute maximum value is ±12 V.
        Depending on the current read-out mode (see `libarc1.arc.READ_MODE`)
        a switch from `libarc1.arc.READ_MODE.TIA4P` to `libarc1.arc.READ_MODE.TIA4P_NEG`
        might be required. This is done automatically.
        """
        if np.abs(val) > 12.0:
            raise ValueError("Vread out of bounds -12 < V < 12")

        # Ensure that TIA4P_NEG is selected when V < 0.0 in TIA4P mode
        if val < 0.0 and self._config.read_mode == READ_MODE.TIA4P:
            read_mode = READ_MODE.TIA4P_NEG
        elif val > 0.0 and self._config.read_mode == READ_MODE.TIA4P_NEG:
            read_mode = READ_MODE.TIA4P
        else:
            read_mode = self._config.read_mode

        self.write_packet(SET_VREAD(val, read_mode))
        self._config.Vread = val
        self._config.read_mode = read_mode

    def _discard_buffer(self):

        # if no operation is running and the buffer is empty then
        # probably the buffer has already been consumed; so return
        if self._operation is None and self._items_in_buffer() == 0:
            return

        # otherwise just consume the buffer; doing nothing
        for _ in iter(self._get_from_buffer, None):
            pass

    def write(self, bytestream):
        """
        Write an arbitrary bytestream to the serial port. None of the
        user-facing functionality requires direct access to the serial
        port. If you really need to write manually to the serial port
        consider using predefined packets with `libarc1.arc.ArC1.write_packet`
        instead.
        """
        with self.lock:
            self._port.write(bytestream)
            time.sleep(self._config.write_delay)

    def write_packet(self, pkt):
        """
        Write a command packet to the serial port. The packet is converted to
        the proper bytestream. All modules and internal operation expose the
        packets required to be sent to the instrument.
        """
        with self.lock:
            for parts in pkt:
                self._port.write(parts)

    def read_line(self):
        """
        Read a line from the serial port. Result is a bytearray. As with
        `libarc1.arc.write` direct read-out from the tool should not be
        required.
        """
        return self._port.readline()

    def reset(self):
        """ Force a uC reset """
        self.write(b"00\n")
        time.sleep(2)

    def close(self):
        """
        Disconnect from the tool closing the serial port
        """
        self._port.close()
        self._port = None

    def initialise(self, port, baud, parity, stop):
        """
        Set up serial ports and initialise the instrument. This
        is always done during instantiation of the `ArC1` object
        but can also be done again at will. This will always reset
        the uC first.
        """

        if self._port is not None:
            self._port.close()
            self._port = None

        self._port = serial.Serial(port=port, baudrate=baud, timeout=7,
            parity=parity, stopbits=stop)

        self.reset()

        self.write_packet(INIT(self._config))

        try:
            confirmation = int(self.read_line())
            if confirmation == 1:
                self.write_packet(INIT_ACK(self._config.read_mode, self._config.Vread))
            else:
                raise ConnectionError("Invalid confirmation")
        except serial.SerialException as se:
            raise ConnectionError(se)

        try:
            time.sleep(0.2)
            self._port.timeout = 2
            self.write(b"999\n")
            data = self.read_bytes(4);
            (major, minor) = struct.unpack("2H", data)
            self._fw_version = (major, minor)
            self._port.timeout = None
        except Exception as exc:
            self._fw_version = None
            self._port.timeout = None

    @property
    def firmware_version(self):
        return self._fw_version

    def finish_op(self):
        """
        Terminate the currently long-running operation. The operation thread is
        waited on and then is dropped.
        """
        if self._operation is not threading.current_thread():
            self._operation.join()
        self._operation = None

    def wait_on_op(self):
        """
        Block until current operation finishes
        """
        if self._operation is not None:
            self._operation.join()

    def select(self, word, bit):
        """
        Close a particular crosspoint. Crosspoint ``word`` × ``bit`` will
        remain closed unless another operation that selects devices is
        executed.
        """
        self.write_packet(SELECT(word,bit))

    def read_one(self, word, bit):
        """
        Read a single device. Blocks until a float is returned
        """
        self.write_packet(READ_ONE(word, bit))

        return self.read_floats(1)[0]

    def pulse_active(self, voltage, pulse_width):
        """
        Pulses device previously selected with `libarc1.arc.ArC1.select`
        """
        self.write_packet(PULSE_ACTIVE(voltage, pulse_width))

    def pulseread_one(self, word, bit, voltage, pulse_width):
        """
        Pulse then read a single device. Blocks until a float is returned
        """
        self.write_packet(PULSEREAD_ONE(word, bit, voltage, pulse_width))

        return self.read_floats(1)[0]

    def _wrap_sequence(self, sequence):

        if sequence.sink is None:
            sink = self.add_to_buffer
        else:
            sink = sequence.sink

        if self._operation is not None:
            raise OperationInProgress(self._operation.name)

        def wrapper():
            sink(json.dumps({'seq': sequence.name,
                'status': 0, 'devs': sequence.devs}))
            for dev in sequence.iterdevs():
                for (targetmod, conf) in sequence.itermods():
                    mod = self._module_from_arg(targetmod, sink)
                    sink(json.dumps({'mod': mod.name,
                        'tag': mod.tag, 'status': 0, 'devs': [dev],
                        'conf': conf}))
                    mod([dev], conf)
                    sink(json.dumps({'mod': mod.name,
                        'tag': mod.tag, 'status': 1}))
            self.finish_op()
            sink(json.dumps({'seq': sequence.name,
                'status': 1}))
            sink(None)

        self._operation = threading.Thread(target=wrapper, name=sequence.name)
        self._operation.start()

        return iter(self._get_from_buffer, None)

    def _wrap_op(self, mod, devs, conf):
        """
        Helper function that wraps the execution of a long-running operation
        (module) in a thread and returns an iterator to the FIFO buffer.
        """

        if self._operation is not None:
            raise OperationInProgress(self._operation.name)

        # this wraps the mod itself and adds the sentinel value at
        # the end of the queue
        def wrapper():
            mod.sink(json.dumps({'mod': mod.name, 'tag': mod.tag,
                'status': 0, 'devs': devs, 'conf': conf}))
            mod(devs, conf)
            self.finish_op()
            mod.sink(json.dumps({'mod': mod.name, 'tag': mod.tag,
                'status': 1}))
            mod.sink(None)

        self._operation = threading.Thread(target=wrapper, name=mod.name)
        self._operation.start()

        return iter(self._get_from_buffer, None)

    def read_all(self, words=32, bits=32):
        """
        Read all the devices up to `words` wordlines and `bits` bitlines. It
        returns an iterator over the internal FIFO buffer so consumption can
        be done in the fairly pythonic way:

        >>> for datum in arc1.read_all():
        >>>     do_smth_with(datum)

        This wraps `libarc1.modules.readops.ReadAll` for convenience.
        """
        return self.run_module(ReadAll, [], {'words': words, 'bits': bits})

    def read_masked(self, devs):
        """
        Read a specific subset of devices. `devs` is a list of tuples
        or other iterables containing (wordline, bitline). This wraps
        `libarc1.modules.readops.ReadMasked` for convenience.
        """

        return self.run_module(ReadMasked, devs, {})

    def retention(self, devs, step=1.0, duration=60.0):
        """
        Read a series of devices every `step` seconds for a total of up to
        `duration` seconds. This wraps `libarc1.modules.readops.Retention`
        for convenience.
        """

        return self.run_module(Retention, devs, \
                {"step": step, "duration": duration})

    def _module_from_arg(self, arg, sink):

        if inspect.isclass(arg) and issubclass(arg, modules.Module):
            mod = arg(self, sink)
        elif isinstance(target, str):
            mod = self.modules[arg](self)
        else:
            raise ValueError("Unrecognised module type: %s" % type(target))

        return mod

    def run_module(self, target, devs, conf=None, sink=None):
        """
        Execute the module `target` on `devs` using configuration `conf`.
        `target` can either be a string or a subclass of `Module`. In the
        first case the module is loaded from the list of registered
        modules, otherwise is instanced directly.
        """
        mod = self._module_from_arg(target, sink)

        if conf is None:
            conf = mod.default_config

        return self._wrap_op(mod, devs, conf)

    def run_sequence(self, sequence, sink=None):
        return self._wrap_sequence(sequence)

