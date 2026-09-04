"""Tests for human_mesh path confinement under phantom_data/."""

from __future__ import annotations

from pathlib import Path

import pytest

from guiskindose import load_settings_example_json
from guiskindose.phantom_class import Phantom
from guiskindose.phantom_mesh_names import (
    assert_safe_human_mesh_stem,
    prefer_reduced_preview_stem,
    resolve_human_mesh_stem,
    resolve_human_mesh_stl_path,
)
from guiskindose.settings import PyskindoseSettings

PHANTOM_DATA = Path(__file__).resolve().parents[2] / "src" / "guiskindose" / "phantom_data"


@pytest.mark.parametrize(
    "stem",
    [
        "../adult_male",
        "..\\adult_male",
        "foo/../adult_male",
        "subdir/adult_male",
        "adult_male.stl",
        "",
        "bad stem",
        "evil\x00mesh",
    ],
)
def test_assert_safe_human_mesh_stem_rejects_traversal(stem: str) -> None:
    with pytest.raises(ValueError):
        assert_safe_human_mesh_stem(stem)


def test_resolve_human_mesh_stl_path_confines_to_phantom_data() -> None:
    path = resolve_human_mesh_stl_path("adult_male")
    assert path.is_file()
    assert path.is_relative_to(PHANTOM_DATA.resolve())
    assert path.name == "adult_male.stl"


def test_resolve_human_mesh_stl_path_rejects_unknown_mesh() -> None:
    with pytest.raises(ValueError, match="Unknown human mesh"):
        resolve_human_mesh_stl_path("not_a_real_phantom_mesh_zz")


def test_resolve_human_mesh_stl_path_rejects_parent_reference(tmp_path: Path) -> None:
    outside = tmp_path / "outside.stl"
    outside.write_bytes(b"solid fake\nendsolid fake\n")
    # Relative escape from phantom_data toward an attacker-controlled path.
    escape = Path("..") / ".." / ".." / ".." / tmp_path.name / "outside"
    # Use a stem that looks like traversal when joined under phantom_data/.
    with pytest.raises(ValueError):
        resolve_human_mesh_stl_path(str(escape).replace("\\", "/"))


def test_phantom_string_mesh_rejects_path_traversal() -> None:
    settings = PyskindoseSettings(settings=load_settings_example_json())
    with pytest.raises(ValueError):
        Phantom(
            phantom_model="human",
            phantom_dim=settings.phantom.dimension,
            human_mesh="../adult_male",
        )


def test_prefer_reduced_preview_stem_ignores_traversal(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        prefer_reduced_preview_stem("../adult_male", phantom_data_dir=tmp_path)


def test_legacy_alias_still_resolves_safely() -> None:
    assert resolve_human_mesh_stem("pediatric_5y_male") == "ped_5y_male"
    path = resolve_human_mesh_stl_path("pediatric_5y_male")
    assert path.name == "ped_5y_male.stl"
