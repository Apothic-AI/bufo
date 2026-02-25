"""Anonymous telemetry collector with local opt-in gating."""

from __future__ import annotations

import json
import platform
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from bufo.config.models import AppSettings
from bufo.paths import state_root


@dataclass(slots=True)
class TelemetryEvent:
    name: str
    properties: dict[str, Any]


class Telemetry:
    def __init__(self, settings: AppSettings, sink_path: Path | None = None) -> None:
        self.settings = settings
        self.sink_path = sink_path or state_root() / "telemetry.jsonl"

        if self.settings.statistics.distinct_id is None:
            self.settings.statistics.distinct_id = str(uuid.uuid4())

    def capture(self, event: TelemetryEvent) -> None:
        if not self.settings.statistics.allow_collect:
            return

        payload = {
            "name": event.name,
            "ts": datetime.now(UTC).isoformat(),
            "distinct_id": self.settings.statistics.distinct_id,
            "properties": {
                "platform": platform.platform(),
                **event.properties,
            },
        }

        self.sink_path.parent.mkdir(parents=True, exist_ok=True)
        with self.sink_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, sort_keys=True) + "\n")
