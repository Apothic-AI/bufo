"""Load/save application settings."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from bufo.config.models import AppSettings
from bufo.paths import settings_path


class SettingsStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or settings_path()

    def load(self) -> AppSettings:
        if not self.path.exists():
            settings = AppSettings()
            self.save(settings)
            return settings

        raw = self.path.read_text(encoding="utf-8")
        try:
            data = json.loads(raw)
            return AppSettings.model_validate(data)
        except (json.JSONDecodeError, ValidationError):
            # Fall back to defaults while preserving corrupt payload for debugging.
            backup = self.path.with_suffix(".corrupt.json")
            backup.write_text(raw, encoding="utf-8")
            settings = AppSettings()
            self.save(settings)
            return settings

    def save(self, settings: AppSettings) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(settings.model_dump(mode="json"), indent=2, sort_keys=True)
        self.path.write_text(f"{payload}\n", encoding="utf-8")

    def update(self, dotted_key: str, value: Any) -> AppSettings:
        settings = self.load()
        data = settings.model_dump()

        keys = dotted_key.split(".")
        cursor: dict[str, Any] = data
        for key in keys[:-1]:
            nested = cursor.get(key)
            if not isinstance(nested, dict):
                raise KeyError(f"Unknown setting path: {dotted_key}")
            cursor = nested
        cursor[keys[-1]] = value

        updated = AppSettings.model_validate(data)
        self.save(updated)
        return updated
