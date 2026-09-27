"""The intended-use wording stays identical across the GUI copy catalog and exports."""

from __future__ import annotations

import json
from pathlib import Path

from guiskindose.intended_use import INTENDED_USE_NOTICE, INTENDED_USE_SHORT

REPO_ROOT = Path(__file__).resolve().parents[2]


def _ui_copy() -> dict:
    return json.loads((REPO_ROOT / "dev-docs" / "ui_copy.json").read_text(encoding="utf-8"))["keys"]


def test_gui_copy_matches_core_notice() -> None:
    keys = _ui_copy()
    assert keys["onboarding.intended_use"]["text"] == INTENDED_USE_NOTICE
    assert keys["results.intended_use"]["text"] == INTENDED_USE_SHORT


def test_notice_states_not_cleared_and_responsibility() -> None:
    assert "not FDA-cleared" in INTENDED_USE_NOTICE
    assert "physicists and physicians are responsible" in INTENDED_USE_NOTICE
    assert "Not FDA-cleared" in INTENDED_USE_SHORT
