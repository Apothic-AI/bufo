"""Conversation orchestrator widget."""

from __future__ import annotations

import asyncio
import shlex
from pathlib import Path
from typing import Any

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Input, RichLog, Static

from bufo.agents.bridge import AcpAgentBridge, AgentEvent
from bufo.config.models import AppSettings
from bufo.persistence.history import ProjectHistories
from bufo.prompt_resources import expand_prompt_resources
from bufo.shell.persistent import PersistentShell
from bufo.shell.safety import classify_command


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
    """

    def __init__(
        self,
        *,
        project_root: Path,
        settings: AppSettings,
        agent_identity: str,
        agent_command: str | None,
        resume_session_id: str | None = None,
        mode_name: str,
    ) -> None:
        self.project_root = project_root
        self.settings = settings
        self.agent_identity = agent_identity
        self.agent_command = agent_command
        self.resume_session_id = resume_session_id
        self.mode_name = mode_name

        self.histories = ProjectHistories(project_root)
        self.shell = PersistentShell(settings.shell.shell_program, project_root)
        self.bridge: AcpAgentBridge | None = None
        self._busy = False
        self._history_cursor = 0
        self._prompt_history = [item.value for item in self.histories.prompt.read()]
        super().__init__()

    def compose(self) -> ComposeResult:
        yield RichLog(id="timeline", wrap=True, markup=True, highlight=False)
        yield Static("idle", id="status")
        yield Input(placeholder="Prompt, slash command, or shell command (!cmd)", id="prompt")

    async def on_mount(self) -> None:
        await self.shell.start()
        self._set_state("notready")
        self._write_line(f"[dim]Project:[/dim] {self.project_root}")
        self._write_line(f"[dim]Agent:[/dim] {self.agent_identity}")

        if self.agent_command:
            self.bridge = AcpAgentBridge(
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
            except Exception as exc:
                self._write_line(f"[red]Agent bridge failed:[/red] {exc}")
        else:
            self._write_line("[yellow]No agent command configured; shell-only mode.[/yellow]")

        self._set_state("idle")

    async def on_unmount(self) -> None:
        if self.bridge is not None:
            await self.bridge.stop()
        await self.shell.close()

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        prompt = event.value.strip()
        event.input.value = ""
        if not prompt:
            return

        self.histories.prompt.append(prompt)
        self._prompt_history.append(prompt)
        self._history_cursor = len(self._prompt_history)

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

    async def _handle_slash(self, prompt: str) -> None:
        command, *rest = shlex.split(prompt)
        arg = rest[0] if rest else ""

        if command == "/help":
            self._write_line("[b]/help[/b], [b]/clear[/b], [b]/mode <agent|shell>[/b], [b]/interrupt[/b]")
        elif command == "/clear":
            self.query_one("#timeline", RichLog).clear()
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
        finally:
            self._set_state("idle")

    async def _handle_agent_prompt(self, prompt: str) -> None:
        self._write_line(f"[bold]You:[/bold] {prompt}")

        if not self.bridge:
            self._write_line("[yellow]No agent bridge active. Use shell commands or configure an agent.[/yellow]")
            return

        transformed, resources = expand_prompt_resources(self.project_root, prompt)

        self._set_state("busy")
        try:
            await self.bridge.prompt(transformed, resources)
        except Exception as exc:
            self._write_line(f"[red]Agent prompt failed:[/red] {exc}")
            self._set_state("idle")

    async def _on_agent_event(self, event: AgentEvent) -> None:
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
            self._write_line(f"[dim red]stderr:[/dim red] {text.rstrip()}")
            return

        self._write_line(f"[dim]{event.type}: {event.payload}[/dim]")

    def _render_session_update(self, payload: dict[str, Any]) -> None:
        if "response" in payload:
            self._write_line(f"[green]Agent:[/green] {payload['response']}")
        if "chunk" in payload:
            self._write_line(str(payload["chunk"]))
        if "thought" in payload:
            self._write_line(f"[dim]Thought:[/dim] {payload['thought']}")
        if "plan" in payload:
            self._write_line(f"[cyan]Plan:[/cyan] {payload['plan']}")
        if "tool_call" in payload:
            self._write_line(f"[magenta]Tool:[/magenta] {payload['tool_call']}")
        if payload.get("state") in {"notready", "busy", "asking", "idle"}:
            self._set_state(str(payload["state"]))

    def _set_state(self, state: str) -> None:
        self._busy = state != "idle"
        self.query_one("#status", Static).update(f"state: {state}")
        if hasattr(self.app, "session_tracker"):
            self.app.session_tracker.update_state(self.mode_name, state)  # type: ignore[attr-defined]

    def _write_line(self, text: str) -> None:
        self.query_one("#timeline", RichLog).write(text)

    async def _ask_permission(self, title: str, detail: str) -> str:
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[str] = loop.create_future()

        modal = self.app.permission_modal(title, detail)  # type: ignore[attr-defined]
        self.app.push_screen(
            modal,
            callback=lambda result: fut.set_result(str(result or "reject_once")),
        )
        return await fut
