"""Path ignore filtering using .gitignore and hardcoded exclusions."""

from __future__ import annotations

from pathlib import Path

import pathspec


class PathFilter:
    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root.resolve()
        self._spec = self._build_spec()

    def _build_spec(self) -> pathspec.PathSpec:
        patterns: list[str] = [".git/", ".venv/", "node_modules/"]

        root = self.project_root
        for parent in [root, *root.parents]:
            gitignore = parent / ".gitignore"
            if not gitignore.exists():
                continue

            for line in gitignore.read_text(encoding="utf-8", errors="replace").splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                patterns.append(line)

            if parent == root:
                break

        return pathspec.PathSpec.from_lines("gitwildmatch", patterns)

    def include(self, path: Path) -> bool:
        try:
            rel = path.resolve().relative_to(self.project_root)
        except ValueError:
            return False

        rel_text = rel.as_posix()
        return not self._spec.match_file(rel_text)
