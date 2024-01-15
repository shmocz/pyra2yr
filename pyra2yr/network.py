import asyncio
import logging
import traceback
from typing import Any, Dict

import aiohttp
from ra2yrproto import core

from .async_container import AsyncDict

debug = logging.debug


async def async_log_exceptions(coro):
    try:
        return await coro
    except Exception:
        logging.error("%s", traceback.format_exc())


def logged_task(coro):
    return asyncio.create_task(async_log_exceptions(coro))


class WebSocketClient:
    def __init__(self, uri: str, timeout=5.0):
        self.uri = uri
        self.in_queue = asyncio.Queue()
        self.out_queue = asyncio.Queue()
        self.timeout = timeout
        self.task = None
        self._tries = 15
        self._connect_delay = 1.0
        self._lock = asyncio.Lock()

    def open(self):
        self.task = asyncio.create_task(async_log_exceptions(self.main()))

    async def close(self):
        await self.in_queue.put(None)
        await self.task

    async def send_message(self, m: str) -> aiohttp.WSMessage:
        async with self._lock:
            await self.in_queue.put(m)
            return await self.out_queue.get()

    async def main(self):
        # send the initial message
        msg = await self.in_queue.get()
        for i in range(self._tries):
            try:
                debug("connect, try %d %d", i, self._tries)
                await self._main_session(msg)
                break
            except asyncio.exceptions.CancelledError:
                break
            except Exception:
                logging.warning("connect failed (try %d/%d)", i + 1, self._tries)
                if i + 1 == self._tries:
                    raise
                await asyncio.sleep(self._connect_delay)

    async def _main_session(self, msg):
        async with aiohttp.ClientSession() as session:
            debug("connecting to %s %s msg %s", self.uri, session, msg)
            async with session.ws_connect(self.uri, autoclose=False) as ws:
                debug("connected to %s", self.uri)
                await ws.send_bytes(msg)

                async for msg in ws:
                    await self.out_queue.put(msg)
                    in_msg = await self.in_queue.get()
                    if in_msg is None:
                        await ws.close()
                        break
                    await ws.send_bytes(in_msg)
            self.in_queue = None
            self.out_queue = None
            debug("close _main_session")


class DualClient:
    def __init__(self, host: str, port: int, timeout: float = 5.0):
        self.host = host
        self.port = port
        self.conns: Dict[str, WebSocketClient] = {}
        self.uri = f"http://{host}:{port}"
        self.queue_id = -1
        self.timeout = timeout
        self.results = AsyncDict()
        self.in_queue = asyncio.Queue()
        self._poll_task = None
        self._stop = asyncio.Event()
        # FIXME: ugly
        self._queue_set = asyncio.Event()

    def connect(self):
        for k in ["command", "poll"]:
            self.conns[k] = WebSocketClient(self.uri, self.timeout)
            self.conns[k].open()
            debug("opened %s", k)
        self._poll_task = asyncio.create_task(async_log_exceptions(self._poll_loop()))

    def make_command(self, msg=None, command_type=None) -> core.Command:
        c = core.Command()
        c.command_type = command_type
        c.command.Pack(msg)
        return c

    def make_poll_blocking(self, queue_id, timeout) -> core.Command:
        c = core.PollResults()
        c.args.queue_id = queue_id
        c.args.timeout = timeout
        return self.make_command(c, core.POLL_BLOCKING)

    def parse_response(self, msg: str) -> core.Response:
        res = core.Response()
        res.ParseFromString(msg)
        return res

    async def run_client_command(self, c: Any) -> core.RunCommandAck:
        msg = await self.conns["command"].send_message(
            self.make_command(c, core.CLIENT_COMMAND).SerializeToString()
        )

        res = self.parse_response(msg.data)
        ack = core.RunCommandAck()
        if not res.body.Unpack(ack):
            raise RuntimeError(f"failed to unpack ack: {res}")
        return ack

    # TODO: could wrap this into task and cancel at exit
    async def exec_command(self, c: Any, timeout: float = None):
        """Execute command and return the result when it's polled back.

        Parameters
        ----------
        c : Any
            Command protobuf object
        timeout : float, optional
            Poll timeout, by default None

        Returns
        -------
        Any
            Command result protobuf object.

        Raises
        ------
        asyncio.exceptions.TimeoutError
            If results were not available within timeout.
        """
        msg = await self.run_client_command(c)
        if self.queue_id < 0:
            self.queue_id = msg.queue_id
            self._queue_set.set()
        # wait until results polled
        return await self.results.get_item(msg.id, timeout=timeout, remove=True)

    async def _poll_loop(self):
        await self._queue_set.wait()
        while not self._stop.is_set():
            msg = await self.conns["poll"].send_message(
                self.make_poll_blocking(
                    self.queue_id, int(self.timeout * 1000)
                ).SerializeToString()
            )
            res = self.parse_response(msg.data)
            cc = core.PollResults()
            if not res.body.Unpack(cc):
                raise RuntimeError(f"failed to unpack poll results {cc}")
            for x in cc.result.results:
                await self.results.put_item(x.command_id, x)

    async def stop(self):
        self._stop.set()
        # TODO: Cancel this immediately. Currently waits up to self.timeout seconds.
        await self._poll_task
        await self.conns["command"].close()
        await self.conns["poll"].close()
