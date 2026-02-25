from __future__ import annotations

import unittest

from bufo.agents.session_updates import normalize_session_update


class SessionUpdateMappingTests(unittest.TestCase):
    def test_maps_chunk_and_completed_response(self) -> None:
        events = normalize_session_update(
            {
                "events": [
                    {"type": "response.chunk", "text": "hello"},
                    {"type": "response.completed", "text": "done"},
                ]
            }
        )
        lines = [event.text for event in events]
        self.assertIn("hello", lines[0])
        self.assertIn("Agent:", lines[1])

    def test_maps_thought_and_plan(self) -> None:
        events = normalize_session_update(
            {
                "events": [
                    {"type": "thought", "text": "considering"},
                    {"type": "plan.updated", "items": ["step1", "step2"]},
                ]
            }
        )
        lines = "\n".join(event.text for event in events)
        self.assertIn("Thought", lines)
        self.assertIn("Plan", lines)
        self.assertIn("step1", lines)

    def test_maps_tool_lifecycle(self) -> None:
        events = normalize_session_update(
            {
                "events": [
                    {"type": "tool_call.started", "name": "lint"},
                    {"type": "tool_call.delta", "name": "lint", "delta": "running"},
                    {"type": "tool_call.completed", "name": "lint", "output": "ok"},
                ]
            }
        )
        lines = "\n".join(event.text for event in events)
        self.assertIn("lint", lines)
        self.assertIn("started", lines)
        self.assertIn("completed", lines)

    def test_maps_mode_and_slash_commands(self) -> None:
        events = normalize_session_update(
            {
                "events": [
                    {"type": "mode.updated", "mode": "shell"},
                    {"type": "slash_commands.updated", "commands": ["/help", "/clear"]},
                ]
            }
        )
        lines = "\n".join(event.text for event in events)
        self.assertIn("Mode", lines)
        self.assertIn("shell", lines)
        self.assertIn("Slash Commands", lines)

    def test_maps_state_reactive_event(self) -> None:
        events = normalize_session_update(
            {"events": [{"type": "session.state", "state": "busy"}]}
        )
        self.assertEqual(events[0].state, "busy")
        self.assertIn("state -> busy", events[0].text)

    def test_legacy_payload_compatibility(self) -> None:
        events = normalize_session_update(
            {
                "response": "legacy response",
                "thought": "legacy thought",
                "plan": ["a", "b"],
                "state": "idle",
            }
        )
        lines = "\n".join(event.text for event in events)
        self.assertIn("legacy response", lines)
        self.assertIn("legacy thought", lines)
        self.assertIn("Plan", lines)
        self.assertTrue(any(event.state == "idle" for event in events))


if __name__ == "__main__":
    unittest.main()
