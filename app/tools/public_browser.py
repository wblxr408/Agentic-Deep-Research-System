"""Read-only browser transport: Chromium never resolves or contacts page hosts."""
from __future__ import annotations

import asyncio
import time
import socket
import threading

from app.channels.execution import HttpReader, public_url,ExecutionBudget
from app.channels.models import ChannelError
from app.execution_control import current_control,check_execution


class PublicBrowserGateway:
    def __init__(self, *, timeout: float = 45,max_requests:int=64):
        self.reader = HttpReader()
        self.deadline = time.monotonic() + timeout
        self.remaining_requests = max(0,int(max_requests))
        self.budget=ExecutionBudget(self.deadline,self.remaining_requests)
        self._request_lock=threading.Lock()
        self.remaining_bytes = 8 * 1024 * 1024
        self._lock = asyncio.Lock()
        self._slots = asyncio.Semaphore(4)
        self._prepared = {}
        self.primary_response=None
        self.cache_controls=[]
        self._deny_socket = None
        self._control=current_control()
        self._close_key='browser:'+str(id(self))

    def close(self):
        if self._control:self._control.remove_closer(self._close_key)
        if self._deny_socket is not None:
            self._deny_socket.close()
            self._deny_socket = None

    async def _read(self, url, method="GET"):
        check_execution()
        public_url(url)
        async with self._slots:
            async with self._lock:
                remaining = self.deadline - time.monotonic()
                limit = min(1024 * 1024, self.remaining_bytes)
                if remaining <= 0 or self.remaining_requests <= 0 or limit <= 0:
                    raise ChannelError("output_limit")
                self.remaining_requests -= 1
                self.remaining_bytes -= limit
            def take():
                with self._request_lock:return self.budget.take()
            response = await asyncio.to_thread(self.reader.read, url, method=method, timeout=remaining, max_bytes=limit,on_request=take)
            async with self._lock:
                self.remaining_bytes += limit - len(response.body)
                if response.headers.get('cache-control'):self.cache_controls.append(response.headers['cache-control'])
            return response

    async def prepare(self, url: str) -> str:
        response = await self._read(url)
        if response.status>=400:
            from app.channels.execution import response_error
            raise response_error(response)
        self.primary_response=response
        self._prepared[response.url] = response
        return response.url

    async def route(self, route):
        try:
            check_execution()
            request = route.request
            if request.method not in {"GET", "HEAD"}:
                raise ChannelError("read_only")
            response = self._prepared.pop(request.url, None) if request.method == "GET" else None
            if response is None:
                response = await self._read(request.url, request.method)
            check_execution()
            await route.fulfill(status=response.status, headers=response.headers, body=response.body)
        except (ChannelError, OSError, ValueError, RuntimeError):
            await route.abort("blockedbyclient")

    async def new_context(self, browser):
        # Reserve a non-listening socket for this context's deny proxy; never
        # assume an arbitrary localhost port has no forwarding service.
        # <-loopback> disables Chromium's implicit localhost proxy bypass.
        self._deny_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self._deny_socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        self._deny_socket.bind(("127.0.0.1", 0))
        port = self._deny_socket.getsockname()[1]
        context = None
        try:
            context = await browser.new_context(
                service_workers="block", accept_downloads=False,
                proxy={"server": f"http://127.0.0.1:{port}", "bypass": "<-loopback>"},
            )
            await context.route("**/*", self.route)
            if self._control:
                loop=asyncio.get_running_loop()
                def stop_context():
                    if not loop.is_closed():
                        asyncio.run_coroutine_threadsafe(context.close(),loop).result(timeout=3)
                self._control.add_closer(self._close_key,stop_context)
            if hasattr(context, "route_web_socket"):
                await context.route_web_socket("**/*", lambda websocket: websocket.close())
            return context
        except BaseException:
            if context is not None:
                await context.close()
            self.close()
            raise
