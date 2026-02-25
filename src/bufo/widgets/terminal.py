"""Terminal output widget used for shell and tool output blocks."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Label

from bufo.widgets.selectable_rich_log import SelectableRichLog


class TerminalPane(Vertical):
    DEFAULT_CSS = """
    TerminalPane {
        border: round $primary;
        height: auto;
        min-height: 8;
        margin: 1 0;
    }

    TerminalPane > Label {
        text-style: bold;
        padding: 0 1;
    }

    TerminalPane > SelectableRichLog {
        height: auto;
        max-height: 20;
        overflow-y: auto;
    }
    """

    def __init__(self, title: str = "Terminal", *, id: str | None = None) -> None:
        self.title = title
        super().__init__(id=id)

    def compose(self) -> ComposeResult:
        yield Label(self.title)
        yield SelectableRichLog(id="terminal-log", wrap=True, markup=False, highlight=False)

    def write(self, text: str) -> None:
        self.query_one("#terminal-log", SelectableRichLog).write(text.rstrip())
