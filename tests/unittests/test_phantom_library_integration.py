"""Integration tests for newly shipped parametric phantom library meshes."""

from __future__ import annotations

from pathlib import Path

import pytest

from mypyskindose import Phantom, PyskindoseSettings, load_settings_example_json
from mypyskindose.gui.helpers import get_human_mesh_names

NEW_MESHES = [
    "pediatric_5y_male",
    "pediatric_5y_female",
    "pediatric_10y_male",
    "pediatric_10y_female",
    "adult_ectomorph_male",
    "adult_ectomorph_female",
    "adult_endomorph_male",
    "adult_endomorph_female",
    "bariatric_class2_male",
    "bariatric_class2_female",
    "bariatric_class2_male_thick_extremities",
    "bariatric_class2_female_thick_extremities",
]

PHANTOM_DATA = Path(__file__).resolve().parents[2] / "src" / "mypyskindose" / "phantom_data"


@pytest.mark.parametrize("mesh_name", NEW_MESHES)
def test_new_mesh_files_exist_with_reduced_variant(mesh_name: str):
    assert (PHANTOM_DATA / f"{mesh_name}.stl").is_file()
    assert (PHANTOM_DATA / f"{mesh_name}_reduced_1000t.stl").is_file()


@pytest.mark.parametrize("mesh_name", NEW_MESHES)
def test_reduced_preview_meshes_are_connected(mesh_name: str):
    """Settings preview uses ``*_reduced_1000t``; subsample soups look like scatter fragments."""
    from stl import mesh as stl_mesh

    from scripts.phantom_gen.generate_reduced import unique_vertex_count

    reduced = stl_mesh.Mesh.from_file(str(PHANTOM_DATA / f"{mesh_name}_reduced_1000t.stl"))
    n_faces = len(reduced.vectors)
    uniq = unique_vertex_count(reduced.vectors)
    assert n_faces == 1000
    # Proper quadric decimation shares verts (~0.5/face); triangle subsample is ~2.7+/face.
    assert uniq / n_faces <= 1.2, f"{mesh_name}_reduced_1000t looks disconnected (uniq={uniq})"


def test_new_meshes_are_discovered():
    names = get_human_mesh_names()
    for mesh_name in NEW_MESHES:
        assert mesh_name in names
    for mesh_name in NEW_MESHES:
        assert f"{mesh_name}_reduced_1000t" not in names


@pytest.mark.parametrize("mesh_name", NEW_MESHES)
def test_new_mesh_loads_with_psd_anchors(mesh_name: str):
    settings = PyskindoseSettings(settings=load_settings_example_json())
    phantom = Phantom(
        phantom_model="human",
        phantom_dim=settings.phantom.dimension,
        human_mesh=mesh_name,
    )
    assert len(phantom.r) > 1000
    assert len(phantom.n) == len(phantom.r)
    # PSD anchors: head at max Z ≈ 0, back at max Y ≈ 0, lateral centered
    assert float(phantom.r[:, 2].max()) == pytest.approx(0.0, abs=1.0)
    assert float(phantom.r[:, 1].max()) == pytest.approx(0.0, abs=1.0)
    x_mid = 0.5 * (float(phantom.r[:, 0].min()) + float(phantom.r[:, 0].max()))
    assert x_mid == pytest.approx(0.0, abs=1.0)
    height = float(phantom.r[:, 2].max() - phantom.r[:, 2].min())
    assert 50.0 < height < 220.0


@pytest.mark.parametrize("mesh_name", ["pediatric_5y_male", "adult_endomorph_male"])
def test_new_mesh_scale_hook_smoke(mesh_name: str):
    settings = PyskindoseSettings(settings=load_settings_example_json())
    unscaled = Phantom(
        phantom_model="human",
        phantom_dim=settings.phantom.dimension,
        human_mesh=mesh_name,
        human_scale=(1.0, 1.0, 1.0),
    )
    scaled = Phantom(
        phantom_model="human",
        phantom_dim=settings.phantom.dimension,
        human_mesh=mesh_name,
        human_scale=(1.2, 1.0, 1.0),
    )
    unscaled_w = float(unscaled.r[:, 0].max() - unscaled.r[:, 0].min())
    scaled_w = float(scaled.r[:, 0].max() - scaled.r[:, 0].min())
    assert scaled_w == pytest.approx(1.2 * unscaled_w, rel=1e-3)
