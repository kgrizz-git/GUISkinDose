"""Light and Full editions: committed value, include lists, PNG gate, missing meshes."""

from __future__ import annotations

import subprocess
from importlib.resources import files
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest

from guiskindose import _edition
from guiskindose.edition import (
    EDITION_FULL,
    EDITION_LIGHT,
    LIGHT_BASE_MESHES,
    PNG_UNAVAILABLE_MESSAGE,
    current_edition,
    edition_phantom_stl_names,
    full_phantom_stl_names,
    light_phantom_stl_names,
    png_export_available,
)
from guiskindose.phantom_mesh_names import (
    HumanMeshNotInstalledError,
    human_mesh_not_installed_message,
    is_clinical_catalog_stem,
    package_phantom_data_dir,
    resolve_human_mesh_stl_path,
)

# One-triangle dose map in the shape ``render_dosemap_png`` takes.
_TRIANGLE = (
    np.zeros(3),
    {
        "patient_skin_cells": {"x": [0.0, 1.0, 0.0], "y": [0.0, 0.0, 1.0], "z": [0.0, 0.0, 0.0]},
        "triangle_vertex_indices": {"i": [0], "j": [1], "k": [2]},
    },
)
_EDITION_FILE = Path(__file__).resolve().parents[2] / "src" / "guiskindose" / "_edition.py"


@pytest.fixture
def light(monkeypatch):
    monkeypatch.setattr(_edition, "EDITION", EDITION_LIGHT)


@pytest.fixture
def no_browser_launch(monkeypatch):
    """Fail the test if anything tries to reach Kaleido or start a process."""
    import kaleido
    import plotly.graph_objects as go

    calls: list[str] = []

    def refuse(name):
        def _refuse(*_args, **_kwargs):
            calls.append(name)
            raise AssertionError(f"{name} called in Light")

        return _refuse

    monkeypatch.setattr(go.Figure, "to_image", refuse("Figure.to_image"))
    monkeypatch.setattr(kaleido, "calc_fig_sync", refuse("kaleido.calc_fig_sync"))
    monkeypatch.setattr(kaleido, "start_sync_server", refuse("kaleido.start_sync_server"))
    monkeypatch.setattr(subprocess, "Popen", refuse("subprocess.Popen"))
    return calls


def test_committed_edition_is_full():
    assert 'EDITION = "full"\n' in _EDITION_FILE.read_text(encoding="utf-8")
    assert current_edition() == EDITION_FULL
    assert png_export_available()


def test_unknown_edition_fails_closed_to_light(monkeypatch):
    monkeypatch.setattr(_edition, "EDITION", "medium")
    assert current_edition() == EDITION_LIGHT
    assert not png_export_available()


def test_environment_does_not_override_edition(monkeypatch):
    monkeypatch.setenv("GUISKINDOSE_EDITION", "light")
    monkeypatch.setenv("GUISKINDOSE_PORTABLE_EDITION", "light")
    assert current_edition() == EDITION_FULL


def test_light_list_is_the_proposed_starter_set():
    names = light_phantom_stl_names()
    assert len(names) == len(LIGHT_BASE_MESHES) * 4 == 28
    assert all(name.endswith(".stl") for name in names)
    assert not any("_reduced_1000t" in name for name in names)
    assert "adult_male_arms_down_reduced_3000t.stl" in names
    shipped = {path.name for path in package_phantom_data_dir().glob("*.stl")}
    assert set(names) <= shipped


def test_full_list_keeps_every_clinical_mesh_but_no_1000t_previews():
    shipped = sorted(path.name for path in package_phantom_data_dir().glob("*.stl"))
    full = full_phantom_stl_names(shipped)
    assert full == edition_phantom_stl_names(EDITION_FULL, shipped)
    assert not any(name.endswith("_reduced_1000t.stl") for name in full)
    assert set(light_phantom_stl_names()) < set(full)
    assert {name for name in shipped if not name.endswith("_reduced_1000t.stl")} == set(full)


def test_light_list_refuses_a_partial_starter_set():
    names = light_phantom_stl_names()[1:]
    with pytest.raises(ValueError, match="missing"):
        edition_phantom_stl_names(EDITION_LIGHT, names)
    with pytest.raises(ValueError, match="unknown edition"):
        edition_phantom_stl_names("spike", names)


def test_light_png_render_returns_none_without_a_browser(light, no_browser_launch):
    from guiskindose.export.images import render_dosemap_png

    png = render_dosemap_png(*_TRIANGLE)

    assert png is None
    assert no_browser_launch == []


