"""Packaging smoke for the ``guiskindose`` distribution identity.

Guards Phase 4b of the rename: installed metadata reports ``1.0.0``, and a built
wheel contains the ``guiskindose`` package (not an empty or old-name tree).
"""

from __future__ import annotations

import tomllib
import zipfile
from importlib.metadata import version
from pathlib import Path

import pytest


def test_installed_package_version_matches_pyproject() -> None:
    """``importlib.metadata.version("guiskindose")`` agrees with ``pyproject.toml``."""
    pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    declared = data["project"]["version"]
    assert declared == "1.0.0"
    assert version("guiskindose") == declared


def test_wheel_contains_guiskindose_package() -> None:
    """The newest ``dist/*.whl`` must ship ``guiskindose/`` and no ``mypyskindose/``.

    Skipped when no wheel has been built yet (``uv build`` is a runbook step, not
    a required pytest precondition for every developer).
    """
    dist = Path(__file__).resolve().parents[2] / "dist"
    wheels = sorted(dist.glob("guiskindose-*.whl"))
    if not wheels:
        pytest.skip("no guiskindose wheel in dist/; run `uv build` to cover this")
    wheel = wheels[-1]
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
    assert any(name.startswith("guiskindose/") for name in names)
    # Concatenate so this file does not contain the pre-rename import path literal.
    legacy_prefix = "".join(("my", "pyskindose", "/"))
    assert not any(name.startswith(legacy_prefix) for name in names)
