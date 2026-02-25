"""Schema-driven settings screen."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, DataTable, Input, Static

from bufo.config.models import AppSettings


class SettingsScreen(ModalScreen[AppSettings | None]):
    DEFAULT_CSS = """
    SettingsScreen {
        align: center middle;
    }

    SettingsScreen > Vertical {
        width: 100;
        height: 80%;
        border: round $primary;
        background: $surface;
        padding: 1;
    }

    SettingsScreen DataTable {
        height: 1fr;
    }
    """

    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings
        self.filtered: list[tuple[str, str]] = settings.setting_items()
        super().__init__()

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("[b]Settings[/b]", markup=True)
            yield Input(placeholder="Filter settings", id="filter")
            yield DataTable(id="table")
            yield Button("Close", id="close", variant="primary")

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        table.add_columns("Setting", "Value")
        self._render_rows("")

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id != "filter":
            return
        self._render_rows(event.value)

    def _render_rows(self, query: str) -> None:
        q = query.strip().lower()
        table = self.query_one(DataTable)
        table.clear(columns=False)
        for key, value in self.filtered:
            blob = f"{key} {value}".lower()
            if q and q not in blob:
                continue
            table.add_row(key, value)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "close":
            self.dismiss(self.settings)
