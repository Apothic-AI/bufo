"""Bufo Textual application shell."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

from textual.app import App, ComposeResult
from textual.css.query import NoMatches
from textual.widgets import Footer, Header, Static

from bufo.agents.catalog import AgentRegistry
from bufo.agents.schema import AgentDescriptor
from bufo.config.models import AppSettings
from bufo.config.store import SettingsStore
from bufo.fs.watch import WatchManager
from bufo.messages import LaunchAgent, OpenSessions, OpenSettings, ResumeAgent
from bufo.notifications import NotificationEvent, Notifier
from bufo.persistence.sessions import SessionStore
from bufo.screens.main import MainScreen
from bufo.screens.modals import PermissionModal
from bufo.screens.sessions import SessionsScreen
from bufo.screens.settings import SettingsScreen
from bufo.screens.store import StoreScreen
from bufo.sessions.tracker import SessionTracker
from bufo.telemetry import Telemetry, TelemetryEvent
from bufo.version import __version__
from bufo.version_check import check_for_update


class BufoApp(App[None]):
    TITLE = "bufo"
    SUB_TITLE = "TUI and Web UI framework for AI agents"

    BINDINGS = [
        ("ctrl+o", "open_store", "Store"),
        ("ctrl+comma", "open_settings", "Settings"),
        ("ctrl+g", "open_sessions", "Sessions"),
        ("ctrl+tab", "next_session", "Next Session"),
        ("ctrl+shift+tab", "prev_session", "Prev Session"),
    ]

    CSS = """
    Screen {
        layout: vertical;
    }

    #welcome {
        height: 1fr;
        content-align: center middle;
        color: $text-muted;
    }
    """

    def __init__(
        self,
        *,
        project_root: Path,
        initial_agent: str | None = None,
        resume_session_id: str | None = None,
        force_store: bool = False,
        ad_hoc_agent_command: str | None = None,
        ad_hoc_agent_name: str = "Custom ACP",
    ) -> None:
        self.project_root = project_root.expanduser().resolve()
        self.initial_agent = initial_agent
        self.resume_session_id = resume_session_id
        self.force_store = force_store
        self.ad_hoc_agent_command = ad_hoc_agent_command
        self.ad_hoc_agent_name = ad_hoc_agent_name

        self.settings_store = SettingsStore()
        self.settings = self.settings_store.load()
        self.settings.paths.project_root = str(self.project_root)

        self.session_store = SessionStore()
        self.session_tracker = SessionTracker()
        self.watch_manager = WatchManager()

        data_dir = Path(__file__).resolve().parent / "data" / "agents"
        self.registry = AgentRegistry(package_data_dir=data_dir)
        loaded = self.registry.load()
        self.catalog = loaded.agents
        self.catalog_warnings = loaded.warnings

        self.notifier = Notifier(self.settings.notifications)
        self.telemetry = Telemetry(self.settings)

        super().__init__()

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield StoreScreen(
            agents=self.catalog,
            recent_sessions=self.session_store.recent(limit=50),
            project_root=self.project_root,
            id="store",
        )
        yield Footer()

    async def on_mount(self) -> None:
        self.theme = self.settings.appearance.theme

        if self.catalog_warnings:
            for warning in self.catalog_warnings:
                self.notify(f"Catalog warning: {warning}", severity="warning")

        self.telemetry.capture(TelemetryEvent(name="app_start", properties={"version": __version__}))
        asyncio.create_task(self._background_version_check())

        if self.force_store:
            return

        if self.initial_agent:
            await self._launch_by_identity(
                self.initial_agent,
                project_root=self.project_root,
                resume_session_id=self.resume_session_id,
            )

    async def _background_version_check(self) -> None:
        latest = await check_for_update("bufo")
        if latest:
            self.notify(f"Update available: {latest}", severity="information")

    async def on_launch_agent(self, message: LaunchAgent) -> None:
        await self._launch_by_identity(message.agent_identity, project_root=message.project_root)

    async def on_resume_agent(self, message: ResumeAgent) -> None:
        existing = self.session_tracker.find_by_agent_pair(
            message.agent_identity,
            message.agent_session_id,
        )
        if existing:
            self.switch_mode(existing.mode_name)
            return

        await self._launch_by_identity(
            message.agent_identity,
            project_root=message.project_root,
            resume_session_id=message.agent_session_id,
        )

    def on_open_settings(self, _message: OpenSettings) -> None:
        self.action_open_settings()

    def on_open_sessions(self, _message: OpenSessions) -> None:
        self.action_open_sessions()

    async def _launch_by_identity(
        self,
        agent_identity: str,
        *,
        project_root: Path,
        resume_session_id: str | None = None,
    ) -> None:
        agent = self._resolve_agent(agent_identity)
        if agent is None:
            self.notify(f"Unknown agent: {agent_identity}", severity="error")
            return

        platform_name = _platform_name()
        command = agent.command_for_platform(platform_name) or agent.command_for_platform("default")

        session = self.session_tracker.create(
            title=agent.name,
            subtitle=str(project_root),
            project_root=project_root,
            agent_identity=agent.identity,
            agent_session_id=resume_session_id,
        )

        # Persist resume metadata, keeping agent pair unique when possible.
        self.session_store.upsert(
            agent_name=agent.name,
            agent_identity=agent.identity,
            agent_session_id=resume_session_id,
            title=f"{agent.name} @ {project_root.name}",
            protocol=agent.protocol,
            metadata={"cwd": str(project_root), "agent": agent.model_dump()},
        )

        self.add_mode(
            session.mode_name,
            lambda session=session, project_root=project_root, agent=agent, command=command, resume_session_id=resume_session_id: MainScreen(
                session=session,
                project_root=project_root,
                settings=self.settings,
                agent=agent.model_copy(update={
                    "run_command": {"default": command} if command else {},
                }),
                resume_session_id=resume_session_id,
                watch_manager=self.watch_manager,
            ),
        )
        self.switch_mode(session.mode_name)

        self.notify(f"Launched {agent.name}", title="Bufo")
        self.notifier.send(
            NotificationEvent(title="Bufo", body=f"Launched {agent.name}"),
            app_focused=bool(getattr(self, "app_focus", True)),
        )

    def _resolve_agent(self, identity: str) -> AgentDescriptor | None:
        for agent in self.catalog:
            if agent.identity == identity:
                return agent

        if identity == "__custom__" and self.ad_hoc_agent_command:
            return AgentDescriptor(
                identity="__custom__",
                name=self.ad_hoc_agent_name,
                protocol="acp",
                description="Ad hoc ACP command",
                run_command={"default": self.ad_hoc_agent_command},
            )

        return None

    def permission_modal(self, title: str, detail: str) -> PermissionModal:
        return PermissionModal(title=title, detail=detail)

    def action_open_store(self) -> None:
        self.switch_mode(self.DEFAULT_MODE)
        self._refresh_store_screen()

    def action_open_settings(self) -> None:
        def _on_close(result: AppSettings | None) -> None:
            if result is None:
                return
            self.settings = result
            self.settings_store.save(self.settings)
            self.theme = self.settings.appearance.theme

        self.push_screen(SettingsScreen(self.settings), callback=_on_close)

    def action_open_sessions(self) -> None:
        sessions = self.session_tracker.all()

        def _on_close(mode_name: str | None) -> None:
            if mode_name is None:
                return
            self.switch_mode(mode_name)

        self.push_screen(SessionsScreen(sessions), callback=_on_close)

    def action_next_session(self) -> None:
        self._step_session(+1)

    def action_prev_session(self) -> None:
        self._step_session(-1)

    def _step_session(self, delta: int) -> None:
        sessions = self.session_tracker.all()
        if not sessions:
            return

        mode_names = [session.mode_name for session in sessions]
        if self.current_mode not in mode_names:
            self.switch_mode(mode_names[0])
            return

        idx = mode_names.index(self.current_mode)
        next_idx = (idx + delta) % len(mode_names)
        self.switch_mode(mode_names[next_idx])

    def _refresh_store_screen(self) -> None:
        try:
            store = self.query_one(StoreScreen)
        except NoMatches:
            return

        store.refresh_recent_sessions(self.session_store.recent(limit=50))

    def on_exit(self) -> None:
        self.settings_store.save(self.settings)
        self.telemetry.capture(TelemetryEvent(name="app_exit", properties={"mode": self.current_mode}))
        self.watch_manager.close()


class AcpCommandApp(BufoApp):
    def __init__(self, *, project_root: Path, command: str, name: str) -> None:
        super().__init__(
            project_root=project_root,
            initial_agent="__custom__",
            force_store=False,
            ad_hoc_agent_command=command,
            ad_hoc_agent_name=name,
        )


def _platform_name() -> str:
    if sys.platform.startswith("linux"):
        return "linux"
    if sys.platform == "darwin":
        return "darwin"
    if os.name == "nt":
        return "windows"
    return "default"
