from __future__ import annotations

import asyncio
import tempfile
import threading
import unittest
import warnings
from pathlib import Path
from typing import Any
from unittest.mock import patch

from textual.widgets import Button, Input, OptionList, Tree

from bufo.agents.bridge import AgentEvent
from bufo.agents.schema import AgentDescriptor
from bufo.app import BufoApp
from bufo.messages import LaunchAgent, ResumeAgent
from bufo.screens.modals import PermissionModal
from bufo.screens.sessions import SessionsScreen
from bufo.screens.settings import SettingsScreen
from bufo.screens.store import StoreScreen
from bufo.widgets.conversation import Conversation
from bufo.widgets.selectable_rich_log import SelectableRichLog

warnings.filterwarnings("ignore", category=ResourceWarning)
warnings.filterwarnings("ignore", category=DeprecationWarning, module=r"pathspec.*")


class FakeWatchManager:
    def __init__(self) -> None:
        self._callbacks: dict[Path, Any] = {}

    def watch(self, path: Path, callback) -> None:  # noqa: ANN001
        self._callbacks[path.resolve()] = callback

    def unwatch(self, path: Path, callback=None) -> None:  # noqa: ANN001, ARG002
        self._callbacks.pop(path.resolve(), None)

    def emit(self, path: Path) -> None:
        callback = self._callbacks.get(path.resolve())
        if callback is not None:
            thread = threading.Thread(target=callback)
            thread.start()
            thread.join(timeout=1)

    def close(self) -> None:
        self._callbacks.clear()


