"""In-memory session tracker used by the app mode system."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

SessionState = Literal["notready", "busy", "asking", "idle"]


@dataclass(slots=True)
class SessionMeta:
    mode_name: str
    index: int
    title: str
    subtitle: str
    project_root: Path
    state: SessionState = "notready"
    agent_identity: str | None = None
    agent_session_id: str | None = None


class SessionTracker:
    def __init__(self) -> None:
        self._sessions: dict[str, SessionMeta] = {}
        self._next_index = 1

    def create(
        self,
        *,
        title: str,
        subtitle: str,
        project_root: Path,
        agent_identity: str | None = None,
        agent_session_id: str | None = None,
    ) -> SessionMeta:
        mode_name = f"session-{self._next_index}"
        self._next_index += 1

        meta = SessionMeta(
            mode_name=mode_name,
            index=len(self._sessions),
            title=title,
            subtitle=subtitle,
            project_root=project_root,
            state="notready",
            agent_identity=agent_identity,
            agent_session_id=agent_session_id,
        )
        self._sessions[mode_name] = meta
        return meta

    def remove(self, mode_name: str) -> None:
        self._sessions.pop(mode_name, None)
        self._reindex()

    def get(self, mode_name: str) -> SessionMeta | None:
        return self._sessions.get(mode_name)

    def all(self) -> list[SessionMeta]:
        return sorted(self._sessions.values(), key=lambda item: item.index)

    def update_state(self, mode_name: str, state: SessionState) -> None:
        meta = self._sessions.get(mode_name)
        if meta is None:
            return
        meta.state = state

    def find_by_agent_pair(self, agent_identity: str, agent_session_id: str) -> SessionMeta | None:
        for session in self._sessions.values():
            if (
                session.agent_identity == agent_identity
                and session.agent_session_id == agent_session_id
            ):
                return session
        return None

    def _reindex(self) -> None:
        for idx, session in enumerate(self.all()):
            session.index = idx
