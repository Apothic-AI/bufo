"""Main work screen for an active Bufo session."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Footer, Header, Static

from bufo.agents.schema import AgentDescriptor
from bufo.config.models import AppSettings
from bufo.fs.watch import WatchManager
from bufo.sessions.tracker import SessionMeta
from bufo.widgets.conversation import Conversation
from bufo.widgets.project_tree import ProjectTreePanel


class MainScreen(Screen):
    BINDINGS = [
        ("ctrl+b", "toggle_sidebar", "Sidebar"),
    ]

    DEFAULT_CSS = """
    MainScreen {
        layout: vertical;
    }

    #main-body {
        height: 1fr;
        layout: horizontal;
    }

    #sidebar {
        width: 28;
        border: round $surface-lighten-2;
        padding: 1;
    }

    #conversation-pane {
        width: 1fr;
        padding: 0 1;
    }

    .hidden {
        display: none;
    }
    """

    def __init__(
        self,
        *,
        session: SessionMeta,
        project_root: Path,
        settings: AppSettings,
        agent: AgentDescriptor,
        resume_session_id: str | None = None,
        watch_manager: WatchManager | None = None,
        bridge_factory: Callable[[str, Path, Any], Any] | None = None,
    ) -> None:
        self.session = session
        self.project_root = project_root
        self.settings = settings
        self.agent = agent
        self.resume_session_id = resume_session_id
        self.watch_manager = watch_manager
        self.bridge_factory = bridge_factory
        self._sidebar_hidden = settings.sidebar.mode == "hidden"
        super().__init__()

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="main-body"):
            with Vertical(id="sidebar", classes="hidden" if self._sidebar_hidden else ""):
                yield Static(f"[b]Plan[/b]\n- Start task\n- Run agent\n- Apply changes", markup=True)
                yield ProjectTreePanel(self.project_root, self.watch_manager)
            with Vertical(id="conversation-pane"):
                yield Conversation(
                    project_root=self.project_root,
                    settings=self.settings,
                    agent_identity=self.agent.identity,
                    agent_command=self.agent.command_for_platform("default"),
                    resume_session_id=self.resume_session_id,
                    mode_name=self.session.mode_name,
                    bridge_factory=self.bridge_factory,
                )
        yield Footer()

    def action_toggle_sidebar(self) -> None:
        sidebar = self.query_one("#sidebar", Vertical)
        if "hidden" in sidebar.classes:
            sidebar.remove_class("hidden")
        else:
            sidebar.add_class("hidden")
