import os
import sys
import asyncio
import argparse
from . import __version__
from . import __commit__

from .msglen import *


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
        parser = argparse.ArgumentParser('msglen',
                                     '''\
MsgLen CLI tool.
''', '')

    parser.add_argument('-m', '--message', metavar='S', type=str, nargs='?', action='append')
    parser.add_argument('-p', '--protocol', metavar='N', nargs='?', type=str, default='msgl')
    parser.add_argument('-s', '--param', metavar='N=V', type=str, nargs='*', action='append')
    parser.add_argument('-o', '--output', metavar='FILE', type=str)
    parser.add_argument('-V', '--version', action="version", version=f"%(prog)s v{__version__} ({__commit__})",
                        help='show %(prog)s\'s version number and exit')
    parser.add_argument('-v', '--verbose', type=int, metavar='N', nargs='?', const=1, default=0)

    parser.add_argument('cmd', metavar='CMD', type=str)

    return parser


def flatten(lists):
    xslt = []
    for sublist in lists:
        if isinstance(sublist, list):
            xslt.extend(sublist)
        else:
            xslt.append(sublist)
    return xslt


async def arun(args=None):
    if args is None:
        parser = mkparser()
        args = parser.parse_args()

    msgType = MsglenB()
    if args.protocol:
        msgType = MsglenL.create(args.protocol)

    msglenb = msgType

    stdinComplete = asyncio.Condition()
    stdinRead = asyncio.Condition()

    data = b''
    lines = []

    async def readstdin(callback=None):
        nonlocal data, lines

        if callback is None:
            async def dataadd(d):
                nonlocal data, lines
                data += d
                lines += [d]

            callback = dataadd

        std_reader, std_writer = await connect_stdin_stdout()

        while True:
            if std_reader:
                fr = await readtimeout(std_reader)
                if fr is not None:
                    res = await callback(fr)
                    async with stdinRead:
                        stdinRead.notify()
                    if len(fr) == 0:
                        break
                    if fr.decode('latin1').strip() == 'exit':
                        res = await callback(b'')
                        break
        async with stdinComplete:
            stdinComplete.notify()
        async with stdinComplete:
            await stdinComplete.wait()
        return data

    datareader = asyncio.create_task(readstdin())

    async def waitforstdinend():
        if args.verbose > 1:
            print('wait for stdin read end')
        async with stdinComplete:
            await stdinComplete.wait()
        if args.verbose > 2:
            print(f'got whole input! {data}')

    async def stdinlinehandler(callback):
        nonlocal lines
        stop = False
        while not stop:
            if args.verbose > 1:
                print('wait for stdin read')
            async with stdinRead:
                await stdinRead.wait()
            while len(lines) > 0:
                data = lines[0]
                if args.verbose > 1:
                    print(f'got {len(lines)} input lines: {data}')
                if len(data) == 0:
                    stop = True
                    break
                await callback(data)
                lines = lines[1:]
        if args.verbose:
            print(f'stdinlinehandler exit')

    async def handleLine_pack(data):
        msg = wrap(data)
        writeOut(outf)(msg)

    async def handleLine_unpack(data):
        msg, meta = msglenb.unwrap(data)
        if args.param:
            print(meta.asJSON())
        elif args.verbose:
            print('meta:', meta)

        if (args.param is None and not args.message) or (args.message):
            writeOut(outf)(msg)

    def writeOut(write):
        def inner(data):
            if write.closed:
                return
            try:
                write.write(data)
            except:
                if isinstance(data, bytes):
                    data = data.decode('utf8')
                    write.write(data)
            outf.flush()
        return inner


    readstdintask = asyncio.create_task(waitforstdinend())

    params = {}
    if args.param:
        params = flatten(args.param)
        params = { k: v for k,v in [item.split('=') for item in params] }
        if args.verbose:
            print('params:', params)

    wrap = msglenb.packer(dict()|params)

    outf = sys.stdout
    outfname= 'stdout'

    if args.output:
        outf = args.output
        if outf != '-':
            outfname = args.output
            outf = open(outfname, 'wb')


    if args.verbose > 1:
        print(f'cmd = {args.cmd}')

    if args.cmd == "wrap":
        await readstdintask
        wrap = msglenb.packer(params)
        msg = wrap(data)
        writeOut(outf)(msg)

    elif args.cmd == "unwrap":
        await readstdintask
        wrap = msglenb.unwrap(data)
        msg, meta = wrap
        if args.param:
            print(meta.asJSON())
        elif args.verbose:
            print('meta:', meta)

        if (args.param is None and not args.message) or (args.message):
            writeOut(outf)(msg)

    elif args.cmd == "wraplines" or args.cmd == "readlines":
        lineradertask = asyncio.create_task(stdinlinehandler(handleLine_pack))
        await lineradertask

    elif args.cmd == "unwrapmsgs" or args.cmd == "unwraplines":
        lineradertask = asyncio.create_task(stdinlinehandler(handleLine_unpack))
        await lineradertask

    async with stdinComplete:
        stdinComplete.notify()

    res = await datareader

def run(args=None):
    asyncio.run(arun(args))

if __name__ == "__main__":
    run()
