from . import Module
from ..packets import *
from .. import generic_triplet_runner


class CTS_PKT(Packet):
    def __init__(self, config, numdevs):
        Vmin = config["Vmin"]
        Vstep = config["Vstep"]
        Vmax = config["Vmax"]
        PWmin = config["PWmin"]
        PWstep = config["PWstep"]
        PWmax = config["PWmax"]
        interpulse = config["interpulse"]
        Rtarget = config["Rtarget"]
        Rttol = config["Rttol"]
        Rotol = config["Rotol"]
        pulses = config["pulses"]
        polarity = config["polarity"]

        self._pkt = [
                String("21".encode()),  # job
                Float(Vmin),            # Vmin
                Float(Vstep),           # Vstep
                Float(Vmax),            # Vmax
                Float(PWmin),           # minimum pulse width
                Float(PWstep),          # pulse width step (%)
                Float(PWmax),           # maximum pulse width
                Float(interpulse),      # interpulse (s)
                Float(Rtarget),         # target resistance (Ω)
                Float(Rttol),           # target R tolerance (%)
                Float(Rotol),           # initial R tolerance (%)
                Integer(pulses),        # num of progr. pulses
                Integer(polarity),      # initial polarity
                Integer(numdevs)]


class ConvergeToState(Module):

    name = "ConvergeToState"
    tag = "CTS"
    description = """Program device at specific state"""

    default_config = {
            "Vmin": 0.5,
            "Vstep": 0.1,
            "Vmax": 2.0,
            "PWmin": 0.1,
            "PWstep": 100,
            "PWmax": 0.1,
            "interpulse": 1e-3,
            "Rtarget": 5000.0,
            "Rttol": 5.0,
            "Rotol": 5.0,
            "pulses": 1,
            "polarity": 1}

    def run(self, devs, conf=default_config, sink=None):
        instr = self.instrument
        pkt = CTS_PKT(conf, len(devs))

        generic_triplet_runner(instr, pkt, devs, sink)
