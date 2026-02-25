"""Bufo Textual application shell."""

from __future__ import annotations

import asyncio
import os
import sys
import time
from pathlib import Path
from typing import Any, Callable

from textual import events
from textual.app import App, ComposeResult, UnknownModeError
from textual.css.query import NoMatches
from textual.widgets import Footer, Header, Static

from bufo.agents.catalog import AgentRegistry
from bufo.agents.schema import AgentDescriptor
from bufo.config.models import AppSettings
from bufo.config.store import SettingsStore
from bufo.fs.watch import NullWatchManager, WatchManager
from bufo.messages import CreateSession, LaunchAgent, OpenSessions, OpenSettings, ResumeAgent, SwitchSession
from bufo.notifications import NotificationEvent, Notifier
from bufo.persistence.sessions import SessionStore
from bufo.runtime_logging import configure_runtime_logging, get_runtime_logger
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
        bridge_factory: Callable[[str, Path, Any], Any] | None = None,
        enable_watchers: bool = True,
        check_updates: bool = True,
        watch_manager: WatchManager | NullWatchManager | None = None,
        log_level: str | None = None,
        log_file: str | Path | None = None,
    ) -> None:
        self.project_root = project_root.expanduser().resolve()
        self.initial_agent = initial_agent
        self.resume_session_id = resume_session_id
        self.force_store = force_store
        self.ad_hoc_agent_command = ad_hoc_agent_command
        self.ad_hoc_agent_name = ad_hoc_agent_name
        self.bridge_factory = bridge_factory
        self.enable_watchers = enable_watchers
        self.check_updates = check_updates
        self.logger = configure_runtime_logging(level=log_level, log_file=log_file)

        self.settings_store = SettingsStore()
        self.settings = self.settings_store.load()
        self.settings.paths.project_root = str(self.project_root)

        self.session_store = SessionStore()
        self.session_tracker = SessionTracker()
        if watch_manager is not None:
            self.watch_manager = watch_manager
        else:
            self.watch_manager = WatchManager() if enable_watchers else NullWatchManager()
        self._last_copied_selection: str | None = None
        self._last_copied_at = 0.0

        data_dir = Path(__file__).resolve().parent / "data" / "agents"
        self.registry = AgentRegistry(package_data_dir=data_dir)
        loaded = self.registry.load()
        self.catalog = loaded.agents
        self.catalog_warnings = loaded.warnings

        self.notifier = Notifier(self.settings.notifications)
        self.telemetry = Telemetry(self.settings)

        self.logger.info(
            "app.initialized",
            project_root=str(self.project_root),
            enable_watchers=enable_watchers,
            check_updates=check_updates,
        )
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
        self.logger.info("app.mounted", theme=self.theme, catalog_size=len(self.catalog))

        if self.catalog_warnings:
            for warning in self.catalog_warnings:
                self.notify(f"Catalog warning: {warning}", severity="warning")

        self.telemetry.capture(TelemetryEvent(name="app_start", properties={"version": __version__}))
        if self.check_updates:
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
        self.logger.debug("app.update_check.start")
        latest = await check_for_update("bufo")
        if latest:
            self.notify(f"Update available: {latest}", severity="information")
            self.logger.info("app.update_check.available", latest=latest)
        else:
            self.logger.debug("app.update_check.none")

    async def on_launch_agent(self, message: LaunchAgent) -> None:
        self.logger.info(
            "app.launch_agent.requested",
            agent_identity=message.agent_identity,
            project_root=str(message.project_root),
        )
        await self._launch_by_identity(message.agent_identity, project_root=message.project_root)

    async def on_resume_agent(self, message: ResumeAgent) -> None:
        self.logger.info(
            "app.resume_agent.requested",
            agent_identity=message.agent_identity,
            agent_session_id=message.agent_session_id,
            project_root=str(message.project_root),
        )
        existing = self.session_tracker.find_by_agent_pair(
            message.agent_identity,
            message.agent_session_id,
        )
        if existing:
            self.switch_mode(existing.mode_name)
            self.logger.info("app.resume_agent.reused_mode", mode_name=existing.mode_name)
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

    def on_switch_session(self, message: SwitchSession) -> None:
        self.logger.info("app.switch_session.requested", mode_name=message.mode_name)
        self.switch_mode(message.mode_name)

    def on_create_session(self, _message: CreateSession) -> None:
        self.logger.info("app.create_session.requested")
        self.action_open_store()

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
            self.logger.error("app.launch_agent.unknown_identity", agent_identity=agent_identity)
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
                bridge_factory=self.bridge_factory,
            ),
        )
        self.switch_mode(session.mode_name)
        self.logger.info(
            "app.launch_agent.started",
            mode_name=session.mode_name,
            agent_identity=agent.identity,
            resume_session_id=resume_session_id,
            project_root=str(project_root),
        )

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
        self.logger.debug("app.action_open_store")
        try:
            self.switch_mode(self.DEFAULT_MODE)
            self._refresh_store_screen()
            return
        except UnknownModeError:
            self.logger.warning("app.action_open_store.fallback_push_screen")
            self.push_screen(
                StoreScreen(
                    agents=self.catalog,
                    recent_sessions=self.session_store.recent(limit=50),
                    project_root=self.project_root,
                    id="store",
                )
            )

    def action_open_settings(self) -> None:
        self.logger.debug("app.action_open_settings")
        def _on_close(result: AppSettings | None) -> None:
            if result is None:
                return
            self.settings = result
            self.settings_store.save(self.settings)
            self.theme = self.settings.appearance.theme

        self.push_screen(SettingsScreen(self.settings), callback=_on_close)

    def action_open_sessions(self) -> None:
        self.logger.debug("app.action_open_sessions")
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
        self.logger.debug(
            "app.action_step_session",
            delta=delta,
            current_mode=self.current_mode,
            target_mode=mode_names[next_idx],
        )
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
        self.logger.info("app.exit", mode=self.current_mode)
        self.watch_manager.close()

    def on_mouse_up(self, _event: events.MouseUp) -> None:
        # Selection is finalized after mouse events settle.
        self.call_after_refresh(self._copy_selected_text_with_notification)

    def _copy_selected_text_with_notification(self) -> bool:
        selected = self.screen.get_selected_text()
        if not selected:
            return False

        now = time.monotonic()
        if selected == self._last_copied_selection and (now - self._last_copied_at) < 0.5:
            return False

        self.copy_to_clipboard(selected)
        self._last_copied_selection = selected
        self._last_copied_at = now
        self.notify("Copied selection to clipboard", severity="information")
        get_runtime_logger().debug(
            "app.selection.copied",
            chars=len(selected),
            mode=self.current_mode,
        )
        return True


class AcpCommandApp(BufoApp):
    def __init__(
        self,
        *,
        project_root: Path,
        command: str,
        name: str,
        log_level: str | None = None,
        log_file: str | Path | None = None,
    ) -> None:
        super().__init__(
            project_root=project_root,
            initial_agent="__custom__",
            force_store=False,
            ad_hoc_agent_command=command,
            ad_hoc_agent_name=name,
            log_level=log_level,
            log_file=log_file,
        )


def _platform_name() -> str:
    if sys.platform.startswith("linux"):
        return "linux"
    if sys.platform == "darwin":
        return "darwin"
    if os.name == "nt":
        return "windows"
    return "default"
