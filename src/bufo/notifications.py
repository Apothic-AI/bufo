"""In-app and OS notification helpers."""

from __future__ import annotations

from dataclasses import dataclass

from bufo.config.models import NotificationSettings

try:
    from notifypy import Notify
except Exception:  # pragma: no cover
    Notify = None


@dataclass(slots=True)
class NotificationEvent:
    title: str
    body: str
    severity: str = "info"


class Notifier:
    def __init__(self, settings: NotificationSettings) -> None:
        self.settings = settings

    def send(self, event: NotificationEvent, *, app_focused: bool = True) -> None:
        if self.settings.only_when_unfocused and app_focused:
            return

        if not self.settings.desktop:
            return

        if Notify is None:
            return

        note = Notify()
        note.title = event.title
        note.message = event.body
        with_sound = self.settings.sound
        if with_sound:
            try:
                note.audio = "default"
            except Exception:
                pass
        try:
            note.send()
        except Exception:
            return
