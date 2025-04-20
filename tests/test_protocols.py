import random
import os
import time

from msglen import msglen


def test_msglen1():
    assert True


def f_proto_wrap(proto, data, meta):
    inst = msglen.create(proto)

    wrap1 = inst.pack(data, meta)

    wrap2a = inst.packer(meta)(data)
    wrap2b = inst.packer()(data, meta)
    wrap2c = inst.packer(meta)(data, meta)

    assert wrap2a == wrap1
    assert wrap2b == wrap1
    assert wrap2c == wrap1

    return wrap1


def f_proto_unwrap(proto, msg):
    inst = msglen.create(proto)
    data, meta = inst.unwrap(msg)
    return data, meta


def test_msglen_protos_1():

    meta = dict(version=random.random(), data=time.time(), str=['a', 'b', 'c', 'äöü'])
    data = os.urandom(31)

    for pr in msglen.protocols:

        print(f'test protocol {pr}')

        msg = f_proto_wrap(pr, data, meta)
        data1, meta1 = f_proto_unwrap(pr, msg)

        assert data == data1
        assert meta == vars(meta1)

        print(pr, data, meta, msg)

def test_msglen_protos_2():

    meta = {}
    data = os.urandom(31)

    for pr in msglen.protocols:

        print(f'test protocol {pr}')

        msg = f_proto_wrap(pr, data, meta)
        data1, meta1 = f_proto_unwrap(pr, msg)

        assert data == data1
        assert meta == vars(meta1)


def test_msglen_protos_header1():

    meta = dict(version=random.random(), data=time.time(), str=['a', 'b', 'c', 'äöü'])
    data = os.urandom(31)

    mhead = msglen.MsglenL().metaHeader(meta)

    for pr in msglen.protocols:

        print(f'test protocol {pr}')

        inst = msglen.create(pr)

        msg = f_proto_wrap(pr, data, meta)

        header = msg[0:inst.totalHeaderSize]

        id, opts, hlen, mlen = inst.unpackHeader(header)

        print(pr)
        print(header)

        assert id == inst.msglenId
        assert hlen == len(mhead)
        assert mlen == len(data)

        assert msg[inst.totalHeaderSize] == b'{'[0]
        assert msg[inst.totalHeaderSize + hlen] == data[0]
        assert len(msg) == inst.totalHeaderSize + hlen + len(data)


def test_msglen_protos_header2():

    meta = {}
    data = os.urandom(31)

    mhead = msglen.MsglenL().metaHeader(meta)
    assert len(mhead) == 0

    for pr in msglen.protocols:

        print(f'test protocol {pr}')

        inst = msglen.create(pr)

        msg = f_proto_wrap(pr, data, meta)

        header = msg[0:inst.totalHeaderSize]

        id, opts, hlen, mlen = inst.unpackHeader(header)

        print(pr)
        print(header)

        assert id == inst.msglenId
        assert hlen == len(mhead)
        assert mlen == len(data)

        assert msg[inst.totalHeaderSize] == data[0]
        assert len(msg) == inst.totalHeaderSize + hlen + len(data)


def test_msglen_protocol_interop1():

    meta = dict(version=random.random(), data=time.time(), str=['a', 'b', 'c'])
    data = os.urandom(31)

    for prf in msglen.protocolFamilies:

        for prSend in msglen.protocolFamilies[prf]:
            for prRecv in msglen.protocolFamilies[prf]:

                print(f'test protocols {prSend} <-> {prRecv}')

                msg = f_proto_wrap(prSend, data, meta)
                data1, meta1 = f_proto_unwrap(prRecv, msg)

                assert data == data1
                assert meta == vars(meta1)


def test_msglen_protocol_interop2():

    meta = {}
    data = os.urandom(31)

    for prf in msglen.protocolFamilies:

        for prSend in msglen.protocolFamilies[prf]:
            for prRecv in msglen.protocolFamilies[prf]:

                print(f'test protocols {prSend} <-> {prRecv}')

                msg = f_proto_wrap(prSend, data, meta)
                data1, meta1 = f_proto_unwrap(prRecv, msg)

                assert data == data1
                assert meta == vars(meta1)


def test_msglen_protos_too_large_1():

    meta = {}
    data = os.urandom(2**24)

    for pr in msglen.protocols:

        print(f'test protocol {pr}')

        try:
            msg = f_proto_wrap(pr, data, meta)
            if pr in ['mx', 'mh', 'msgb', 'msgh', 'msgd']:
                # protocols should raise an exception when data len > 2^24
                print(f'has size limit: {pr}')
                assert False
        except msglen.SizeException as ex:
            msg = None
        except BaseException as ex:
            print(ex)
            assert False

        if msg:
            data1, meta1 = f_proto_unwrap(pr, msg)

            assert data == data1
            assert meta == vars(meta1)


if __name__ == "__main__":
    test_msglen2()
