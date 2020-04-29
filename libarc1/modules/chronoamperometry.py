from . import Module
from ..packets import *
from .. import generic_triplet_runner


class CRA_PKT(Packet):

    def __init__(self, config, numdevs):
        bias = config["bias"]
        pw = config["pw"]
        num_reads = config["num_reads"]

        self._pkt = [
                String("220".encode()), # job
                Float(bias),            # voltage
                Float(pw),              # pulse width
                Integer(num_reads),     # number of reads
                Integer(numdevs)]


class ChronoAmperometry(Module):

    name = "ChronoAmperometry"
    tag = "CRA"
    description = """Read device(s) continuously under bias."""

    default_config = {
            "bias":  1.0,
            "pw": 100e-3,
            "num_reads": 2 }

    def run(self, devs, conf=default_config, sink=None):
        instr = self.instrument
        pkt = CRA_PKT(conf, len(devs))

        generic_triplet_runner(instr, pkt, devs, sink)
