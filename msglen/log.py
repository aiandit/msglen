import time
import asyncio
import sys

class Logger:

    def __init__(self):
        self.msgs = []
        self.t0 = time.time()
        self.task = None
        self.lines = []
        self.event = asyncio.Event()
        self.closed = False

    def __del__(self):
        if self.task:
            self.task.cancel()

    def close(self):
        self.closed = True
        self.event.set()

    def start(self):
        if self.task is None:
            self.task = asyncio.create_task(self.loop())
        return self.task

    def log(self, *msg):
        tst = time.time() - self.t0
        self.lines += [(tst, list(msg))]
        self.event.set()

    def sethandler(self, handle):
        self.handler = handle

    async def loop(self):
        while True:
            if len(self.lines) == 0:
                if self.closed:
                    break
                await self.event.wait()
                self.event.clear()
            else:
                try:
                    self.handler(self.lines[0])
                    self.lines = self.lines[1:]
                except BlockingIOError as ex:
                    await asyncio.sleep(1e-1)


def printmsg(msg_):
    tst, msg = msg_
    msg = ' '.join([str(s) for s in msg])
    print(f'{tst:.6f}: {msg}')


logger = Logger()

logger.sethandler(printmsg)


def log(*msg):
    logger.log(*msg)

def start():
    return logger.start()

def close():
    logger.close()
