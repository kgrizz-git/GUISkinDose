"""Integration tests for newly shipped parametric phantom library meshes."""

from __future__ import annotations

from pathlib import Path

import pytest

from mypyskindose import Phantom, PyskindoseSettings, load_settings_example_json
from mypyskindose.gui.helpers import get_human_mesh_names
from mypyskindose.phantom_mesh_names import resolve_human_mesh_stem

NEW_MESHES = [
    "ped_preschool_male",
    "ped_preschool_female",
    "ped_5y_male",
    "ped_5y_female",
    "ped_10y_male",
    "ped_10y_female",
    "adult_ecto_male",
    "adult_ecto_female",
    "adult_endo_male",
    "adult_endo_female",
    "adult_bariatric_male_1",
    "adult_bariatric_female_1",
    "adult_bariatric_male_2",
    "adult_bariatric_female_2",
    "adult_bariatric_male_3",
    "adult_bariatric_female_3",
]

ARMS_DOWN_MESHES = [
    f"{stem}_arms_down"
    for stem in [
        "ped_preschool_male",
        "ped_preschool_female",
        "ped_5y_male",
        "ped_5y_female",
        "ped_10y_male",
        "ped_10y_female",
        "junior_male",
        "junior_female",
        "adult_male",
        "adult_female",
        "adult_ecto_male",
        "adult_ecto_female",
        "adult_endo_male",
        "adult_endo_female",
        "adult_bariatric_male_1",
        "adult_bariatric_female_1",
        "adult_bariatric_male_2",
        "adult_bariatric_female_2",
        "adult_bariatric_male_3",
        "adult_bariatric_female_3",
        "senior_male",
        "senior_female",
        "hudfrid",
    ]
]

PHANTOM_DATA = Path(__file__).resolve().parents[2] / "src" / "mypyskindose" / "phantom_data"


@pytest.mark.parametrize("mesh_name", NEW_MESHES + ARMS_DOWN_MESHES)
def test_new_mesh_files_exist_with_reduced_variant(mesh_name: str):
    assert (PHANTOM_DATA / f"{mesh_name}.stl").is_file()
    assert (PHANTOM_DATA / f"{mesh_name}_reduced_1000t.stl").is_file()
    assert (PHANTOM_DATA / f"{mesh_name}_reduced_3000t.stl").is_file()


@pytest.mark.parametrize("mesh_name", NEW_MESHES + ARMS_DOWN_MESHES)
def test_reduced_preview_meshes_are_connected(mesh_name: str):
    """Settings / plot_procedure prefer ``*_reduced_3000t``; 1k companions remain shipped."""
    from stl import mesh as stl_mesh

    from scripts.phantom_gen.generate_reduced import unique_vertex_count

    for suffix, n_faces in (("_reduced_3000t", 3000), ("_reduced_1000t", 1000)):
        reduced = stl_mesh.Mesh.from_file(str(PHANTOM_DATA / f"{mesh_name}{suffix}.stl"))
        assert len(reduced.vectors) == n_faces
        uniq = unique_vertex_count(reduced.vectors)
        # Proper quadric decimation shares verts (~0.5/face); triangle subsample is ~2.7+/face.
        assert uniq / n_faces <= 1.2, f"{mesh_name}{suffix} looks disconnected (uniq={uniq})"


def test_new_meshes_are_discovered():
    names = get_human_mesh_names()
    for mesh_name in NEW_MESHES + ARMS_DOWN_MESHES:
        assert mesh_name in names
    for mesh_name in NEW_MESHES + ARMS_DOWN_MESHES:
        assert f"{mesh_name}_reduced_1000t" not in names
        assert f"{mesh_name}_reduced_3000t" not in names


@pytest.mark.parametrize("mesh_name", NEW_MESHES + ARMS_DOWN_MESHES)
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


@pytest.mark.parametrize("mesh_name", ["ped_5y_male", "adult_endo_male"])
def test_new_mesh_scale_hook_smoke(mesh_name: str):
    settings = PyskindoseSettings(settings=load_settings_example_json())
    phantom = Phantom(
        phantom_model="human",
        phantom_dim=settings.phantom.dimension,
        human_mesh=mesh_name,
        human_scale=(1.1, 0.9, 1.05),
    )
    assert len(phantom.r) > 1000


def test_arms_down_label_and_sort_order():
    from mypyskindose.phantom_mesh_names import human_mesh_display_label, sort_clinical_mesh_stems

    assert human_mesh_display_label("ped_5y_male_arms_down") == "Pediatric 5y Male (arms down)"
    ordered = sort_clinical_mesh_stems(["ped_5y_male_arms_down", "ped_5y_female", "ped_5y_male"])
    assert ordered == ["ped_5y_male", "ped_5y_male_arms_down", "ped_5y_female"]


def test_legacy_mesh_aliases_resolve_and_load():
    assert resolve_human_mesh_stem("pediatric_5y_male") == "ped_5y_male"
    assert resolve_human_mesh_stem("bariatric_class2_male_thick_extremities") == "adult_bariatric_male_2"
    assert resolve_human_mesh_stem("cosmic_buddha_reduced_1000t") == "demo_cosmic_buddha_reduced_1000t"
    settings = PyskindoseSettings(settings=load_settings_example_json())
    phantom = Phantom(
        phantom_model="human",
        phantom_dim=settings.phantom.dimension,
        human_mesh="pediatric_10y_female",
    )
    assert phantom.human_model == "ped_10y_female"
    assert len(phantom.r) > 1000
