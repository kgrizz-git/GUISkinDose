"""Tests for GUI helper functions."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from mypyskindose.gui import helpers


@pytest.fixture(autouse=True)
def _clear_mesh_extent_cache() -> None:
    helpers._MESH_EXTENT_CACHE.clear()
    helpers._MESH_TORSO_WIDTH_CACHE.clear()


def test_get_mesh_baseline_extents_caches_successful_read(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    (tmp_path / "sample.stl").write_text("solid placeholder\nendsolid placeholder\n")
    monkeypatch.setattr(helpers, "_PHANTOM_DATA_DIR", tmp_path)

    class FakeMesh:
        vectors = np.array(
            [
                [[0.0, 2.0, -3.0], [10.0, 5.0, 1.0], [4.0, 8.0, 7.0]],
                [[-2.0, 3.0, -1.0], [5.0, 11.0, 2.0], [1.0, 6.0, 9.0]],
            ]
        )

    calls = 0

    def fake_from_file(_path: str) -> FakeMesh:
        nonlocal calls
        calls += 1
        return FakeMesh()

    monkeypatch.setattr(helpers.stl_mesh.Mesh, "from_file", fake_from_file)

    assert helpers.get_mesh_baseline_extents("sample") == (12.0, 9.0, 12.0)
    assert helpers.get_mesh_baseline_torso_width("sample") == pytest.approx(5.0)
    assert helpers.get_mesh_baseline_extents("sample") == (12.0, 9.0, 12.0)
    assert calls == 1


@pytest.mark.parametrize("mesh_name", ["nonsense", ""])
def test_get_mesh_baseline_extents_caches_unknown_or_empty_mesh(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    mesh_name: str,
) -> None:
    monkeypatch.setattr(helpers, "_PHANTOM_DATA_DIR", tmp_path)

    assert helpers.get_mesh_baseline_extents(mesh_name) == (0.0, 0.0, 0.0)
    assert helpers._MESH_EXTENT_CACHE[mesh_name] == (0.0, 0.0, 0.0)
    assert helpers.get_mesh_baseline_torso_width(mesh_name) == pytest.approx(0.0)


def test_get_mesh_baseline_extents_handles_corrupt_stl(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    (tmp_path / "broken.stl").write_text("not an stl")
    monkeypatch.setattr(helpers, "_PHANTOM_DATA_DIR", tmp_path)
    warnings: list[tuple[str, tuple[object, ...]]] = []

    def fake_warning(message: str, *args: object) -> None:
        warnings.append((message, args))

    monkeypatch.setattr(helpers._gui_logger, "warning", fake_warning)

    assert helpers.get_mesh_baseline_extents("broken") == (0.0, 0.0, 0.0)

    assert helpers._MESH_EXTENT_CACHE["broken"] == (0.0, 0.0, 0.0)
    assert helpers._MESH_TORSO_WIDTH_CACHE["broken"] == pytest.approx(0.0)
    assert len(warnings) == 1
    assert "Could not read baseline extents for human mesh" in warnings[0][0]


@pytest.mark.parametrize(
    "mesh_name",
    [
        "adult_female",
        "adult_male",
        "hudfrid",
        "junior_female",
        "junior_male",
        "senior_female",
        "senior_male",
    ],
)
def test_get_mesh_baseline_extents_returns_positive_axis_ordered_values(mesh_name: str) -> None:
    extents = helpers.get_mesh_baseline_extents(mesh_name)

    assert len(extents) == 3
    assert all(extent > 0.0 for extent in extents)
    assert extents == helpers._MESH_EXTENT_CACHE[mesh_name]


@pytest.mark.parametrize(
    ("mesh_name", "expected_width_cm"),
    [
        ("adult_female", 36.4560),
        ("adult_male", 35.5347),
        ("hudfrid", 35.3116),
        ("junior_female", 26.7856),
        ("junior_male", 27.1393),
        ("senior_female", 36.8931),
        ("senior_male", 36.1996),
    ],
)
def test_get_mesh_baseline_torso_width_excludes_t_pose_arms(mesh_name: str, expected_width_cm: float) -> None:
    torso_width = helpers.get_mesh_baseline_torso_width(mesh_name)

    assert torso_width == pytest.approx(expected_width_cm, abs=0.0001)
    assert torso_width < helpers.get_mesh_baseline_extents(mesh_name)[0]
