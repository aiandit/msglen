import struct
import json
import math
import io
import asyncio
import binascii
from inspect import iscoroutinefunction

from astunparse import xml2json, json2xml

protocols = [
    'mx', 'mh',
    'msgl', 'msgb', 'msgh', 'msgd',
]

protocolFamilies = {
    'mx': ['mx', 'mh'],
    'msgl': ['msgl', 'msgb', 'msgh', 'msgd'],
}

nBytesAlign = 8
maxMetaSize = 2**14
metaPreferedOutput = 'json'

trace_head = 0b001
trace_meta = 0b010
trace_data = 0b100


def ensure_co(readfunc):
    if iscoroutinefunction(readfunc):
        return readfunc
    else:
        async def c(*args, **kwargs):
            return readfunc(*args, **kwargs)
        return c


def getpad(n):
    if n >= 2:
        res = b' ' * (n-2) + b'\x0d\x0a'
    else:
        res = b' ' * n
    return res


class SizeException(BaseException):
    pass


class MsgMeta:
    def __init__(self, data):
        if isinstance(data, bytes):
            data = data.decode('utf8')
        if isinstance(data, dict):
            self._dict = data
            self.data = json.dumps(data)
        else:
            self.data = data
            self._dict = json.loads(self.data)

    def isJSON(self):
        return self.data[0] == '{' or self.data[0] == '['

    def isXML(self):
        return self.data[0] == '<'

    def getJSON(self):
        return self.data if self.isJSON() else xml2json(self.data)

    def getXML(self):
        return self.data if self.isXML() else json2xml(self.data)

    def __str__(self):
        if metaPrefereedOutput == 'xml':
            return 'Meta::' + self.getXML()
        else:
            return 'Meta::' + self.getJSON()

    def __repr__(self):
        return 'MsgMeta(' + f'{repr(self.getJSON())})'

    @property
    def __dict__(self):
        return self._dict

    def get(self, key, default):
        return self._dict.get(key, default)

