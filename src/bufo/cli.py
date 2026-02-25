"""CLI entrypoint for Bufo."""

from __future__ import annotations

import json
from pathlib import Path

import click

from bufo.app import AcpCommandApp, BufoApp
from bufo.paths import settings_path
from bufo.version import __version__


@click.group(invoke_without_command=True, context_settings={"help_option_names": ["-h", "--help"]})
@click.pass_context
def main(ctx: click.Context) -> None:
    """Bufo: terminal-first AI orchestration for ACP agents."""
    if ctx.invoked_subcommand is None:
        ctx.invoke(run)


@main.command()
@click.argument("project_dir", required=False, default=".")
@click.option("--agent", "agent_identity", help="Agent identity to launch immediately")
@click.option("--resume", "resume_session_id", help="Resume by agent session ID")
@click.option("--store", "force_store", is_flag=True, help="Open store screen on startup")
@click.option("--serve", is_flag=True, help="Run with textual-serve if available")
@click.option("--host", default="127.0.0.1", show_default=True)
@click.option("--port", default=8123, type=int, show_default=True)
@click.option("--public", is_flag=True, help="Expose via public URL when supported")
def run(
    project_dir: str,
    agent_identity: str | None,
    resume_session_id: str | None,
    force_store: bool,
    serve: bool,
    host: str,
    port: int,
    public: bool,
) -> None:
    """Run Bufo."""
    project_root = Path(project_dir).expanduser().resolve()

    if serve:
        _serve_app(project_root, agent_identity, resume_session_id, force_store, host, port, public)
        return

    app = BufoApp(
        project_root=project_root,
        initial_agent=agent_identity,
        resume_session_id=resume_session_id,
        force_store=force_store,
    )
    app.run()


@main.command()
@click.argument("project_dir", required=False, default=".")
@click.option("--host", default="127.0.0.1", show_default=True)
@click.option("--port", default=8123, type=int, show_default=True)
@click.option("--public", is_flag=True)
def serve(project_dir: str, host: str, port: int, public: bool) -> None:
    """Serve Bufo via browser using textual-serve."""
    project_root = Path(project_dir).expanduser().resolve()
    _serve_app(project_root, None, None, True, host, port, public)


@main.command("acp")
@click.argument("command")
@click.option("--name", default="Custom ACP", show_default=True)
@click.argument("project_dir", required=False, default=".")
def acp_command(command: str, name: str, project_dir: str) -> None:
    """Run a custom ACP command without catalog installation."""
    app = AcpCommandApp(
        project_root=Path(project_dir).expanduser().resolve(),
        command=command,
        name=name,
    )
    app.run()


@main.command("settings-path")
def settings_path_command() -> None:
    """Print settings file path."""
    click.echo(str(settings_path()))


@main.command()
def about() -> None:
    """Show version and project summary."""
    payload = {
        "name": "bufo",
        "version": __version__,
        "description": "TUI and Web UI framework for AI agents",
    }
    click.echo(json.dumps(payload, indent=2))


@main.command()
@click.argument("path")
@click.option("--limit", type=int, default=100, show_default=True)
def replay(path: str, limit: int) -> None:
    """Replay a JSONL stream for ACP debugging."""
    file_path = Path(path).expanduser().resolve()
    if not file_path.exists():
        raise click.ClickException(f"File not found: {file_path}")

    lines = file_path.read_text(encoding="utf-8", errors="replace").splitlines()
    for line in lines[-limit:]:
        click.echo(line)


def _serve_app(
    project_root: Path,
    agent_identity: str | None,
    resume_session_id: str | None,
    force_store: bool,
    host: str,
    port: int,
    public: bool,
) -> None:
    try:
        from textual_serve.server import Server
    except Exception as exc:
        raise click.ClickException(
            f"textual-serve is not available in this environment: {exc}"
        )

    app = BufoApp(
        project_root=project_root,
        initial_agent=agent_identity,
        resume_session_id=resume_session_id,
        force_store=force_store,
    )
    server = Server(app, host=host, port=port, public_url=public)
    server.serve()


if __name__ == "__main__":
    main()
