"""Unit tests for the native save-dialog helpers."""

from __future__ import annotations

import asyncio
import logging
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

pytest.importorskip("anyio")

from guiskindose.gui import io_helpers


def _native_modules(monkeypatch: pytest.MonkeyPatch, *, result) -> None:
    """Install a fake native window whose dialog returns *result*."""

    class _MainWindow:
        async def create_file_dialog(self, *_args, **_kwargs):
            return result

    nicegui = SimpleNamespace(
        app=SimpleNamespace(native=SimpleNamespace(main_window=_MainWindow())),
    )
    monkeypatch.setitem(sys.modules, "nicegui", nicegui)
    monkeypatch.setitem(sys.modules, "webview", SimpleNamespace(FileDialog=SimpleNamespace(SAVE=1), SAVE_DIALOG=1))


@pytest.mark.asyncio
@pytest.mark.parametrize("result", [None, (), [], ""])
async def test_request_native_save_path_any_empty_result_is_a_cancel(
    monkeypatch: pytest.MonkeyPatch, result
) -> None:
    """A falsy dialog result is a genuine cancel, not a failure."""
    _native_modules(monkeypatch, result=result)

    assert await io_helpers._request_native_save_path("out.json", "json") is None


@pytest.mark.asyncio
@pytest.mark.parametrize("result", [("out.json",), ["out.json"], "out.json"])
async def test_request_native_save_path_returns_the_chosen_path(
    monkeypatch: pytest.MonkeyPatch, result
) -> None:
    """A tuple, a list, or a bare string all resolve to the chosen path."""
    _native_modules(monkeypatch, result=result)

    assert await io_helpers._request_native_save_path("out.json", "json") == "out.json"


@pytest.mark.asyncio
async def test_request_native_save_path_dialog_failure_propagates(monkeypatch: pytest.MonkeyPatch) -> None:
    """A dialog error is not a cancel: it must reach the wrapper, not become ``None``."""

    class _MainWindow:
        async def create_file_dialog(self, *_args, **_kwargs):
            raise RuntimeError("dialog failed")

    nicegui = SimpleNamespace(
        app=SimpleNamespace(native=SimpleNamespace(main_window=_MainWindow())),
    )
    monkeypatch.setitem(sys.modules, "nicegui", nicegui)
    monkeypatch.setitem(sys.modules, "webview", SimpleNamespace(FileDialog=SimpleNamespace(SAVE=1), SAVE_DIALOG=1))

    with pytest.raises(RuntimeError, match="dialog failed"):
        await io_helpers._request_native_save_path("out.json", "json")


@pytest.mark.asyncio
async def test_request_native_save_path_missing_webview_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """In native mode a missing pywebview is a failure to report, not a silent cancel."""
    _native_modules(monkeypatch, result=None)
    monkeypatch.setitem(sys.modules, "webview", None)  # makes ``import webview`` raise ImportError

    with pytest.raises(ImportError):
        await io_helpers._request_native_save_path("out.json", "json")


@pytest.mark.asyncio
async def test_request_native_save_path_browser_mode_skips_webview(monkeypatch: pytest.MonkeyPatch) -> None:
    """Browser mode returns ``None`` before ``webview`` is ever imported."""
    nicegui = SimpleNamespace(
        app=SimpleNamespace(native=SimpleNamespace(main_window=None)),
    )
    monkeypatch.setitem(sys.modules, "nicegui", nicegui)
    monkeypatch.setitem(sys.modules, "webview", None)  # would raise if imported

    assert await io_helpers._request_native_save_path("out.json", "json") is None


@pytest.mark.asyncio
async def test_request_native_save_path_without_native_window_guard_returns_none(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """When the native-window lookup itself fails, browser fallback applies."""
    monkeypatch.delitem(sys.modules, "nicegui", raising=False)

    class _BrokenApp:
        @property
        def native(self):
            raise RuntimeError("no app context")

    monkeypatch.setitem(sys.modules, "nicegui", SimpleNamespace(app=_BrokenApp()))

    with caplog.at_level(logging.DEBUG, logger=io_helpers.logger.name):
        assert await io_helpers._request_native_save_path("out.json", "json") is None
    records = [r for r in caplog.records if "native_save_dialog_window_lookup" in r.getMessage()]
    assert records
    assert all(r.levelno == logging.DEBUG for r in records)
    assert all("no app context" not in r.getMessage() for r in caplog.records)


@pytest.mark.asyncio
async def test_get_save_path_browser_mode_returns_none_without_dialog(monkeypatch: pytest.MonkeyPatch) -> None:
    """The wrapper passes browser-mode ``None`` through with no notification."""
    notify = AsyncMock()
    nicegui = SimpleNamespace(
        app=SimpleNamespace(native=SimpleNamespace(main_window=None)),
        ui=SimpleNamespace(notify=notify),
    )
    monkeypatch.setitem(sys.modules, "nicegui", nicegui)

    assert await io_helpers._get_save_path("out.json", "json") is None


@pytest.mark.asyncio
async def test_get_save_path_cancellation_propagates(monkeypatch: pytest.MonkeyPatch) -> None:
    """A cancelled shutdown raises; nothing turns it into a ``None`` result."""

    async def _cancelled(_default_name: str, _extension: str):
        raise asyncio.CancelledError("The app has shut down.")

    monkeypatch.setattr(io_helpers, "_request_native_save_path", _cancelled)

    with pytest.raises(asyncio.CancelledError):
        await io_helpers._get_save_path("out.json", "json")
