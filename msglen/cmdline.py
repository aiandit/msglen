import sys
import asyncio
import argparse
from . import __version__
from . import __commit__

from .msglen import MsglenB, MsglenL
from .stdinreader import connect_stdin_stdout, readmuch


def mkparser(parser=None):
    if parser is None:
        parser = argparse.ArgumentParser('msglen',
                                         '''\
MsgLen CLI tool.
''', '')

    parser.add_argument('-m', '--message', metavar='S', type=str, nargs='?', action='append')
    parser.add_argument('-n', '--num-lines', metavar='N', nargs='?', type=int, const=10)
    parser.add_argument('-l', '--lines', action='store_true')
    parser.add_argument('-d', '--decode', action='store_true')
    parser.add_argument('-u', '--unwrap', action='store_true')
    parser.add_argument('-p', '--protocol', metavar='N', nargs='?', type=str, default='msgl')
    parser.add_argument('-s', '--param', metavar='N=V', type=str, nargs='*', action='append')
    parser.add_argument('-o', '--output', metavar='FILE', type=str)
    parser.add_argument('-V', '--version', action="version", version=f"%(prog)s v{__version__} ({__commit__})",
                        help='show %(prog)s\'s version number and exit')
    parser.add_argument('-v', '--verbose', type=int, metavar='N', nargs='?', const=1, default=0)

    parser.add_argument('cmd', metavar='CMD', type=str, nargs='?')

    return parser


def flatten(lists):
    xslt = []
    for sublist in lists:
        if isinstance(sublist, list):
            xslt.extend(sublist)
        else:
            xslt.append(sublist)
    return xslt


async def adoit(args=None):
    if args is None:
        parser = mkparser()
        args = parser.parse_args()

    msgType = MsglenB()
    if args.protocol:
        msgType = MsglenL.create(args.protocol)

    msglenb = msgType

    stdinComplete = asyncio.Event()
    stdinClose = asyncio.Event()
    stdinRead = asyncio.Condition()

    data = b''
    lines = []

    async def readstdin(std_reader, std_writer, callback=None):
        nonlocal data, lines

        if callback is None:
            async def dataadd(d):
                nonlocal data, lines
                data += d
                lines += [d]

            callback = dataadd

        count = 0

        while count < 1 or not stdinClose.is_set():
            count += 1
            if std_reader:
                fr = await readmuch(std_reader)
                if args.verbose:
                    print(f'readstdin: {len(fr)} B')

                if fr is not None:
                    await callback(fr)
                    async with stdinRead:
                        stdinRead.notify()
                    if len(fr) == 0:
                        break
                    if fr.decode('latin1').strip() == 'exit':
                        await callback(b'')
                        break

        await stdinClose.wait()

        if args.verbose:
            print('readstdin exit')

        return data


    std_reader, std_writer = await connect_stdin_stdout()
    datareader = asyncio.create_task(readstdin(std_reader, std_writer))

    async def waitforstdinend():
        if args.verbose > 1:
            print('wait for stdin read end')
        await stdinComplete.wait()
        if args.verbose > 2:
            print(f'got whole input! {data}')

    async def stdinlinehandler(callback, maxlines=None):
        nonlocal lines
        stop = False
        nlines = 0
        while maxlines is None or nlines < maxlines:
            if args.verbose > 1:
                print('wait for stdin read')
            async with stdinRead:
                await stdinRead.wait()
            while len(lines) > 0:
                if maxlines is not None and nlines >= maxlines:
                    break
                data = lines[0]
                if args.verbose > 1:
                    print(f'got {len(lines)} input lines: {data}')
                if len(data) == 0:
                    stop = True
                    break
                await callback(data)
                lines = lines[1:]
                nlines += 1
        if args.verbose:
            print('stdinlinehandler exit')

    async def handleLine_pack(data):
        msg = wrap(data)
        writeOut(outf)(msg)

    async def handleLine_unpack(data):
        try:
            msg, meta = msglenb.unwrap(data)
        except ValueError as ex:
            msg, meta = None, None
            print(f'msglen unwrap failed to process {len(data)} B of data: ', ex)
            print(f'msglen infalid data: {data[0:128]}')
            return
        if args.param:
            print(meta.asJSON())
        elif args.verbose:
            print('meta:', meta)

        if (args.param is None and not args.message) or (args.message):
            writeOut(outf)(msg)

    async def handleLine_repack(data):
        try:
            msg, meta = msglenb.unwrap(data)
        except ValueError as ex:
            msg, meta = None, None
            print(f'msglen unwrap failed to process {len(data)} B of data: ', ex)
            print(f'msglen infalid data: {data[0:128]}')
            return
        if args.param:
            print(meta.asJSON())
        elif args.verbose:
            print('meta:', meta)

        rmsg = wrap(msg, vars(meta))
        writeOut(outf)(rmsg)


    def writeOut(write):
        def inner(data):
            if write.closed:
                return
            try:
                write.write(data)
            except BaseException:
                if isinstance(data, bytes):
                    data = data.decode('utf8')
                    write.write(data)
            write.flush()
        return inner

    waitforstdinendtask = asyncio.create_task(waitforstdinend())

    params = {}
    if args.param:
        params = flatten(args.param)
        params = {k: v for k, v in [item.split('=') for item in params]}
        if args.verbose:
            print('params:', params)

    wrap = msglenb.packer(dict() | params)

    outf = sys.stdout
    outfname = 'stdout'

    if args.output:
        outf = args.output
        if outf != '-':
            outfname = args.output
            outf = open(outfname, 'wb')

    if args.verbose > 1:
        print(f'cmd = {args.cmd}')

    if args.cmd == "wrap":
        stdinClose.set()
        await datareader
        wrap = msglenb.packer(params)
        msg = wrap(data)
        writeOut(outf)(msg)

    elif args.cmd == "unwrap":
        await waitforstdinendtask
        wrap = msglenb.unwrap(data)
        msg, meta = wrap
        if args.param:
            print(meta.asJSON())
        elif args.verbose:
            print('meta:', meta)

        if (args.param is None and not args.message) or (args.message):
            writeOut(outf)(msg)

    elif args.lines:
        lineradertask = asyncio.create_task(
            stdinlinehandler(
                handleLine_unpack if args.unwrap or args.decode else handleLine_pack,
                maxlines = args.num_lines
            )
        )
        await lineradertask

    elif args.cmd == "wraplines" or args.cmd == "readlines":
        lineradertask = asyncio.create_task(stdinlinehandler(handleLine_pack))
        await lineradertask

    elif args.cmd == "unwrapmsgs" or args.cmd == "unwraplines":
        lineradertask = asyncio.create_task(stdinlinehandler(handleLine_unpack))
        await lineradertask

    elif args.cmd == "head":
        lineradertask = asyncio.create_task(
            stdinlinehandler(
                handleLine_repack,
                maxlines = args.num_lines
            )
        )
        await lineradertask

    stdinComplete.set()
    stdinClose.set()

    if args.verbose:
        print('cancel datareader')
    datareader.cancel()

    await asyncio.gather(*[waitforstdinendtask, datareader], return_exceptions=True)

    if args.verbose:
        print('msgl command exit')

    #std_info[0].close()
    #std_info[2].close()


async def arun(args=None):
    try:
        await adoit(args=args)
    except asyncio.exceptions.CancelledError as ex:
        # print(f'cmdline program task cancelled: {ex}')
        pass
    except BaseException as ex:
        print(f'cmdline program caught exception: {ex}')
        raise ex


def run(args=None):
    asyncio.run(arun(args))


if __name__ == "__main__":
    run()
