"""Tests for packaging/portable/selfcheck.py pure helper functions."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any

import pytest

_PORTABLE = Path(__file__).resolve().parents[2] / "packaging" / "portable"


@pytest.fixture(scope="module")
def selfcheck() -> Any:
    sys.path.insert(0, str(_PORTABLE))
    try:
        yield importlib.import_module("selfcheck")
    finally:
        sys.path.remove(str(_PORTABLE))


def test_require_preview_stem(selfcheck: Any) -> None:
    selfcheck._require_preview_stem("adult_male_reduced_3000t")
    with pytest.raises(ValueError, match="edition_phantom_payload_wrong"):
        selfcheck._require_preview_stem("adult_male")
    with pytest.raises(ValueError, match="edition_phantom_payload_wrong"):
        selfcheck._require_preview_stem("adult_male_reduced_1000t")


def test_bundled_browser_present_darwin_helpers_layout(selfcheck: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    contents = tmp_path / "GUISkinDose.app" / "Contents"
    macos = contents / "MacOS"
    macos.mkdir(parents=True)
    exe = macos / "GUISkinDose"
    exe.write_bytes(b"")
    monkeypatch.setattr(sys, "executable", str(exe))
    monkeypatch.setattr(sys, "platform", "darwin")
    assert not selfcheck._bundled_browser_present()
    (contents / "Helpers" / "Chromium.app").mkdir(parents=True)
    assert selfcheck._bundled_browser_present()


def test_bundled_browser_present_linux_chromium_dir(selfcheck: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    exe = tmp_path / "GUISkinDose"
    exe.write_bytes(b"")
    monkeypatch.setattr(sys, "executable", str(exe))
    monkeypatch.setattr(sys, "platform", "linux")
    assert not selfcheck._bundled_browser_present()
    (tmp_path / "chromium").mkdir()
    assert selfcheck._bundled_browser_present()


def test_check_edition_rejects_a_non_3000t_preview_stem(selfcheck: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    import guiskindose.phantom_mesh_names as names

    monkeypatch.setattr(names, "prefer_reduced_preview_stem", lambda _stem: "adult_male_reduced_1000t")
    with pytest.raises(ValueError, match="edition_phantom_payload_wrong"):
        selfcheck._check_edition()
