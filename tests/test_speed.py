import os
import sys
import asyncio
import struct
import random
import math
import time
import binascii

sys.path += ['.']

from msglen import msglen

from test_msglen import checkRes

def test_msglen_proto6():
    data = "Test"

    meta_enc = dict(encoding='utf8')

    meta = dict(a=dict(f=1,g=2,h=3),b=3,c=0)
    #meta = {}

    inst = msglen.create('mx')
    #inst.enableFlagsMap = False
    pack, unwrap = inst.wrappers(meta)

    def roundtrip(data, meta={}, flags=0):
        msg = pack(data, meta, flags)
        res = unwrap(msg)
        return res


    N = int(1e4)
    L = 12

    msgs = [ binascii.b2a_base64(os.urandom(int(math.ceil(random.random()*L)))) for i in range(N) ]


    def timeit(func):
        def inner(*args, **kw):
            t0 = time.time()
            res = func(*args, **kw)
            t1 = time.time()
            return (t1 - t0), res
        return inner

    def allMsgs(func):
        def inner(msgs):
            return [ func(m) for m in msgs ]
        return inner


    tpack = timeit(allMsgs(pack))(msgs)
    packed = tpack[1]

    print(msgs[0:3])
    print(packed[0:3])

    tunwrap = timeit(allMsgs(unwrap))(packed)
    tround = timeit(allMsgs(roundtrip))(msgs)

    print(N, tpack[0], tpack[0]/N)
    print(N, tunwrap[0], tunwrap[0]/N)
    print(N, tround[0], tround[0]/N)

    for i in range(N):
        assert msgs[i] == tunwrap[1][i][0]
        assert msgs[i] == tround[1][i][0]

if __name__ == "__main__":
    test_msglen2()
