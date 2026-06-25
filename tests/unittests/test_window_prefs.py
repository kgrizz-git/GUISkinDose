"""Unit tests for native window geometry preferences."""

from __future__ import annotations

import json

import pytest

pytest.importorskip("nicegui")

from mypyskindose.gui.window_prefs import (
    NativeWindowPrefs,
    ScreenBounds,
    config_path,
    default_normal_bounds,
    geometry_looks_maximized,
    load_native_window_prefs,
    primary_screen,
    save_native_window_prefs,
    title_bar_accessible_on_any_screen,
    validate_prefs,
)

PRIMARY = ScreenBounds(0, 0, 1920, 1080, is_primary=True)
SECONDARY = ScreenBounds(1920, 0, 1280, 720)


def test_load_missing_file_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "mypyskindose.gui.window_prefs.config_path",
        lambda: tmp_path / "missing" / "gui.json",
    )
    assert load_native_window_prefs() is None


def test_load_corrupt_json_returns_none(tmp_path, monkeypatch):
    path = tmp_path / "gui.json"
    path.write_text("{not json", encoding="utf-8")
    monkeypatch.setattr("mypyskindose.gui.window_prefs.config_path", lambda: path)
    assert load_native_window_prefs() is None


def test_load_wrong_schema_returns_none(tmp_path, monkeypatch):
    path = tmp_path / "gui.json"
    path.write_text(
        json.dumps({"schema_version": 2, "native_window": {"maximized": False}}),
        encoding="utf-8",
    )
    monkeypatch.setattr("mypyskindose.gui.window_prefs.config_path", lambda: path)
    assert load_native_window_prefs() is None


def test_load_save_round_trip(tmp_path, monkeypatch):
    monkeypatch.setattr("mypyskindose.gui.window_prefs.config_path", lambda: tmp_path / "gui.json")
    prefs = NativeWindowPrefs(maximized=True, width=1200, height=800, x=100, y=50)
    save_native_window_prefs(prefs)
    loaded = load_native_window_prefs()
    assert loaded == prefs


def test_save_creates_parent_directory(tmp_path, monkeypatch):
    target = tmp_path / "nested" / "gui.json"
    monkeypatch.setattr("mypyskindose.gui.window_prefs.config_path", lambda: target)
    save_native_window_prefs(NativeWindowPrefs(False, 800, 600, 0, 0))
    assert target.is_file()


def test_screen_bounds_coerces_floats():
    screen = ScreenBounds(10.9, 20.1, 800.5, 600.7)
    assert (screen.x, screen.y, screen.width, screen.height) == (10, 20, 800, 600)


def test_primary_screen_prefers_is_primary():
    assert primary_screen([SECONDARY, PRIMARY]) == PRIMARY


def test_primary_screen_uses_largest_without_primary_flag():
    large = ScreenBounds(0, 0, 2560, 1440)
    small = ScreenBounds(0, 0, 1280, 720)
    assert primary_screen([small, large]) == large


def test_geometry_looks_maximized_empty_screens():
    assert geometry_looks_maximized(1920, 1080, []) is False


def test_geometry_looks_maximized_threshold():
    assert geometry_looks_maximized(1700, 900, [PRIMARY]) is False
    assert geometry_looks_maximized(1920, 1000, [PRIMARY]) is True


def test_title_bar_accessible_empty_screens():
    assert title_bar_accessible_on_any_screen(0, 0, 800, 600, []) is False


def test_title_bar_accessible_rejects_above_screen():
    assert title_bar_accessible_on_any_screen(0, -50, 800, 600, [PRIMARY]) is False


def test_title_bar_accessible_accepts_secondary_monitor():
    assert title_bar_accessible_on_any_screen(2000, 50, 800, 600, [PRIMARY, SECONDARY]) is True


def test_validate_prefs_empty_screens_preserves_position():
    prefs = NativeWindowPrefs(False, 800, 600, 2500, 100)
    validated = validate_prefs(prefs, [])
    assert validated.x == 2500
    assert validated.y == 100


def test_validate_prefs_reclamps_off_screen_title_bar():
    prefs = NativeWindowPrefs(False, 800, 600, 100, -50)
    validated = validate_prefs(prefs, [PRIMARY])
    assert title_bar_accessible_on_any_screen(
        validated.x, validated.y, validated.width, validated.height, [PRIMARY]
    )


def test_default_normal_bounds_empty_screens():
    prefs = default_normal_bounds([])
    assert (prefs.width, prefs.height, prefs.x, prefs.y) == (1024, 768, 0, 0)
    assert prefs.maximized is False


def test_default_normal_bounds_centered_seventy_five_percent():
    prefs = default_normal_bounds([PRIMARY])
    assert prefs.width == int(1920 * 0.75)
    assert prefs.height == int(1080 * 0.75)
    assert prefs.x == (1920 - prefs.width) // 2
    assert prefs.y == (1080 - prefs.height) // 2


def test_config_path_under_home():
    assert config_path().name == "gui.json"
    assert config_path().parent.name == ".mypyskindose"


def test_window_prefs_source_has_no_webview_import():
    from pathlib import Path

    import mypyskindose.gui.window_prefs as wp

    source = Path(wp.__file__).read_text(encoding="utf-8")
    assert "import webview" not in source
    assert "from webview" not in source
