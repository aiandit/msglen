import asyncio

from msglen import msglen

def test_msglen1():
    assert True

msglend = msglen.MsglenD()
msglenb = msglen.MsglenB()
msglenl = msglen.MsglenL()

msglenProto = msglend

async def f_test_msglen2_read():
    maxconnect = 3
    async def connected(reader, writer):
        nonlocal maxconnect
        msglenProto.trace = 1
        msgread = msglenProto.reader(reader.read)
        msgwrite = msglenb.writer(writer, dict(server='Test123', encoding='utf8'))
        while True:
            msg, meta = await msgread()
            if msg is None and meta is None:
                print(f'server: Client disconnected')
                break
            print(f'server: Got client message [{meta}]: {msg}')
            msgwrite(msg)
        writer.close()
        print('server: client task done')
    server = await asyncio.start_server(connected, port=11001)
    print('server: started')
    return server

async def f_test_msglen2_write():
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


async def atest_msglen2():
    server = await f_test_msglen2_read()
#    serve = asyncio.create_task(server.serve_forever())
    clients = [f_test_msglen2_write() for i in range(3)]
    cres = await asyncio.gather(*clients)
    print('clients done')
    if False:
        sres = await server.serve_forever()
        print('server done')
    else:
        sres = await asyncio.sleep(1)
        print('server test exit')

def test_msglen2():
    asyncio.run(atest_msglen2())
    assert True

if __name__ == "__main__":
    test_msglen2()
