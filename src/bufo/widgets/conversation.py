"""Conversation orchestrator widget."""

from __future__ import annotations

import asyncio
import shlex
from pathlib import Path
from typing import Any, Callable

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Input, OptionList, Static

from bufo.agents.bridge import AcpAgentBridge, AgentEvent
from bufo.agents.session_updates import normalize_session_update
from bufo.config.models import AppSettings
from bufo.persistence.history import ProjectHistories
from bufo.prompt_resources import expand_prompt_resources
from bufo.runtime_logging import get_runtime_logger
from bufo.shell.persistent import PersistentShell
from bufo.shell.safety import classify_command
from bufo.widgets.selectable_rich_log import SelectableRichLog

_DEFAULT_SLASH_COMMANDS = [
    "/help",
    "/clear",
    "/interrupt",
    "/mode",
    "/mode agent",
    "/mode shell",
    "/mode auto",
]


class Conversation(Vertical):
    DEFAULT_CSS = """
    Conversation {
        height: 1fr;
    }

    #timeline {
        height: 1fr;
        border: round $surface-lighten-2;
        overflow-y: auto;
    }

    #status {
        height: 1;
        color: $text-muted;
    }

    #slash-menu {
        height: auto;
        max-height: 7;
        margin-top: 1;
    }

    .hidden {
        display: none;
    }
    """

    def __init__(
        self,
        *,
        project_root: Path,
        settings: AppSettings,
        agent_identity: str,
        agent_name: str,
        agent_command: str | None,
        resume_session_id: str | None = None,
        mode_name: str,
        bridge_factory: Callable[[str, Path, Any], Any] | None = None,
    ) -> None:
        self.project_root = project_root
        self.settings = settings
        self.agent_identity = agent_identity
        self.agent_name = agent_name
        self.agent_command = agent_command
        self.resume_session_id = resume_session_id
        self.mode_name = mode_name
        self.bridge_factory = bridge_factory or AcpAgentBridge

        self.histories = ProjectHistories(project_root)
        self.shell = PersistentShell(settings.shell.shell_program, project_root)
        self.bridge: AcpAgentBridge | None = None
        self._busy = False
        self._history_cursor = 0
        self._prompt_history = [item.value for item in self.histories.prompt.read()]
        self._slash_commands: list[str] = list(_DEFAULT_SLASH_COMMANDS)
        self._visible_slash_commands: list[str] = []
        self.logger = get_runtime_logger()
        self.timeline_entries: list[str] = []
        super().__init__()

    def compose(self) -> ComposeResult:
        yield SelectableRichLog(id="timeline", wrap=True, markup=True, highlight=False)
        yield Static("idle", id="status")
        yield Input(placeholder="Prompt, slash command, or shell command (!cmd)", id="prompt")
        yield OptionList(id="slash-menu", classes="hidden")

    async def on_mount(self) -> None:
        self.logger.info(
            "conversation.mounted",
            mode_name=self.mode_name,
            agent_identity=self.agent_identity,
            agent_name=self.agent_name,
            project_root=str(self.project_root),
        )
        await self.shell.start()
        self._set_state("notready")
        self._write_line(f"[dim]Project:[/dim] {self.project_root}")
        self._write_line(f"[dim]Agent:[/dim] {self.agent_name}")

        if self.agent_command:
            self.bridge = self.bridge_factory(
                self.agent_command,
                self.project_root,
                self._on_agent_event,
            )
            try:
                await self.bridge.start()
                await self.bridge.initialize()
                if self.resume_session_id:
                    await self.bridge.load_session(
                        session_id=self.resume_session_id,
                        cwd=self.project_root,
                    )
                else:
                    await self.bridge.new_session(cwd=self.project_root)
                self._write_line("[green]Agent bridge connected[/green]")
                self.logger.info(
                    "conversation.bridge.connected",
                    agent_identity=self.agent_identity,
                    agent_name=self.agent_name,
                    resume_session_id=self.resume_session_id,
                )
            except Exception as exc:
                self._write_line(f"[red]Agent bridge failed:[/red] {exc}")
                self.logger.error("conversation.bridge.failed", error=str(exc), agent_identity=self.agent_identity)
        else:
            self._write_line("[yellow]No agent command configured; shell-only mode.[/yellow]")

        self._set_state("idle")

    async def on_unmount(self) -> None:
        self.logger.info("conversation.unmount", mode_name=self.mode_name)
        if self.bridge is not None:
            await self.bridge.stop()
        await self.shell.close()

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        prompt = event.value.strip()
        event.input.value = ""
        self._hide_slash_menu()
        if not prompt:
            return

        selected = self._selected_slash_command()
        if (
            selected is not None
            and prompt.startswith("/")
            and " " not in prompt
            and prompt != selected
        ):
            prompt = selected

        self.histories.prompt.append(prompt)
        self._prompt_history.append(prompt)
        self._history_cursor = len(self._prompt_history)
        self.logger.debug(
            "conversation.prompt.submitted",
            mode_name=self.mode_name,
            prompt=prompt,
        )

        if prompt.startswith("/"):
            await self._handle_slash(prompt)
            return

        if self._is_shell_prompt(prompt):
            command = prompt[1:].strip() if prompt.startswith("!") else prompt
            await self._handle_shell(command)
            return

        await self._handle_agent_prompt(prompt)

    async def on_input_key(self, event: Input.Key) -> None:
        input_widget = event.input
        if self._slash_menu_visible() and event.key in {"up", "down"}:
            menu = self.query_one("#slash-menu", OptionList)
            if event.key == "up":
                menu.action_cursor_up()
            else:
                menu.action_cursor_down()
            event.stop()
            return
        if self._slash_menu_visible() and event.key == "tab":
            self._apply_selected_slash_command()
            event.stop()
            return

        if event.key == "up" and input_widget.cursor_position == 0:
            if self._prompt_history and self._history_cursor > 0:
                self._history_cursor -= 1
                input_widget.value = self._prompt_history[self._history_cursor]
                input_widget.cursor_position = len(input_widget.value)
            event.stop()
        elif event.key == "down" and input_widget.cursor_position == len(input_widget.value):
            if self._history_cursor < len(self._prompt_history) - 1:
                self._history_cursor += 1
                input_widget.value = self._prompt_history[self._history_cursor]
            else:
                self._history_cursor = len(self._prompt_history)
                input_widget.value = ""
            input_widget.cursor_position = len(input_widget.value)
            event.stop()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id != "prompt":
            return
        self._refresh_slash_menu(event.value)

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option_list.id != "slash-menu":
            return
        self._apply_selected_slash_command()
        event.stop()

    async def _handle_slash(self, prompt: str) -> None:
        command, *rest = shlex.split(prompt)
        arg = rest[0] if rest else ""
        self.logger.debug("conversation.prompt.slash", command=command, arg=arg, mode_name=self.mode_name)

        if command == "/help":
            self._write_line("[b]/help[/b], [b]/clear[/b], [b]/mode <agent|shell>[/b], [b]/interrupt[/b]")
        elif command == "/clear":
            self.query_one("#timeline", SelectableRichLog).clear()
        elif command == "/interrupt":
            await self.shell.interrupt()
            self._write_line("[yellow]Interrupt sent to shell[/yellow]")
        elif command == "/mode":
            self.settings.shell.default_mode = arg if arg in {"agent", "shell", "auto"} else "auto"
            self._write_line(f"[cyan]Prompt routing mode set to {self.settings.shell.default_mode}[/cyan]")
            if self.bridge:
                await self.bridge.set_mode(self.settings.shell.default_mode)
        else:
            self._write_line(f"[yellow]Unknown slash command:[/yellow] {command}")

    def _is_shell_prompt(self, prompt: str) -> bool:
        if prompt.startswith("!"):
            return True

        mode = self.settings.shell.default_mode
        if mode == "shell":
            return True
        if mode == "agent":
            return False

        first = prompt.split()[0] if prompt.split() else ""
        likely_shell = {
            "ls",
            "cd",
            "pwd",
            "cat",
            "git",
            "rg",
            "find",
            "cp",
            "mv",
            "rm",
            "mkdir",
            "touch",
            "python",
            "uv",
        }
        return first in likely_shell

    async def _handle_shell(self, command: str) -> None:
        risk = classify_command(command, self.project_root)
        self._write_line(f"[bold cyan]$ {command}[/bold cyan]")
        self.histories.shell.append(command)
        self.logger.debug(
            "conversation.prompt.shell",
            mode_name=self.mode_name,
            command=command,
            risk_level=risk.level,
        )

        if risk.level in {"dangerous", "destructive"}:
            decision = await self._ask_permission(
                "Shell command approval",
                f"{risk.level.upper()}: {risk.reason}\n\n{command}",
            )
            if decision not in {"allow_once", "allow_always"}:
                self._write_line("[red]Command rejected[/red]")
                return

        self._set_state("busy")
        try:
            result = await self.shell.run(command)
            block = (
                f"[dim]exit={result.exit_code} cwd={result.cwd}[/dim]\n"
                f"{result.output if result.output else '[dim](no output)[/dim]'}"
            )
            self._write_line(block)
        except Exception as exc:
            self._write_line(f"[red]Shell error:[/red] {exc}")
            self.logger.error("conversation.shell.error", mode_name=self.mode_name, error=str(exc))
        finally:
            self._set_state("idle")

    async def _handle_agent_prompt(self, prompt: str) -> None:
        self._write_line(f"[bold]You:[/bold] {prompt}")

        if not self.bridge:
            self._write_line("[yellow]No agent bridge active. Use shell commands or configure an agent.[/yellow]")
            return

        transformed, resources = expand_prompt_resources(self.project_root, prompt)
        self.logger.debug(
            "conversation.prompt.agent",
            mode_name=self.mode_name,
            prompt=prompt,
            transformed=transformed,
            resource_count=len(resources),
        )

        self._set_state("busy")
        try:
            await self.bridge.prompt(transformed, resources)
        except Exception as exc:
            self._write_line(f"[red]Agent prompt failed:[/red] {exc}")
            self._set_state("idle")
            self.logger.error("conversation.agent_prompt.failed", mode_name=self.mode_name, error=str(exc))

    async def _on_agent_event(self, event: AgentEvent) -> None:
        self.logger.debug("conversation.agent_event", mode_name=self.mode_name, event_type=event.type)
        if event.type == "session/update":
            self._render_session_update(event.payload)
            return

        if event.type == "permission/request":
            self._set_state("asking")
            detail = str(event.payload)
            decision = await self._ask_permission("Agent permission request", detail)
            self._write_line(f"[yellow]Permission decision:[/yellow] {decision}")
            self._set_state("idle")
            return

        if event.type == "agent/stderr":
            text = event.payload.get("text", "")
            if text.strip():
                self.logger.warning(
                    "conversation.agent_stderr",
                    mode_name=self.mode_name,
                    agent_identity=self.agent_identity,
                    agent_name=self.agent_name,
                    message=text.rstrip(),
                )
            return

        self._write_line(f"[dim]{event.type}: {event.payload}[/dim]")

    def _render_session_update(self, payload: dict[str, Any]) -> None:
        self._update_slash_commands_from_payload(payload)
        events = normalize_session_update(payload)
        for event in events:
            self._write_line(event.text)
            if event.state is not None:
                self._set_state(event.state)

    def _set_state(self, state: str) -> None:
        self._busy = state != "idle"
        self.query_one("#status", Static).update(f"state: {state}")
        self.logger.debug("conversation.state", mode_name=self.mode_name, state=state)
        if hasattr(self.app, "session_tracker"):
            self.app.session_tracker.update_state(self.mode_name, state)  # type: ignore[attr-defined]

    def _write_line(self, text: str) -> None:
        self.timeline_entries.append(text)
        self.query_one("#timeline", SelectableRichLog).write(text)

    def _refresh_slash_menu(self, value: str) -> None:
        text = value.strip()
        if not text.startswith("/") or " " in text:
            self._hide_slash_menu()
            return

        matches = [command for command in self._slash_commands if command.startswith(text)]
        if not matches:
            self._hide_slash_menu()
            return

        menu = self.query_one("#slash-menu", OptionList)
        if matches != self._visible_slash_commands:
            menu.set_options(matches)
            menu.highlighted = 0
            self._visible_slash_commands = matches
        menu.remove_class("hidden")

    def _hide_slash_menu(self) -> None:
        menu = self.query_one("#slash-menu", OptionList)
        menu.add_class("hidden")
        self._visible_slash_commands = []

    def _slash_menu_visible(self) -> bool:
        return "hidden" not in self.query_one("#slash-menu", OptionList).classes

    def _selected_slash_command(self) -> str | None:
        menu = self.query_one("#slash-menu", OptionList)
        highlighted = menu.highlighted
        if highlighted is None or highlighted >= len(menu.options):
            return None
        option = menu.options[highlighted]
        return str(option.prompt)

    def _apply_selected_slash_command(self) -> None:
        selected = self._selected_slash_command()
        if selected is None:
            return
        prompt = self.query_one("#prompt", Input)
        prompt.value = selected
        prompt.cursor_position = len(prompt.value)
        self._hide_slash_menu()

    def _update_slash_commands_from_payload(self, payload: dict[str, Any]) -> None:
        event_items: list[dict[str, Any]] = []
        if isinstance(payload.get("events"), list):
            event_items.extend(event for event in payload["events"] if isinstance(event, dict))
        if isinstance(payload.get("update"), dict):
            event_items.append(payload["update"])
        if not event_items:
            event_items.append(payload)

        commands: list[str] = []
        for event in event_items:
            event_type = str(event.get("type", "")).strip().lower()
            session_update = str(event.get("sessionUpdate", "")).strip().lower()

            source: list[Any] | None = None
            if event_type in {"slash_commands.updated", "slash.updated", "session.commands"}:
                maybe = event.get("commands") or event.get("slash_commands")
                if isinstance(maybe, list):
                    source = maybe
            elif session_update in {"available_commands_update", "slash_commands.updated", "session.commands"}:
                maybe = event.get("availableCommands") or event.get("commands") or event.get("slash_commands")
                if isinstance(maybe, list):
                    source = maybe

            if source is None:
                continue
            for item in source:
                if isinstance(item, dict):
                    name = str(item.get("name", "")).strip()
                else:
                    name = str(item).strip()
                if not name:
                    continue
                commands.append(name if name.startswith("/") else f"/{name}")

        if not commands:
            return
        deduped = list(dict.fromkeys([*_DEFAULT_SLASH_COMMANDS, *commands]))
        if deduped != self._slash_commands:
            self._slash_commands = deduped
            self.logger.debug(
                "conversation.slash_commands.updated",
                mode_name=self.mode_name,
                command_count=len(self._slash_commands),
            )

    async def _ask_permission(self, title: str, detail: str) -> str:
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[str] = loop.create_future()

        modal = self.app.permission_modal(title, detail)  # type: ignore[attr-defined]
        self.app.push_screen(
            modal,
            callback=lambda result: fut.set_result(str(result or "reject_once")),
        )
        return await fut