class MsglenL:
    #FIXME: 16
    totalHeaderSize = 12
    nBytesID = 4
    nBytesHeaderLength = 4
    nBytesBodyLength = 4
    nBytesOptions = 4
    maxMetaLength = 2**32
    maxDataLength = 2**32

    msglenId = b'msgl'
    headerFmt = struct.Struct('> 4s L L')

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
        datahead = self.file.read(self.totalHeaderSize)
        id, headlen, msglen = self.unpackHeader(datahead)
        self.header = dict(id=id, headlen=headlen, msglen=msglen)

    def readMeta(self):
        if self.header is None:
            self.readHeader()
        if self.canSeek and self.needSeek(self.totalHeaderSize):
            self.file.seek(self.totalHeaderSize)
        datameta = self.file.read(self.header['headlen'])
        return MsgMeta(datameta)

    def readData(self):
        if self.header is None:
            self.readHeader()
        if self.canSeek and self.needSeek(self.header['headlen'] + self.totalHeaderSize):
            self.file.seek(self.header.headlen + self.totalHeaderSize)
        data = self.file.read(self.header.msglen)
        return data

    def writeMeta(self, meta):
        self.file.seek(0)
        datahead = self.file.read(self.totalHeaderSize)
        id, headlen, msglen = self.unpackHeader(datahead)
        datameta = b''
        if len(meta):
            datameta = json.dumps(meta).encode('utf8')
            if len(datameta) > headlen:
                raise BaseException('Header data too large')
            datameta = datameta + getpad(headlen - len(datameta))
            self.file.seek(self.totalHeaderSize)
            self.file.write(datameta)

    @classmethod
    def packHeader(cls, hlen, msglen):
        #print(f'pack header: {cls.__name__}, {cls.msglenId}: ' +
        # f' data limit {cls.maxDataLength}, actual {msglen}'\
        # f' meta limit {cls.maxMetaLength}, actual {hlen}')
        if hlen >= cls.maxMetaLength:
            raise SizeException(f'Meta length {hlen} ({hlen:#x}) is too large for protocol {cls.msglenId}')
        if msglen >= cls.maxDataLength:
            raise SizeException(f'Data length {hlen} ({hlen:#x}) is too large for protocol {cls.msglenId}')
        return cls._packHeader(hlen, msglen)

    @classmethod
    def _packHeader(cls, hlen, msglen):
        return cls.headerFmt.pack(cls.msglenId, hlen, msglen)

    msglenImpl = dict()

    def unpackHeader(self, data):
        id = data[0:self.nBytesID]
        if id == b"msgl":
            id, hlen, msglen = MsglenL._unpackHeader(data)
        elif id == b"msgb":
            id, hlen, msglen = MsglenB._unpackHeader(data)
        elif id == b"msgh":
            id, hlen, msglen = MsglenH._unpackHeader(data)
        elif id == b"msgd":
            id, hlen, msglen = MsglenD._unpackHeader(data)
        elif id == b"mx":
            id, hlen, msglen = MsglenMx._unpackHeader(data)
        elif id == b"mh":
            id, hlen, msglen = MsglenMh._unpackHeader(data)
        else:
            raise BaseException(f'invalid msglen format: {id}')
        if self.trace & trace_head:
            print(f'read header:', data, hlen, msglen)
        return id, hlen, msglen

    @classmethod
    def _unpackHeader(cls, data):
        id, hlen, msglen = cls.headerFmt.unpack(data)
        return id, hlen, msglen

    def unwrap(self, data):
        id, hlen, msglen = self.unpackHeader(data[0:self.totalHeaderSize])
        return self.unpack(data[self.totalHeaderSize:], hlen, msglen)

    def metaHeader(self, meta=None):
        if meta:
            mdata = json.dumps(meta).encode('utf8')
            mlen = len(mdata)
            mspc = nBytesAlign * int(math.ceil(mlen / nBytesAlign))
            padlen = mspc - mlen
            mdata += getpad(padlen)
            # print(f'header length: {headlen} B = {self.totalHeaderSize} B + {mlen} B (meta) + {padlen} B (pad)')
        else:
            mdata = b''
        return mdata

    def pack(self, data, meta={}):
        enc = meta.get('encoding', None)
        if enc:
            data = data.encode(enc)
        assert isinstance(data, bytes)

        mhead = self.metaHeader(meta)
        header = self.packHeader(len(mhead), len(data))

        if self.trace & trace_head:
            print(f'pack header {header}:', len(mhead), len(data))

        return header + mhead + data

    def packer(self, meta={}):
        meta_ = meta
        enc = meta_.get('encoding', None)
        mhead = self.metaHeader(meta_)

        def inner(data, meta={}):
            nonlocal enc
            meta = meta_ | meta
            if meta:
                mhead = self.metaHeader(meta)
                enc = meta.get('encoding', enc)
            else:
                mhead = b''
            if enc:
                data = data.encode(enc)
            header = self.packHeader(len(mhead), len(data))
            return header + mhead + data

        return inner

    @classmethod
    def unpack(cls, data, headlen, msglen, toDict=True):
        datameta = data[0:headlen]
        databody = data[headlen:]

        assert len(databody) == msglen

        if toDict:
            meta = {}
            if len(datameta):
                meta = vars(MsgMeta(datameta))
        else:
            meta = MsgMeta('{}')
            if len(datameta):
                meta = MsgMeta(datameta)

        enc = meta.get('encoding', None)
        if enc:
            data = databody.decode(enc)
        else:
            data = databody

        return data, meta


    def reader(self, read):

        async def inner():
            datahead = await read(self.totalHeaderSize)
            if len(datahead) < self.totalHeaderSize: return None, None
            id, headlen, msglen = self.unpackHeader(datahead)
            data = await read(msglen + headlen)
            return self.unpack(data, headlen, msglen)

        return inner

    def writer(self, writer, meta={}):
        meta_ = meta
        def inner(data, meta={}):

            data = self.pack(data, meta_|meta)
            wres = writer.write(data)

        return inner

    def wrappers(self, meta={}):
        return self.packer(meta=meta), self.unwrap

    def readers(self, reader, writer, meta={}):
        return self.reader(reader), self.writer(writer, meta=meta)

    @classmethod
    def create(cls, protocol='msgl'):
        if protocol == 'msgl':
            inst = MsglenL()
        elif protocol == 'msgb':
            inst = MsglenB()
        elif protocol == 'msgh':
            inst = MsglenH()
        elif protocol == 'msgd':
            inst = MsglenD()
        elif protocol == 'mx':
            inst = MsglenMx()
        elif protocol == 'mh':
            inst = MsglenMh()
        return inst

    @classmethod
    def createwrappers(cls, protocol='msgl'):
        return cls.create(protocol).wrappers()


create = MsglenL.create
createwrappers = MsglenL.createwrappers


class MsglenB(MsglenL):
    msglenId = b'msgb'
    headerFmt = struct.Struct('> 4s 4s 4s')
    maxMetaLength = 2**24
    maxDataLength = 2**24

    @classmethod
    def _packHeader(cls, hlen, msglen):
        data = MsglenL.headerFmt.pack(MsglenL.msglenId, hlen, msglen)

        assert data[4] == 0
        assert data[8] == 0

        hlenb = data[5:8]
        msglenb = data[9:12]

        hlend = binascii.b2a_base64(hlenb, newline=False)
        msglend = binascii.b2a_base64(msglenb, newline=False)

        return cls.headerFmt.pack(cls.msglenId, hlend, msglend)

    @classmethod
    def _unpackHeader(cls, data):
        id, hlend, msglend = data[0:4], data[4:8], data[8:12]

        hlenb = binascii.a2b_base64(hlend)
        msglenb = binascii.a2b_base64(msglend)

        rawdata = id + b'\00' + hlenb + b'\00' + msglenb

        id, hlen, msglen = MsglenL.headerFmt.unpack(rawdata)
        return id, hlen, msglen


