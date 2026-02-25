"""Modal screens for permission questions and diffs."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Static


class PermissionModal(ModalScreen[str]):
    DEFAULT_CSS = """
    PermissionModal {
        align: center middle;
    }

    PermissionModal > Vertical {
        width: 80;
        height: auto;
        border: round $warning;
        background: $surface;
        padding: 1;
    }

    PermissionModal Button {
        width: 1fr;
        margin: 1 0;
    }
    """

    def __init__(self, title: str, detail: str) -> None:
        super().__init__()
        self.permission_title = title
        self.detail = detail

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static(f"[b]{self.permission_title}[/b]\n\n{self.detail}", markup=True)
            yield Button("Allow Once", id="allow_once", variant="success")
            yield Button("Reject Once", id="reject_once", variant="error")
            yield Button("Allow Always", id="allow_always")
            yield Button("Reject Always", id="reject_always")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        decision = event.button.id or "reject_once"
        self.dismiss(decision)


class DiffModal(ModalScreen[None]):
    DEFAULT_CSS = """
    DiffModal {
        align: center middle;
    }

    DiffModal > Vertical {
        width: 120;
        height: 80%;
        border: round $accent;
        background: $surface;
        padding: 1;
    }

    DiffModal Static {
        overflow: auto;
        height: 1fr;
    }
    """

    def __init__(self, title: str, diff_text: str) -> None:
        super().__init__()
        self.diff_title = title
        self.diff_text = diff_text

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static(f"[b]{self.diff_title}[/b]", markup=True)
            yield Static(self.diff_text)
            yield Button("Close", id="close", variant="primary")

    def on_button_pressed(self, _event: Button.Pressed) -> None:
        self.dismiss(None)
