"""Coverage for Settings phantom-preview controller."""

from __future__ import annotations

from typing import cast
from unittest.mock import MagicMock

import pytest

pytest.importorskip("nicegui")

import mypyskindose.gui.phantom_preview_controller as phantom_preview_controller  # noqa: E402
from mypyskindose.gui.phantom_preview_controller import PhantomPreviewController  # noqa: E402
from mypyskindose.gui.state import state  # noqa: E402


def _controller() -> PhantomPreviewController:
    return PhantomPreviewController(MagicMock(), MagicMock(), debounce_sec=0.01)


@pytest.mark.asyncio
async def test_run_refresh_clears_plot_for_non_human() -> None:
    ctrl = _controller()
    state.phantom_model = "plane"
    await ctrl._run_refresh(ctrl.preview_request_id)
    cast(MagicMock, ctrl.plot.update_figure).assert_called_with({})
    cast(MagicMock, ctrl.status_label.set_text).assert_called()


@pytest.mark.asyncio
async def test_run_refresh_skips_stale_request() -> None:
    ctrl = _controller()
    state.phantom_model = "human"
    ctrl.preview_request_id = 5
    await ctrl._run_refresh(4)
    cast(MagicMock, ctrl.plot.update_figure).assert_not_called()


@pytest.mark.asyncio
async def test_run_refresh_applies_figure(monkeypatch: pytest.MonkeyPatch) -> None:
    ctrl = _controller()
    state.phantom_model = "human"
    fig = {"data": [], "layout": {}}

    async def _fake_io_bound(fn, *args, **kwargs):
        return fig

    monkeypatch.setattr(phantom_preview_controller, "capture_phantom_preview_snapshot", lambda st: {"mesh": "hudfrid"})
    monkeypatch.setattr(phantom_preview_controller.run, "io_bound", _fake_io_bound)

    await ctrl._run_refresh(ctrl.preview_request_id)

    cast(MagicMock, ctrl.plot.update_figure).assert_called_with(fig)
    cast(MagicMock, ctrl.status_label.set_text).assert_called_with("")


@pytest.mark.asyncio
async def test_run_refresh_unavailable_when_fig_none(monkeypatch: pytest.MonkeyPatch) -> None:
    ctrl = _controller()
    state.phantom_model = "human"

    async def _fake_io_bound(fn, *args, **kwargs):
        return None

    monkeypatch.setattr(phantom_preview_controller, "capture_phantom_preview_snapshot", lambda st: {})
    monkeypatch.setattr(phantom_preview_controller.run, "io_bound", _fake_io_bound)

    await ctrl._run_refresh(ctrl.preview_request_id)

    cast(MagicMock, ctrl.plot.update_figure).assert_called_with({})
    cast(MagicMock, ctrl.status_label.set_text).assert_called()


def test_schedule_refresh_bumps_request_id(monkeypatch: pytest.MonkeyPatch) -> None:
    from nicegui import ui

    timers: list[object] = []
    monkeypatch.setattr(ui, "timer", lambda *a, **k: timers.append(object()) or MagicMock())
    ctrl = _controller()
    before = ctrl.preview_request_id
    ctrl.schedule_refresh()
    assert ctrl.preview_request_id == before + 1
    assert timers
