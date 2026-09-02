"""Native-window geometry tracking for the NiceGUI desktop (pywebview) mode.

Owns debounced resize/move commits and preference persistence so ``app.run_gui``
stays a thin launcher. Browser mode does not use this module.
"""

from __future__ import annotations

import asyncio

from nicegui import app
from nicegui.events import NativeEventArguments

from .window_prefs import (
    NativeWindowPrefs,
    ScreenBounds,
    geometry_looks_maximized,
    save_native_window_prefs,
)


class NativeGeometryTracker:
    """Debounce native window geometry events and persist prefs on settle/close."""

    def __init__(self, screens: list[ScreenBounds], initial: NativeWindowPrefs) -> None:
        self._screens = screens
        self._current = NativeWindowPrefs(
            maximized=initial.maximized,
            width=initial.width,
            height=initial.height,
            x=initial.x,
            y=initial.y,
        )
        self._commit_task: asyncio.Task[None] | None = None
        self._save_task: asyncio.Task[None] | None = None
        self._pending_commit: NativeEventArguments | None = None

    def apply_pending_commit_sync(self) -> None:
        """Apply the latest pending resize/move when the window is not maximized."""
        if self._pending_commit is None or self._current.maximized:
            return
        event = self._pending_commit
        self._pending_commit = None
        if event.type == "resized":
            width, height = int(event.args["width"]), int(event.args["height"])
            if geometry_looks_maximized(width, height, self._screens):
                return
            self._current.width, self._current.height = width, height
        elif event.type == "moved":
            self._current.x, self._current.y = int(event.args["x"]), int(event.args["y"])

    def schedule_geometry_commit(self, event: NativeEventArguments) -> None:
        """Debounce resize/move commits until the window settles (~300 ms)."""
        self._pending_commit = event
        if self._commit_task is not None:
            self._commit_task.cancel()

        async def _commit_after_settle() -> None:
            await asyncio.sleep(0.3)
            self.apply_pending_commit_sync()

        self._commit_task = asyncio.create_task(_commit_after_settle())

    def schedule_debounced_save(self) -> None:
        """Persist prefs after a short idle window (~1 s)."""
        if self._save_task is not None:
            self._save_task.cancel()

        async def _wait_and_save() -> None:
            await asyncio.sleep(1.0)
            save_native_window_prefs(self._current)

        self._save_task = asyncio.create_task(_wait_and_save())

    def apply_native_event(self, event: NativeEventArguments) -> None:
        """Handle a single native window event and schedule a prefs save."""
        if event.type == "maximized":
            self._current.maximized = True
            if self._commit_task is not None:
                self._commit_task.cancel()
                self._commit_task = None
        elif event.type == "restored":
            self._current.maximized = False
        elif event.type in ("resized", "moved"):
            self.schedule_geometry_commit(event)
        self.schedule_debounced_save()

    def on_native_closed(self, _event: NativeEventArguments) -> None:
        """Flush pending geometry and persist prefs when the native window closes."""
        if self._commit_task is not None:
            self._commit_task.cancel()
            self._commit_task = None
        self.apply_pending_commit_sync()
        if self._save_task is not None:
            self._save_task.cancel()
            self._save_task = None
        save_native_window_prefs(self._current)


def register_native_geometry_tracking(
    screens: list[ScreenBounds],
    initial: NativeWindowPrefs,
) -> NativeGeometryTracker:
    """Wire :class:`NativeGeometryTracker` handlers onto ``app.native``."""
    tracker = NativeGeometryTracker(screens, initial)
    app.native.on("resized", tracker.apply_native_event)
    app.native.on("moved", tracker.apply_native_event)
    app.native.on("maximized", tracker.apply_native_event)
    app.native.on("restored", tracker.apply_native_event)
    app.native.on("closed", tracker.on_native_closed)
    return tracker
