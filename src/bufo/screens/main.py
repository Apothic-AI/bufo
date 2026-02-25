"""Main work screen for an active Bufo session."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from textual import events
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Static

from bufo.agents.schema import AgentDescriptor
from bufo.config.models import AppSettings
from bufo.fs.watch import WatchManager
from bufo.messages import CreateSession, OpenSessions, SwitchSession
from bufo.runtime_logging import get_runtime_logger
from bufo.sessions.tracker import SessionMeta
from bufo.widgets.conversation import Conversation
from bufo.widgets.project_tree import ProjectTreePanel


class MainScreen(Screen):
    BINDINGS = [
        ("ctrl+b", "toggle_sidebar", "Sidebar"),
        ("ctrl+n", "new_session", "New Session"),
    ]

    DEFAULT_CSS = """
    MainScreen {
        layout: vertical;
    }

    #session-strip {
        height: 3;
        layout: horizontal;
        padding: 0 1;
        border-bottom: tall $surface-lighten-1;
    }

    #session-tabs {
        width: 1fr;
        height: 3;
        align-vertical: middle;
    }

    #new-session, #manage-sessions {
        width: auto;
        margin-left: 1;
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
        self.logger = get_runtime_logger()
        super().__init__()

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="session-strip"):
            with Horizontal(id="session-tabs"):
                yield Static("No sessions yet", id="no-session-tabs")
            yield Button("+ New Session", id="new-session", variant="success")
            yield Button("Sessions", id="manage-sessions")
        with Horizontal(id="main-body"):
            with Vertical(id="sidebar", classes="hidden" if self._sidebar_hidden else ""):
                yield Static(f"[b]Plan[/b]\n- Start task\n- Run agent\n- Apply changes", markup=True)
                yield ProjectTreePanel(self.project_root, self.watch_manager)
            with Vertical(id="conversation-pane"):
                yield Conversation(
                    project_root=self.project_root,
                    settings=self.settings,
                    agent_identity=self.agent.identity,
                    agent_name=self.agent.name,
                    agent_command=self.agent.command_for_platform("default"),
                    resume_session_id=self.resume_session_id,
                    mode_name=self.session.mode_name,
                    bridge_factory=self.bridge_factory,
                )
        yield Footer()

    def on_mount(self) -> None:
        self._refresh_session_tabs()

    def on_screen_resume(self, _event: events.ScreenResume) -> None:
        self._refresh_session_tabs()

    def action_new_session(self) -> None:
        self.post_message(CreateSession())

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id or ""
        if button_id.startswith("session-tab-"):
            mode_name = button_id.removeprefix("session-tab-")
            if mode_name and mode_name != self.app.current_mode:
                self.logger.debug(
                    "main_screen.session_tab.activated",
                    current_mode=self.app.current_mode,
                    target_mode=mode_name,
                )
                self.post_message(SwitchSession(mode_name=mode_name))
            return
        if button_id == "new-session":
            self.post_message(CreateSession())
            return
        if button_id == "manage-sessions":
            self.post_message(OpenSessions())

    def action_toggle_sidebar(self) -> None:
        sidebar = self.query_one("#sidebar", Vertical)
        if "hidden" in sidebar.classes:
            sidebar.remove_class("hidden")
        else:
            sidebar.add_class("hidden")

    def _refresh_session_tabs(self) -> None:
        self.run_worker(
            self._rebuild_session_tabs,
            group=f"session-tabs-{self.session.mode_name}",
            exclusive=True,
            exit_on_error=False,
        )

    async def _rebuild_session_tabs(self) -> None:
        container = self.query_one("#session-tabs", Horizontal)
        await container.remove_children()

        sessions = list(self.app.session_tracker.all())
        if not sessions:
            await container.mount(Static("No sessions yet", id="no-session-tabs"))
            return

        for session in sessions:
            label = f"{session.title} ({session.state})"
            is_active = session.mode_name == self.app.current_mode
            await container.mount(
                Button(
                    label,
                    id=f"session-tab-{session.mode_name}",
                    classes="session-tab",
                    variant="primary" if is_active else "default",
                )
            )
