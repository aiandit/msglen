import time
import asyncio

class Logger:

    def __init__(self):
        self.msgs = []
        self.t0 = time.time()

    def log(self, *msg):
        tst = time.time() - self.t0
        self.handler((tst, list(msg)))

    def sethandler(self, handle):
        self.handler = handle


def printmsg(msg_):
    tst, msg = msg_
    msg = ' '.join(list(msg))
    print(f'{tst}: {msg}')


logger = Logger()

logger.sethandler(printmsg)


def log(*msg):
    logger.log(*msg)
