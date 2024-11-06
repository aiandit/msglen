import struct
import json
import math
import io
import asyncio
import binascii

from inspect import iscoroutinefunction


def ensure_co(readfunc):
    if iscoroutinefunction(readfunc):
        return readfunc
    else:
        async def c(*args, **kwargs):
            return readfunc(*args, **kwargs)
        return c


alignTo = 8
baseHeadLen = 16

trace_head = 0b001
trace_meta = 0b010
trace_data = 0b100


def getpad(n):
    if n >= 2:
        res = b' ' * (n-2) + b'\x0d\x0a'
    else:
        res = b' ' * n
    return res


class MsglenL:
    msglenId = b'msgl'
    headerFmt = struct.Struct('> 4s L Q')

    file = None
    reader = None
    header = None
    meta = None
    canSeek = False
    trace = 0

    def __init__(self, source=None, trace=0, **kw):
        super().__init__(**kw)
        self.trace = trace
        if source is not None:
            self.canSeek = True
            self.file = source
            self.reader = ensure_co(source.read)
            self.writer = ensure_co(source.write)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        pass

    def needSeek(self, pos):
        return self.file.tell() != pos

    def readHeader(self):
        if self.canSeek and self.needSeek(10):
            self.file.seek(0)
        datahead = self.file.read(16)
        id, headlen, msglen = self.unpackHeader(datahead)
        self.header = dict(id=id, headlen=headlen, msglen=msglen)

    def readMeta(self):
        if self.header is None:
            self.readHeader()
        if self.canSeek and self.needSeek(16):
            self.file.seek(16)
        datameta = self.file.read(self.header['headlen'])
        return datameta.decode('utf8')

    def readData(self):
        if self.header is None:
            self.readHeader()
        if self.canSeek and self.needSeek(self.header['headlen'] + 16):
            self.file.seek(self.header.headlen + 16)
        data = self.file.read(self.header.msglen)
        return data

    def writeMeta(self, meta):
        self.file.seek(0)
        datahead = self.file.read(16)
        id, headlen, msglen = self.unpackHeader(datahead)
        datameta = b''
        if len(meta):
            datameta = json.dumps(meta).encode('utf8')
            if len(datameta) > headlen:
                raise BaseException('Header data too large')
            datameta = datameta + getpad(headlen - len(datameta))
            self.file.seek(16)
            self.file.write(datameta)

    def packHeader(self, hlen, msglen):
        return self.headerFmt.pack(self.msglenId, hlen, msglen)

    msglenImpl = dict()

    def unpackHeader(self, data):
        id = data[0:4]
        if id == b"msgl":
            id, hlen, msglen = MsglenL._unpackHeader(data)
        elif id == b"msgb":
            id, hlen, msglen = MsglenB._unpackHeader(data)
        elif id == b"msgh":
            id, hlen, msglen = MsglenH._unpackHeader(data)
        elif id == b"msgd":
            id, hlen, msglen = MsglenD._unpackHeader(data)
        else:
            raise BaseException(f'invalid msglen format: {id}')
        if self.trace & trace_head:
            print(f'read header:', data, hlen, msglen)
        return id, hlen, msglen

    @classmethod
    def _unpackHeader(cls, data):
        id, hlen, msglen = cls.headerFmt.unpack(data)
        return id, hlen, msglen

    def metaHeader(self, meta=None):
        if meta:
            mdata = json.dumps(meta).encode('utf8')
            mlen = len(mdata)
            mspc = alignTo * int(math.ceil(mlen / alignTo))
            padlen = mspc - mlen
            mdata += getpad(padlen)
            # print(f'header length: {headlen} B = {baseHeadLen} B + {mlen} B (meta) + {padlen} B (pad)')
        else:
            mdata = b''
        return mdata

    def pack(self, data, meta):
        enc = meta.get('encoding', None)
        if enc:
            data = data.encode(enc)
        assert isinstance(data, bytes)

        mhead = self.metaHeader(meta)
        header = self.packHeader(len(mhead), len(data))

        if self.trace & trace_head:
            print(f'pack header {header}:', len(mhead), len(data))

        return header + mhead + data

    def packer(self, meta):
        enc = meta.get('encoding', None)
        mhead = self.metaHeader(meta)

        def inner(data):
            if enc:
                data = data.encode(enc)
            header = self.packHeader(len(mhead), len(data))
            return header + mhead + data

        return inner

    @classmethod
    def unpack(cls, data, headlen, msglen):
        datameta = data[0:headlen]
        databody = data[headlen:]

        assert len(datameta) == headlen
        assert len(databody) == msglen

        meta = {}
        if len(datameta) and datameta[0] == b'{'[0]:
            meta = json.loads(datameta.decode('utf8'))

        enc = meta.get('encoding', None)
        if enc:
            data = databody.decode(enc)

        return data, meta


    def reader(self, read):

        async def inner():
            datahead = await read(16)
            if len(datahead) < 16: return None, None
            id, headlen, msglen = self.unpackHeader(datahead)
            data = await read(msglen + headlen)
            return self.unpack(data, headlen, msglen)

        return inner

    def writer(self, writer, meta):

        def inner(data):

            data = self.pack(data, meta)
            wres = writer.write(data)

        return inner


