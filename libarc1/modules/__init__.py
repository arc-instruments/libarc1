from abc import ABCMeta, abstractmethod


class Module(metaclass=ABCMeta):

    def __init__(self, instrument):
        self.instrument = instrument

    def __call__(self, *args):
        self.run(*args)

    @abstractmethod
    def run(self, devs, conf=None, sink=None):
        return
