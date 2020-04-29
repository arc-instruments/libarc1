from enum import IntEnum
from . import Module
from ..packets import *
from .. import generic_triplet_runner


class FF_SR(IntEnum):
    R1K = 1
    R10K = 2
    R100K = 3
    R1M = 4
    R0 = 7


class FF_PWMode(IntEnum):
    LOG10 = 0
    LINEAR = 1


class FF_PKT(Packet):

    def __init__(self, config, numdevs):
        mode = config["mode"]
        PWnum = config["PWnum"]
        Vmin = config["Vmin"]
        Vstep = config["Vstep"]
        Vmax = config["Vmax"]
        PWmin = config["PWmin"]
        PWstep = config["PWstep"]
        PWmax = config["PWmax"]
        PWinter = config["PWinter"]
        Rthr = config["Rthr"]
        RthrP = config["RthrP"]
        pSR = config["pSR"]

        self._pkt = [
                String("141".encode()),  # job
                Float(Vmin),             # Vmin
                Float(Vstep),            # Vstep
                Float(Vmax),             # Vmax
                Float(PWmin),            # pulse width min
                Float(PWstep),           # pulse width step
                Float(PWmax),            # pulse width max
                Float(PWinter),          # interpulse)
                Float(Rthr),             # resistance threshold
                Float(RthrP),            # resistance threshold (%) if used
                Integer(mode),           # 0: log progression, 1: lin progression
                Integer(pSR),            # Series resistance
                                         # 1: 1k; 2: 10k; 3: 100k; 4: 1M;
                                         # anything else: no pSR
                Integer(PWnum),          # number of programming pulses
                Integer(numdevs)]


class FormFinder(Module):

    name = "FormFinder"
    tag = "FF"
    description = \
        """Generic voltage ramp/pulse train generator."""

    default_config = {
            "mode": FF_PWMode.LOG10,
            "PWnum": 1,
            "Vmin": 0.25,
            "Vstep": 0.25,
            "Vmax": 3.0,
            "PWmin": 100e-6,
            "PWstep": 100.0,
            "PWmax": 1e-3,
            "PWinter": 10e-3,
            "Rthr": 1e6,
            "RthrP": 0.0,
            "pSR": FF_SR.R0 }

    def run(self, devs, conf=default_config, sink=None):
        instr = self.instrument
        pkt = FF_PKT(conf, len(devs))

        generic_triplet_runner(instr, pkt, devs, sink)
