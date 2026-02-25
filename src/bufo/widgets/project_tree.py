"""Project file tree panel with scanner + watcher refresh."""

from __future__ import annotations

import asyncio
from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Button, Tree

from bufo.fs.scanner import scan_tree
from bufo.fs.watch import WatchManager


class ProjectTreePanel(Vertical):
    DEFAULT_CSS = """
    ProjectTreePanel {
        height: 1fr;
    }

    ProjectTreePanel Tree {
        height: 1fr;
        border: round $surface-lighten-2;
    }

    ProjectTreePanel Button {
        margin-top: 1;
    }
    """

    def __init__(self, project_root: Path, watch_manager: WatchManager | None = None) -> None:
        self.project_root = project_root
        self.watch_manager = watch_manager
        super().__init__()

    def compose(self) -> ComposeResult:
        yield Tree(f"{self.project_root.name}/", id="tree")
        yield Button("Refresh", id="refresh-tree")

    def on_mount(self) -> None:
        self.refresh_tree()
        if self.watch_manager is not None:
            self.watch_manager.watch(self.project_root, self._watch_callback)

    def on_unmount(self) -> None:
        if self.watch_manager is not None:
            self.watch_manager.unwatch(self.project_root)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "refresh-tree":
            self.refresh_tree()

    def refresh_tree(self) -> None:
        self.run_worker(self._scan_and_render(), group="project-tree", exclusive=True)

    async def _scan_and_render(self) -> None:
        entries = await asyncio.to_thread(scan_tree, self.project_root, max_duration_s=1.5)
        tree = self.query_one(Tree)
        tree.clear()
        root = tree.root
        root.set_label(f"{self.project_root.name}/")

        # Keep render bounded for responsiveness.
        for entry in entries[:400]:
            rel = entry.path.relative_to(self.project_root)
            root.add_leaf(rel.as_posix() + ("/" if entry.is_dir else ""))
        root.expand()

    def _watch_callback(self) -> None:
        self.app.call_from_thread(self.refresh_tree)
