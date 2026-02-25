"""ACP process bridge over JSON-RPC stdio."""

from __future__ import annotations

import asyncio
import contextlib
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable

from bufo.protocol.jsonrpc import JsonRpcConnection

EventHandler = Callable[["AgentEvent"], Awaitable[None]]


@dataclass(slots=True)
class AgentEvent:
    type: str
    payload: dict[str, Any]


class AcpAgentBridge:
    """Bidirectional ACP bridge.

    This implements the expected client-to-agent calls and accepts
    agent-to-client callbacks for session updates, permission asks,
    filesystem operations, and terminal operations.
    """

    def __init__(self, command: str, cwd: Path, on_event: EventHandler) -> None:
        self.command = command
        self.cwd = cwd
        self.on_event = on_event
        self.process: asyncio.subprocess.Process | None = None
        self.connection: JsonRpcConnection | None = None
        self._reader_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        argv = shlex.split(self.command)
        self.process = await asyncio.create_subprocess_exec(
            *argv,
            cwd=str(self.cwd),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        async def sender(line: str) -> None:
            assert self.process is not None
            assert self.process.stdin is not None
            self.process.stdin.write(line.encode("utf-8") + b"\n")
            await self.process.stdin.drain()

        self.connection = JsonRpcConnection(sender)
        self.connection.register_method("session/update", self._on_session_update)
        self.connection.register_method("permission/request", self._on_permission_request)
        self.connection.register_method("filesystem/read", self._on_filesystem_read)
        self.connection.register_method("filesystem/write", self._on_filesystem_write)
        self.connection.register_method("terminal/create", self._on_terminal)
        self.connection.register_method("terminal/output", self._on_terminal)
        self.connection.register_method("terminal/kill", self._on_terminal)
        self.connection.register_method("terminal/release", self._on_terminal)
        self.connection.register_method("terminal/wait_for_exit", self._on_terminal)

        self._reader_task = asyncio.create_task(self._read_stdout_loop())
        asyncio.create_task(self._read_stderr_loop())

    async def stop(self) -> None:
        if self.connection is not None:
            self.connection.shutdown()

        if self._reader_task is not None:
            self._reader_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._reader_task
            self._reader_task = None

        if self.process is not None and self.process.returncode is None:
            self.process.terminate()
            with contextlib.suppress(ProcessLookupError):
                await asyncio.wait_for(self.process.wait(), timeout=2)
        self.process = None

    async def initialize(self, client_name: str = "bufo", version: str = "0.0.1") -> Any:
        return await self._call("initialize", {"client": {"name": client_name, "version": version}})

    async def new_session(self, *, cwd: Path) -> Any:
        return await self._call("session/new", {"cwd": str(cwd)})

    async def load_session(self, *, session_id: str, cwd: Path) -> Any:
        return await self._call("session/load", {"sessionId": session_id, "cwd": str(cwd)})

    async def prompt(self, text: str, resources: list[dict[str, Any]] | None = None) -> Any:
        payload: dict[str, Any] = {"prompt": text}
        if resources:
            payload["resources"] = resources
        return await self._call("session/prompt", payload)

    async def set_mode(self, mode: str) -> Any:
        return await self._call("session/mode", {"mode": mode})

    async def cancel(self) -> Any:
        return await self._call("session/cancel", {})

    async def _call(self, method: str, params: dict[str, Any]) -> Any:
        if self.connection is None:
            raise RuntimeError("Bridge not started")
        return await self.connection.call(method, params)

    async def _read_stdout_loop(self) -> None:
        assert self.process is not None
        assert self.process.stdout is not None
        while True:
            line = await self.process.stdout.readline()
            if not line:
                break
            if self.connection is None:
                continue
            await self.connection.feed(line.decode("utf-8", errors="replace"))

    async def _read_stderr_loop(self) -> None:
        assert self.process is not None
        assert self.process.stderr is not None
        while True:
            line = await self.process.stderr.readline()
            if not line:
                break
            await self.on_event(
                AgentEvent(
                    type="agent/stderr",
                    payload={"text": line.decode("utf-8", errors="replace")},
                )
            )

    async def _on_session_update(self, params: dict[str, Any] | list[Any] | None) -> dict[str, Any]:
        payload = params if isinstance(params, dict) else {"raw": params}
        await self.on_event(AgentEvent(type="session/update", payload=payload))
        return {"ok": True}

    async def _on_permission_request(self, params: dict[str, Any] | list[Any] | None) -> dict[str, Any]:
        payload = params if isinstance(params, dict) else {"raw": params}
        await self.on_event(AgentEvent(type="permission/request", payload=payload))
        return {"decision": "reject_once"}

    async def _on_filesystem_read(self, params: dict[str, Any] | list[Any] | None) -> dict[str, Any]:
        payload = params if isinstance(params, dict) else {}
        rel_path = str(payload.get("path", ""))
        file_path = (self.cwd / rel_path).resolve()

        try:
            file_path.relative_to(self.cwd.resolve())
        except ValueError:
            return {"ok": False, "error": "path outside project"}

        if not file_path.exists():
            return {"ok": False, "error": "not found"}

        return {
            "ok": True,
            "path": rel_path,
            "content": file_path.read_text(encoding="utf-8", errors="replace"),
        }

    async def _on_filesystem_write(self, params: dict[str, Any] | list[Any] | None) -> dict[str, Any]:
        payload = params if isinstance(params, dict) else {}
        rel_path = str(payload.get("path", ""))
        content = str(payload.get("content", ""))
        file_path = (self.cwd / rel_path).resolve()

        try:
            file_path.relative_to(self.cwd.resolve())
        except ValueError:
            return {"ok": False, "error": "path outside project"}

        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
        await self.on_event(AgentEvent(type="filesystem/write", payload={"path": rel_path}))
        return {"ok": True}

    async def _on_terminal(self, params: dict[str, Any] | list[Any] | None) -> dict[str, Any]:
        payload = params if isinstance(params, dict) else {"raw": params}
        await self.on_event(AgentEvent(type="terminal/request", payload=payload))
        return {"ok": False, "error": "terminal adapter not wired"}
