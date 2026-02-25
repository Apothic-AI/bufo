from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from bufo.app import BufoApp
from bufo.config.store import SettingsStore
from bufo.fs.watch import NullWatchManager
from bufo.persistence.sessions import SessionStore
from bufo.prompt_resources import expand_prompt_resources
from bufo.protocol.jsonrpc import JsonRpcConnection


class SettingsStoreTests(unittest.TestCase):
    def test_load_save_update_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            store = SettingsStore(path)

            settings = store.load()
            self.assertTrue(path.exists())
            self.assertEqual(settings.schema_version, 1)

            updated = store.update("shell.default_mode", "shell")
            self.assertEqual(updated.shell.default_mode, "shell")

            reloaded = store.load()
            self.assertEqual(reloaded.shell.default_mode, "shell")


class SessionStoreTests(unittest.TestCase):
    def test_upsert_and_recent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "sessions.sqlite3"
            store = SessionStore(db_path)

            sid1 = store.upsert(
                agent_name="Codex",
                agent_identity="codex-cli",
                agent_session_id="abc",
                title="A",
                protocol="acp",
                metadata={"cwd": "/tmp"},
            )
            sid2 = store.upsert(
                agent_name="Codex",
                agent_identity="codex-cli",
                agent_session_id="xyz",
                title="B",
                protocol="acp",
                metadata={"cwd": "/tmp2"},
            )

            self.assertNotEqual(sid1, sid2)
            self.assertEqual(len(store.recent()), 2)
            match = store.get_by_agent_pair("codex-cli", "abc")
            self.assertIsNotNone(match)
            assert match is not None
            self.assertEqual(match.title, "A")


class PromptResourceTests(unittest.TestCase):
    def test_text_resource_expansion(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            file_path = root / "notes.txt"
            file_path.write_text("hello", encoding="utf-8")

            text, resources = expand_prompt_resources(root, "please read @notes.txt")
            self.assertEqual(text, "please read notes.txt")
            self.assertEqual(len(resources), 1)
            self.assertEqual(resources[0]["type"], "text")
            self.assertEqual(resources[0]["text"], "hello")


class JsonRpcTests(unittest.IsolatedAsyncioTestCase):
    async def test_call_and_response(self) -> None:
        outbound: list[str] = []

        async def sender(line: str) -> None:
            outbound.append(line)

        conn = JsonRpcConnection(sender)

        async def resolve() -> None:
            await asyncio.sleep(0)
            request = json.loads(outbound[0])
            await conn.feed(
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": request["id"],
                        "result": {"ok": True},
                    }
                )
            )

        task = asyncio.create_task(resolve())
        result = await conn.call("ping", {"x": 1})
        await task

        self.assertEqual(result, {"ok": True})


class BufoAppBootstrapTests(unittest.TestCase):
    def test_falls_back_to_null_watch_manager_when_inotify_limit_hit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with patch(
                "bufo.app.WatchManager",
                side_effect=OSError(24, "inotify instance limit reached"),
            ):
                app = BufoApp(
                    project_root=Path(tmp),
                    force_store=True,
                    check_updates=False,
                )

        self.assertIsInstance(app.watch_manager, NullWatchManager)
        self.assertIn("Errno 24", app._watcher_startup_error or "")  # noqa: SLF001
        self.assertIn("inotify", app._watcher_startup_message().lower())  # noqa: SLF001


if __name__ == "__main__":
    unittest.main()
