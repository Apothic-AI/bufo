"""Minimal async JSON-RPC 2.0 connection utilities."""

from __future__ import annotations

import asyncio
import json
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

JsonDict = dict[str, Any]
MethodHandler = Callable[[dict[str, Any] | list[Any] | None], Awaitable[Any]]
Sender = Callable[[str], Awaitable[None]]


@dataclass(slots=True)
class JsonRpcFailure(Exception):
    code: int
    message: str
    data: Any | None = None

    def __str__(self) -> str:
        return f"JSON-RPC error {self.code}: {self.message}"


class JsonRpcConnection:
    def __init__(self, sender: Sender) -> None:
        self._sender = sender
        self._next_id = 1
        self._pending: dict[int, asyncio.Future[Any]] = {}
        self._methods: dict[str, MethodHandler] = {}

    def register_method(self, name: str, handler: MethodHandler) -> None:
        self._methods[name] = handler

    async def call(
        self,
        method: str,
        params: dict[str, Any] | list[Any] | None = None,
        *,
        timeout: float | None = None,
    ) -> Any:
        request_id = self._next_id
        self._next_id += 1

        payload: JsonDict = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
        }
        if params is not None:
            payload["params"] = params

        fut: asyncio.Future[Any] = asyncio.get_running_loop().create_future()
        self._pending[request_id] = fut

        await self._sender(json.dumps(payload, separators=(",", ":")))

        if timeout is None:
            return await fut
        return await asyncio.wait_for(fut, timeout=timeout)

    async def notify(
        self,
        method: str,
        params: dict[str, Any] | list[Any] | None = None,
    ) -> None:
        payload: JsonDict = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            payload["params"] = params
        await self._sender(json.dumps(payload, separators=(",", ":")))

    async def feed(self, raw_line: str) -> None:
        if not raw_line.strip():
            return

        try:
            message = json.loads(raw_line)
        except json.JSONDecodeError:
            return

        if "method" in message:
            await self._handle_request(message)
            return
        if "id" in message:
            self._handle_response(message)

    async def _handle_request(self, message: JsonDict) -> None:
        method = str(message.get("method", ""))
        params = message.get("params")
        request_id = message.get("id")

        handler = self._methods.get(method)
        if handler is None:
            if request_id is not None:
                await self._send_error(request_id, -32601, f"Method not found: {method}")
            return

        try:
            result = await handler(params)
        except JsonRpcFailure as exc:
            if request_id is not None:
                await self._send_error(request_id, exc.code, exc.message, exc.data)
            return
        except Exception as exc:  # pragma: no cover - defensive edge path
            if request_id is not None:
                await self._send_error(request_id, -32000, str(exc))
            return

        if request_id is not None:
            await self._sender(
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "result": result,
                    },
                    separators=(",", ":"),
                )
            )

    def _handle_response(self, message: JsonDict) -> None:
        request_id = message.get("id")
        if not isinstance(request_id, int):
            return

        fut = self._pending.pop(request_id, None)
        if fut is None:
            return

        if "error" in message:
            error = message["error"] or {}
            fut.set_exception(
                JsonRpcFailure(
                    code=int(error.get("code", -32000)),
                    message=str(error.get("message", "Unknown error")),
                    data=error.get("data"),
                )
            )
            return

        fut.set_result(message.get("result"))

    async def _send_error(self, request_id: int, code: int, message: str, data: Any | None = None) -> None:
        payload: JsonDict = {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": code, "message": message},
        }
        if data is not None:
            payload["error"]["data"] = data

        await self._sender(json.dumps(payload, separators=(",", ":")))

    def shutdown(self) -> None:
        for fut in self._pending.values():
            if not fut.done():
                fut.cancel()
        self._pending.clear()

    def batch(self) -> "RequestBatch":
        return RequestBatch(self)


@dataclass(slots=True)
class OutboundCall:
    method: str
    params: dict[str, Any] | list[Any] | None = None


class RequestBatch(AbstractAsyncContextManager["RequestBatch"]):
    """Collect one or more outbound calls and send them in sequence on exit."""

    def __init__(self, connection: JsonRpcConnection) -> None:
        self.connection = connection
        self.calls: list[OutboundCall] = []
        self.results: list[Any] = []

    def add(self, method: str, params: dict[str, Any] | list[Any] | None = None) -> "RequestBatch":
        self.calls.append(OutboundCall(method=method, params=params))
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool | None:  # type: ignore[override]
        if exc is not None:
            return None
        for call in self.calls:
            self.results.append(await self.connection.call(call.method, call.params))
        return None


def api_method(name: str) -> Callable[[Callable[..., dict[str, Any] | list[Any] | None]], Callable[..., Awaitable[Any]]]:
    """Decorator for declaring outbound RPC wrappers on a class with `.connection`."""

    def decorator(fn: Callable[..., dict[str, Any] | list[Any] | None]) -> Callable[..., Awaitable[Any]]:
        async def wrapper(self, *args: Any, **kwargs: Any) -> Any:
            params = fn(self, *args, **kwargs)
            return await self.connection.call(name, params)

        wrapper.__name__ = fn.__name__
        wrapper.__doc__ = fn.__doc__
        return wrapper

    return decorator
