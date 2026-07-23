"""Integration tests for shipped demo / non-clinical phantoms."""

from __future__ import annotations

from pathlib import Path

import pytest

from mypyskindose import Phantom, PyskindoseSettings, load_settings_example_json
from mypyskindose.gui.helpers import (
    DEMO_HUMAN_MESHES,
    DEMO_MESH_SECTION_KEY,
    DEMO_MESH_SECTION_LABEL,
    GUI_HIDDEN_HUMAN_MESHES,
    get_human_mesh_names,
    get_human_mesh_options,
)

# Demo stems that may appear in Settings when the local flag is on.
SHIPPED_DEMO_MESHES = sorted(DEMO_HUMAN_MESHES)

# On-disk demo binaries (includes GUI-hidden Ramesses).
ON_DISK_DEMO_MESHES = sorted(DEMO_HUMAN_MESHES | GUI_HIDDEN_HUMAN_MESHES)

PHANTOM_DATA = Path(__file__).resolve().parents[2] / "src" / "mypyskindose" / "phantom_data"


@pytest.mark.parametrize("mesh_name", ON_DISK_DEMO_MESHES)
def test_demo_mesh_files_exist_with_reduced_variant(mesh_name: str):
    assert (PHANTOM_DATA / f"{mesh_name}.stl").is_file()
    assert (PHANTOM_DATA / f"{mesh_name}_reduced_1000t.stl").is_file()


def test_default_mesh_options_hide_demos_and_ramesses():
    names = get_human_mesh_names()
    options = get_human_mesh_options(include_demos=False)
    for mesh_name in SHIPPED_DEMO_MESHES:
        assert mesh_name in names
        assert mesh_name not in options
    for hidden in GUI_HIDDEN_HUMAN_MESHES:
        assert hidden in names
        assert hidden not in options
    assert DEMO_MESH_SECTION_KEY not in options
    assert options["adult_female"] == "Adult Female"
    assert "Mickey" not in str(options.values())


def test_demo_mesh_options_when_enabled_have_section_at_end():
    options = get_human_mesh_options(include_demos=True)
    keys = list(options)
    assert DEMO_MESH_SECTION_KEY in options
    assert options[DEMO_MESH_SECTION_KEY] == DEMO_MESH_SECTION_LABEL
    section_idx = keys.index(DEMO_MESH_SECTION_KEY)
    # Clinical meshes come first; demos after the separator.
    assert section_idx > 0
    for mesh_name in SHIPPED_DEMO_MESHES:
        assert mesh_name in options
        assert keys.index(mesh_name) > section_idx
        assert "demo" in options[mesh_name].lower()
    assert "headless" in options["cosmic_buddha"].lower()
    for hidden in GUI_HIDDEN_HUMAN_MESHES:
        assert hidden not in options
    assert "Mickey" not in options.get("steamboat_willie", "")


def test_show_demo_phantoms_enabled_defaults_false(monkeypatch, tmp_path):
    from mypyskindose.gui import window_prefs

    cfg = tmp_path / "gui.json"
    monkeypatch.setattr(window_prefs, "config_path", lambda: cfg)
    assert window_prefs.show_demo_phantoms_enabled() is False
    cfg.write_text('{"show_demo_phantoms": true}\n', encoding="utf-8")
    assert window_prefs.show_demo_phantoms_enabled() is True


@pytest.mark.parametrize("mesh_name", ON_DISK_DEMO_MESHES)
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
