"""Unit tests for native phantom-pack file open helper."""

from __future__ import annotations

import asyncio
import builtins
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

pytest.importorskip("anyio")

from guiskindose.gui import io_helpers


@pytest.mark.asyncio
async def test_open_phantom_pack_stream_dialog_cancel_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:

    class _MainWindow:
        async def create_file_dialog(self, *_args, **_kwargs):
            return None

    async def _io_bound(fn, *args, **kwargs):
        return fn(*args, **kwargs)

    nicegui = SimpleNamespace(
        app=SimpleNamespace(native=SimpleNamespace(main_window=_MainWindow())),
        run=SimpleNamespace(io_bound=_io_bound),
    )
    webview = SimpleNamespace(FileDialog=SimpleNamespace(OPEN=1), OPEN_DIALOG=1)
    monkeypatch.setitem(sys.modules, "nicegui", nicegui)
    monkeypatch.setitem(sys.modules, "webview", webview)
    assert await io_helpers.open_phantom_pack_stream() is None


@pytest.mark.asyncio
async def test_open_phantom_pack_stream_dialog_failure_propagates(monkeypatch: pytest.MonkeyPatch) -> None:
    """A dialog error is not a cancel: it must reach the caller, not become ``None``."""

    class _MainWindow:
        async def create_file_dialog(self, *_args, **_kwargs):
            raise RuntimeError("dialog failed")

    nicegui = SimpleNamespace(
        app=SimpleNamespace(native=SimpleNamespace(main_window=_MainWindow())),
        run=SimpleNamespace(io_bound=AsyncMock()),
    )
    webview = SimpleNamespace(FileDialog=SimpleNamespace(OPEN=1), OPEN_DIALOG=1)
    monkeypatch.setitem(sys.modules, "nicegui", nicegui)
    monkeypatch.setitem(sys.modules, "webview", webview)

    with pytest.raises(RuntimeError, match="dialog failed"):
        await io_helpers.open_phantom_pack_stream()


def _native_modules(monkeypatch: pytest.MonkeyPatch, *, result) -> AsyncMock:
    """Install a fake native window whose dialog returns *result*; return the io_bound mock."""

    class _MainWindow:
        async def create_file_dialog(self, *_args, **_kwargs):
            return result

    io_bound = AsyncMock(return_value="stream")
    nicegui = SimpleNamespace(
        app=SimpleNamespace(native=SimpleNamespace(main_window=_MainWindow())),
        run=SimpleNamespace(io_bound=io_bound),
    )
    monkeypatch.setitem(sys.modules, "nicegui", nicegui)
    monkeypatch.setitem(sys.modules, "webview", SimpleNamespace(FileDialog=SimpleNamespace(OPEN=1), OPEN_DIALOG=1))
    return io_bound


@pytest.mark.asyncio
@pytest.mark.parametrize("result", [None, (), [], ""])
async def test_open_phantom_pack_stream_any_empty_result_is_a_cancel(monkeypatch: pytest.MonkeyPatch, result) -> None:
    """pywebview may report a cancel as None, an empty tuple or list, or an empty string."""
    io_bound = _native_modules(monkeypatch, result=result)

    assert await io_helpers.open_phantom_pack_stream() is None
    io_bound.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("result", [("pack.zip",), ["pack.zip"], "pack.zip"])
async def test_open_phantom_pack_stream_opens_the_chosen_file(monkeypatch: pytest.MonkeyPatch, result) -> None:
    """A tuple, a list, or a bare string all open the chosen file."""
    io_bound = _native_modules(monkeypatch, result=result)

    assert await io_helpers.open_phantom_pack_stream() == "stream"
    io_bound.assert_awaited_once_with(open, "pack.zip", "rb")


@pytest.mark.asyncio
async def test_open_phantom_pack_stream_missing_webview_propagates(monkeypatch: pytest.MonkeyPatch) -> None:
    """In native mode a missing pywebview is a failure to report, not a silent cancel."""
    _native_modules(monkeypatch, result=None)
    monkeypatch.setitem(sys.modules, "webview", None)  # makes ``import webview`` raise ImportError

    with pytest.raises(ImportError):
        await io_helpers.open_phantom_pack_stream()


@pytest.mark.asyncio
async def test_open_phantom_pack_stream_cancellation_propagates(monkeypatch: pytest.MonkeyPatch) -> None:
    """A cancelled io_bound open raises; nothing turns it into a ``None`` result."""

    class _MainWindow:
        async def create_file_dialog(self, *_args, **_kwargs):
            return ["/tmp/phantom-pack.zip"]

    async def _io_bound(_fn, *_args, **_kwargs):
        raise asyncio.CancelledError("The app has shut down.")

    nicegui = SimpleNamespace(
        app=SimpleNamespace(native=SimpleNamespace(main_window=_MainWindow())),
        run=SimpleNamespace(io_bound=_io_bound),
    )
    webview = SimpleNamespace(FileDialog=SimpleNamespace(OPEN=1), OPEN_DIALOG=1)
    monkeypatch.setitem(sys.modules, "nicegui", nicegui)
    monkeypatch.setitem(sys.modules, "webview", webview)

    with pytest.raises(asyncio.CancelledError):
        await io_helpers.open_phantom_pack_stream()


@pytest.mark.asyncio
async def test_open_phantom_pack_stream_open_failure_propagates(monkeypatch: pytest.MonkeyPatch) -> None:

    class _MainWindow:
        async def create_file_dialog(self, *_args, **_kwargs):
            return ["/tmp/phantom-pack.zip"]

    def _boom(_path: str, _mode: str = "rb"):
        raise OSError("cannot open")

    nicegui = SimpleNamespace(
        app=SimpleNamespace(native=SimpleNamespace(main_window=_MainWindow())),
        run=SimpleNamespace(io_bound=AsyncMock(side_effect=lambda fn, *a, **k: fn(*a, **k))),
    )
    webview = SimpleNamespace(FileDialog=SimpleNamespace(OPEN=1), OPEN_DIALOG=1)
    monkeypatch.setitem(sys.modules, "nicegui", nicegui)
    monkeypatch.setitem(sys.modules, "webview", webview)
    monkeypatch.setattr(builtins, "open", _boom)
    with pytest.raises(OSError, match="cannot open"):
        await io_helpers.open_phantom_pack_stream()
