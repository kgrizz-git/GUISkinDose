"""Export render-failure vs cancellation contract.

Driving the interactive GUI end-to-end (load an RDSR, calculate, click Export) was out of
scope for this dispatch, so these tests exercise ``ExportTabController.download_html`` /
``download_png`` directly at the unit level with a patched ``nicegui.run.io_bound``, forcing
the two situations the handlers must tell apart:

1. A NiceGUI cancellation/shutdown (NiceGUI 4.0 raises ``asyncio.CancelledError`` instead of
   returning ``None``) — must propagate without a render-failure notification.
2. A real render failure inside ``make_dosemap_html`` / ``make_dosemap_png`` (an exception
   propagates out of ``run.io_bound``) — must show the actionable negative notify.

``ui.notify`` is stubbed (capturing calls) rather than run against a live client/slot, matching
the precedent in ``tests/gui/test_gui_operation_guard.py`` — these tests assert only the
notify-dispatch contract, not rendering.
"""

from __future__ import annotations

import asyncio

import pytest

pytest.importorskip("nicegui")

from nicegui import run, ui

from guiskindose.export.png_browser import (
    BUNDLED_BROWSER_MESSAGE,
    PNG_RENDER_MESSAGE,
    BundledBrowserUnavailableError,
    PngRenderError,
)
from guiskindose.gui.state import state
from guiskindose.gui.tabs import export as export_tab


@pytest.fixture(autouse=True)
def _capture_notify(monkeypatch):
    calls: list[tuple[tuple, dict]] = []
    monkeypatch.setattr(ui, "notify", lambda *a, **k: calls.append((a, k)))
    return calls


def _messages(calls: list[tuple[tuple, dict]]) -> list[str]:
    return [str(a[0]) if a else "" for a, _k in calls]


async def _fake_cancelled_io_bound(callback, *args, **kwargs):
    """Mirror NiceGUI 4's cancel/shutdown contract: raise, never return."""
    raise asyncio.CancelledError("The app has shut down.")


@pytest.mark.asyncio
async def test_download_html_cancel_propagates_without_render_failure(monkeypatch, _capture_notify):
    state.calculation_done = True
    monkeypatch.setattr(run, "io_bound", _fake_cancelled_io_bound)
    controller = export_tab.ExportTabController()

    with pytest.raises(asyncio.CancelledError):
        await controller.download_html()

    assert _messages(_capture_notify) == []


@pytest.mark.asyncio
async def test_download_png_cancel_propagates_without_render_failure(monkeypatch, _capture_notify):
    state.calculation_done = True
    monkeypatch.setattr(run, "io_bound", _fake_cancelled_io_bound)
    monkeypatch.setattr(export_tab, "png_export_available", lambda: True)
    controller = export_tab.ExportTabController()

    with pytest.raises(asyncio.CancelledError):
        await controller.download_png()

    assert _messages(_capture_notify) == []


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
    assert not any("cancelled" in m.lower() for m in messages), messages
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
    assert not any("cancelled" in m.lower() for m in messages), messages
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
    assert not any("cancelled" in m.lower() for m in messages), messages
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
    assert not any("cancelled" in m.lower() for m in messages), messages
    assert any("png_export" in m or "png dose map" in m.lower() for m in messages), messages
    negative_calls = [(a, k) for a, k in _capture_notify if k.get("type") == "negative"]
    assert negative_calls, "expected at least one negative-type notify"


@pytest.mark.asyncio
async def test_download_png_bundled_browser_missing_shows_bundled_message_not_kaleido(monkeypatch, _capture_notify):
    state.calculation_done = True

    def _boom(*a, **k):
        raise BundledBrowserUnavailableError()

    monkeypatch.setattr(export_tab, "make_dosemap_png", _boom)
    controller = export_tab.ExportTabController()

    await controller.download_png()

    messages = _messages(_capture_notify)
    assert BUNDLED_BROWSER_MESSAGE in messages, messages
    assert not any("kaleido" in m for m in messages), messages


@pytest.mark.asyncio
async def test_download_png_render_error_shows_render_message_not_kaleido(monkeypatch, _capture_notify):
    state.calculation_done = True

    def _boom(*a, **k):
        raise PngRenderError()

    monkeypatch.setattr(export_tab, "make_dosemap_png", _boom)
    controller = export_tab.ExportTabController()

    await controller.download_png()

    messages = _messages(_capture_notify)
    assert PNG_RENDER_MESSAGE in messages, messages
    assert not any("kaleido" in m for m in messages), messages
