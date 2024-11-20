import time
import asyncio

class Logger:

    def __init__(self):
        self.msgs = []

    def log(self, msg):
        tst = time.time()
        self.handler((tst, msg))

    def sethandler(self, handle):
        self.handler = handle


def printmsg(msg):
    tst, msg = msg
    print(f'{tst}: {msg}')


logger = Logger()

logger.sethandler(printmsg)


def log(msg):
    logger.log(msg)
