"""Shared watchdog observer manager with update coalescing."""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any, Callable

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from bufo.runtime_logging import get_runtime_logger


class _DebouncedHandler(FileSystemEventHandler):
    def __init__(
        self,
        callback: Callable[[], None],
        *,
        path: Path,
        debounce_s: float = 0.25,
    ) -> None:
        super().__init__()
        self.callback = callback
        self.path = path
        self.debounce_s = debounce_s
        self._lock = threading.Lock()
        self._last_event_at = 0.0
        self._timer: threading.Timer | None = None
        self._logger = get_runtime_logger()

    def on_any_event(self, event) -> None:  # type: ignore[override]
        with self._lock:
            self._last_event_at = time.monotonic()
            if self._timer is not None:
                self._timer.cancel()
            self._timer = threading.Timer(self.debounce_s, self._fire_if_stable)
            self._timer.start()
        self._logger.debug(
            "watch.event",
            path=str(self.path),
            event_type=getattr(event, "event_type", "unknown"),
            is_directory=bool(getattr(event, "is_directory", False)),
            src_path=str(getattr(event, "src_path", "")),
        )

    def _fire_if_stable(self) -> None:
        with self._lock:
            elapsed = time.monotonic() - self._last_event_at
            if elapsed < self.debounce_s:
                return
        try:
            self.callback()
            self._logger.debug("watch.callback.fired", path=str(self.path))
        except Exception as exc:
            self._logger.error("watch.callback.failed", path=str(self.path), error=str(exc))


class WatchManager:
    def __init__(self) -> None:
        self._observer = Observer()
        self._observer.start()
        self._handlers: dict[Path, _DebouncedHandler] = {}
        self._callbacks: dict[Path, list[Callable[[], None]]] = {}
        self._watches: dict[Path, Any] = {}
        self._logger = get_runtime_logger()
        self._logger.info("watch.manager.started")

    def watch(self, path: Path, callback: Callable[[], None]) -> None:
        key = path.resolve()
        callbacks = self._callbacks.setdefault(key, [])
        callbacks.append(callback)
        if key in self._handlers:
            self._logger.debug("watch.manager.reused", path=str(key), callback_count=len(callbacks))
            return

        def dispatch() -> None:
            for cb in list(self._callbacks.get(key, [])):
                cb()

        handler = _DebouncedHandler(dispatch, path=key)
        self._handlers[key] = handler
        self._watches[key] = self._observer.schedule(handler, str(key), recursive=True)
        self._logger.info("watch.manager.watch", path=str(key), callback_count=len(callbacks))

    def unwatch(self, path: Path, callback: Callable[[], None] | None = None) -> None:
        key = path.resolve()
        callbacks = self._callbacks.get(key)
        if callbacks is None:
            return

        if callback is None:
            if callbacks:
                callbacks.pop()
        else:
            try:
                callbacks.remove(callback)
            except ValueError:
                pass

        if callbacks:
            self._logger.debug("watch.manager.unwatch.defer", path=str(key), callback_count=len(callbacks))
            return

        self._callbacks.pop(key, None)
        watch = self._watches.pop(key, None)
        if watch is not None:
            try:
                self._observer.unschedule(watch)
            except Exception:
                pass
        self._handlers.pop(key, None)
        self._logger.info("watch.manager.unwatch", path=str(key))

    def close(self) -> None:
        self._observer.stop()
        self._observer.join(timeout=2)
        self._callbacks.clear()
        self._handlers.clear()
        self._watches.clear()
        self._logger.info("watch.manager.closed")


class NullWatchManager:
    """No-op watcher for tests and restricted environments."""

    def watch(self, path: Path, callback: Callable[[], None]) -> None:  # noqa: ARG002
        return

    def unwatch(self, path: Path, callback: Callable[[], None] | None = None) -> None:  # noqa: ARG002
        return

    def close(self) -> None:
        return
