import os
import sys
import asyncio
import argparse
from inspect import iscoroutinefunction
from . import __version__
from . import __commit__
from . import log


class MyWriter(asyncio.Protocol):
    def __init__(self):
        self.transport = None

    def connection_made(self, transport):
        self.transport = transport
        print('Connected')

    def data_received(self, data):
        print('Received:', data.decode())

    def connection_lost(self, exc):
        print('Connection lost')


class MyReader(asyncio.Protocol):
    def __init__(self, reader, loop=None):
        self.transport = None
        self.reader = reader
        self.loop = loop

    def connection_made(self, transport):
        self.transport = transport
        print('Connected')

    def data_received(self, data):
        print('Received:', data.decode())
        return data.decode()

    def connection_lost(self, exc):
        print('Connection lost')


def ensure_co(readfunc):
    if iscoroutinefunction(readfunc):
        return readfunc
    else:
        async def c(*args, **kwargs):
            return readfunc(*args, **kwargs)
        return c



async def connect_stdin_stdoutn(limit=asyncio.streams._DEFAULT_LIMIT, loop=None):
    if loop is None:
        loop = asyncio.get_event_loop()

    if sys.platform == 'win32':
        return _win32_stdio(loop)

    reader = asyncio.StreamReader(limit=limit, loop=loop)
    await loop.connect_read_pipe(
        lambda: asyncio.StreamReaderProtocol(reader, loop=loop),
        sys.stdin)

    writer_transport, writer_protocol = await loop.connect_write_pipe(
        lambda: asyncio.streams.FlowControlMixin(loop=loop),
        os.fdopen(sys.stdout.fileno(), 'wb'))
    writer = asyncio.streams.StreamWriter(
        writer_transport, writer_protocol, None, loop)

    return reader, writer



async def connect_stdin_stdout():
    loop = asyncio.get_event_loop()
    reader = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(reader)
    r_transport, r_protocol = await loop.connect_read_pipe(lambda: protocol, sys.stdin)
    w_transport, w_protocol = await loop.connect_write_pipe(asyncio.streams.FlowControlMixin, sys.stdout)
    writer = asyncio.StreamWriter(w_transport, w_protocol, reader, loop)
    #return reader, writer, (r_transport, r_protocol, w_transport, w_protocol)
    return reader, writer


async def readmuch(std_reader):
    data = await std_reader.read(1<<24)
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

    std_reader = None


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

    async def start(self, callback=None):
        self.std_reader, self.std_writer = await connect_stdin_stdout()

    async def run(self, callback=None):
        await self.start()
        await self.readstdin(callback=callback)

    async def release(self):
        async with self.stdinComplete:
            await self.stdinComplete.wait()
        async with self.stdinCanclose:
            self.stdinCanclose.notify()

    async def close(self):
        self.std_writer.close()

    async def readstdin(self, callback=None):
        while True:
            if self.std_reader:
                fr = await readmuch(self.std_reader)
                if fr is not None:
                    if self.verbose:
                        log.log(f'data read {len(fr)}')
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

        if self.verbose:
            log.log('read loop exited')
        if self.datacallback:
            await self.datacallback(self.data)

        if self.endcallback:
            await self.endcallback()

        async with self.stdinComplete:
            self.stdinComplete.notify()

        if self.verbose:
            log.log('wait close')
        async with self.stdinCanclose:
            await self.stdinCanclose.wait()

        if self.verbose:
            log.log('stdinread exit')

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
