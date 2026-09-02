"""Pytest configuration for unit tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


@pytest.fixture(autouse=True)
def _isolate_new_gui_config_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep load_gui_config() from reading a real ~/.guiskindose/gui.json.

    Dual-read in PR 0 checks the new home path first. Tests that only patch
    ``config_path`` would otherwise leak to the developer's real new file.
    Tests that need the new path present re-patch ``new_config_path``.
    """
    from mypyskindose.gui import window_prefs

    monkeypatch.setattr(
        window_prefs,
        "new_config_path",
        lambda: tmp_path / "missing-guiskindose" / "gui.json",
    )
