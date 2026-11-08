"""Unit tests for native phantom-pack file open helper."""

from __future__ import annotations

import builtins
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

pytest.importorskip("anyio")

from guiskindose.gui import io_helpers


@pytest.mark.asyncio
async def test_open_phantom_pack_stream_cancelled_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:

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
