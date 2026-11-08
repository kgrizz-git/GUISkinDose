"""Maintainer phantom pack builder and pin check."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from guiskindose.phantom_pack import manifest_sha256
from guiskindose.phantom_pack_pin import EXPECTED_PHANTOM_PACK_SHA256
from scripts.build_phantom_pack import _load_version, _pack_stl_paths, build_pack_manifest


def test_committed_pin_matches_builder_manifest_digest() -> None:
    paths = _pack_stl_paths()
    manifest = build_pack_manifest(paths, app_version=_load_version())
    digest = manifest_sha256(manifest)
    assert EXPECTED_PHANTOM_PACK_SHA256
    assert digest == EXPECTED_PHANTOM_PACK_SHA256


def test_build_script_check_mode_passes() -> None:
    root = Path(__file__).resolve().parents[2]
    completed = subprocess.run(
        [sys.executable, str(root / "scripts/build_phantom_pack.py"), "--check"],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr


def test_is_allowed_pack_stem_rejects_unsafe_names() -> None:
    from guiskindose.phantom_pack import is_allowed_pack_stem

    assert not is_allowed_pack_stem("senior male")
    assert not is_allowed_pack_stem("manifest.json")
