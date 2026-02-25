"""Settings schema for Bufo."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator

SessionState = Literal["notready", "busy", "asking", "idle"]


class AppearanceSettings(BaseModel):
    theme: str = Field(default="textual-dark", description="Textual theme name")
    compact_prompt: bool = Field(default=False)
    thought_visibility: Literal["expanded", "collapsed", "auto"] = Field(default="auto")


class SidebarSettings(BaseModel):
    mode: Literal["always", "hidden", "auto"] = Field(default="auto")
    show_project_tree: bool = Field(default=True)
    show_plan_panel: bool = Field(default=True)


class NotificationSettings(BaseModel):
    desktop: bool = Field(default=True)
    sound: bool = Field(default=False)
    flash_terminal_title: bool = Field(default=True)
    only_when_unfocused: bool = Field(default=True)


class ToolSettings(BaseModel):
    default_expanded: bool = Field(default=True)
    auto_expand_errors: bool = Field(default=True)


class ShellSafetySettings(BaseModel):
    warn_unknown: bool = Field(default=True)
    warn_dangerous: bool = Field(default=True)
    escalate_outside_project: bool = Field(default=True)


class ShellSettings(BaseModel):
    shell_program: str = Field(default="/bin/bash")
    default_mode: Literal["agent", "shell", "auto"] = Field(default="auto")
    max_terminal_buffer_lines: int = Field(default=4000, ge=500, le=100000)
    safety: ShellSafetySettings = Field(default_factory=ShellSafetySettings)


class DiffSettings(BaseModel):
    mode: Literal["auto", "unified", "split"] = Field(default="auto")


class StatisticsSettings(BaseModel):
    allow_collect: bool = Field(default=False)
    distinct_id: str | None = Field(default=None)


class LauncherSettings(BaseModel):
    favorites: list[str] = Field(default_factory=list)


class PathsSettings(BaseModel):
    project_root: str = Field(default_factory=lambda: str(Path.cwd()))

    @field_validator("project_root")
    @classmethod
    def validate_path(cls, value: str) -> str:
        path = Path(value).expanduser()
        return str(path)


class AppSettings(BaseModel):
    schema_version: int = Field(default=1)
    appearance: AppearanceSettings = Field(default_factory=AppearanceSettings)
    sidebar: SidebarSettings = Field(default_factory=SidebarSettings)
    notifications: NotificationSettings = Field(default_factory=NotificationSettings)
    tools: ToolSettings = Field(default_factory=ToolSettings)
    shell: ShellSettings = Field(default_factory=ShellSettings)
    diff: DiffSettings = Field(default_factory=DiffSettings)
    statistics: StatisticsSettings = Field(default_factory=StatisticsSettings)
    launcher: LauncherSettings = Field(default_factory=LauncherSettings)
    paths: PathsSettings = Field(default_factory=PathsSettings)

    def setting_items(self) -> list[tuple[str, str]]:
        """Flatten key/value pairs for schema-driven settings UI."""

        result: list[tuple[str, str]] = []

        def walk(prefix: str, value: object) -> None:
            if isinstance(value, BaseModel):
                for key, nested in value.model_dump().items():
                    walk(f"{prefix}.{key}" if prefix else key, nested)
            else:
                result.append((prefix, str(value)))

        walk("", self)
        return result
