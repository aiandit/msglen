import sys
import asyncio
import argparse
from inspect import iscoroutinefunction
from . import __version__
from . import __commit__


def ensure_co(readfunc):
    if iscoroutinefunction(readfunc):
        return readfunc
    else:
        async def c(*args, **kwargs):
            return readfunc(*args, **kwargs)
        return c


async def connect_stdin_stdout():
    loop = asyncio.get_event_loop()
    reader = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(reader)
    await loop.connect_read_pipe(lambda: protocol, sys.stdin)
    w_transport, w_protocol = await loop.connect_write_pipe(asyncio.streams.FlowControlMixin, sys.stdout)
    writer = asyncio.StreamWriter(w_transport, w_protocol, reader, loop)
    return reader, writer


async def readtimeout(std_reader, timeout=1e-4):
    data = b''
    try:
        data = await asyncio.wait_for(std_reader.read(10000), timeout)
    except TimeoutError:
        data = None
    return data


def mkparser(parser=None):
    if parser is None:
        parser = argparse.ArgumentParser('stdinreader',
                                         '''\
StdinReader class CLI test tool.
''', '')

    parser.add_argument('-V', '--version', action="version", version=f"%(prog)s v{__version__} ({__commit__})",
                        help='show %(prog)s\'s version number and exit')
    parser.add_argument('-v', '--verbose', type=int, metavar='N', nargs='?', const=1, default=0)

    parser.add_argument('cmd', metavar='CMD', type=str)

    return parser


class StdinReader:

    stdinComplete = asyncio.Condition()
    stdinRead = asyncio.Condition()

    data = b''
    lines = []
    verbose = 0

    datacallback = None
    linecallback = None
    endcallback = None

    def __init__(self, datacallback=None, linecallback=None, endcallback=None, verbose=0, **kw):
        self.stdinComplete = asyncio.Condition()
        self.stdinRead = asyncio.Condition()
        self.stdinCanclose = asyncio.Condition()

        self.data = b''
        self.lines = []

        if datacallback:
            self.datacallback = ensure_co(datacallback)
        if linecallback:
            self.linecallback = ensure_co(linecallback)
        if endcallback:
            self.endcallback = ensure_co(endcallback)

        self.verbose = verbose

    def __del__(self):
        pass

    async def run(self, callback=None):
        await self.readstdin(callback=callback)

    async def release(self):
        async with self.stdinCanclose:
            self.stdinCanclose.notify()

    async def close(self):
        self.std_writer.close()

    async def readstdin(self, callback=None):

        self.std_reader, self.std_writer = await connect_stdin_stdout()

        while True:
            if self.std_reader:
                fr = await readtimeout(self.std_reader)
                if fr is not None:
                    if self.datacallback:
                        self.data += fr
                    else:
                        self.data = fr
                    if self.linecallback:
                        self.lines += [fr]
                        await self.linecallback(fr)
                    async with self.stdinRead:
                        self.stdinRead.notify()
                    if len(fr) == 0:
                        break
                    if fr.decode('latin1').strip() == 'exit':
                        await self.linecallback(b'')
                        break

        print('read loop exited')
        if self.datacallback:
            await self.datacallback(self.data)

        if self.endcallback:
            await self.endcallback()

        async with self.stdinComplete:
            self.stdinComplete.notify()

        print('wait close')
        async with self.stdinCanclose:
            await self.stdinCanclose.wait()

        if self.verbose:
            print('stdinread exit')

        return self.data


async def arun(args=None):
    if args is None:
        parser = mkparser()
        args = parser.parse_args()

    reader = StdinReader(linecallback=lambda x: print('line', x),
                         datacallback=lambda x: print('data', x),
                         **vars(args))

    rtask = asyncio.create_task(reader.run())

    await rtask


def run(args=None):
    asyncio.run(arun(args))


if __name__ == "__main__":
    run()