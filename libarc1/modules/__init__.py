from abc import ABCMeta, abstractmethod


class Module(metaclass=ABCMeta):

    def __init__(self, instrument, sink=None):
        self.instrument = instrument
        if sink is None:
            self.sink = self.instrument.add_to_buffer
        else:
            self.sink = sink

    def __call__(self, *args):
        self.run(*args)

    @abstractmethod
    def run(self, devs, conf=None):
        return
