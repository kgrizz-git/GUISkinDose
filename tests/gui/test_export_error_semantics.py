"""Step 1.6 substitute for the manual GUI check (HTML_EXPORT_BACKGROUND_TASK_FIX_PLAN.md Task 1).

Driving the interactive GUI end-to-end (load an RDSR, calculate, click Export) was out of
scope for this dispatch, so these tests exercise ``ExportTabController.download_html`` /
``download_png`` directly at the unit level with a real ``nicegui.run.io_bound`` call, forcing
both of the two situations ``require_io_result`` must distinguish:

1. A genuine NiceGUI cancel/shutdown (``run.io_bound`` returns ``None``) — must show the
   "Export cancelled" warning notify, never the render-failure message.
2. A real render failure inside ``make_dosemap_html`` / ``make_dosemap_png`` (an exception
   propagates out of ``run.io_bound``) — must show the actionable negative notify, never the
   "Background task was cancelled" text.

``ui.notify`` is stubbed (capturing calls) rather than run against a live client/slot, matching
the precedent in ``tests/gui/test_gui_operation_guard.py`` — these tests assert only the
notify-dispatch contract, not rendering.
"""

from __future__ import annotations

import pytest

pytest.importorskip("nicegui")

from nicegui import run, ui

from mypyskindose.gui.state import state
from mypyskindose.gui.tabs import export as export_tab


@pytest.fixture(autouse=True)
def _capture_notify(monkeypatch):
    calls: list[tuple[tuple, dict]] = []
    monkeypatch.setattr(ui, "notify", lambda *a, **k: calls.append((a, k)))
    return calls


def _messages(calls: list[tuple[tuple, dict]]) -> list[str]:
    return [str(a[0]) if a else "" for a, _k in calls]


async def _fake_cancelled_io_bound(callback, *args, **kwargs):
    """Mirror NiceGUI's real cancel/shutdown contract: return None, call nothing."""
    return


@pytest.mark.asyncio
async def test_download_html_cancel_shows_cancel_notify_not_render_failure(monkeypatch, _capture_notify):
    state.calculation_done = True
    monkeypatch.setattr(run, "io_bound", _fake_cancelled_io_bound)
    controller = export_tab.ExportTabController()

    await controller.download_html()

    messages = _messages(_capture_notify)
    assert any("cancelled" in m.lower() for m in messages), messages
    assert not any("Background task was cancelled" in m for m in messages), messages


@pytest.mark.asyncio
async def test_download_png_cancel_shows_cancel_notify_not_render_failure(monkeypatch, _capture_notify):
    state.calculation_done = True
    monkeypatch.setattr(run, "io_bound", _fake_cancelled_io_bound)
    controller = export_tab.ExportTabController()

    await controller.download_png()

    messages = _messages(_capture_notify)
    assert any("cancelled" in m.lower() for m in messages), messages
    assert not any("Background task was cancelled" in m for m in messages), messages


@pytest.mark.asyncio
async def test_download_html_render_failure_shows_actionable_notify_not_cancel(monkeypatch, _capture_notify):
    state.calculation_done = True

    def _boom(*a, **k):
        raise ValueError("synthetic render failure — forced for Step 1.6 verification")

    monkeypatch.setattr(export_tab, "make_dosemap_html", _boom)
    controller = export_tab.ExportTabController()

    await controller.download_html()

    messages = _messages(_capture_notify)
    assert messages, "expected at least one ui.notify call on render failure"
    assert not any("Background task was cancelled" in m or "cancelled" in m.lower() for m in messages), messages
    assert any("html_export" in m or "html dose map" in m.lower() for m in messages), messages


@pytest.mark.asyncio
async def test_download_png_render_failure_shows_actionable_notify_not_cancel(monkeypatch, _capture_notify):
    state.calculation_done = True

    def _boom(*a, **k):
        raise ValueError("synthetic render failure — forced for Step 1.6 verification")

    monkeypatch.setattr(export_tab, "make_dosemap_png", _boom)
    controller = export_tab.ExportTabController()

    await controller.download_png()

    messages = _messages(_capture_notify)
    assert messages, "expected at least one ui.notify call on render failure"
    assert not any("Background task was cancelled" in m or "cancelled" in m.lower() for m in messages), messages
    assert any("png_export" in m or "png dose map" in m.lower() for m in messages), messages


@pytest.mark.asyncio
async def test_download_html_builder_runtime_error_shows_actionable_notify_not_cancel(monkeypatch, _capture_notify):
    """Regression test — Task 1 review finding.

    ``make_dosemap_html``/``make_dosemap_png`` raise ``RuntimeError("Dose map figure could not be
    built")`` (not just arbitrary exceptions) when the builder fails. The bare ``raise`` inside the
    old ``except RuntimeError`` handler was a sibling of ``except Exception`` — a re-raised
    exception from one ``except`` clause is NOT caught by a sibling ``except`` on the same
    ``try``, so this exact non-cancel ``RuntimeError`` used to escape the handler uncaught instead
    of producing an actionable notification. This test forces that specific ``RuntimeError`` and
    asserts it is fully handled (does not propagate) and produces a negative, non-cancel notify.
    """
    state.calculation_done = True

    def _boom(*a, **k):
        raise RuntimeError("Dose map figure could not be built")

    monkeypatch.setattr(export_tab, "make_dosemap_html", _boom)
    controller = export_tab.ExportTabController()

    await controller.download_html()  # must not raise — the bug let this escape

    messages = _messages(_capture_notify)
    assert messages, "expected at least one ui.notify call on render failure"
    assert not any("Background task was cancelled" in m or "cancelled" in m.lower() for m in messages), messages
    assert any("html_export" in m or "html dose map" in m.lower() for m in messages), messages
    negative_calls = [(a, k) for a, k in _capture_notify if k.get("type") == "negative"]
    assert negative_calls, "expected at least one negative-type notify"


@pytest.mark.asyncio
async def test_download_png_builder_runtime_error_shows_actionable_notify_not_cancel(monkeypatch, _capture_notify):
    """Regression test — Task 1 review finding (PNG mirror).

    See ``test_download_html_builder_runtime_error_shows_actionable_notify_not_cancel`` for the
    full rationale: a non-cancel ``RuntimeError`` raised by the builder must be fully handled, not
    escape via the broken sibling-``except`` ``raise``.
    """
    state.calculation_done = True

    def _boom(*a, **k):
        raise RuntimeError("Dose map figure could not be built")

    monkeypatch.setattr(export_tab, "make_dosemap_png", _boom)
    controller = export_tab.ExportTabController()

    await controller.download_png()  # must not raise — the bug let this escape

    messages = _messages(_capture_notify)
    assert messages, "expected at least one ui.notify call on render failure"
    assert not any("Background task was cancelled" in m or "cancelled" in m.lower() for m in messages), messages
    assert any("png_export" in m or "png dose map" in m.lower() for m in messages), messages
    negative_calls = [(a, k) for a, k in _capture_notify if k.get("type") == "negative"]
    assert negative_calls, "expected at least one negative-type notify"
