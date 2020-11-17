from .params import Integer, String, Float, IntegerList

class Packet():

    def __iter__(self):
        return self._pkt.__iter__()


class INIT(Packet):

    def __init__(self, conf):

        self._pkt = [String("0".encode()), \
                Integer(conf.read_cycles), \
                Integer(conf.words), \
                Integer(conf.bits), \
                Integer(conf.read_mode), \
                Integer(conf.session_type), \
                Integer(conf.sneak_path), \
                Float(conf.Vread)]


class INIT_ACK(Packet):

    def __init__(self, read_mode, read_voltage):

        self._pkt = [String("01".encode()), \
                Integer(read_mode), \
                Float(read_voltage)]


class SELECT(Packet):

    def __init__(self, w, b):
        self._pkt = [String("02".encode()), \
                Integer(w), Integer(b)]


class READ_ONE(Packet):

    def __init__(self, w, b):
        self._pkt = [String("1".encode()), \
                Integer(w), Integer(b)]


class PULSEREAD_ONE(Packet):

    def __init__(self, w, b, amplitude, pulse_width):
        self._pkt = [String("3".encode()), \
                Integer(w), Integer(b), \
                Float(amplitude), Float(pulse_width)]


class PULSE_ACTIVE(Packet):
    """
    Pulses device previously selected with `SELECT`
    """

    def __init__(self, amplitude, pulse_width):
        self._pkt = [String("04".encode()), \
                Float(amplitude), Float(pulse_width)]


class DEVICE(Packet):
    def __init__(self, word, bit):

        self._pkt = [Integer(word), Integer(bit)]


class READ_ALL(Packet):

    def __init__(self, words, bits):
        self._pkt = [String("2".encode()), Integer(1), Integer(words), \
                Integer(bits)]

class SET_VREAD(Packet):

    def __init__(self, voltage, readoption):
        self._pkt = [String("01".encode()), Integer(readoption), \
                Float(voltage)]
