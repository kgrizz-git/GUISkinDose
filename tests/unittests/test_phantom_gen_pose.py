"""Unit tests for optional catalog pose resolution (no Blender required)."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.phantom_gen.mpfb_generate import _resolve_pose_path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_resolve_pose_path_none_when_unset():
    assert _resolve_pose_path(REPO_ROOT, {}) is None
    assert _resolve_pose_path(REPO_ROOT, {"pose": None}) is None


def test_resolve_pose_path_named_pose_file():
    path = _resolve_pose_path(REPO_ROOT, {"pose": "arms_down_default_fk"})
    assert path is not None
    assert path.name == "arms_down_default_fk.json"
    assert path.is_file()
    assert path.parent.name == "poses"


def test_resolve_pose_path_explicit_pose_file_relative(tmp_path: Path):
    poses = tmp_path / "poses"
    poses.mkdir()
    pose_file = poses / "custom.json"
    pose_file.write_text("{}", encoding="utf-8")
    # Relative paths are resolved under scripts/phantom_gen/
    # Use an absolute path here to avoid depending on repo layout for the fixture.
    path = _resolve_pose_path(REPO_ROOT, {"pose_file": str(pose_file)})
    assert path == pose_file


def test_resolve_pose_path_missing_named_pose_still_returns_path():
    """Resolver returns the expected path; apply step raises if the file is missing."""
    path = _resolve_pose_path(REPO_ROOT, {"pose": "does_not_exist_pose"})
    assert path is not None
    assert path.name == "does_not_exist_pose.json"
    assert not path.is_file()


def test_apply_catalog_pose_missing_file_raises(tmp_path: Path):
    """Missing pose file must fail clearly (without requiring Blender for the check)."""
    from scripts.phantom_gen import mpfb_generate as mod

    entry = {"pose_file": str(tmp_path / "missing_pose.json")}
    with pytest.raises(FileNotFoundError, match="Catalog pose file not found"):
        mod._apply_catalog_pose(
            basemesh=None,
            entry=entry,
            HumanService=None,
            ObjectService=None,
            RigService=None,
            repo_root=REPO_ROOT,
        )