class MsglenH(MsglenB):
    msglenId = b'msgh'
    maxMetaLength = 2**16
    maxDataLength = 2**16


    @classmethod
    def _packHeader(cls, hlen, msglen):
        data = MsglenL.headerFmt.pack(MsglenL.msglenId, hlen, msglen)

        assert data[4] == 0
        assert data[5] == 0
        assert data[8] == 0
        assert data[9] == 0

        hlenb = data[6:8]
        msglenb = data[10:12]

        hlend = binascii.b2a_hex(hlenb)
        msglend = binascii.b2a_hex(msglenb)

        return cls.headerFmt.pack(cls.msglenId, hlend, msglend)


    @classmethod
    def _unpackHeader(cls, data):
        id, hlend, msglend = data[0:4], data[4:8], data[8:12]

        hlenb = binascii.a2b_hex(hlend)
        msglenb = binascii.a2b_hex(msglend)

        rawdata = id + b'\00'*2 + hlenb + b'\00'*2 + msglenb

        id, hlen, msglen = MsglenL.headerFmt.unpack(rawdata)
        return id, hlen, msglen


class MsglenD(MsglenH):
    msglenId = b'msgd'

    @classmethod
    def _packHeader(cls, hlen, msglen):
        hlenb = f'{hlen:4d}'.encode('utf8')
        msglend = f'{msglen:4d}'
        if msglend[0] == ' ' and msglend[1] == ' ':
            msglend = msglend[1:] + ' '
        msglenb = msglend.encode('utf8')

        return cls.headerFmt.pack(cls.msglenId, hlenb, msglenb)


    @classmethod
    def _unpackHeader(cls, data):
        id, hlend_and_msglend = data[0:4], data[4:].decode('utf8')

        hlen, msglen = [ int(v) for v in hlend_and_msglend.split(' ') if v !=  '' ]

        return id, hlen, msglen

class MslenReader:

    def __init__(self, reader, proto='msgl', **kw):
        super().__init__(**kw)

        inst = MsglenL.create(proto)

        self.reader = reader
        self.readhandle = inst.reader(reader)

    async def read(self):
        return await self.readhandle()


class MslenWriter:

    def __init__(self, writer, proto='msgl', meta={}, **kw):
        super().__init__(**kw)

        inst = MsglenL.create(proto)

        self.writer = writer
        self.writehandle = inst.writer(writer, meta)

    def write(self, data, meta={}):
        return self.writehandle(data, meta)


class MsglenMx(MsglenL):
    totalHeaderSize = 8
    nBytesID = 2
    nBytesOptions = 1
    nBytesHeaderLength = 2
    nBytesBodyLength = 3
    maxMetaLength = 2**16
    maxDataLength = 2**24

    msglenId = b'mx'
    headerFmt = struct.Struct('> 2s B H B H')

    @classmethod
    def _packHeader(cls, hlen, msglen):
        ml_hi = (msglen >> 16) & 0xf
        ml_lo = msglen & 0xffff
        data = MsglenMx.headerFmt.pack(cls.msglenId, 0, hlen, ml_hi, ml_lo)
        return data

    @classmethod
    def _unpackHeader(cls, data):
        id, flags, hlen, ml_hi, ml_lo = cls.headerFmt.unpack(data)
        msglen = (ml_hi << 16) | ml_lo
        return id, hlen, msglen


class MsglenMh(MsglenMx):
    maxMetaLength = 2**8
    maxDataLength = 2**12

    msglenId = b'mh'
    headerFmt = struct.Struct('> 2s s 2s 3s')

    @classmethod
    def _packHeader(cls, hlen, msglen):
        data = MsglenMx._packHeader(hlen, msglen)
        hlenb = data[3:5]
        msglenb = data[5:]
        hlend = binascii.b2a_hex(hlenb)
        msglend = binascii.b2a_hex(msglenb)
        data = cls.headerFmt.pack(cls.msglenId, b'0', hlend[2:], msglend[3:])
        return data

    @classmethod
    def _unpackHeader(cls, data):
        id, flagsb, hlend, msglend = cls.headerFmt.unpack(data)
        hlenb = binascii.a2b_hex(hlend)
        msglenb = binascii.a2b_hex(b'0' + msglend)
        id, hlen, msglen = MsglenMx._unpackHeader(id + flagsb + b'\0' + hlenb + b'\0' + msglenb)
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
