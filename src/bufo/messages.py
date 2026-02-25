"""Textual message objects for screen/app coordination."""

from __future__ import annotations

from pathlib import Path

from textual.message import Message


class LaunchAgent(Message):
    def __init__(self, *, agent_identity: str, project_root: Path) -> None:
        self.agent_identity = agent_identity
        self.project_root = project_root
        super().__init__()


class ResumeAgent(Message):
    def __init__(self, *, agent_identity: str, agent_session_id: str, project_root: Path) -> None:
        self.agent_identity = agent_identity
        self.agent_session_id = agent_session_id
        self.project_root = project_root
        super().__init__()


class OpenSettings(Message):
    pass


class OpenSessions(Message):
    pass


class SwitchSession(Message):
    def __init__(self, *, mode_name: str) -> None:
        self.mode_name = mode_name
        super().__init__()


class CreateSession(Message):
    pass
