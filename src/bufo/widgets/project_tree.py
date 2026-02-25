"""Project file tree panel with scanner + watcher refresh."""

from __future__ import annotations

import asyncio
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Tree

from bufo.fs.scanner import scan_tree
from bufo.fs.watch import WatchManager
from bufo.runtime_logging import get_runtime_logger


class ProjectTreePanel(Vertical):
    DEFAULT_CSS = """
    ProjectTreePanel {
        height: 1fr;
    }

    ProjectTreePanel Tree {
        height: 1fr;
        border: round $surface-lighten-2;
    }
    """

    def __init__(self, project_root: Path, watch_manager: WatchManager | None = None) -> None:
        self.project_root = project_root
        self.watch_manager = watch_manager
        self.logger = get_runtime_logger()
        self._worker_group = f"project-tree-{id(self)}"
        super().__init__()

    def compose(self) -> ComposeResult:
        yield Tree(f"{self.project_root.name}/", id="tree")

    def on_mount(self) -> None:
        self.refresh_tree()
        if self.watch_manager is not None:
            self.logger.debug("project_tree.watch.start", project_root=str(self.project_root))
            self.watch_manager.watch(self.project_root, self._watch_callback)

    def on_unmount(self) -> None:
        if self.watch_manager is not None:
            self.watch_manager.unwatch(self.project_root, self._watch_callback)
            self.logger.debug("project_tree.watch.stop", project_root=str(self.project_root))

    def refresh_tree(self) -> None:
        self.logger.debug("project_tree.refresh.requested", project_root=str(self.project_root))
        self.run_worker(self._scan_and_render(), group=self._worker_group, exclusive=True)

    async def _scan_and_render(self) -> None:
        entries = await asyncio.to_thread(scan_tree, self.project_root, max_duration_s=1.5)
        self.logger.debug(
            "project_tree.refresh.scanned",
            entry_count=len(entries),
            project_root=str(self.project_root),
        )
        tree = self.query_one(Tree)
        expanded_paths = self._collect_expanded_paths(tree.root)
        tree.clear()
        root = tree.root
        root.set_label(f"{self.project_root.name}/")
        root.data = {"path": "", "is_dir": True}

        node_map: dict[tuple[str, ...], Any] = {(): root}
        # Keep render bounded for responsiveness, but deterministic for visual stability.
        for entry in self._sorted_entries(entries[:400]):
            rel = entry.path.relative_to(self.project_root)
            parts = rel.parts
            parent_key = parts[:-1]
            parent_node = self._ensure_parent(node_map, parent_key)
            label = parts[-1]
            rel_path = rel.as_posix()
            if entry.is_dir:
                node = parent_node.add(
                    f"{label}/",
                    data={"path": rel_path, "is_dir": True},
                    expand=False,
                )
                node_map[parts] = node
            else:
                parent_node.add_leaf(label, data={"path": rel_path, "is_dir": False})

        for parts, node in node_map.items():
            if parts in expanded_paths:
                node.expand()
        root.expand()

    def _watch_callback(self) -> None:
        self.logger.debug("project_tree.watch.callback", project_root=str(self.project_root))
        self.app.call_from_thread(self.refresh_tree)

    def _collect_expanded_paths(self, node: Any) -> set[tuple[str, ...]]:
        expanded: set[tuple[str, ...]] = set()
        data = node.data if isinstance(getattr(node, "data", None), dict) else {}
        path = str(data.get("path", "")).strip()
        if node.is_expanded:
            expanded.add(tuple(part for part in path.split("/") if part))
        for child in node.children:
            expanded.update(self._collect_expanded_paths(child))
        return expanded

    def _ensure_parent(self, node_map: dict[tuple[str, ...], Any], parts: tuple[str, ...]) -> Any:
        if parts in node_map:
            return node_map[parts]

        parent = self._ensure_parent(node_map, parts[:-1])
        label = parts[-1]
        rel_path = "/".join(parts)
        node = parent.add(
            f"{label}/",
            data={"path": rel_path, "is_dir": True},
            expand=False,
        )
        node_map[parts] = node
        return node

    def _sorted_entries(self, entries: Iterable[Any]) -> list[Any]:
        return sorted(
            entries,
            key=lambda item: (
                item.path.relative_to(self.project_root).parts,
                0 if item.is_dir else 1,
            ),
        )
