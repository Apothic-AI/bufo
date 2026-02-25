"""Concurrent filesystem scanning used by tree/path selectors."""

from __future__ import annotations

import concurrent.futures
import time
from dataclasses import dataclass
from pathlib import Path

from bufo.fs.filtering import PathFilter


@dataclass(slots=True)
class ScanEntry:
    path: Path
    is_dir: bool


def scan_tree(
    project_root: Path,
    *,
    max_duration_s: float = 4.0,
    max_workers: int = 8,
) -> list[ScanEntry]:
    project_root = project_root.resolve()
    path_filter = PathFilter(project_root)
    started = time.monotonic()
    entries: list[ScanEntry] = []

    def walk_dir(path: Path) -> list[Path]:
        try:
            return sorted(path.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower()))
        except OSError:
            return []

    pending = [project_root]

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
        while pending and (time.monotonic() - started) < max_duration_s:
            chunk = pending[: max_workers * 2]
            pending = pending[max_workers * 2 :]

            futures = {pool.submit(walk_dir, path): path for path in chunk}
            for future in concurrent.futures.as_completed(futures):
                for child in future.result():
                    if not path_filter.include(child):
                        continue
                    is_dir = child.is_dir()
                    entries.append(ScanEntry(path=child, is_dir=is_dir))
                    if is_dir:
                        pending.append(child)

    return entries