class MsglenB(MsglenL):
    msglenId = b'msgb'
    headerFmt = struct.Struct('> 4s 4s 8s')

    def packHeader(self, hlen, msglen):
        data = MsglenL.headerFmt.pack(MsglenL.msglenId, hlen, msglen)

        assert data[4] == 0
        assert data[8] == 0
        assert data[9] == 0

        hlenb = data[5:8]
        msglenb = data[10:]

        hlend = binascii.b2a_base64(hlenb, newline=False)
        msglend = binascii.b2a_base64(msglenb, newline=False)

        return self.headerFmt.pack(self.msglenId, hlend, msglend)

    @classmethod
    def _unpackHeader(cls, data):
        id, hlend, msglend = data[0:4], data[4:8], data[8:]

        hlenb = binascii.a2b_base64(hlend)
        msglenb = binascii.a2b_base64(msglend)

        rawdata = id + b'\00' + hlenb + b'\00\00' + msglenb

        id, hlen, msglen = MsglenL.headerFmt.unpack(rawdata)
        return id, hlen, msglen


class MsglenH(MsglenB):
    msglenId = b'msgh'

    def packHeader(self, hlen, msglen):
        data = MsglenL.headerFmt.pack(MsglenL.msglenId, hlen, msglen)

        assert data[4] == 0
        assert data[5] == 0
        assert data[8] == 0
        assert data[9] == 0
        assert data[10] == 0
        assert data[11] == 0

        hlenb = data[6:8]
        msglenb = data[12:]

        hlend = binascii.b2a_hex(hlenb)
        msglend = binascii.b2a_hex(msglenb)

        return self.headerFmt.pack(self.msglenId, hlend, msglend)

    @classmethod
    def _unpackHeader(cls, data):
        id, hlend, msglend = data[0:4], data[4:8], data[8:]

        hlenb = binascii.a2b_hex(hlend)
        msglenb = binascii.a2b_hex(msglend)

        rawdata = id + b'\00'*2 + hlenb + b'\00'*4 + msglenb

        id, hlen, msglen = MsglenL.headerFmt.unpack(rawdata)
        return id, hlen, msglen


class MsglenD(MsglenB):
    msglenId = b'msgd'

    def packHeader(self, hlen, msglen):
        data = MsglenL.headerFmt.pack(MsglenL.msglenId, hlen, msglen)

        hlenb = f'{hlen:4d}'.encode('utf8')
        msglend = f'{msglen:8d}'
        if msglend[0] == ' ' and msglend[1] == ' ':
            msglend = msglend[1:] + ' '
        msglenb = msglend.encode('utf8')

        return self.headerFmt.pack(self.msglenId, hlenb, msglenb)

    @classmethod
    def _unpackHeader(cls, data):
        id, hlend, msglend = data[0:4], data[4:8], data[8:]

        hlen = int(hlend.decode('utf8'))
        msglen = int(msglend.decode('utf8'))

        return id, hlen, msglen


async def run():

    msgType = MsglenB

    msglenb = msgType()

    wrap = msglenb.packer(dict(encoding='utf8'))
    msg = wrap('Hallo Welt')
    print(msg)
    print(msg.decode('utf8'))

    reader = io.BytesIO(msg)

    unwrap = msglenb.reader(reader.read)

    data, meta = await unwrap()

    print(f'"{data}", {meta}')

    reader = io.BytesIO(msg)
    with msgType(reader) as f:
        print(f.readMeta())


if __name__ == "__main__":
    asyncio.run(run())
