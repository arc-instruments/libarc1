class Sequence():

    def __init__(self, name, mods=[], devs=[]):
        self._name = name
        self._mods = mods
        self._devs = devs

    @property
    def name(self):
        return self._name

    @property
    def devs(self):
        return self._devs

    def add_module(self, mod, conf=None):
        if conf is None:
            conf = mod.default_config
        self._mods.append((mod, conf))

    def add_device(self, dev):
        self._devs.append(dev)

    def iterdevs(self):
        return iter(self._devs)

    def itermods(self):
        return iter(self._mods)
