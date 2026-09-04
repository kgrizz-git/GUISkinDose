"""Debounced Settings phantom-preview controller (NiceGUI).

Owns the Plotly panel refresh lifecycle: request-id gating, debounce timer,
UI-thread snapshot capture, and ``run.io_bound`` figure builds. Does not read
live ``state`` on the worker — only via ``capture_phantom_preview_snapshot``.
"""

from __future__ import annotations

from typing import Any

from nicegui import run, ui

from .constants import GEOMETRY_DEBOUNCE_SEC
from .phantom_preview import capture_phantom_preview_snapshot, make_phantom_preview_fig
from .state import state
from .ui_copy import copy_text


class PhantomPreviewController:
    """Schedule and apply Settings phantom preview figure updates."""

    def __init__(
        self,
        plot: Any,
        status_label: Any,
        *,
        debounce_sec: float = GEOMETRY_DEBOUNCE_SEC,
    ) -> None:
        self.plot = plot
        self.status_label = status_label
        self.debounce_sec = float(debounce_sec)
        self._timer: Any | None = None
        self.preview_request_id = 0

    def schedule_refresh(self) -> None:
        """Bump generation id, cancel pending timer, start one-shot debounce."""
        self.preview_request_id += 1
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None
        request_id = self.preview_request_id

        async def _fire() -> None:
            await self._run_refresh(request_id)

        self._timer = ui.timer(self.debounce_sec, _fire, once=True)

    async def _run_refresh(self, request_id: int) -> None:
        self._timer = None
        if request_id != self.preview_request_id:
            return

        if state.phantom_model != "human":
            if request_id == self.preview_request_id:
                self.plot.update_figure({})
                self.status_label.set_text(copy_text("settings.phantom_preview.human_only"))
            return

        snapshot = capture_phantom_preview_snapshot(state)
        fig = await run.io_bound(make_phantom_preview_fig, snapshot)
        if request_id != self.preview_request_id:
            return

        if fig is None:
            self.plot.update_figure({})
            self.status_label.set_text(copy_text("settings.phantom_preview.unavailable"))
            return

        self.plot.update_figure(fig)
        self.status_label.set_text("")
