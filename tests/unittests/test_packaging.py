"""Packaging smoke for the ``guiskindose`` distribution identity.

Guards Phase 4b of the rename: installed metadata reports ``1.0.0``, and a built
wheel contains the ``guiskindose`` package (not an empty or old-name tree).

Phase D (correction-data distribution proof) adds content assertions: every
manifest-declared runtime lookup table plus the manifest itself must ship in
the wheel, and the sdist file list must cover the same set.
"""

from __future__ import annotations

import json
import re
import tarfile
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


def test_dunder_version_attribute_matches_pyproject() -> None:
    """``guiskindose.__version__`` exists and agrees with ``pyproject.toml``.

    User-facing docs (e.g. the bug-report issue template) tell users to query
    ``guiskindose.__version__``; it must never silently disappear.
    """
    import guiskindose

    pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
    declared = tomllib.loads(pyproject.read_text(encoding="utf-8"))["project"]["version"]
    assert guiskindose.__version__ == declared


def test_sphinx_release_matches_pyproject() -> None:
    """Sphinx ``release`` in ``docs/source/conf.py`` tracks ``pyproject.toml``."""
    repo = Path(__file__).resolve().parents[2]
    pyproject = tomllib.loads((repo / "pyproject.toml").read_text(encoding="utf-8"))
    declared = pyproject["project"]["version"]
    conf = (repo / "docs" / "source" / "conf.py").read_text(encoding="utf-8")
    match = re.search(r'^release\s*=\s*["\']([^"\']+)["\']', conf, re.MULTILINE)
    assert match is not None
    assert match.group(1) == declared


def test_wheel_contains_guiskindose_package() -> None:
    """The newest ``dist/*.whl`` must ship the ``guiskindose/`` tree, not an empty or old-name tree.

    (The legacy package name is built by concatenation below so this file holds no
    pre-rename import-path literal.)

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
    # In-app GUI help markdown must ship in the wheel; help_button.py reads it
    # from the installed package at runtime (MANIFEST.in recursive-include).
    assert any(name.startswith("guiskindose/gui/help/") and name.endswith(".md") for name in names)
    # Concatenate so this file does not contain the pre-rename import path literal.
    legacy_prefix = "".join(("my", "pyskindose", "/"))
    assert not any(name.startswith(legacy_prefix) for name in names)


def _runtime_lookup_wheel_paths() -> list[str]:
    """Manifest-declared runtime lookup tables as wheel-relative paths.

    "Required" (master §5) means runtime lookups plus the manifest itself —
    not the build-input HVL CSVs or the provenance-only ``device_info.csv``
    that ``MANIFEST.in`` also ships.
    """
    repo = Path(__file__).resolve().parents[2]
    manifest_path = repo / "src" / "guiskindose" / "table_data" / "correction_data_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    paths = [
        "guiskindose/table_data/" + table["file"]
        for table in manifest["tables"]
        if table.get("role") == "runtime_lookup"
    ]
    paths.append("guiskindose/table_data/correction_data_manifest.json")
    assert len(paths) >= 2, "manifest declares no runtime lookup tables"
    return sorted(paths)


def test_wheel_contains_correction_runtime_tables() -> None:
    """The newest ``dist/*.whl`` must ship every runtime lookup CSV + manifest.

    Skipped when no wheel has been built yet (``uv build`` is a runbook step,
    not a required pytest precondition for every developer).
    """
    dist = Path(__file__).resolve().parents[2] / "dist"
    wheels = sorted(dist.glob("guiskindose-*.whl"))
    if not wheels:
        pytest.skip("no guiskindose wheel in dist/; run `uv build` to cover this")
    with zipfile.ZipFile(wheels[-1]) as archive:
        names = set(archive.namelist())
    missing = [path for path in _runtime_lookup_wheel_paths() if path not in names]
    assert not missing, f"wheel is missing correction-data files: {missing}"


def test_sdist_contains_correction_runtime_tables() -> None:
    """The newest ``dist/*.tar.gz`` file list must cover the same set as the wheel.

    Build-and-install from the sdist is out of scope (needs network build
    deps); list parity is the Phase D bar.
    """
    dist = Path(__file__).resolve().parents[2] / "dist"
    sdists = sorted(dist.glob("guiskindose-*.tar.gz"))
    if not sdists:
        pytest.skip("no guiskindose sdist in dist/; run `uv build` to cover this")
    with tarfile.open(sdists[-1], "r:gz") as archive:
        names = archive.getnames()
    missing = [
        path for path in _runtime_lookup_wheel_paths() if not any(name.endswith("/src/" + path) for name in names)
    ]
    assert not missing, f"sdist is missing correction-data files: {missing}"
