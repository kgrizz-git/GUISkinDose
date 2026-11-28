"""A downloaded/user-library mesh is visible in the Settings preview."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

pytest.importorskip("nicegui")

from guiskindose.gui import phantom_preview as phantom_preview_mod
from guiskindose.gui.phantom_preview import PreviewSnapshot, make_phantom_preview_fig, resolve_preview_mesh
from guiskindose.phantom_mesh_names import package_phantom_data_dir

pytestmark = pytest.mark.nicegui_main_file("tests/gui/nicegui_main.py")


def _snapshot(stem: str) -> PreviewSnapshot:
    return PreviewSnapshot(
        phantom_model="human",
        human_mesh=stem,
        patient_orientation="head_first_supine",
        scale_lat=1.0,
        scale_ap=1.0,
        scale_lon=1.0,
        d_lon=0.0,
        d_ver=0.0,
        d_lat=0.0,
    )


def test_downloaded_mesh_is_used_by_settings_preview(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = package_phantom_data_dir() / "adult_male.stl"
    if not source.is_file():
        pytest.skip("shipped adult_male.stl is required for the preview fixture")
    shipped = tmp_path / "shipped"
    library = tmp_path / "library"
    shipped.mkdir()
    library.mkdir()
    shutil.copyfile(source, library / "senior_male.stl")

    monkeypatch.setattr(phantom_preview_mod, "_PHANTOM_DATA_DIR", shipped)
    monkeypatch.setattr(
        "guiskindose.phantom_library.default_user_library_dir",
        lambda: library,
    )

    assert resolve_preview_mesh("senior_male") == "senior_male"
    fig = make_phantom_preview_fig(_snapshot("senior_male"))
    assert fig is not None
    assert any(trace.get("type") == "mesh3d" for trace in fig.get("data", []))