def test_light_rich_report_marks_images_unavailable_without_a_browser(light, no_browser_launch):
    from guiskindose import PyskindoseSettings, load_settings_example_json
    from guiskindose.export import collect_export_payload
    from guiskindose.export.writers import render_bytes
    from guiskindose.main import build_cli_export_source

    settings = PyskindoseSettings(settings=load_settings_example_json())
    settings.mode = "calculate_dose"
    settings.phantom.model = "plane"
    rdsr = files("guiskindose") / "example_data" / "RDSR" / "siemens_axiom_example_procedure.dcm"
    source = build_cli_export_source([str(rdsr)], settings)

    payload = collect_export_payload(source, with_images=True)
    html = render_bytes(payload, "html")

    assert payload.images
    assert all(image.png_bytes is None for image in payload.images)
    assert all(PNG_UNAVAILABLE_MESSAGE in (image.error_message or "") for image in payload.images)
    assert PNG_UNAVAILABLE_MESSAGE.encode() in html
    for fmt in ("pdf", "docx", "xlsx"):
        assert render_bytes(payload, fmt)
    assert no_browser_launch == []


def test_full_png_render_reaches_the_kaleido_entry(monkeypatch):
    """Control for the Light tests: in Full the same call does reach ``to_image``."""
    import plotly.graph_objects as go

    from guiskindose.export.images import render_dosemap_png

    monkeypatch.setattr(go.Figure, "to_image", lambda *_a, **_k: b"png")
    assert render_dosemap_png(*_TRIANGLE) == b"png"


def test_light_static_dose_maps_stop_before_rendering(light, capsys):
    from guiskindose.plotting.create_dose_map_plot import _write_and_show_static_dose_maps

    fig = MagicMock()
    _write_and_show_static_dose_maps(fig, MagicMock())

    fig.to_image.assert_not_called()
    assert PNG_UNAVAILABLE_MESSAGE in capsys.readouterr().out


@pytest.fixture
def starter_only(tmp_path):
    """A phantom_data folder holding only one starter mesh."""
    source = package_phantom_data_dir() / "adult_male.stl"
    (tmp_path / "adult_male.stl").write_bytes(source.read_bytes())
    return tmp_path


def test_catalog_stems_include_aliases_poses_and_previews():
    assert is_clinical_catalog_stem("senior_male")
    assert is_clinical_catalog_stem("senior_male_arms_down_reduced_3000t")
    assert is_clinical_catalog_stem("pediatric_10y_male")  # legacy alias
    assert not is_clinical_catalog_stem("demo_cosmic_buddha")
    assert not is_clinical_catalog_stem("../senior_male")


def test_non_starter_mesh_is_reported_not_installed(light, starter_only):
    assert resolve_human_mesh_stl_path("adult_male", phantom_data_dir=starter_only).is_file()

    with pytest.raises(HumanMeshNotInstalledError) as excinfo:
        resolve_human_mesh_stl_path("senior_male", phantom_data_dir=starter_only)

    message = str(excinfo.value)
    assert "Senior Male" in message
    assert "senior_male" in message
    assert "Light" in message
    assert "Full download" in message
    assert str(starter_only) not in message


def test_missing_mesh_in_full_points_at_reinstall(starter_only):
    message = human_mesh_not_installed_message("senior_male", phantom_data_dir=starter_only)
    assert message is not None
    assert "Reinstall" in message
    assert human_mesh_not_installed_message("adult_male", phantom_data_dir=starter_only) is None


def test_unknown_stem_is_still_unknown_not_missing(starter_only):
    with pytest.raises(ValueError, match="Unknown human mesh stem") as excinfo:
        resolve_human_mesh_stl_path("not_a_catalog_mesh", phantom_data_dir=starter_only)
    assert not isinstance(excinfo.value, HumanMeshNotInstalledError)


def test_phantom_refuses_a_missing_mesh_instead_of_replacing_it(light, starter_only, monkeypatch):
    from guiskindose import load_settings_example_json, phantom_mesh_names
    from guiskindose.phantom_class import Phantom
    from guiskindose.settings import PyskindoseSettings

    monkeypatch.setattr(phantom_mesh_names, "package_phantom_data_dir", lambda: starter_only)
    dims = PyskindoseSettings(settings=load_settings_example_json()).phantom.dimension

    with pytest.raises(HumanMeshNotInstalledError, match="senior_male"):
        Phantom(phantom_model="human", phantom_dim=dims, human_mesh="senior_male")
    assert Phantom(phantom_model="human", phantom_dim=dims, human_mesh="adult_male").human_model == "adult_male"
