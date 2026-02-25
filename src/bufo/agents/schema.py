"""Typed contracts for agent registry descriptors."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Platform = Literal["linux", "darwin", "windows", "default"]


class AgentAction(BaseModel):
    name: str
    description: str = ""
    commands: dict[Platform, str] = Field(default_factory=dict)


class AgentDescriptor(BaseModel):
    identity: str
    name: str
    protocol: str = "acp"
    category: str = "coding"
    description: str = ""
    recommended: bool = False
    launcher_default: bool = False
    run_command: dict[Platform, str] = Field(default_factory=dict)
    actions: list[AgentAction] = Field(default_factory=list)
    welcome_markdown: str | None = None

    def command_for_platform(self, platform: str) -> str | None:
        if platform in self.run_command:
            return self.run_command[platform]  # type: ignore[index]
        return self.run_command.get("default")


class AgentCatalog(BaseModel):
    agents: list[AgentDescriptor]
