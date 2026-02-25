"""Shared watchdog observer manager with update coalescing."""

from __future__ import annotations

import threading
import time
from collections import defaultdict
from pathlib import Path
from typing import Callable

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer


class _DebouncedHandler(FileSystemEventHandler):
    def __init__(self, callback: Callable[[], None], debounce_s: float = 0.25) -> None:
        super().__init__()
        self.callback = callback
        self.debounce_s = debounce_s
        self._lock = threading.Lock()
        self._last_event_at = 0.0
        self._timer: threading.Timer | None = None

    def on_any_event(self, event) -> None:  # type: ignore[override]
        if event.is_directory:
            return

        with self._lock:
            self._last_event_at = time.monotonic()
            if self._timer is not None:
                self._timer.cancel()
            self._timer = threading.Timer(self.debounce_s, self._fire_if_stable)
            self._timer.start()

    def _fire_if_stable(self) -> None:
        with self._lock:
            elapsed = time.monotonic() - self._last_event_at
            if elapsed < self.debounce_s:
                return
        self.callback()


class WatchManager:
    def __init__(self) -> None:
        self._observer = Observer()
        self._observer.start()
        self._handlers: dict[Path, _DebouncedHandler] = {}
        self._refcount: dict[Path, int] = defaultdict(int)

    def watch(self, path: Path, callback: Callable[[], None]) -> None:
        key = path.resolve()
        self._refcount[key] += 1

        if key in self._handlers:
            return

        handler = _DebouncedHandler(callback)
        self._handlers[key] = handler
        self._observer.schedule(handler, str(key), recursive=True)

    def unwatch(self, path: Path) -> None:
        key = path.resolve()
        if key not in self._refcount:
            return

        self._refcount[key] -= 1
        if self._refcount[key] > 0:
            return

        del self._refcount[key]
        # watchdog does not support unschedule by path cleanly on all backends,
        # so we keep observer alive and drop callback references.
        self._handlers.pop(key, None)

    def close(self) -> None:
        self._observer.stop()
        self._observer.join(timeout=2)
