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
    elif n >= 1:
        res = b'\x0a'
    else:
        res = b''
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

    def asJSON(self):
        return self.data.strip() if self.isJSON() else xml2json(self.data)

    def asXML(self):
        return self.data.strip() if self.isXML() else json2xml(self.data)

    def __str__(self):
        if metaPreferedOutput == 'xml':
            return 'Meta::' + self.asXML()
        else:
            return 'Meta::' + self.asJSON()

    def __repr__(self):
        return 'MsgMeta(' + f'{repr(self.asJSON())})'

    @property
    def __dict__(self):
        return self._dict

    @__dict__.setter
    def __dict__(self, d):
        self._dict = d
        if self.isJSON():
            self.data = json.dumps(self._dict)

    def get(self, key, default):
        return self._dict.get(key, default)


class MsglenL:
    totalHeaderSize = 16
    nBytesID = 4
    nBytesHeaderLength = 4
    nBytesBodyLength = 4
    nBytesFlags = 4
    maxMetaLength = 2**32
    maxDataLength = 2**32

    msglenId = b'msgl'
    headerFmt = struct.Struct('> 4s L L L')

    enableFlagsMap = True
    _flagsMap = {}
    _meta = {}

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
        self._flagsMap = {}
        self._meta = {}

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
        id, headlen, msglen, flags = self.unpackHeader(datahead)
        self.header = dict(id=id, headlen=headlen, msglen=msglen, flags=flags)

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
    def packHeader(cls, hlen, msglen, flags=0):
        #print(f'pack header: {cls.__name__}, {cls.msglenId}: ' +
        # f' data limit {cls.maxDataLength}, actual {msglen}'\
        # f' meta limit {cls.maxMetaLength}, actual {hlen}')
        if hlen >= cls.maxMetaLength:
            raise SizeException(f'Meta length {hlen} ({hlen:#x}) is too large for protocol {cls.msglenId}')
        if msglen >= cls.maxDataLength:
            raise SizeException(f'Data length {msglen} ({msglen:#x}) is too large for protocol {cls.msglenId}')
        return cls._packHeader(hlen, msglen, flags)

    @classmethod
    def _packHeader(cls, hlen, msglen, flags=0):
        return cls.headerFmt.pack(cls.msglenId, hlen, msglen, flags)

    msglenImpl = dict()

    def headerInfo(self, data):
        header = self.unpackHeader(data)
        return header[1:3]

    def unpackHeader(self, data):
        id = data[0:self.nBytesID]
        if id == b"msgl":
            header = MsglenL._unpackHeader(data)
        elif id == b"msgb":
            header = MsglenB._unpackHeader(data)
        elif id == b"msgh":
            header = MsglenH._unpackHeader(data)
        elif id == b"msgd":
            header = MsglenD._unpackHeader(data)
        elif id == b"mx":
            header = MsglenMx._unpackHeader(data)
        elif id == b"mh":
            header = MsglenMh._unpackHeader(data)
        else:
            raise BaseException(f'invalid msglen format: {id}')
        if self.trace & trace_head:
            print(f'read header:', *header)
        return header

    @classmethod
    def _unpackHeader(cls, data):
        return cls.headerFmt.unpack(data)

    def unwrap(self, data, toDict=False):
        id, hlen, msglen, flags = self.unpackHeader(data[0:self.totalHeaderSize])
        data, meta = self.unpack(data[self.totalHeaderSize:], hlen, msglen, flags, toDict=toDict)
        if meta:
            self.handleMeta(vars(meta))
        if self.enableFlagsMap:
            meta.__dict__ = self.dictFromFlags(flags) | meta.__dict__
        return data, meta

    def dictFromFlags(self, flags):
        mask = 0
        res = {}
        names = list(self._flagsMap.keys())
        for i in range(32):
            mask = 1 << i
            if flags & mask:
                if i < len(names):
                    flagname = names[i]
                else:
                    flagname = f'flag{i:02}'
                res[flagname] = 1
        return res

    def flagsFromDict(self, meta):
        flags = 0
        for i, name in enumerate(self._flagsMap):
            if name in meta and meta[name]:
                flags |= (1 << i)
        return flags

    def handleMeta(self, meta):
        if 'reset-meta' in meta:
            self._meta = {}
        if self.enableFlagsMap:
            if 'set-flags-map' in meta:
                self._flagsMap = {k: 1 for k in meta['set-flags-map']}
        self._meta = self._meta | meta

    def metaHeader(self, meta=None):
        if meta:
            mdata = json.dumps(meta).encode('utf8')
            mlen = len(mdata)
            mspc = nBytesAlign * int(math.ceil(mlen / nBytesAlign))
            padlen = mspc - mlen
            mdata += getpad(padlen)
            # print(f'meta length: {len(mdata)} B = {mlen} B (meta) + {padlen} B (pad)')
        else:
            mdata = b''
        return mdata

    def pack(self, data, meta={}, flags=0):
        enc = meta.get('encoding', None)
        if enc and isinstance(data, str):
            data = data.encode(enc)
        assert isinstance(data, bytes)

        mhead = self.metaHeader(meta)
        if self.enableFlagsMap:
            flags |= self.flagsFromDict(meta)
        header = self.packHeader(len(mhead), len(data), flags)

        if self.trace & trace_head:
            print(f'pack header {header}:', len(mhead), len(data))
            print(f'packet {len(header)} B + {len(mhead)} B + {len(data)} B')

        return header + mhead + data

    def packer(self, meta={}, flags=0, mask=0):
        meta_ = meta
        flags_ = flags

        def inner(data, meta={}, flags=0):
            meta = meta_ | meta
            flags = (flags | flags_) & ~mask
            return self.pack(data, meta, flags)

        return inner

    @classmethod
    def unpack(cls, data, headlen, msglen, flags=0, toDict=True):
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

        if cls.trace & trace_meta:
            print(f'meta data: ', vars(meta))

        enc = meta.get('encoding', None)
        if enc:
            data = databody.decode(enc)
        else:
            data = databody

        return data, meta


    def reader(self, read):

        async def inner():
            datahead = await read(self.totalHeaderSize)
            if len(datahead) == 0: return None, None
            if len(datahead) < self.totalHeaderSize:
                raise BaseException(f'read invalid header data: {len(datahead)} B')
            if self.trace & trace_head:
                print(f'read header data: {len(datahead)} B')
            headlen, msglen = self.headerInfo(datahead)
            data = await read(msglen + headlen)
            if self.trace & (trace_meta | trace_data):
                print(f'read data: {len(data)} B')
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
    headerFmt = struct.Struct('> 4s 4s 4s 4s')
    maxMetaLength = 2**24
    maxDataLength = 2**24

    @classmethod
    def _packHeader(cls, hlen, msglen, flags=0):
        data = MsglenL.headerFmt.pack(MsglenL.msglenId, hlen, msglen, flags)

        assert data[4] == 0
        assert data[8] == 0
        assert data[12] == 0

        hlenb = data[5:8]
        msglenb = data[9:12]
        flagsb = data[13:16]

        hlend = binascii.b2a_base64(hlenb, newline=False)
        msglend = binascii.b2a_base64(msglenb, newline=False)
        flagsd = binascii.b2a_base64(flagsb, newline=False)

        return cls.headerFmt.pack(cls.msglenId, hlend, msglend, flagsd)

    @classmethod
    def _unpackHeader(cls, data):
        id, hlend, msglend, flagsd = data[0:4], data[4:8], data[8:12], data[12:16]

        hlenb = binascii.a2b_base64(hlend)
        msglenb = binascii.a2b_base64(msglend)
        flagsb = binascii.a2b_base64(flagsd)

        rawdata = id + b'\00' + hlenb + b'\00' + msglenb + b'\00' + flagsb

        return MsglenL.headerFmt.unpack(rawdata)


