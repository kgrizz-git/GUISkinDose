"""Unit tests for GUI first-run onboarding preferences."""

from __future__ import annotations

import json

import pytest

pytest.importorskip("nicegui")

import mypyskindose.gui.window_prefs as window_prefs
from mypyskindose.gui.onboarding import dismiss_onboarding, is_onboarding_dismissed, reset_onboarding
from mypyskindose.gui.window_prefs import NativeWindowPrefs, save_native_window_prefs


def test_is_onboarding_dismissed_false_for_missing_file(tmp_path, monkeypatch):
    monkeypatch.setattr(window_prefs, "config_path", lambda: tmp_path / "gui.json")

    assert is_onboarding_dismissed() is False


def test_is_onboarding_dismissed_false_when_key_missing_or_false(tmp_path, monkeypatch):
    target = tmp_path / "gui.json"
    monkeypatch.setattr(window_prefs, "config_path", lambda: target)

    target.write_text(json.dumps({"schema_version": 1}), encoding="utf-8")
    assert is_onboarding_dismissed() is False

    target.write_text(json.dumps({"onboardingDismissed": False}), encoding="utf-8")
    assert is_onboarding_dismissed() is False


def test_is_onboarding_dismissed_true_when_key_true(tmp_path, monkeypatch):
    target = tmp_path / "gui.json"
    target.write_text(json.dumps({"onboardingDismissed": True}), encoding="utf-8")
    monkeypatch.setattr(window_prefs, "config_path", lambda: target)

    assert is_onboarding_dismissed() is True


def test_dismiss_onboarding_writes_true_and_preserves_existing_keys(tmp_path, monkeypatch):
    target = tmp_path / "gui.json"
    target.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "native_window": {"maximized": True, "width": 1024, "height": 768, "x": 0, "y": 0},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(window_prefs, "config_path", lambda: target)

    dismiss_onboarding()

    loaded = json.loads(target.read_text(encoding="utf-8"))
    assert loaded["onboardingDismissed"] is True
    assert loaded["native_window"]["maximized"] is True


def test_reset_onboarding_writes_false_and_preserves_existing_keys(tmp_path, monkeypatch):
    target = tmp_path / "gui.json"
    target.write_text(json.dumps({"schema_version": 1, "custom": "keep", "onboardingDismissed": True}), encoding="utf-8")
    monkeypatch.setattr(window_prefs, "config_path", lambda: target)

    reset_onboarding()

    loaded = json.loads(target.read_text(encoding="utf-8"))
    assert loaded["onboardingDismissed"] is False
    assert loaded["custom"] == "keep"


def test_corrupt_gui_config_defaults_to_not_dismissed(tmp_path, monkeypatch):
    target = tmp_path / "gui.json"
    target.write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(window_prefs, "config_path", lambda: target)

    assert is_onboarding_dismissed() is False


def test_native_window_save_after_dismiss_preserves_onboarding_flag(tmp_path, monkeypatch):
    target = tmp_path / "gui.json"
    monkeypatch.setattr(window_prefs, "config_path", lambda: target)

    dismiss_onboarding()
    save_native_window_prefs(NativeWindowPrefs(False, 900, 700, 10, 20))

    loaded = json.loads(target.read_text(encoding="utf-8"))
    assert loaded["onboardingDismissed"] is True
    assert loaded["native_window"]["width"] == 900
