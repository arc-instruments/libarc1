import struct

class Param():

    def __init__(self, value):
        self.value = value

    def __str__(self):
        return str(self.value)

class SimpleParam(Param):

    def __bytes__(self):
        return (b"%s\n" % self.identifier.encode()) % self.value

    def __iter__(self):
        return bytes(self).__iter__()

class BytePackedParam(Param):

    def __bytes__(self):
        return struct.pack(self.identifier, *self.value)

    def __iter__(self):
        return bytes(self).__iter__()

class ParamClass(type):

    def __new__(cls, name, parents, attrs):
        return type.__new__(cls, name, parents, attrs)

class SimpleParamClass(ParamClass):

    @staticmethod
    def new(name, identifier):
        return SimpleParamClass(name, (SimpleParam,), {'identifier': identifier})

class BytePackedParamClass(ParamClass):

    @staticmethod
    def new(name, identifier):
        return BytePackedParamClass(name, (BytePackedParam,), {'identifier': identifier})


Integer = SimpleParamClass.new('Integer', '%d')
Float = SimpleParamClass.new('Float', '%f')
Char = SimpleParamClass.new('Char', '%c')
Byte = Char
String = SimpleParamClass.new('String', '%s')

