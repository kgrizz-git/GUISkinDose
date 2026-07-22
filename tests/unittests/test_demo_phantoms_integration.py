"""Integration tests for shipped demo / non-clinical phantoms."""

from __future__ import annotations

from pathlib import Path

import pytest

from mypyskindose import Phantom, PyskindoseSettings, load_settings_example_json
from mypyskindose.gui.helpers import DEMO_HUMAN_MESHES, get_human_mesh_names, get_human_mesh_options

# Only meshes that actually shipped (Petite Herculanaise remains blocked).
SHIPPED_DEMO_MESHES = sorted(DEMO_HUMAN_MESHES)

PHANTOM_DATA = Path(__file__).resolve().parents[2] / "src" / "mypyskindose" / "phantom_data"


@pytest.mark.parametrize("mesh_name", SHIPPED_DEMO_MESHES)
def test_demo_mesh_files_exist_with_reduced_variant(mesh_name: str):
    assert (PHANTOM_DATA / f"{mesh_name}.stl").is_file()
    assert (PHANTOM_DATA / f"{mesh_name}_reduced_1000t.stl").is_file()


def test_demo_meshes_are_discovered_and_labeled():
    names = get_human_mesh_names()
    options = get_human_mesh_options()
    for mesh_name in SHIPPED_DEMO_MESHES:
        assert mesh_name in names
        assert mesh_name in options
        assert options[mesh_name].endswith("(demo)")
        assert f"{mesh_name}_reduced_1000t" not in names
    # NiceGUI contract: every options key is a discovered stem (bound value).
    assert set(options) == set(names)
    assert options["adult_female"] == "Adult Female"
    assert "Mickey" not in options.get("steamboat_willie", "")


@pytest.mark.parametrize("mesh_name", SHIPPED_DEMO_MESHES)
def test_demo_mesh_loads_with_psd_anchors(mesh_name: str):
    settings = PyskindoseSettings(settings=load_settings_example_json())
    phantom = Phantom(
        phantom_model="human",
        phantom_dim=settings.phantom.dimension,
        human_mesh=mesh_name,
    )
    assert len(phantom.r) > 1000
    assert len(phantom.n) == len(phantom.r)
    assert float(phantom.r[:, 2].max()) == pytest.approx(0.0, abs=1.0)
    assert float(phantom.r[:, 1].max()) == pytest.approx(0.0, abs=1.0)
    x_mid = 0.5 * (float(phantom.r[:, 0].min()) + float(phantom.r[:, 0].max()))
    assert x_mid == pytest.approx(0.0, abs=1.0)
    height = float(phantom.r[:, 2].max() - phantom.r[:, 2].min())
    assert 50.0 < height < 220.0
