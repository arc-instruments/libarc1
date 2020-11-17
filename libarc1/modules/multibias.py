from enum import IntEnum
from . import Module
from ..packets import *


class MB_RW(IntEnum):
    READ = 1
    WRITE = 2


class MB_PKT(Packet):

    def __init__(self, config):
        Vwrite = config["Vwrite"]
        Vread = config["Vread"]
        PWwrite = config["PWwrite"]
        bitline = config["bitline"]
        wordlines = config["wordlines"]
        action = config["action"]

        self._pkt = [
                String("50".encode()),   # job
                Float(Vwrite),           # read voltage
                Float(PWwrite),          # pulse width for write pulses (s)
                Float(Vread),            # write voltage
                Integer(len(wordlines)), # number of wordlines
                Integer(bitline),        # active bitline
                Integer(action),         # read or write
                IntegerList(wordlines)]  # wordlines to integrate


class MultiBias(Module):

    name = "MultiBias"
    tag = "MB"
    description = "Read/write multiple wordlines"

    default_config = {
            "Vwrite": 1.0,
            "Vread": 0.5,
            "PWwrite": 100e-6,
            "bitline": 1,
            "wordlines": [1, 2],
            "action": MB_RW.READ }

    def run(self, devs=None, conf=default_config):
        instr = self.instrument
        sink = self.sink
        words = instr.config.words
        bitline = conf["bitline"]
        vwrite = conf["Vwrite"]
        pwwrite = conf["PWwrite"]

        instr.write_packet(MB_PKT(conf))

        if conf["action"] == MB_RW.READ:
            values = instr.read_floats(3)
            current = values[1]/values[0]
            sink((bitline, current))
        else:
            for device in range(1, words+1):
                values = instr.read_floats(3)
                sink((device, bitline, values[0], values[1], values[2]))

            for device in range(1, words+1):
                values = instr.read_floats(3)
                if device in conf["wordlines"]:
                    sink((device, bitline, values[0], vwrite, pwwrite))
                else:
                    sink((device, bitline, values[0], vwrite/2, pwwrite))
