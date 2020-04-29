from . import Module
from ..packets import *
from .. import generic_triplet_runner

class EN_PKT(Packet):

    def __init__(self, config, numdevs):
        Vpos = config["Vpos"]
        Vneg = config["Vneg"]
        PWpos = config["PWpos"]
        PWneg = config["PWneg"]
        CCpos = config["CCpos"]
        CCneg = config["CCneg"]
        Pinter = config["Pinter"]
        PWnumpos = config["PWnumpos"]
        PWnumneg = config["PWnumneg"]
        cycles = config["cycles"]

        self._pkt = [
                String("191".encode()),  # job
                Float(Vpos),             # positive voltage
                Float(PWpos),            # pulse width for positive pulses
                Float(CCpos),            # current compliance for pos. pulses
                Float(Vneg),             # negative voltage
                Float(PWneg),            # pulse width for negative pulses
                Float(CCneg),            # current compliance for neg. pulses
                Float(Pinter),           # interpulse
                Integer(PWnumpos),       # number of positive pulses
                Integer(PWnumneg),       # number of negative pulses
                Integer(cycles),         # number of cycles (repetitions)
                Integer(numdevs)]


class Endurance(Module):

    name = "Endurance"
    tag = "EN"
    description = \
        """Repeated on/off switching cycles."""

    default_config = {
            "Vpos":  1.0,
            "Vneg": -1.0,
            "PWpos": 100e-6,
            "PWneg": 100e-6,
            "CCpos": 0.0,
            "CCneg": 0.0,
            "Pinter": 1e-3,
            "PWnumpos": 1,
            "PWnumneg": 1,
            "cycles": 10}

    def run(self, devs, conf=default_config, sink=None):
        instr = self.instrument
        pkt = EN_PKT(conf, len(devs))

        generic_triplet_runner(instr, pkt, devs, sink)
