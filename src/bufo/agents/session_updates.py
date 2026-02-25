"""Normalize ACP session updates into timeline render events."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable


@dataclass(slots=True)
class RenderEvent:
    text: str
    state: str | None = None


_STATE_VALUES = {"notready", "busy", "asking", "idle"}


def normalize_session_update(payload: dict[str, Any]) -> list[RenderEvent]:
    events: list[RenderEvent] = []

    event_items = payload.get("events")
    if isinstance(event_items, list):
        for event in event_items:
            if isinstance(event, dict):
                _map_event(event, events)
    else:
        _map_event(payload, events)

    if not events:
        events.append(RenderEvent(text=_compact(payload)))

    return events


def _map_event(event: dict[str, Any], events: list[RenderEvent]) -> None:
    nested = event.get("update")
    if isinstance(nested, dict):
        _map_event(nested, events)
        if events:
            return

    event_type = str(event.get("type", "")).strip().lower()

    if event_type:
        _map_typed_event(event_type, event, events)
        return

    session_update = str(event.get("sessionUpdate", event.get("session_update", ""))).strip().lower()
    if session_update:
        _map_session_update(session_update, event, events)
        return

    # Legacy / shorthand payloads used by various ACP implementations.
    if "response" in event:
        events.append(RenderEvent(text=f"[green]Agent:[/green] {event['response']}"))
    if "chunk" in event:
        events.append(RenderEvent(text=str(event["chunk"])))
    if "thought" in event:
        events.append(RenderEvent(text=f"[dim]Thought:[/dim] {event['thought']}"))
    if "plan" in event:
        plan_text = _render_plan(event["plan"])
        events.append(RenderEvent(text=f"[cyan]Plan:[/cyan] {plan_text}"))

    tool = event.get("tool_call")
    if tool is not None:
        events.extend(_render_tool_event(tool, fallback_status="update"))

    maybe_state = event.get("state")
    if isinstance(maybe_state, str) and maybe_state in _STATE_VALUES:
        events.append(RenderEvent(text=f"[dim]state -> {maybe_state}[/dim]", state=maybe_state))


def _map_typed_event(event_type: str, event: dict[str, Any], events: list[RenderEvent]) -> None:
    if event_type in {
        "response.chunk",
        "assistant.chunk",
        "message.chunk",
        "message.delta",
        "response.delta",
    }:
        chunk = event.get("text") or event.get("delta") or event.get("chunk")
        if chunk:
            events.append(RenderEvent(text=str(chunk)))
        return

    if event_type in {
        "response.completed",
        "response.message",
        "assistant.message",
        "message.completed",
    }:
        text = event.get("text") or event.get("response") or event.get("content")
        if text is not None:
            events.append(RenderEvent(text=f"[green]Agent:[/green] {_compact(text)}"))
        return

    if event_type in {"thought", "thought.delta", "reasoning", "reasoning.delta"}:
        text = event.get("text") or event.get("thought") or event.get("delta")
        if text is not None:
            events.append(RenderEvent(text=f"[dim]Thought:[/dim] {_compact(text)}"))
        return

    if event_type in {"plan", "plan.updated", "plan.delta"}:
        events.append(RenderEvent(text=f"[cyan]Plan:[/cyan] {_render_plan(event.get('plan') or event.get('items') or event)}"))
        return

    if event_type in {
        "tool_call.started",
        "tool_call.delta",
        "tool_call.completed",
        "tool_call.failed",
        "tool_call.cancelled",
        "tool.call",
        "tool_call",
    }:
        tool = event.get("tool_call") or event
        fallback = event_type.split(".")[-1]
        events.extend(_render_tool_event(tool, fallback_status=fallback))
        return

    if event_type in {"mode.updated", "session.mode", "session_mode.updated"}:
        mode = event.get("mode")
        if mode is not None:
            events.append(RenderEvent(text=f"[blue]Mode:[/blue] {mode}"))
        return

    if event_type in {"slash_commands.updated", "slash.updated", "session.commands"}:
        commands = event.get("commands") or event.get("slash_commands") or []
        events.append(RenderEvent(text=f"[blue]Slash Commands:[/blue] {_render_sequence(commands)}"))
        return

    if event_type in {"session.state", "state.updated", "session.updated"}:
        maybe_state = event.get("state")
        if isinstance(maybe_state, str) and maybe_state in _STATE_VALUES:
            events.append(RenderEvent(text=f"[dim]state -> {maybe_state}[/dim]", state=maybe_state))
        elif event:
            events.append(RenderEvent(text=f"[dim]{event_type}: {_compact(event)}[/dim]"))
        return

    if event_type in {"permission.requested", "permission.request"}:
        details = event.get("message") or event.get("reason") or _compact(event)
        events.append(RenderEvent(text=f"[yellow]Permission requested:[/yellow] {details}"))
        return

    events.append(RenderEvent(text=f"[dim]{event_type}: {_compact(event)}[/dim]"))


def _map_session_update(session_update: str, event: dict[str, Any], events: list[RenderEvent]) -> None:
    if session_update in {"agent_message_chunk", "agent.message.chunk"}:
        text = _extract_text(event.get("content"))
        if text:
            events.append(RenderEvent(text=text))
        return

    if session_update in {"agent_message", "agent.message", "agent_message_completed"}:
        text = (
            _extract_text(event.get("content"))
            or _extract_text(event.get("message"))
            or _extract_text(event.get("text"))
        )
        if text is not None:
            events.append(RenderEvent(text=f"[green]Agent:[/green] {_compact(text)}"))
        return

    if session_update in {"current_mode_update", "session_mode.updated", "mode.updated"}:
        mode = event.get("currentModeId") or event.get("modeId") or event.get("mode")
        if mode is not None:
            events.append(RenderEvent(text=f"[blue]Mode:[/blue] {mode}"))
        return

    if session_update in {"available_commands_update", "slash_commands.updated", "session.commands"}:
        commands = event.get("availableCommands") or event.get("commands") or event.get("slash_commands") or []
        events.append(RenderEvent(text=f"[blue]Slash Commands:[/blue] {_render_commands(commands)}"))
        return

    maybe_state = event.get("state")
    if isinstance(maybe_state, str) and maybe_state in _STATE_VALUES:
        events.append(RenderEvent(text=f"[dim]state -> {maybe_state}[/dim]", state=maybe_state))
        return

    events.append(RenderEvent(text=f"[dim]{session_update}: {_compact(event)}[/dim]"))


def _render_tool_event(tool: Any, fallback_status: str) -> list[RenderEvent]:
    if isinstance(tool, list):
        rendered: list[RenderEvent] = []
        for item in tool:
            rendered.extend(_render_tool_event(item, fallback_status=fallback_status))
        return rendered

    if not isinstance(tool, dict):
        return [RenderEvent(text=f"[magenta]Tool:[/magenta] {_compact(tool)}")]

    name = tool.get("name") or tool.get("tool") or tool.get("id") or "tool"
    status = str(tool.get("status") or fallback_status)

    detail = tool.get("output")
    if detail is None:
        detail = tool.get("error")
    if detail is None:
        detail = tool.get("delta")

    base = f"[magenta]Tool[/magenta] {name} ({status})"
    if detail is None:
        return [RenderEvent(text=base)]
    return [RenderEvent(text=f"{base}: {_compact(detail)}")]


def _render_plan(plan: Any) -> str:
    if isinstance(plan, str):
        return plan
    if isinstance(plan, dict):
        items = plan.get("items") or plan.get("steps")
        if items is not None:
            return _render_sequence(items)
        return _compact(plan)
    if isinstance(plan, list):
        return _render_sequence(plan)
    return _compact(plan)


def _render_sequence(values: Iterable[Any]) -> str:
    return " | ".join(_compact(value) for value in values)


def _render_commands(values: Any) -> str:
    if not isinstance(values, list):
        return _compact(values)

    normalized: list[str] = []
    for value in values:
        if isinstance(value, dict):
            name = str(value.get("name", "")).strip()
        else:
            name = str(value).strip()
        if not name:
            continue
        normalized.append(name if name.startswith("/") else f"/{name}")

    if not normalized:
        return "[]"
    return _render_sequence(normalized)


def _extract_text(value: Any) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        text = value.get("text")
        if isinstance(text, str):
            return text
        inner = value.get("content")
        if inner is not None:
            return _extract_text(inner)
    if isinstance(value, list):
        chunks = [_extract_text(item) for item in value]
        filtered = [item for item in chunks if item]
        if filtered:
            return "".join(filtered)
    return None


def _compact(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float, bool)) or value is None:
        return str(value)
    if isinstance(value, list):
        return "[" + ", ".join(_compact(item) for item in value) + "]"
    if isinstance(value, dict):
        pairs = ", ".join(f"{key}={_compact(val)}" for key, val in value.items())
        return "{" + pairs + "}"
    return repr(value)
