"""Unit tests for native-window startup behavior in gui.app."""

from __future__ import annotations

import pytest

pytest.importorskip("nicegui")

import guiskindose.gui.app as gui_app
from guiskindose.gui.window_prefs import NativeWindowPrefs, ScreenBounds

PRIMARY = ScreenBounds(0, 0, 1920, 1080, is_primary=True)


def test_normalize_macos_maximized_startup_uses_visible_bounds(monkeypatch) -> None:
    monkeypatch.setattr(gui_app.sys, "platform", "darwin")
    monkeypatch.setattr(
        gui_app,
        "_detect_macos_visible_primary_bounds",
        lambda: ScreenBounds(20, 38, 1512, 945, is_primary=True),
    )
    prefs = NativeWindowPrefs(maximized=True, width=1200, height=800, x=100, y=50)

    normalized = gui_app._normalize_macos_maximized_startup(prefs, [PRIMARY])

    assert normalized == NativeWindowPrefs(
        maximized=False,
        width=1512,
        height=945,
        x=20,
        y=38,
    )


def test_normalize_macos_maximized_startup_falls_back_to_primary_screen(monkeypatch) -> None:
    monkeypatch.setattr(gui_app.sys, "platform", "darwin")
    monkeypatch.setattr(gui_app, "_detect_macos_visible_primary_bounds", lambda: None)
    prefs = NativeWindowPrefs(maximized=True, width=1200, height=800, x=100, y=50)

    normalized = gui_app._normalize_macos_maximized_startup(prefs, [PRIMARY])

    assert normalized.maximized is False
    assert normalized.width == int(PRIMARY.width * 0.9)
    assert normalized.height == int(PRIMARY.height * 0.9)
    assert normalized.x == PRIMARY.x + (PRIMARY.width - normalized.width) // 2
    assert normalized.y == PRIMARY.y + (PRIMARY.height - normalized.height) // 2


def test_normalize_macos_maximized_startup_is_noop_off_macos(monkeypatch) -> None:
    monkeypatch.setattr(gui_app.sys, "platform", "linux")
    prefs = NativeWindowPrefs(maximized=True, width=1200, height=800, x=100, y=50)

    normalized = gui_app._normalize_macos_maximized_startup(prefs, [PRIMARY])

    assert normalized == prefs


def test_run_gui_native_persists_normalized_macos_startup(monkeypatch) -> None:
    monkeypatch.setattr(gui_app.sys, "platform", "darwin")
    monkeypatch.setattr(gui_app, "configure_logging", lambda **kwargs: None)
    monkeypatch.setattr(gui_app, "_detect_native_screens", lambda: [PRIMARY])
    monkeypatch.setattr(
        gui_app,
        "_resolve_native_window_prefs",
        lambda screens: NativeWindowPrefs(maximized=True, width=1200, height=800, x=100, y=50),
    )
    monkeypatch.setattr(
        gui_app,
        "_normalize_macos_maximized_startup",
        lambda prefs, screens: NativeWindowPrefs(maximized=False, width=1512, height=945, x=20, y=38),
    )
    monkeypatch.setattr(gui_app, "register_native_geometry_tracking", lambda screens, prefs: None)
    monkeypatch.setattr(gui_app.ui, "run", lambda **kwargs: None)
    monkeypatch.setattr(gui_app.app.native, "window_args", {}, raising=False)

    saved: list[NativeWindowPrefs] = []
    monkeypatch.setattr(gui_app, "save_native_window_prefs", saved.append)

    gui_app.run_gui(native=True)

    assert saved == [NativeWindowPrefs(maximized=False, width=1512, height=945, x=20, y=38)]
    assert gui_app.app.native.window_args["width"] == 1512
    assert gui_app.app.native.window_args["height"] == 945
    assert gui_app.app.native.window_args["x"] == 20
    assert gui_app.app.native.window_args["y"] == 38
    assert "maximized" not in gui_app.app.native.window_args
