"""Store/launcher screen for discovering and launching agents."""

from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, Input, ListItem, ListView, Static

from bufo.agents.schema import AgentDescriptor
from bufo.messages import LaunchAgent, OpenSessions, OpenSettings, ResumeAgent
from bufo.persistence.sessions import SessionRecord


class StoreScreen(Screen):
    BINDINGS = [
        ("ctrl+comma", "settings", "Settings"),
        ("ctrl+r", "resume", "Resume"),
    ]

    DEFAULT_CSS = """
    StoreScreen {
        layout: vertical;
    }

    #store-root {
        layout: horizontal;
        height: 1fr;
    }

    #left, #right {
        width: 1fr;
        padding: 1;
    }

    ListView {
        height: 1fr;
        border: round $panel;
    }

    Input {
        margin-bottom: 1;
    }
    """

    def __init__(self, *, agents: list[AgentDescriptor], recent_sessions: list[SessionRecord], project_root: Path) -> None:
        self.agents = agents
        self.recent_sessions = recent_sessions
        self.project_root = project_root
        super().__init__()

    def compose(self) -> ComposeResult:
        yield Static("[b]Bufo Agent Store[/b]", markup=True)
        yield Input(value=str(self.project_root), id="project-root", placeholder="Project directory")

        with Horizontal(id="store-root"):
            with Vertical(id="left"):
                yield Static("Launch Agents")
                agent_items = [
                    ListItem(Static(f"{agent.name} - {agent.description}"), id=agent.identity)
                    for agent in self.agents
                ]
                yield ListView(*agent_items, id="agent-list")
                yield Button("Launch Selected", id="launch", variant="success")

            with Vertical(id="right"):
                yield Static("Recent Sessions")
                recent_items = [
                    ListItem(
                        Static(
                            f"{session.agent_name} | {session.title} | {session.last_used_at}",
                            markup=False,
                        ),
                        id=f"{session.agent_identity}::{session.agent_session_id or ''}::{session.id}",
                    )
                    for session in self.recent_sessions
                ]
                yield ListView(*recent_items, id="recent-list")
                yield Button("Resume Selected", id="resume", variant="primary")

        with Horizontal():
            yield Button("Settings", id="settings")
            yield Button("Sessions", id="sessions")

    def action_settings(self) -> None:
        self.post_message(OpenSettings())

    def action_resume(self) -> None:
        self._resume_selected()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id
        if button_id == "launch":
            self._launch_selected()
        elif button_id == "resume":
            self._resume_selected()
        elif button_id == "settings":
            self.post_message(OpenSettings())
        elif button_id == "sessions":
            self.post_message(OpenSessions())

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if event.list_view.id == "agent-list":
            self._launch_selected()
        elif event.list_view.id == "recent-list":
            self._resume_selected()

    def _current_project_root(self) -> Path:
        value = self.query_one("#project-root", Input).value.strip() or "."
        return Path(value).expanduser().resolve()

    def _launch_selected(self) -> None:
        list_view = self.query_one("#agent-list", ListView)
        index = list_view.index
        if index is None or index < 0 or index >= len(self.agents):
            return

        agent = self.agents[index]
        self.post_message(
            LaunchAgent(agent_identity=agent.identity, project_root=self._current_project_root())
        )

    def _resume_selected(self) -> None:
        list_view = self.query_one("#recent-list", ListView)
        if list_view.index is None:
            return
        if list_view.index < 0 or list_view.index >= len(self.recent_sessions):
            return

        session = self.recent_sessions[list_view.index]
        if not session.agent_session_id:
            return

        self.post_message(
            ResumeAgent(
                agent_identity=session.agent_identity,
                agent_session_id=session.agent_session_id,
                project_root=self._current_project_root(),
            )
        )

    def refresh_recent_sessions(self, sessions: list[SessionRecord]) -> None:
        self.recent_sessions = sessions
        recent = self.query_one("#recent-list", ListView)
        recent.clear()
        recent.extend(
            [
                ListItem(
                    Static(
                        f"{session.agent_name} | {session.title} | {session.last_used_at}",
                        markup=False,
                    ),
                    id=f"{session.agent_identity}::{session.agent_session_id or ''}::{session.id}",
                )
                for session in sessions
            ]
        )
