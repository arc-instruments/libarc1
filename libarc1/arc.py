import os.path
import serial
import time
import functools
import inspect, importlib, pkgutil
import threading
import numpy as np
import glob
import json
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
    CLASSIC = 0
    TIA = 1
    TIA4P = 2
    TIA4P_NEG = 3


class SESSION(IntEnum):
    LOCAL = 0
    EXTERNAL_BNC = 1
    BNC_TO_LOCAL = 2
    OFFLINE = 3


class SNEAKPATH_LIMIT(IntEnum):
    ONE_THIRD = 0
    ONE_HALF = 1
    FLOAT = 2


@dataclass
class ArC1Conf:
    read_cycles: int = 30
    words: int = 32
    bits: int = 32
    read_mode: int = READ_MODE.TIA4P
    session_type: int = SESSION.LOCAL
    sneak_path: int = SNEAKPATH_LIMIT.ONE_THIRD
    Vread: float = 0.5
    write_delay: float = 0.001


class ConnectionError(Exception):

    def __init__(self, message=""):
        self.message = message


class OperationInProgress(Exception):

    def __init__(self, op_name=""):
        if op_name == "":
            self.message = "An operation is in progress"
        else:
            self.message = "%s operation is in progress" % op_name


class ArC1():

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
        Load all non-package modules found under `modules`.
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
        return self._config

    def register_module(self, mod):
        """
        Register module `mod`. Note that if a module with the same tag exists
        it will be overwritten.
        """
        if not issubclass(mod, modules.Module):
            raise ValueError("Invalid module type; must subclass `libarc.modules.Module`")

        self.modules[mod.tag] = mod

    @staticmethod
    def _import_predicate(mod):
        return inspect.isclass(mod) and \
                issubclass(mod, modules.Module) and \
                mod is not modules.Module

    def open_modules_from_file(self, path):
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

    def open_modules_from_folder(self, path):
        """
        Same as `open_modules_from_file` but instead of a single file load all
        modules found in python source files under specified `path`.
        """
        if not os.path.isdir(path):
            raise ValueError("%s is not a folder" % path)

        mods = []

        files = glob.glob(os.path.join(path, '*.py'))
        for f in files:
            mods.extend(self.open_modules_from_file(f))

        return mods

    def register_modules_from_file(self, path):
        """
        Load modules from file into the internal module list. File must be
        ending in .py.
        """
        for mod in self.open_modules_from_file(path):
            self.modules[mod.tag] = mod

    def register_modules_from_folder(self, path):
        """
        Load and register all modules from python files found under folder `path`.
        """
        for mod in self.open_modules_from_folder(path):
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
        values = self._port.read(how_many)
        return memoryview(values)

    def update_Vread(self, val):
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
        Write an arbitrary bytestream to the serial port
        """
        with self.lock:
            self._port.write(bytestream)
            time.sleep(self._config.write_delay)

    def write_packet(self, pkt):
        """
        Write a command packet to the serial port. The packet is
        converted to the proper bytestream
        """
        with self.lock:
            for parts in pkt:
                self._port.write(parts)

    def read_line(self):
        """
        Read a line from the serial port. Result is a bytearray
        """
        return self._port.readline()

    def reset(self):
        """
        Force a uC reset
        """
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

    def finish_op(self):
        """
        Terminate the currently long-running operation. The operation thread is
        waited on and then is forced to be DECREF'd by essentially dropping it.
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

    def select(self, w, b):
        """
        Close a particular crosspoint
        """
        self.write_packet(SELECT(w,b))

    def read_one(self, w, b):
        """
        Read a single device. Blocks until a float is returned
        """
        self.write_packet(READ_ONE(w, b))

        return self.read_floats(1)[0]

    def pulse_active(self, voltage, pulse_width):
        """
        Pulses device previously selected with `select`
        """
        self.write_packet(PULSE_ACTIVE(voltage, pulse_width))

    def pulseread_one(self, w, b, voltage, pulse_width):
        """
        Pulse then read a single device. Blocks until a float is returned
        """
        self.write_packet(PULSEREAD_ONE(w, b, voltage, pulse_width))

        return self.read_floats(1)[0]

    def _wrap_sequence(self, sequence, sink=None):

        if self._operation is not None:
            raise OperationInProgress(self._operation.name)

        def wrapper():
            self.add_to_buffer(json.dumps({'seq': sequence.name,
                'status': 0, 'devs': sequence.devs}))
            for dev in sequence.iterdevs():
                for (targetmod, conf) in sequence.itermods():
                    mod = self._module_from_arg(targetmod)
                    self.add_to_buffer(json.dumps({'mod': mod.name,
                        'tag': mod.tag, 'status': 0, 'devs': [dev],
                        'conf': conf}))
                    mod([dev], conf, sink)
                    self.add_to_buffer(json.dumps({'mod': mod.name,
                        'tag': mod.tag, 'status': 1}))
            self.finish_op()
            self.add_to_buffer(json.dumps({'seq': sequence.name,
                'status': 1}))
            self.add_to_buffer(None)

        self._operation = threading.Thread(target=wrapper, name=sequence.name)
        self._operation.start()

        return iter(self._get_from_buffer, None)

    def _wrap_op(self, mod, devs, conf, sink):
        """
        Helper function that wraps the execution of a long-running operation
        (module) in a thread and returns an iterator to the FIFO buffer.
        """

        if self._operation is not None:
            raise OperationInProgress(self._operation.name)

        # this wraps the mod itself and adds the sentinel value at
        # the end of the queue
        def wrapper():
            self.add_to_buffer(json.dumps({'mod': mod.name, 'tag': mod.tag,
                'status': 0, 'devs': devs, 'conf': conf}))
            mod(devs, conf, sink)
            self.finish_op()
            self.add_to_buffer(json.dumps({'mod': mod.name, 'tag': mod.tag,
                'status': 1}))
            self.add_to_buffer(None)

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
        """
        return self.run_module(ReadAll, [], {'words': words, 'bits': bits})

    def read_masked(self, devs):
        """
        Read a specific subset of devices. `devs` is a list of tuples
        or other iterables containing (wordline, bitline).
        """

        return self.run_module(ReadMasked, devs, {})

    def retention(self, devs, step=1.0, duration=60.0):
        """
        Read a series of devices every `step` seconds for a total of up to
        `duration` seconds.
        """

        return self.run_module(Retention, devs, \
                {"step": step, "duration": duration})

    def _module_from_arg(self, arg):

        if inspect.isclass(arg) and issubclass(arg, modules.Module):
            mod = arg(self)
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
        mod = self._module_from_arg(target)

        if conf is None:
            conf = mod.default_config

        return self._wrap_op(mod, devs, conf, sink)

    def run_sequence(self, sequence, sink=None):
        return self._wrap_sequence(sequence, sink)
