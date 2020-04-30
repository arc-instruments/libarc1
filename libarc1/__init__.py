from .arc import ArC1, ArC1Conf
from .sequence import Sequence
from .packets import DEVICE
from .log import LOG


def generic_triplet_runner(instr, pkt, devs, sink):
    """
    This is a generic "triplet generator". A lot of the builtin
    ArC modules return a triplet of values (resistance, voltage, pulse width)
    and before terminating they return a triplet of zeros (0, 0, 0). As this
    behaviour is quite common a utility function is provided.
    """
    instr.write_packet(pkt)

    for (word, bit) in devs:
        dev_pkt = DEVICE(word, bit)
        instr.write_packet(dev_pkt)
        while True:
            (res, voltage, pw) = instr.read_floats(3)
            if not (int(res) <= 0):
                sink((word, bit, res, voltage, pw))
            else:
                break
