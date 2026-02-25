"""Project-scoped JSONL histories for prompts and shell commands."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from bufo.paths import project_data_dir


def _ts() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(slots=True)
class HistoryItem:
    value: str
    created_at: str


class JsonlHistory:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, value: str) -> None:
        record = {"value": value, "created_at": _ts()}
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=True) + "\n")

    def read(self, limit: int = 200) -> list[HistoryItem]:
        if not self.path.exists():
            return []

        items: list[HistoryItem] = []
        with self.path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                items.append(
                    HistoryItem(
                        value=str(payload.get("value", "")),
                        created_at=str(payload.get("created_at", "")),
                    )
                )

        if len(items) <= limit:
            return items
        return items[-limit:]


class ProjectHistories:
    def __init__(self, project_root: Path) -> None:
        base = project_data_dir(project_root)
        self.prompt = JsonlHistory(base / "prompt-history.jsonl")
        self.shell = JsonlHistory(base / "shell-history.jsonl")
