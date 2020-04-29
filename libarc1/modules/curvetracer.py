from enum import IntEnum

from . import Module
from ..packets import *
from .. import generic_triplet_runner


class CTMode(IntEnum):
    STAIRCASE = 0
    PULSED = 1


class CTSpan(IntEnum):
    TOWARDS_VP = 0
    TOWARDS_VN = 1
    VP_ONLY = 2
    VN_ONLY = 3


class CT_PKT(Packet):
    def __init__(self, config, numdevs):
        Vpos = config["Vposmax"]
        Vneg = config["Vnegmax"]
        Vstart = config["Vstart"]
        Vstep = config["Vstep"]
        PW = config["PW"]
        interpulse = config["interpulse"]

        # Ensure signs are correct
        CSp = abs(config["CSp"])
        CSn = -abs(config["CSn"])

        # watch out for the transitioning case of 10 us
        if int(CSp * 1000000 * 10) == 100:
            CSp =  10.1/1000000
        if int(CSn * 1000000 * 10) == -100:
            CSn = -10.1/1000000

        cycles = config["cycles"]
        IVtype = int(config["IVtype"])
        IVspan = int(config["IVspan"])
        if config["halt"] not in [True, False]:
            raise ValueError("Invalid return check can only be True or False")
        halt = config["halt"]


        self._pkt = [
                String("201".encode()),  # job
                Float(Vpos),             # Positive voltage (V)
                Float(Vneg),             # Negative voltage (V)
                Float(Vstart),           # Initial voltage (V)
                Float(Vstep),            # Voltage step (V)
                Float(PW),               # Hold time (s)
                Float(interpulse),       # Interpulse time (s)
                Float(CSp),              # Positive cut-off (V)
                Float(CSn),              # Negative cut-off (V)
                Integer(cycles),         # Cycles
                Integer(IVtype),         # IV type (staircase: 0 or pulsed: 1)
                Integer(IVspan),         # IV span (0: V+ first, 1: V- first,
                                         # 2: V+ only, 3: V- only)
                Integer(halt),           # Halt biasing when CC is hit
                Integer(numdevs)]


class CurveTracer(Module):

    name = "CurveTracer"
    tag = "CT"
    description = """Generic I-V module"""

    default_config = {
            "Vposmax": 1.0,
            "Vnegmax": 1.0,
            "Vstart": 0.1,
            "Vstep": 0.1,
            "PW": 10e-3,
            "interpulse": 10e-3,
            "CSp": 0.0,
            "CSn": 0.0,
            "cycles": 1,
            "IVtype": CTMode.STAIRCASE,
            "IVspan": CTSpan.TOWARDS_VP,
            "halt": False }

    def run(self, devs, conf=default_config, sink=None):
        instr = self.instrument
        pkt = CT_PKT(conf, len(devs))

        instr.write_packet(pkt)

        if sink is None:
            sink = instr.add_to_buffer

        for (word, bit) in devs:
            dev_pkt = DEVICE(word, bit)
            instr.write_packet(dev_pkt)
            for cycle in range(conf["cycles"]):
                while True:
                    (res, voltage, pw) = instr.read_floats(3)
                    if not (int(res) <= 0):
                        sink((word, bit, res, voltage, voltage/res, cycle))
                    else:
                        break
