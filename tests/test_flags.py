import sys

sys.path += ['.']

from msglen import msglen

from test_msglen import checkRes

def test_msglen_proto6():
    data = "Test"

    meta_enc = dict(encoding='utf8')

    meta = meta_enc | dict(a=dict(f=1,g=2,h=3),b=3,c=0)

    inst = msglen.create('mx')
    pack, unwrap = inst.wrappers(dict(encoding='utf8'))

    def roundtrip(data, meta, flags=0):
        msg = pack(data, meta, flags)
        print('msg', msg)
        res = unwrap(msg)
        print('res', res)
        return res

    res = roundtrip(data, meta)
    checkRes(res, data, meta)

    meta |= {'set-flags-map': ['a', 'b', 'c', 'd']}
    res = roundtrip(data, meta)
    checkRes(res, data, meta)

    print(inst._flagsMap)
    print(inst._meta)
    print(inst.dictFromFlags(3))

    meta = meta_enc
    res = roundtrip(data, meta, 3)
    checkRes(res, data, meta|inst.dictFromFlags(3))

    res = roundtrip(data, meta, 127)
    checkRes(res, data, meta|inst.dictFromFlags(127))

    res = roundtrip(data, meta, 0b10101010)
    checkRes(res, data, meta|inst.dictFromFlags(0b10101010))


if __name__ == "__main__":
    test_msglen2()
