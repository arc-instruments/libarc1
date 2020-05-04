from enum import IntEnum
from . import Module
from ..packets import *
from .. import generic_triplet_runner


class SS2_MODE(IntEnum):
    AUTO = 0
    STAGEII_ONLY_POS = 1
    STAGEII_ONLY_NEG = 2


class SS2_ALGO(IntEnum):
    FAST = 15
    SLOW = 152


class SS2_PKT(Packet):

    def __init__(self, config, numdevs):

        reads = config["reads"]
        pulses = config["pulses"]
        PW = config["PW"]
        Vmin = config["Vmin"]
        Vstep = config["Vstep"]
        Vmax = config["Vmax"]
        cycles = config["cycles"]
        tolerance = int(config["tolerance"]*100)
        interpulse = config["interpulse"]
        threshold = config["threshold"]
        pulseread = int(config["pulseread"])

        if config["mode"] == SS2_MODE.AUTO:
            stageII_pol = 0
        elif config["mode"] == SS2_MODE.STAGEII_ONLY_POS:
                stageII_pol = 1
        else:
            stageII_pol = -1

        jobnum = int(config["algorithm"])
        job = String(str(jobnum).encode())

        self._pkt = [
                String(job),            # job
                Float(PW),              # pulse width (s)
                Float(Vmin),            # initial voltage (V)
                Float(Vstep),           # voltage step (V)
                Float(Vmax),            # maximum voltage (V)
                Float(interpulse),      # interpulse period between pulses (s)
                Float(threshold),       # resistance threshold (Ω)
                Integer(reads),         # number of reads
                Integer(pulses),        # number of programming pulses
                Integer(cycles),        # number of switching cycles
                Integer(tolerance),     # tolerance threshold (%)
                Integer(pulseread),     # also read after programming
                Integer(stageII_pol),   # polarity of stage II if stage I
                                        # is skipped
                Integer(numdevs)]


class SwitchSeeker(Module):

    name = "SwitchSeeker"
    tag = "SS2"
    description = \
        "Analogue resistive switching parameter finder"

    default_config = {
            "mode": SS2_MODE.AUTO,
            "algorithm": SS2_ALGO.SLOW,
            "reads": 5,
            "pulses": 10,
            "PW": 100e-6,
            "Vmin": 0.5,
            "Vstep": 0.2,
            "Vmax": 3.0,
            "cycles": 5,
            "tolerance": 0.1,
            "interpulse": 1e-3,
            "threshold": 1000000.0,
            "pulseread": False }

    def run(self, devs, conf=default_config):
        instr = self.instrument
        pkt = SS2_PKT(conf, len(devs))

        generic_triplet_runner(instr, pkt, devs, self.sink)
