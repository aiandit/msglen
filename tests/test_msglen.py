import sys
import asyncio
import struct
import random
import math

sys.path += ['.']

from msglen import msglen

def test_msglen1():
    assert True

msglend = msglen.MsglenD()
msglenb = msglen.MsglenB()
msglenl = msglen.MsglenL()

msglenProto = msglend

async def af_atest_msglen_async2_read():
    maxconnect = 3
    msglenProto.trace = 0
    async def connected(reader, writer):
        nonlocal maxconnect
        msgread = msglenProto.reader(reader.read)
        msgwrite = msglenb.writer(writer, dict(server='Test123', encoding='utf8'))
        while True:
            msg, meta = await msgread()
            if msg is None and meta is None:
                print('server: Client disconnected')
                break
            print(f'server: Got client message [{meta}]: {msg}')
            msgwrite(msg)
        writer.close()
        print('server: client task done')
    print('start server')
    server = await asyncio.start_server(connected, port=11001)
    print('server: started')
    return server

async def af_atest_msglen_async2_writer():
    reader, writer = await asyncio.open_connection(port=11001)
    msgread = msglenProto.reader(reader.read)
    msgwrite = msglenProto.writer(writer, dict(client='Client123', encoding='utf8'))
    n = 5
    for i in range(n):
        msgwrite(f'Hallo {i}')
        wres = await writer.drain()
        msg, meta = await msgread()
        print(f'Got server response [{meta}]: {msg}')
    writer.close()


async def af_atest_msglen_async2():
    server = await af_atest_msglen_async2_read()
    clients = [af_atest_msglen_async2_writer() for i in range(3)]
    cres = await asyncio.gather(*clients)
    print('clients done')
    if False:
        sres = await server.serve_forever()
        print('server done')
    else:
        sres = await asyncio.sleep(1)
        print('server test exit')

async def atest_msglen_async2():
    await asyncio.wait_for(af_atest_msglen_async2(), 10)

def test_msglen_async2():
    asyncio.run(atest_msglen_async2())
    assert True


def test_msglenl3():
    data = b"Hallo, Welt!"
    msg = msglenl.pack(data)
    print (data)
    assert len(msg) == msglen.MsglenL.totalHeaderSize + len(data)
    assert len(msg) % 8 == len(data) % 8

def test_msglenl4():
    data = b"Hallo, Welt!"
    msg = msglenl.pack(data)
    hlen, = struct.unpack('>l', msg[4:8])
    mlen, = struct.unpack('>l', msg[8:12])
    assert hlen == 0
    assert mlen == len(data)

def test_msglenl5():
    data = b"Hallo, Welt!"
    msg = msglenl.pack(data, {'data': 123})
    hlen, = struct.unpack('>l', msg[4:8])
    mlen, = struct.unpack('>l', msg[8:12])
    assert hlen > 0
    assert mlen == len(data)
    assert len(msg) % 8 == len(data) % 8

def test_msglenl6():
    data = b"Hallo, Welt!"
    meta = {'data': 123}
    if random.random() > 0.65:
        meta['r1'] = random.random()
    if random.random() > 0.65:
        meta['r2'] = random.random()
    if random.random() > 0.65:
        meta['r3'] = random.random()
    if random.random() > 0.65:
        meta['r4'] = random.random()
    print(meta)
    msg = msglenl.pack(data, meta)
    assert len(msg) % 8 == len(data) % 8

def roundtrip(packer, unpacker, check=True):
    def inner(data, meta):
        msg = packer(data, meta)
        print('packed:', msg)
        rdata, rmeta = res = unpacker(msg)
        assert rdata == data
        print(rmeta)
        print(type(rmeta))
        print(rmeta, vars(rmeta))
        assert vars(rmeta) == meta
        return (data, rmeta)
    return inner

def checkRes(res, data, meta):
    res_d, res_m = res
    assert res_d == data
    assert vars(res_m) == meta

fround = roundtrip(msglenl.packer(), msglenl.unwrap)
sround = roundtrip(msglenl.packer(meta=dict(encoding='utf8')), msglenl.unwrap)

def test_msglenl7():
    data = b"Hallo, Welt!"
    meta = {'data': 123}

    res_d, res_m = res = fround(data, meta)
    assert res_d == data
    assert vars(res_m) == meta
    checkRes(res, data, meta)

def test_msglenl8():
    data = b"Hallo, Welt!"
    meta = {}

    res = fround(data, meta)
    checkRes(res, data, meta)

def test_msglenl9():
    data = b"Hallo, Welt?!"
    meta = {}

    res = fround(data, meta)
    checkRes(res, data, meta)

def test_msglenl10():
    data = b"Hallo, Welt?!"
    meta = dict(a=dict(f=1,g=2,h=3),b='Grüße',c=['Dörren', math.pi])

    res = fround(data, meta)
    print(res)
    checkRes(res, data, meta)

def test_msglenl11():
    data = "Grüße, Welt!"
    meta = dict(encoding='utf8',a=dict(f=1,g=2,h=3))

    res = sround(data, meta)
    print(res)
    checkRes(res, data, meta)

def test_msglen_proto1():
    data = "Grüße, Welt!"
    meta = dict(encoding='utf8',a=dict(f=1,g=2,h=3))

    pack, unwrap = msglen.createwrappers('msgl')
    msg = pack(data, meta)
    res = unwrap(msg)
    print(res)
    checkRes(res, data, meta)

def test_msglen_proto1a():
    data = "Grüße, Welt!"
    meta = dict(encoding='utf8',a=dict(f=1,g=2,h=3))

    pack, unwrap = msglen.createwrappers('msgl')
    msg = pack(data, meta)
    res = unwrap(msg)
    print(res)
    checkRes(res, data, meta)

def test_msglen_proto2():
    data = "Grüße, Welt!"
    meta = dict(encoding='utf8',a=dict(f=1,g=2,h=3))

    pack, unwrap = msglen.createwrappers('msgd')
    msg = pack(data, meta)
    res = unwrap(msg)
    print(res)
    checkRes(res, data, meta)

def test_msglen_proto3():
    data = "Grüße, Welt!"
    meta = dict(encoding='utf8',a=dict(f=1,g=2,h=3))

    pack, unwrap = msglen.createwrappers('msgh')
    msg = pack(data, meta)
    res = unwrap(msg)
    print(res)
    checkRes(res, data, meta)

def test_msglen_proto4():
    data = "Grüße, Welt!"
    meta = dict(encoding='utf8',a=dict(f=1,g=2,h=3))

    pack, unwrap = msglen.createwrappers('msgd')
    msg = pack(data, meta)
    res = unwrap(msg)
    print(res)
    checkRes(res, data, meta)

def test_msglen_proto5():
    data = "Grüße, Welt!"
    meta = dict(encoding='utf8',a=dict(f=1,g=2,h=3))

    pack, unwrap = msglen.createwrappers('mx')
    msg = pack(data, meta)
    res = unwrap(msg)
    print(msg)
    print(res)
    checkRes(res, data, meta)

def test_msglen_proto6():
    data = "Grüße, Welt!"
    meta = dict(encoding='utf8',a=dict(f=1,g=2,h=3))

    pack, unwrap = msglen.createwrappers('mh')
    msg = pack(data, meta)
    print(msg)
    res = unwrap(msg)
    print(res)
    checkRes(res, data, meta)


if __name__ == "__main__":
    test_msglen2()
