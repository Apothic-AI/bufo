"""Heuristic command danger analyzer for shell prompt UX."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

DESTRUCTIVE_TOKENS = {
    "rm",
    "dd",
    "mkfs",
    "shutdown",
    "reboot",
    "poweroff",
    "chown",
    "chmod",
    "truncate",
}

DANGEROUS_TOKENS = {
    "sudo",
    "curl",
    "wget",
    "scp",
    "mv",
    "cp",
    "tee",
    "sed",
}


@dataclass(slots=True)
class CommandRisk:
    level: str
    reason: str


def classify_command(command: str, project_root: Path) -> CommandRisk:
    stripped = command.strip()
    if not stripped:
        return CommandRisk(level="safe", reason="empty command")

    first = stripped.split()[0]
    if first in DESTRUCTIVE_TOKENS:
        level = "destructive"
        reason = f"contains destructive command token '{first}'"
    elif first in DANGEROUS_TOKENS:
        level = "dangerous"
        reason = f"contains potentially mutating token '{first}'"
    elif first.isalpha():
        level = "unknown"
        reason = "command not in known-safe allowlist"
    else:
        level = "safe"
        reason = "command appears non-mutating"

    if ".." in stripped and level in {"dangerous", "destructive"}:
        return CommandRisk(level="destructive", reason="targets parent path outside project context")

    return CommandRisk(level=level, reason=reason)
