"""Expand @path prompt references into ACP content resources."""

from __future__ import annotations

import base64
import mimetypes
import re
from pathlib import Path
from typing import Any

_PATTERN = re.compile(r"(?<!\S)@(?P<path>[\w./-]+)")


def expand_prompt_resources(project_root: Path, prompt: str) -> tuple[str, list[dict[str, Any]]]:
    resources: list[dict[str, Any]] = []

    def repl(match: re.Match[str]) -> str:
        rel_path = match.group("path")
        path = (project_root / rel_path).resolve()

        try:
            path.relative_to(project_root.resolve())
        except ValueError:
            return match.group(0)

        if not path.exists() or not path.is_file():
            return match.group(0)

        mime = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        data = path.read_bytes()
        if mime.startswith("text/"):
            resources.append(
                {
                    "type": "text",
                    "path": rel_path,
                    "mime": mime,
                    "text": data.decode("utf-8", errors="replace"),
                }
            )
        else:
            resources.append(
                {
                    "type": "binary",
                    "path": rel_path,
                    "mime": mime,
                    "base64": base64.b64encode(data).decode("ascii"),
                }
            )

        return rel_path

    transformed = _PATTERN.sub(repl, prompt)
    return transformed, resources
