from __future__ import annotations

import asyncio
import time
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, Mock

from bufo.agents.bridge import DEFAULT_CONTROL_RPC_TIMEOUT_S, AcpAgentBridge


async def _noop_event(_event: Any) -> None:  # noqa: ANN401
    return


class AcpBridgeTests(unittest.IsolatedAsyncioTestCase):
    async def test_new_session_captures_session_id(self) -> None:
        bridge = AcpAgentBridge("agent --acp", Path.cwd(), _noop_event)
        bridge._call = AsyncMock(return_value={"sessionId": "sess-1"})  # type: ignore[method-assign]

        await bridge.new_session(cwd=Path("/tmp"))

        self.assertEqual(bridge.session_id, "sess-1")
        bridge._call.assert_awaited_once_with(
            "session/new",
            {"cwd": "/tmp"},
            timeout=DEFAULT_CONTROL_RPC_TIMEOUT_S,
        )

    async def test_load_session_sets_active_session_id(self) -> None:
        bridge = AcpAgentBridge("agent --acp", Path.cwd(), _noop_event)
        bridge._call = AsyncMock(return_value={"ok": True})  # type: ignore[method-assign]

        await bridge.load_session(session_id="resume-123", cwd=Path("/tmp"))

        self.assertEqual(bridge.session_id, "resume-123")
        bridge._call.assert_awaited_once_with(
            "session/load",
            {"sessionId": "resume-123", "cwd": "/tmp"},
            timeout=DEFAULT_CONTROL_RPC_TIMEOUT_S,
        )

    async def test_prompt_payload_includes_session_id_and_blocks(self) -> None:
        bridge = AcpAgentBridge("agent --acp", Path.cwd(), _noop_event)
        bridge.session_id = "sess-abc"
        bridge._call = AsyncMock(return_value={"ok": True})  # type: ignore[method-assign]

        resources = [
            {
                "type": "text",
                "path": "notes.txt",
                "mime": "text/plain",
                "text": "hello",
            },
            {
                "type": "binary",
                "path": "image.png",
                "mime": "image/png",
                "base64": "AAAA",
            },
        ]

        await bridge.prompt("Hello", resources)

        bridge._call.assert_awaited_once()
        method, payload = bridge._call.await_args.args
        self.assertEqual(method, "session/prompt")
        self.assertEqual(payload["sessionId"], "sess-abc")
        self.assertEqual(payload["prompt"][0], {"type": "text", "text": "Hello"})
        self.assertEqual(payload["prompt"][1]["resource"]["uri"], "notes.txt")
        self.assertEqual(payload["prompt"][2]["resource"]["uri"], "image.png")

    async def test_session_update_can_backfill_session_id(self) -> None:
        events: list[dict[str, Any]] = []

        async def on_event(event: Any) -> None:  # noqa: ANN401
            events.append(event.payload)

        bridge = AcpAgentBridge("agent --acp", Path.cwd(), on_event)

        result = await bridge._on_session_update({"sessionId": "sid-x", "events": []})

        self.assertEqual(result, {"ok": True})
        self.assertEqual(bridge.session_id, "sid-x")
        self.assertEqual(events[0]["sessionId"], "sid-x")

    async def test_new_session_then_prompt_sends_required_session_id(self) -> None:
        """Regression guard for strict ACP servers that require sessionId."""

        bridge = AcpAgentBridge("agent --acp", Path.cwd(), _noop_event)

        async def fake_call(method: str, params: dict[str, Any], timeout: float | None = None) -> dict[str, Any]:
            if method == "session/new":
                self.assertEqual(params, {"cwd": "/tmp"})
                self.assertEqual(timeout, DEFAULT_CONTROL_RPC_TIMEOUT_S)
                return {"sessionId": "strict-session-1", "modes": []}

            if method == "session/prompt":
                # This was the bug: prompt calls were missing sessionId.
                self.assertEqual(params.get("sessionId"), "strict-session-1")
                self.assertIsInstance(params.get("prompt"), list)
                self.assertEqual(params["prompt"][0], {"type": "text", "text": "Hello"})
                self.assertIsNone(timeout)
                return {"stopReason": "end_turn"}

            self.fail(f"Unexpected RPC method: {method}")
            return {}

        bridge._call = AsyncMock(side_effect=fake_call)  # type: ignore[method-assign]

        new_result = await bridge.new_session(cwd=Path("/tmp"))
        prompt_result = await bridge.prompt("Hello")

        self.assertEqual(bridge.session_id, "strict-session-1")
        self.assertEqual(new_result.get("sessionId"), "strict-session-1")
        self.assertEqual(prompt_result.get("stopReason"), "end_turn")
        self.assertEqual(bridge._call.await_count, 2)

    async def test_initialize_fails_fast_if_agent_process_exits(self) -> None:
        bridge = AcpAgentBridge("sh -c 'echo bridge-failed >&2; exit 2'", Path.cwd(), _noop_event)
        started = time.monotonic()
        await bridge.start()
        try:
            with self.assertRaises(RuntimeError) as ctx:
                await bridge.initialize()
        finally:
            await bridge.stop()

        self.assertLess(time.monotonic() - started, 2.0)
        self.assertIn("exited with code 2", str(ctx.exception))

    async def test_call_raises_runtime_error_when_connection_cancelled_after_process_exit(self) -> None:
        bridge = AcpAgentBridge("agent --acp", Path.cwd(), _noop_event)
        bridge.connection = Mock()
        bridge.connection.call = AsyncMock(side_effect=asyncio.CancelledError())  # type: ignore[attr-defined]
        bridge.process = Mock(returncode=3)
        bridge._stderr_tail.append("unexpected argument")  # noqa: SLF001

        with self.assertRaises(RuntimeError) as ctx:
            await bridge._call("initialize", {"client": {"name": "bufo"}})  # noqa: SLF001

        self.assertIn("exited with code 3", str(ctx.exception))
        self.assertIn("unexpected argument", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
