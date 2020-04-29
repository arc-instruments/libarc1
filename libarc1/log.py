import os
import sys
from enum import IntEnum

class LOG_LEVEL(IntEnum):
    INFO = 0
    DEBUG = 1
    TRACE = 2


class Logger():

    def __init__(self, lvl):
        self.lvl = lvl

    def _log(self, *args, **kwargs):
        if 'file' in kwargs.keys():
            kwargs.pop('file')

        print(*args, file=sys.stderr, **kwargs)

    def info(self, *args, **kwargs):

        if self.lvl < LOG_LEVEL.INFO:
            return

        args = list(args)
        args.insert(0, '[INFO]')
        self._log(*args, **kwargs)

    def debug(self, *args, **kwargs):

        if self.lvl < LOG_LEVEL.DEBUG:
            return

        args = list(args)
        args.insert(0, '[DBUG]')
        self._log(*args, **kwargs)

    def trace(self, *args, **kwargs):

        if self.lvl < LOG_LEVEL.TRACE:
            return

        args = list(args)
        args.insert(0, '[TRCE]')
        self._log(*args, **kwargs)

LOG = Logger(int(os.environ.get('MARCDBG', 0)))
