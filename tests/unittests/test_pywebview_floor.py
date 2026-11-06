"""The native extra and the freeze group both require pywebview 6.1 or newer."""

from __future__ import annotations

import tomllib
from pathlib import Path

from packaging.requirements import Requirement
from packaging.version import Version

_ROOT = Path(__file__).resolve().parents[2]
_FLOOR = Version("6.1")
_BELOW_FLOOR = Version("6.0")


def _pywebview_requirement(requirements: list[str]) -> Requirement:
    """Return the single ``pywebview`` requirement in a dependency list."""
    found = [req for item in requirements if (req := Requirement(item)).name == "pywebview"]
    assert len(found) == 1
    return found[0]


def test_pywebview_floor_is_at_least_6_1() -> None:
    data = tomllib.loads((_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    gui_native = data["project"]["optional-dependencies"]["gui-native"]
    portable = data["dependency-groups"]["portable"]
    assert _FLOOR in _pywebview_requirement(gui_native).specifier
    assert _FLOOR in _pywebview_requirement(portable).specifier
    assert _BELOW_FLOOR not in _pywebview_requirement(gui_native).specifier
    assert _BELOW_FLOOR not in _pywebview_requirement(portable).specifier
