from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from bufo.cli import main


class CliE2ETests(unittest.TestCase):
    def setUp(self) -> None:
        self.runner = CliRunner()

    def test_help(self) -> None:
        result = self.runner.invoke(main, ["--help"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("Commands:", result.output)
        self.assertIn("run", result.output)

    def test_about(self) -> None:
        result = self.runner.invoke(main, ["about"])
        self.assertEqual(result.exit_code, 0)
        payload = json.loads(result.output)
        self.assertEqual(payload["name"], "bufo")
        self.assertIn("version", payload)

    def test_settings_path(self) -> None:
        result = self.runner.invoke(main, ["settings-path"])
        self.assertEqual(result.exit_code, 0)
        self.assertTrue(result.output.strip().endswith("settings.json"))

    def test_replay_outputs_tail_lines(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            path.write_text("a\nb\nc\n", encoding="utf-8")
            result = self.runner.invoke(main, ["replay", str(path), "--limit", "2"])

        self.assertEqual(result.exit_code, 0)
        self.assertEqual(result.output.strip().splitlines(), ["b", "c"])

    def test_run_constructs_app(self) -> None:
        with patch("bufo.cli.BufoApp.run", return_value=None) as run_mock:
            result = self.runner.invoke(main, ["run", ".", "--store"])

        self.assertEqual(result.exit_code, 0)
        run_mock.assert_called_once()

    def test_acp_constructs_custom_app(self) -> None:
        with patch("bufo.cli.AcpCommandApp.run", return_value=None) as run_mock:
            result = self.runner.invoke(main, ["acp", "agent --acp", "--name", "X", "."])

        self.assertEqual(result.exit_code, 0)
        run_mock.assert_called_once()


if __name__ == "__main__":
    unittest.main()
