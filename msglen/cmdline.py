import sys
import asyncio
import argparse
import aiaio

from . import __version__
from . import __commit__

from .msglen import MsglenB, MsglenL
from .stdinreader import connect_stdin_stdout, readmuch
from . import log

def mkparser(parser=None):
    if parser is None:
        parser = argparse.ArgumentParser('msglen',
                                         '''\
MsgLen CLI tool.
''', '')

    parser.add_argument('-m', '--message', metavar='S', type=str, nargs='?', action='append')
    parser.add_argument('-n', '--num-lines', metavar='N', nargs='?', type=int, const=10)
    parser.add_argument('-l', '--lines', action='store_true')
    parser.add_argument('-c', '--count', action='store_true')
    parser.add_argument('-d', '--decode', action='store_true')
    parser.add_argument('-u', '--unwrap', action='store_true')
    parser.add_argument('-r', '--rewrap', action='store_true')
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

        while not stdinClose.is_set():
            if std_reader:
                fr = await readmuch(std_reader)
                if args.verbose:
                    log.log(f'readstdin: {len(fr)} B')

                if fr is not None:
                    await callback(fr)
                    async with stdinRead:
                        stdinRead.notify()
                    if len(fr) == 0:
                        break
                    if fr.decode('latin1').strip() == 'exit':
                        await callback(b'')
                        break

        stdinClose.set()

        if args.verbose:
            log.log('readstdin exit')

        return data


    std_reader, std_writer = await connect_stdin_stdout()
    datareader = asyncio.create_task(readstdin(std_reader, std_writer))

    async def stdinlinehandler(callback, maxlines=None):
        nonlocal lines
        stop = False
        nlines = 0
        while not stop and (maxlines is None or nlines < maxlines):
            if args.verbose > 1:
                log.log(f'{len(lines)} lines available')
            if len(lines) == 0:
                if stdinClose.is_set():
                    break
                else:
                    if args.verbose > 1:
                        log.log('wait for stdin read')
                    async with stdinRead:
                        await stdinRead.wait()
            while len(lines) > 0:
                if maxlines is not None and nlines >= maxlines:
                    break
                data = lines[0]
                if args.verbose > 1:
                    log.log(f'got {len(lines)} input lines')
                    log.log(f'first line: {data[0:16]} ({len(data)} B)')
                if len(data) == 0:
                    stop = True
                    break
                await callback(data)
                lines = lines[1:]
                nlines += 1
        if args.verbose:
            log.log('stdinlinehandler exit')

    async def handleLine_pack(data):
        msg = wrap(data)
        await (writeOut(outf))(msg)

    async def handleLine_unpack(data):
        try:
            msg, meta = msglenb.unwrap(data)
        except ValueError as ex:
            msg, meta = None, None
            log.log(f'msglen unwrap failed to process {len(data)} B of data: ', ex)
            log.log(f'msglen invalid data: {data[0:128]}')
            return
        if args.param:
            log.log(meta.asJSON())
        elif args.verbose:
            log.log('meta:', meta)

        if (args.param is None and not args.message) or (args.message):
            await (writeOut(outf))(msg)

    async def handleLine_repack(data):
        try:
            msg, meta = msglenb.unwrap(data)
        except ValueError as ex:
            msg, meta = None, None
            log.log(f'msglen unwrap failed to process {len(data)} B of data: ', ex)
            log.log(f'msglen invalid data: {data[0:128]}')
            return
        if args.param:
            log.log(meta.asJSON())
        elif args.verbose:
            log.log('meta:', meta)

        rmsg = wrap(msg, vars(meta))
        await (writeOut(outf))(rmsg)


    msgcount = dict(count=0,rawbytes=0,bytes=0,errors=0,errbytes=0)
    async def handleLine_count(data):
        msgcount['rawbytes'] += len(data)
        try:
            msg, meta = msglenb.unwrap(data)
            msgcount['count'] += 1
            msgcount['bytes'] += len(msg)
        except ValueError as ex:
            msgcount['errors'] += 1
            msgcount['errbytes'] += len(data)
            msg, meta = None, None
            log.log(f'msglen unwrap failed to process {len(data)} B of data: ', ex)
            log.log(f'msglen invalid data: {data[0:128]}')
            return


    nwrt = 0
    def writeOut(write):
        async def inner(data):
            nonlocal nwrt
            await write.write(data, offset=nwrt)
            nwrt += len(data)
        return inner

    params = {}
    if args.param:
        params = flatten(args.param)
        params = {k: v for k, v in [item.split('=') for item in params]}
        if args.verbose:
            log.log('params:', params)

    wrap = msglenb.packer(dict() | params)

    outf = sys.stdout
    outfname = 'stdout'

    if args.output and args.output != '-':
        outfname = args.output
        outf = aiaio.AIOFile(outfname, 'wb')
        await outf.open()

    if args.verbose > 1:
        log.log(f'cmd = {args.cmd}')

    if args.cmd == "wrap":
        await stdinClose.wait()
        wrap = msglenb.packer(params)
        msg = wrap(data)
        await (writeOut(outf))(msg)

    elif args.cmd == "unwrap":
        await stdinClose.wait()
        wrap = msglenb.unwrap(data)
        msg, meta = wrap
        if args.param:
            log.log(meta.asJSON())
        elif args.verbose:
            log.log('meta:', meta)

        if (args.param is None and not args.message) or (args.message):
            await (writeOut(outf))(msg)

    elif args.lines:
        lineradertask = asyncio.create_task(
            stdinlinehandler(
                handleLine_unpack if args.unwrap or args.decode else
                handleLine_count if args.count else
                handleLine_repack if args.rewrap else
                handleLine_pack,
                maxlines = args.num_lines
            )
        )
        await lineradertask
        if args.count:
            log.log(f'{msgcount} messages unwrapped')

    elif args.cmd == "wraplines" or args.cmd == "readlines":
        lineradertask = asyncio.create_task(stdinlinehandler(handleLine_pack))
        await lineradertask

    elif args.cmd == "unwrapmsgs" or args.cmd == "unwraplines":
        lineradertask = asyncio.create_task(stdinlinehandler(handleLine_unpack))
        await lineradertask

    stdinClose.set()
    datareader.cancel()

    await asyncio.gather(*[datareader], return_exceptions=True)

    await outf.close()
    await aiaio.aio.release_globals()

    if args.verbose:
        log.log('msgl command exit')
    log.close()
    await log.start()


async def arun(args=None):
    log.start()
    try:
        await adoit(args=args)
    except asyncio.exceptions.CancelledError as ex:
        # log.log(f'cmdline program task cancelled: {ex}')
        pass
    except SystemExit as ex:
        sys.exit(ex)
    except BaseException as ex:
        log.log(f'cmdline program caught exception: {ex} ({type(ex)})')
        raise ex


def run(args=None):
    asyncio.run(arun(args))


if __name__ == "__main__":
    run()
