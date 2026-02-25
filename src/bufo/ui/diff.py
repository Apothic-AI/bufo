"""Diff rendering helpers for permission review surfaces."""

from __future__ import annotations

import difflib
from dataclasses import dataclass


@dataclass(slots=True)
class DiffDocument:
    path: str
    before: str
    after: str


def render_unified(doc: DiffDocument, context: int = 3) -> str:
    lines = difflib.unified_diff(
        doc.before.splitlines(),
        doc.after.splitlines(),
        fromfile=f"a/{doc.path}",
        tofile=f"b/{doc.path}",
        lineterm="",
        n=context,
    )
    return "\n".join(lines)


def render_split(doc: DiffDocument) -> str:
    before = doc.before.splitlines()
    after = doc.after.splitlines()
    rows: list[str] = [f"--- {doc.path} (left=before | right=after)"]

    max_len = max(len(before), len(after))
    for idx in range(max_len):
        left = before[idx] if idx < len(before) else ""
        right = after[idx] if idx < len(after) else ""
        rows.append(f"{idx + 1:>4} | {left:<60} | {right}")

    return "\n".join(rows)
