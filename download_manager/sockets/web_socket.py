import asyncio
import socket
import aiohttp


class CustomSocket:
    def __init__(self):
        self.sock = None

    def __call__(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # 1 MB receive buffer
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1048576)
        # 1 MB send buffer
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 1048576)
        return self.sock


async def create_custom_connector():
    loop = asyncio.get_event_loop()
    conn = aiohttp.TCPConnector(loop=loop)

    async def socket_factory(*args, **kwargs):
        return CustomSocket()()

    conn._factory = socket_factory
    return conn
