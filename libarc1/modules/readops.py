from . import Module
from ..packets import *

from datetime import datetime
import time

class _READALL_PKT(Packet):
    def __init__(self, words, bits):

        self._pkt = [
                String("2".encode()), # job
                Integer(1),           # read everything
                Integer(words),       # num of words to scan
                Integer(bits)]        # num of bits to scan

class _READMASK_PKT(Packet):
    def __init__(self, num_devs):

        self._pkt = [
                String("2".encode()), # job
                Integer(2),           # masked read
                Integer(32),          # useless
                Integer(32),          # useless
                Integer(num_devs)]    # total devices to read


class ReadAll(Module):

    name = "ReadAll"
    tag = "RA"
    description = "Read all devices from the crossbar"

    default_config = {
            "words": 32,
            "bits": 32 }

    def run(self, devs=None, conf=default_config, sink=None):

        instr = self.instrument

        if sink is None:
            sink = instr.add_to_buffer

        words = conf["words"]
        bits = conf["bits"]
        instr.write_packet(_READALL_PKT(words, bits))

        for word in range(1, words+1):
            for bit in range(1, bits+1):
                x = instr.read_floats(1)[0]
                sink((word, bit, x))


class Retention(Module):

    name = "Retention"
    tag = "RET"
    description = "Read devices continuously"

    default_config = {
            "step": 1.0,
            "duration": 60.0 }

    def run(self, devs, conf=default_config, sink=None):
        instr = self.instrument

        if sink is None:
            sink = instr.add_to_buffer

        duration = conf["duration"]
        step = conf["step"]
        steps = int(duration/step)

        start = datetime.now()
        vread = instr.config.Vread

        for _ in range(steps):
            for (w, b) in devs:
                res = instr.read_one(w, b)
                cur = vread/res
                dt = datetime.now() - start
                seconds = dt.seconds + dt.microseconds*1e-6
                sink((w, b, res, cur, seconds))
            time.sleep(step)


class ReadMasked(Module):

    name = "ReadMasked"
    tag = "RM"
    description = "Sequentially read a series of crosspoints"

    def run(self, devs, conf={}, sink=None):

        instr = self.instrument

        if sink is None:
            sink = instr.add_to_buffer

        instr.write_packet(_READMASK_PKT(len(devs)))

        for (word, bit) in devs:
            instr.write_packet(DEVICE(word, bit))
            x = instr.read_floats(1)[0]
            sink((word, bit, x))
