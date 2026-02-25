"""Active sessions overview screen."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, ListItem, ListView, Static

from bufo.sessions.tracker import SessionMeta


class SessionsScreen(ModalScreen[str | None]):
    DEFAULT_CSS = """
    SessionsScreen {
        align: center middle;
    }

    SessionsScreen > Vertical {
        width: 80;
        height: auto;
        max-height: 70%;
        border: round $secondary;
        background: $surface;
        padding: 1;
    }

    SessionsScreen ListView {
        height: 1fr;
        min-height: 8;
    }
    """

    def __init__(self, sessions: list[SessionMeta]) -> None:
        self.sessions = sessions
        super().__init__()

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("[b]Sessions[/b]", markup=True)
            items = [
                ListItem(Static(f"{session.title} [{session.state}] ({session.mode_name})", markup=False), id=session.mode_name)
                for session in self.sessions
            ]
            yield ListView(*items, id="session-list")
            yield Button("Close", id="close", variant="primary")

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        item_id = event.item.id if event.item else None
        self.dismiss(item_id)

    def on_button_pressed(self, _event: Button.Pressed) -> None:
        self.dismiss(None)