class MsglenH(MsglenB):
    msglenId = b'msgh'
    maxMetaLength = 2**16
    maxDataLength = 2**24
    headerFmt = struct.Struct('> 4s 12s')

    @classmethod
    def _packHeader(cls, hlen, msglen, flags=0):
        headerd = f'{msglen:x}'
        if hlen != 0:
            headerd += f' {hlen:x}'
        if flags != 0:
            headerd += f' {flags:x}'
        headerd = ' ' * (12 - len(headerd)) + headerd
        return cls.headerFmt.pack(cls.msglenId, headerd.encode('utf8'))

    @classmethod
    def _unpackNumbers(cls, headerd, base=16):
        items = [v for v in headerd.split(' ') if v != '']
        items += ['0'] * (3 - len(items))
        return [ int(v, base) for v in items ]

    @classmethod
    def _unpackHeader(cls, data):
        id, headerd = data[0:4], data[4:cls.totalHeaderSize].decode('utf8')
        msglen, hlen, flags = cls._unpackNumbers(headerd, base=16)
        return id, hlen, msglen, flags


class MsglenD(MsglenH):
    msglenId = b'msgd'

    @classmethod
    def _packHeader(cls, hlen, msglen, flags=0):
        headerd = f'{msglen:d}'
        if hlen != 0:
            headerd += f' {hlen:d}'
        if flags != 0:
            headerd += f' {flags:d}'
        headerd = ' ' * (12 - len(headerd)) + headerd
        return cls.headerFmt.pack(cls.msglenId, headerd.encode('utf8'))


    @classmethod
    def _unpackHeader(cls, data):
        id, headerd = data[0:4], data[4:cls.totalHeaderSize].decode('utf8')
        msglen, hlen, flags = cls._unpackNumbers(headerd, base=10)
        return id, hlen, msglen, flags


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
    nBytesFlags = 1
    nBytesHeaderLength = 2
    nBytesBodyLength = 3
    maxMetaLength = 2**16
    maxDataLength = 2**24

    msglenId = b'mx'
    headerFmt = struct.Struct('> 2s B H B H')

    @classmethod
    def _packHeader(cls, hlen, msglen, flags=0):
        ml_hi = (msglen >> 16) & 0xf
        ml_lo = msglen & 0xffff
        data = MsglenMx.headerFmt.pack(cls.msglenId, flags, hlen, ml_hi, ml_lo)
        return data

    @classmethod
    def _unpackHeader(cls, data):
        id, flags, hlen, ml_hi, ml_lo = cls.headerFmt.unpack(data)
        msglen = (ml_hi << 16) | ml_lo
        return id, hlen, msglen, flags


class MsglenMh(MsglenMx):
    maxMetaLength = 2**12
    maxDataLength = 2**24

    msglenId = b'mh'
    headerFmt = struct.Struct('> 2s 6s')

    @classmethod
    def _packHeader(cls, hlen, msglen, flags=0):
        headerd = f'{msglen:x}'
        if hlen != 0:
            headerd += f' {hlen:x}'
        if flags != 0:
            headerd += f' {flags:x}'
        headerd = ' ' * (6 - len(headerd)) + headerd
        data = cls.headerFmt.pack(cls.msglenId, headerd.encode('utf8'))
        return data

    @classmethod
    def _unpackHeader(cls, data):
        id, headerb  = cls.headerFmt.unpack(data)
        mlen, hlen, flags = MsglenH._unpackNumbers(headerb.decode('utf8'), base=16)
        return id, hlen, mlen, flags


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
