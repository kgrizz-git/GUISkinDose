"""The native extra and the freeze group both require pywebview 6.1 or newer."""

from __future__ import annotations

import tomllib
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]


def test_pywebview_floor_is_at_least_6_1() -> None:
    data = tomllib.loads((_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    gui_native = data["project"]["optional-dependencies"]["gui-native"]
    portable = data["dependency-groups"]["portable"]
    assert "pywebview>=6.1" in gui_native
    assert "pywebview>=6.1" in portable
