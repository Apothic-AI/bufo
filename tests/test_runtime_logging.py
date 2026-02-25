from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from bufo.runtime_logging import configure_runtime_logging


class RuntimeLoggingTests(unittest.TestCase):
    def test_writes_jsonl_and_filters_by_level(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "runtime.jsonl"
            logger = configure_runtime_logging(level="info", log_file=path)
            logger.debug("debug.hidden", foo="bar")
            logger.info("info.visible", foo="bar")

            lines = path.read_text(encoding="utf-8").splitlines()
            self.assertGreaterEqual(len(lines), 2)  # includes logging.configured event
            payloads = [json.loads(line) for line in lines]
            self.assertTrue(any(item["event"] == "info.visible" for item in payloads))
            self.assertFalse(any(item["event"] == "debug.hidden" for item in payloads))

    def test_uses_environment_variables(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "from-env.jsonl"
            with patch.dict(
                os.environ,
                {"BUFO_LOG_LEVEL": "debug", "BUFO_LOG_FILE": str(path)},
                clear=False,
            ):
                logger = configure_runtime_logging()
                logger.debug("env.debug", alpha=1)

            lines = path.read_text(encoding="utf-8").splitlines()
            payloads = [json.loads(line) for line in lines]
            self.assertTrue(any(item["event"] == "env.debug" for item in payloads))


if __name__ == "__main__":
    unittest.main()
