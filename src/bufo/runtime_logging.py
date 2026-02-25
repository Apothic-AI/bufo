"""Structured JSONL runtime logging for Bufo."""

from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from bufo.paths import state_root

LogLevel = Literal["off", "error", "warning", "info", "debug"]

_LEVEL_VALUES: dict[str, int] = {
    "off": 100,
    "error": 40,
    "warning": 30,
    "info": 20,
    "debug": 10,
}

_runtime_logger: "RuntimeLogger | None" = None


def parse_level(value: str | None, default: LogLevel = "warning") -> LogLevel:
    if not value:
        return default
    normalized = value.strip().lower()
    if normalized in {"warn"}:
        normalized = "warning"
    if normalized in {"none", "disabled", "0"}:
        normalized = "off"
    if normalized not in _LEVEL_VALUES:
        return default
    return normalized  # type: ignore[return-value]


def resolve_log_file(path: str | Path | None) -> Path:
    if path is None:
        return state_root() / "logs" / "bufo.runtime.jsonl"
    return Path(path).expanduser().resolve()


@dataclass(slots=True)
class RuntimeLogger:
    level: LogLevel
    sink_path: Path
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def enabled(self, level: str) -> bool:
        current = _LEVEL_VALUES.get(self.level, _LEVEL_VALUES["warning"])
        incoming = _LEVEL_VALUES.get(level, _LEVEL_VALUES["debug"])
        return incoming >= current and current < _LEVEL_VALUES["off"]

    def log(self, level: str, event: str, **fields: Any) -> None:
        if not self.enabled(level):
            return
        payload = {
            "ts": datetime.now(UTC).isoformat(),
            "level": level,
            "event": event,
            "pid": os.getpid(),
            **fields,
        }
        line = json.dumps(payload, sort_keys=True)
        with self._lock:
            self.sink_path.parent.mkdir(parents=True, exist_ok=True)
            with self.sink_path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")

    def debug(self, event: str, **fields: Any) -> None:
        self.log("debug", event, **fields)

    def info(self, event: str, **fields: Any) -> None:
        self.log("info", event, **fields)

    def warning(self, event: str, **fields: Any) -> None:
        self.log("warning", event, **fields)

    def error(self, event: str, **fields: Any) -> None:
        self.log("error", event, **fields)


class _DisabledLogger(RuntimeLogger):
    def __init__(self) -> None:
        super().__init__(level="off", sink_path=Path("/dev/null"))

    def log(self, level: str, event: str, **fields: Any) -> None:  # noqa: ARG002
        return


def configure_runtime_logging(
    *,
    level: str | None = None,
    log_file: str | Path | None = None,
) -> RuntimeLogger:
    global _runtime_logger

    env_level = os.getenv("BUFO_LOG_LEVEL")
    env_file = os.getenv("BUFO_LOG_FILE")
    effective_level = parse_level(level or env_level, default="warning")
    effective_file = resolve_log_file(log_file or env_file)
    if effective_level == "off":
        _runtime_logger = _DisabledLogger()
    else:
        _runtime_logger = RuntimeLogger(level=effective_level, sink_path=effective_file)
        _runtime_logger.info(
            "logging.configured",
            configured_level=effective_level,
            sink_path=str(effective_file),
        )
    return _runtime_logger


def get_runtime_logger() -> RuntimeLogger:
    global _runtime_logger
    if _runtime_logger is None:
        _runtime_logger = configure_runtime_logging()
    return _runtime_logger