class FakeBridge:
    instances: list["FakeBridge"] = []

    def __init__(self, command: str, cwd: Path, on_event) -> None:  # noqa: ANN001
        self.command = command
        self.cwd = cwd
        self.on_event = on_event
        self.prompts: list[tuple[str, list[dict[str, Any]]]] = []
        self.modes: list[str] = []
        self.started = False
        self.stopped = False
        FakeBridge.instances.append(self)

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.stopped = True

    async def initialize(self, client_name: str = "bufo", version: str = "0.0.1") -> dict[str, Any]:
        return {"ok": True, "client": client_name, "version": version}

    async def new_session(self, *, cwd: Path) -> dict[str, Any]:
        await self.on_event(
            AgentEvent(
                type="session/update",
                payload={
                    "events": [
                        {"type": "mode.updated", "mode": "agent"},
                        {"type": "slash_commands.updated", "commands": ["/help", "/clear"]},
                        {"type": "session.state", "state": "idle"},
                    ]
                },
            )
        )
        return {"ok": True, "cwd": str(cwd)}

    async def load_session(self, *, session_id: str, cwd: Path) -> dict[str, Any]:
        await self.on_event(
            AgentEvent(
                type="session/update",
                payload={
                    "events": [
                        {
                            "type": "response.completed",
                            "text": f"resumed {session_id}",
                        },
                        {"type": "session.state", "state": "idle"},
                    ]
                },
            )
        )
        return {"ok": True, "sessionId": session_id, "cwd": str(cwd)}

    async def prompt(self, text: str, resources: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        resources = resources or []
        self.prompts.append((text, resources))

        if "ask-permission" in text:
            await self.on_event(
                AgentEvent(
                    type="permission/request",
                    payload={"message": "approve file write?", "kind": "write"},
                )
            )

        if "lifecycle" in text:
            await self.on_event(
                AgentEvent(
                    type="session/update",
                    payload={
                        "events": [
                            {"type": "session.state", "state": "busy"},
                            {"type": "tool_call.started", "name": "build", "id": "t1"},
                            {"type": "tool_call.delta", "name": "build", "delta": "50%"},
                            {"type": "tool_call.completed", "name": "build", "output": "ok"},
                            {"type": "response.completed", "text": "done"},
                            {"type": "session.state", "state": "idle"},
                        ]
                    },
                )
            )
        else:
            await self.on_event(
                AgentEvent(
                    type="session/update",
                    payload={
                        "events": [
                            {"type": "session.state", "state": "busy"},
                            {"type": "response.chunk", "text": "chunk-1"},
                            {"type": "thought", "text": "thinking"},
                            {"type": "plan.updated", "items": ["a", "b"]},
                            {
                                "type": "response.completed",
                                "text": f"echo:{text}",
                            },
                            {"type": "session.state", "state": "idle"},
                        ]
                    },
                )
            )

        return {"ok": True}

    async def set_mode(self, mode: str) -> dict[str, Any]:
        self.modes.append(mode)
        return {"ok": True, "mode": mode}

    async def cancel(self) -> dict[str, Any]:
        return {"ok": True}


class BufoAppE2ETests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        FakeBridge.instances.clear()
        self.tmp = tempfile.TemporaryDirectory()
        self.project_root = Path(self.tmp.name)
        (self.project_root / "note.txt").write_text("hello resource", encoding="utf-8")

    async def asyncTearDown(self) -> None:
        self.tmp.cleanup()

    def _make_app(self, **kwargs: Any) -> BufoApp:
        return BufoApp(
            project_root=self.project_root,
            force_store=True,
            bridge_factory=FakeBridge,
            enable_watchers=False,
            check_updates=False,
            **kwargs,
        )

    async def _launch_first_agent(self, app: BufoApp, pilot, resume_id: str | None = None) -> Conversation:  # noqa: ANN001
        identity = app.catalog[0].identity
        if resume_id is None:
            app.post_message(LaunchAgent(agent_identity=identity, project_root=self.project_root))
        else:
            app.post_message(
                ResumeAgent(
                    agent_identity=identity,
                    agent_session_id=resume_id,
                    project_root=self.project_root,
                )
            )
        await pilot.pause(0.25)
        return app.screen.query_one(Conversation)

    async def _submit_prompt(self, conversation: Conversation, text: str, pilot) -> None:  # noqa: ANN001
        prompt = conversation.query_one("#prompt", Input)
        prompt.value = text
        await prompt.action_submit()
        await pilot.pause(0.25)

    async def _press_permission(self, app: BufoApp, button_id: str, pilot) -> None:  # noqa: ANN001
        for _ in range(25):
            if isinstance(app.screen, PermissionModal):
                app.screen.dismiss(button_id)
                await asyncio.sleep(0.1)
                return
            await asyncio.sleep(0.05)
        raise AssertionError(f"Permission modal button {button_id} not found")

    async def test_store_to_session_launch_flow(self) -> None:
        app = self._make_app()
        async with app.run_test() as pilot:
            conversation = await self._launch_first_agent(app, pilot)
            self.assertTrue(app.current_mode.startswith("session-"))
            self.assertEqual(len(app.session_tracker.all()), 1)
            self.assertTrue(any("Agent bridge connected" in line for line in conversation.timeline_entries))

    async def test_unsupported_protocol_agent_is_rejected_without_launching_session(self) -> None:
        app = self._make_app()
        app.catalog = [
            AgentDescriptor(
                identity="mcp-only-agent",
                name="MCP Agent",
                protocol="mcp",
                description="MCP-only test agent",
                run_command={"default": "mcp-agent"},
            )
        ]
        with patch.object(app, "notify") as notify_mock:
            async with app.run_test() as pilot:
                app.post_message(
                    LaunchAgent(agent_identity="mcp-only-agent", project_root=self.project_root)
                )
                await pilot.pause(0.2)

        self.assertEqual(len(app.session_tracker.all()), 0)
        notify_mock.assert_called()
        args, kwargs = notify_mock.call_args
        self.assertIn("supports ACP agents only", args[0])
        self.assertEqual(kwargs.get("severity"), "error")

    async def test_resume_reuses_existing_session_mode(self) -> None:
        app = self._make_app()
        async with app.run_test() as pilot:
            await self._launch_first_agent(app, pilot, resume_id="abc-123")
            self.assertEqual(len(app.session_tracker.all()), 1)
            initial_mode = app.current_mode

            app.post_message(
                ResumeAgent(
                    agent_identity=app.catalog[0].identity,
                    agent_session_id="abc-123",
                    project_root=self.project_root,
                )
            )
            await pilot.pause(0.2)

            self.assertEqual(len(app.session_tracker.all()), 1)
            self.assertEqual(app.current_mode, initial_mode)

    async def test_open_settings_modal(self) -> None:
        app = self._make_app()
        async with app.run_test() as pilot:
            app.action_open_settings()
            await pilot.pause(0.1)
            self.assertIsInstance(app.screen, SettingsScreen)
            app.screen.query_one("#close", Button).press()
            await pilot.pause(0.1)

    async def test_open_sessions_modal(self) -> None:
        app = self._make_app()
        async with app.run_test() as pilot:
            await self._launch_first_agent(app, pilot)
            app.action_open_sessions()
            await pilot.pause(0.1)
            self.assertIsInstance(app.screen, SessionsScreen)
            app.screen.query_one("#close", Button).press()
            await pilot.pause(0.1)

    async def test_prompt_agent_flow_renders_response_thought_plan(self) -> None:
        app = self._make_app()
        async with app.run_test() as pilot:
            conversation = await self._launch_first_agent(app, pilot)
            await self._submit_prompt(conversation, "hello", pilot)

            lines = "\n".join(conversation.timeline_entries)
            self.assertIn("chunk-1", lines)
            self.assertIn("Thought", lines)
            self.assertIn("Plan", lines)
            self.assertIn("state -> idle", lines)

    async def test_prompt_resource_attachment_is_passed_to_bridge(self) -> None:
        app = self._make_app()
        async with app.run_test() as pilot:
            conversation = await self._launch_first_agent(app, pilot)
            await self._submit_prompt(conversation, "please read @note.txt", pilot)

            bridge = FakeBridge.instances[-1]
            _, resources = bridge.prompts[-1]
            self.assertEqual(len(resources), 1)
            self.assertEqual(resources[0]["path"], "note.txt")
            self.assertEqual(resources[0]["type"], "text")

    async def test_slash_mode_updates_settings_and_bridge(self) -> None:
        app = self._make_app()
        async with app.run_test() as pilot:
            conversation = await self._launch_first_agent(app, pilot)
            await self._submit_prompt(conversation, "/mode shell", pilot)

            bridge = FakeBridge.instances[-1]
            self.assertEqual(app.settings.shell.default_mode, "shell")
            self.assertIn("shell", bridge.modes)

    async def test_slash_menu_appears_and_cycles(self) -> None:
        app = self._make_app()
        async with app.run_test() as pilot:
            conversation = await self._launch_first_agent(app, pilot)
            prompt = conversation.query_one("#prompt", Input)
            prompt.focus()
            prompt.value = "/"
            await pilot.pause(0.1)

            menu = conversation.query_one("#slash-menu", OptionList)
            self.assertNotIn("hidden", menu.classes)
            self.assertGreater(menu.option_count, 1)

            initial = menu.highlighted
            menu.action_cursor_down()
            self.assertNotEqual(menu.highlighted, initial)

            await pilot.press("tab")
            await pilot.pause(0.1)
            self.assertTrue(prompt.value.startswith("/"))

    async def test_shell_command_runs_end_to_end(self) -> None:
        app = self._make_app()
        async with app.run_test() as pilot:
            conversation = await self._launch_first_agent(app, pilot)
            await self._submit_prompt(conversation, "!echo bufo-e2e", pilot)

            lines = "\n".join(conversation.timeline_entries)
            self.assertIn("bufo-e2e", lines)

    async def test_shell_dangerous_command_rejected_via_permission_modal(self) -> None:
        app = self._make_app()
        async with app.run_test() as pilot:
            conversation = await self._launch_first_agent(app, pilot)
            submit_task = asyncio.create_task(conversation._handle_shell("rm -rf tmp"))  # noqa: SLF001
            await asyncio.sleep(0.1)
            await self._press_permission(app, "reject_once", pilot)
            await asyncio.wait_for(submit_task, timeout=2)

            lines = "\n".join(conversation.timeline_entries)
            self.assertIn("Command rejected", lines)

    async def test_agent_permission_modal_flow(self) -> None:
        app = self._make_app()
        async with app.run_test() as pilot:
            conversation = await self._launch_first_agent(app, pilot)
            submit_task = asyncio.create_task(conversation._handle_agent_prompt("ask-permission"))  # noqa: SLF001
            await asyncio.sleep(0.1)
            await self._press_permission(app, "allow_once", pilot)
            await asyncio.wait_for(submit_task, timeout=2)

            lines = "\n".join(conversation.timeline_entries)
            self.assertIn("Permission decision:", lines)
            self.assertIn("allow_once", lines)

    async def test_tool_lifecycle_updates_render(self) -> None:
        app = self._make_app()
        async with app.run_test() as pilot:
            conversation = await self._launch_first_agent(app, pilot)
            await self._submit_prompt(conversation, "lifecycle", pilot)

            lines = "\n".join(conversation.timeline_entries)
            self.assertIn("Tool", lines)
            self.assertIn("build", lines)
            self.assertIn("started", lines)
            self.assertIn("completed", lines)

    async def test_custom_agent_uses_display_name_in_timeline_header(self) -> None:
        app = self._make_app(
            ad_hoc_agent_command="demo-agent --acp",
            ad_hoc_agent_name="Demo ACP Agent",
        )
        async with app.run_test() as pilot:
            app.post_message(LaunchAgent(agent_identity="__custom__", project_root=self.project_root))
            await pilot.pause(0.25)
            conversation = app.screen.query_one(Conversation)

            lines = "\n".join(conversation.timeline_entries)
            self.assertIn("Agent:", lines)
            self.assertIn("Demo ACP Agent", lines)
            self.assertNotIn("[dim]Agent:[/dim] __custom__", lines)

    async def test_provider_style_session_updates_are_rendered_and_commands_registered(self) -> None:
        app = self._make_app()
        async with app.run_test() as pilot:
            conversation = await self._launch_first_agent(app, pilot)
            await conversation._on_agent_event(  # noqa: SLF001
                AgentEvent(
                    type="session/update",
                    payload={
                        "sessionId": "sid-1",
                        "update": {
                            "sessionUpdate": "available_commands_update",
                            "availableCommands": [
                                {"name": "agent:mode"},
                                {"name": "agent:global-memory"},
                            ],
                        },
                    },
                )
            )
            await conversation._on_agent_event(  # noqa: SLF001
                AgentEvent(
                    type="session/update",
                    payload={
                        "sessionId": "sid-1",
                        "update": {
                            "sessionUpdate": "current_mode_update",
                            "currentModeId": "unrestricted",
                        },
                    },
                )
            )
            await conversation._on_agent_event(  # noqa: SLF001
                AgentEvent(
                    type="session/update",
                    payload={
                        "sessionId": "sid-1",
                        "update": {
                            "sessionUpdate": "agent_message_chunk",
                            "content": {"type": "text", "text": "Hello parsed"},
                        },
                    },
                )
            )

            lines = "\n".join(conversation.timeline_entries)
            self.assertIn("Slash Commands", lines)
            self.assertIn("/agent:mode", lines)
            self.assertIn("Mode", lines)
            self.assertIn("unrestricted", lines)
            self.assertIn("Hello parsed", lines)
            self.assertNotIn("sessionUpdate=agent_message_chunk", lines)
            self.assertIn("/agent:mode", conversation._slash_commands)  # noqa: SLF001

    async def test_agent_stderr_is_logged_but_not_rendered_in_timeline(self) -> None:
        app = self._make_app()
        async with app.run_test() as pilot:
            conversation = await self._launch_first_agent(app, pilot)
            before = len(conversation.timeline_entries)
            with patch.object(type(conversation.logger), "warning", autospec=True) as warning_mock:
                await conversation._on_agent_event(  # noqa: SLF001
                    AgentEvent(type="agent/stderr", payload={"text": "noisy stderr line\n"})
                )
            self.assertEqual(len(conversation.timeline_entries), before)
            warning_mock.assert_called_once()
            self.assertEqual(warning_mock.call_args.args[1], "conversation.agent_stderr")
            self.assertEqual(warning_mock.call_args.kwargs["message"], "noisy stderr line")

    async def test_tool_call_details_are_collapsed_then_expandable(self) -> None:
        app = self._make_app()
        async with app.run_test() as pilot:
            conversation = await self._launch_first_agent(app, pilot)
            await conversation._on_agent_event(  # noqa: SLF001
                AgentEvent(
                    type="session/update",
                    payload={
                        "sessionId": "sid-1",
                        "update": {
                            "sessionUpdate": "tool_call",
                            "toolCallId": "script-abc",
                            "title": "Execute generated Python script",
                            "status": "pending",
                            "content": [
                                {
                                    "type": "content",
                                    "content": {
                                        "type": "text",
                                        "text": "```python\nprint('hello')\n```",
                                    },
                                }
                            ],
                        },
                    },
                )
            )

            collapsed_lines = "\n".join(conversation.timeline_entries)
            self.assertIn("Tool:", collapsed_lines)
            self.assertIn("/tool-expand script-abc", collapsed_lines)
            self.assertNotIn("print('hello')", collapsed_lines)

            await conversation._handle_slash("/tool-expand script-abc")  # noqa: SLF001
            expanded_lines = "\n".join(conversation.timeline_entries)
            self.assertIn("Tool details expanded:", expanded_lines)
            self.assertIn("print('hello')", expanded_lines)

    async def test_selection_copy_helper_copies_and_notifies(self) -> None:
        app = self._make_app()
        async with app.run_test() as pilot:
            await self._launch_first_agent(app, pilot)
            app.screen.get_selected_text = lambda: "copied text"  # type: ignore[method-assign]
            with patch("bufo.app.pyperclip.copy") as clipboard_copy, patch.object(app, "notify") as notify_mock:
                self.assertTrue(app._copy_selected_text_with_notification())  # noqa: SLF001
                self.assertFalse(app._copy_selected_text_with_notification())  # noqa: SLF001
            self.assertEqual(app.clipboard, "copied text")
            clipboard_copy.assert_called_once_with("copied text")
            notify_mock.assert_called_once()

    async def test_selection_copy_helper_degrades_when_system_clipboard_fails(self) -> None:
        app = self._make_app()
        async with app.run_test() as pilot:
            await self._launch_first_agent(app, pilot)
            app.screen.get_selected_text = lambda: "copied text"  # type: ignore[method-assign]
            with patch("bufo.app.pyperclip.copy", side_effect=RuntimeError("clipboard error")), patch.object(app, "notify") as notify_mock:
                self.assertTrue(app._copy_selected_text_with_notification())  # noqa: SLF001
            self.assertEqual(app.clipboard, "copied text")
            notify_mock.assert_called_once()
            args, kwargs = notify_mock.call_args
            self.assertIn("app clipboard", args[0])
            self.assertEqual(kwargs.get("severity"), "warning")

    async def test_timeline_exposes_selection_offsets_for_mouse_drag(self) -> None:
        app = self._make_app()
        async with app.run_test() as pilot:
            conversation = await self._launch_first_agent(app, pilot)
            timeline = conversation.query_one("#timeline", SelectableRichLog)
            geometry = app.screen.find_widget(timeline)
            widget, offset = app.screen.get_widget_and_offset_at(
                geometry.region.x + 1,
                geometry.region.y + 1,
            )
            self.assertIs(widget, timeline)
            self.assertIsNotNone(offset)

    async def test_project_tree_auto_refreshes_when_watch_event_fires(self) -> None:
        watch_manager = FakeWatchManager()
        app = self._make_app(watch_manager=watch_manager)
        async with app.run_test() as pilot:
            await self._launch_first_agent(app, pilot)
            tree = app.screen.query_one("#tree", Tree)
            existing = [str(node.label) for node in tree.root.children]
            self.assertFalse(any("auto-refresh.txt" in item for item in existing))

            (self.project_root / "auto-refresh.txt").write_text("x", encoding="utf-8")
            watch_manager.emit(self.project_root)
            await pilot.pause(0.35)

            labels = [str(node.label) for node in tree.root.children]
            self.assertTrue(any("auto-refresh.txt" in item for item in labels))

    async def test_project_tree_renders_expandable_directory_nodes(self) -> None:
        nested_dir = self.project_root / "nested-dir"
        nested_dir.mkdir(parents=True, exist_ok=True)
        (nested_dir / "child.txt").write_text("x", encoding="utf-8")

        app = self._make_app()
        async with app.run_test() as pilot:
            await self._launch_first_agent(app, pilot)
            await pilot.pause(0.2)

            tree = app.screen.query_one("#tree", Tree)
            root_labels = [str(node.label) for node in tree.root.children]
            self.assertTrue(any("nested-dir/" in label for label in root_labels))
            self.assertFalse(any("nested-dir/child.txt" in label for label in root_labels))

            dir_node = next(node for node in tree.root.children if "nested-dir/" in str(node.label))
            self.assertTrue(dir_node.allow_expand)
            child_labels = [str(node.label) for node in dir_node.children]
            self.assertTrue(any("child.txt" in label for label in child_labels))

    async def test_session_navigation_next_prev(self) -> None:
        app = self._make_app()
        async with app.run_test() as pilot:
            await self._launch_first_agent(app, pilot)
            first_mode = app.current_mode

            second_identity = app.catalog[1].identity
            app.post_message(LaunchAgent(agent_identity=second_identity, project_root=self.project_root))
            await pilot.pause(0.25)
            second_mode = app.current_mode
            self.assertNotEqual(first_mode, second_mode)

            app.action_prev_session()
            await pilot.pause(0.1)
            self.assertEqual(app.current_mode, first_mode)

            app.action_next_session()
            await pilot.pause(0.1)
            self.assertEqual(app.current_mode, second_mode)

    async def test_session_tabs_and_new_session_button(self) -> None:
        app = self._make_app()
        async with app.run_test() as pilot:
            await self._launch_first_agent(app, pilot)
            first_mode = app.current_mode
            second_identity = app.catalog[1].identity
            app.post_message(LaunchAgent(agent_identity=second_identity, project_root=self.project_root))
            await pilot.pause(0.25)
            second_mode = app.current_mode
            self.assertNotEqual(first_mode, second_mode)

            app.screen.query_one(f"#session-tab-{first_mode}", Button).press()
            await pilot.pause(0.2)
            self.assertEqual(app.current_mode, first_mode)

            app.screen.query_one("#new-session", Button).press()
            await pilot.pause(0.2)
            self.assertIsInstance(app.screen, StoreScreen)


if __name__ == "__main__":
    unittest.main()
