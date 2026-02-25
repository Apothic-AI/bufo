"""ACP process bridge over JSON-RPC stdio."""

from __future__ import annotations

import asyncio
import contextlib
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable

from bufo.protocol.jsonrpc import JsonRpcConnection, JsonRpcFailure
from bufo.runtime_logging import get_runtime_logger

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
        self.session_id: str | None = None
        self.logger = get_runtime_logger()

    async def start(self) -> None:
        argv = shlex.split(self.command)
        self.logger.info("bridge.start", command=self.command, cwd=str(self.cwd))
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
        self.logger.debug("bridge.started")

    async def stop(self) -> None:
        self.logger.info("bridge.stop", session_id=self.session_id)
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
        self.logger.debug("bridge.stopped")

    async def initialize(self, client_name: str = "bufo", version: str = "0.0.1") -> Any:
        self.logger.debug("bridge.initialize", client_name=client_name, version=version)
        return await self._call("initialize", {"client": {"name": client_name, "version": version}})

    async def new_session(self, *, cwd: Path) -> Any:
        self.logger.info("bridge.new_session", cwd=str(cwd))
        result = await self._call("session/new", {"cwd": str(cwd)})
        if isinstance(result, dict):
            session_id = result.get("sessionId")
            if isinstance(session_id, str) and session_id:
                self.session_id = session_id
                self.logger.info("bridge.session.created", session_id=self.session_id)
        return result

    async def load_session(self, *, session_id: str, cwd: Path) -> Any:
        self.logger.info("bridge.load_session", session_id=session_id, cwd=str(cwd))
        result = await self._call("session/load", {"sessionId": session_id, "cwd": str(cwd)})
        self.session_id = session_id
        return result

    async def prompt(self, text: str, resources: list[dict[str, Any]] | None = None) -> Any:
        payload = self._build_prompt_payload(text, resources or [])
        self.logger.debug(
            "bridge.prompt",
            session_id=self.session_id,
            resource_count=len(resources or []),
            prompt_type="blocks",
        )
        try:
            return await self._call("session/prompt", payload)
        except JsonRpcFailure as exc:
            # Compatibility fallback for ACP servers expecting legacy string prompt payloads.
            if exc.code != -32602:
                raise
            self.logger.warning(
                "bridge.prompt.legacy_fallback",
                session_id=self.session_id,
                error_code=exc.code,
                error_message=exc.message,
            )
            legacy_payload: dict[str, Any] = {
                "sessionId": self.session_id,
                "prompt": text,
            }
            if resources:
                legacy_payload["resources"] = resources
            return await self._call("session/prompt", legacy_payload)

    async def set_mode(self, mode: str) -> Any:
        payload = {"sessionId": self.session_id, "modeId": mode}
        self.logger.debug("bridge.set_mode", session_id=self.session_id, mode=mode)
        try:
            return await self._call("session/set_mode", payload)
        except JsonRpcFailure as exc:
            # Compatibility fallback for ACP servers exposing a legacy mode endpoint.
            if exc.code != -32601:
                raise
            self.logger.warning("bridge.set_mode.legacy_fallback", session_id=self.session_id, mode=mode)
            return await self._call(
                "session/mode",
                {"sessionId": self.session_id, "mode": mode},
            )

    async def cancel(self) -> Any:
        self.logger.info("bridge.cancel", session_id=self.session_id)
        return await self._call("session/cancel", {"sessionId": self.session_id})

    async def _call(self, method: str, params: dict[str, Any]) -> Any:
        if self.connection is None:
            raise RuntimeError("Bridge not started")
        self.logger.debug("bridge.rpc.call", method=method, session_id=self.session_id)
        return await self.connection.call(method, params)

    async def _read_stdout_loop(self) -> None:
        assert self.process is not None
        assert self.process.stdout is not None
        while True:
            line = await self.process.stdout.readline()
            if not line:
                self.logger.debug("bridge.stdout.closed", session_id=self.session_id)
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
            self.logger.debug("bridge.stderr.line", session_id=self.session_id)
            await self.on_event(
                AgentEvent(
                    type="agent/stderr",
                    payload={"text": line.decode("utf-8", errors="replace")},
                )
            )

    async def _on_session_update(self, params: dict[str, Any] | list[Any] | None) -> dict[str, Any]:
        payload = params if isinstance(params, dict) else {"raw": params}
        session_id = payload.get("sessionId")
        if isinstance(session_id, str) and session_id:
            self.session_id = session_id
            self.logger.info("bridge.session.updated", session_id=self.session_id)
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

    def _build_prompt_payload(self, text: str, resources: list[dict[str, Any]]) -> dict[str, Any]:
        prompt_blocks: list[dict[str, Any]] = [{"type": "text", "text": text}]

        for resource in resources:
            resource_type = resource.get("type")
            path = str(resource.get("path", "resource"))
            mime = str(resource.get("mime", "application/octet-stream"))

            if resource_type == "text":
                prompt_blocks.append(
                    {
                        "type": "resource",
                        "resource": {
                            "uri": path,
                            "mimeType": mime,
                            "text": str(resource.get("text", "")),
                        },
                    }
                )
            elif resource_type == "binary":
                prompt_blocks.append(
                    {
                        "type": "resource",
                        "resource": {
                            "uri": path,
                            "mimeType": mime,
                            "blob": str(resource.get("base64", "")),
                        },
                    }
                )

        return {
            "sessionId": self.session_id,
            "prompt": prompt_blocks,
        }
