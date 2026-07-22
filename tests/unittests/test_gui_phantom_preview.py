"""Unit tests for Settings phantom preview figure builder (no NiceGUI).

Covers mesh resolve, habitus scale ratios, patient offsets, orientation,
uirevision, and no-RDSR construction via PreviewSnapshot injection.
"""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from mypyskindose.constants import COLOR_PAD, COLOR_PATIENT, COLOR_TABLE
from mypyskindose.gui.phantom_preview import (
    PreviewSnapshot,
    capture_phantom_preview_snapshot,
    make_phantom_preview_fig,
    resolve_preview_mesh,
)
from mypyskindose.gui.state import AppState


def _snapshot(**overrides) -> PreviewSnapshot:
    base = PreviewSnapshot(
        phantom_model="human",
        human_mesh="hudfrid",
        patient_orientation="head_first_supine",
        scale_lat=1.0,
        scale_ap=1.0,
        scale_lon=1.0,
        d_lon=0.0,
        d_ver=0.0,
        d_lat=0.0,
    )
    return replace(base, **overrides) if overrides else base


def _mesh3d_traces(fig: dict) -> list[dict]:
    return [t for t in fig.get("data", []) if t.get("type") == "mesh3d"]


def _patient_trace(fig: dict) -> dict:
    for t in _mesh3d_traces(fig):
        if t.get("color") == COLOR_PATIENT:
            return t
    raise AssertionError("patient Mesh3d not found")


def _span(trace: dict, axis: str) -> float:
    vals = np.asarray(trace[axis], dtype=float)
    return float(vals.max() - vals.min())


def test_resolve_preview_mesh_prefers_reduced_when_present():
    assert resolve_preview_mesh("hudfrid") == "hudfrid_reduced_1000t"


def test_resolve_preview_mesh_returns_stem_when_reduced_absent(tmp_path, monkeypatch):
    # Point resolver at an empty phantom_data dir so reduced companion is missing.
    monkeypatch.setattr(
        "mypyskindose.gui.phantom_preview._PHANTOM_DATA_DIR",
        tmp_path,
    )
    (tmp_path / "only_full.stl").write_bytes(b"solid empty\nendsolid empty\n")
    assert resolve_preview_mesh("only_full") == "only_full"


def test_resolve_preview_mesh_never_double_appends_reduced_suffix():
    assert resolve_preview_mesh("hudfrid_reduced_1000t") == "hudfrid_reduced_1000t"


def test_make_phantom_preview_fig_builds_patient_table_pad_without_rdsr():
    fig = make_phantom_preview_fig(_snapshot())
    assert fig is not None
    colors = {t.get("color") for t in _mesh3d_traces(fig)}
    assert COLOR_PATIENT in colors
    assert COLOR_TABLE in colors
    assert COLOR_PAD in colors


def test_make_phantom_preview_fig_unknown_stem_returns_none():
    assert make_phantom_preview_fig(_snapshot(human_mesh="definitely_not_a_mesh")) is None


def test_make_phantom_preview_fig_uniform_scale_changes_spans():
    base = make_phantom_preview_fig(_snapshot())
    scaled = make_phantom_preview_fig(_snapshot(scale_lat=1.2, scale_ap=1.2, scale_lon=1.2))
    assert base is not None and scaled is not None
    bp, sp = _patient_trace(base), _patient_trace(scaled)
    assert _span(sp, "x") / _span(bp, "x") == pytest.approx(1.2, rel=0.05)
    assert _span(sp, "y") / _span(bp, "y") == pytest.approx(1.2, rel=0.05)
    assert _span(sp, "z") / _span(bp, "z") == pytest.approx(1.2, rel=0.05)


def test_make_phantom_preview_fig_nonuniform_scale_changes_corresponding_spans():
    base = make_phantom_preview_fig(_snapshot())
    scaled = make_phantom_preview_fig(_snapshot(scale_lat=1.2, scale_ap=0.8, scale_lon=1.4))
    assert base is not None and scaled is not None
    bp, sp = _patient_trace(base), _patient_trace(scaled)
    assert _span(sp, "x") / _span(bp, "x") == pytest.approx(1.2, rel=0.05)
    assert _span(sp, "y") / _span(bp, "y") == pytest.approx(0.8, rel=0.05)
    assert _span(sp, "z") / _span(bp, "z") == pytest.approx(1.4, rel=0.05)


def test_make_phantom_preview_fig_offsets_shift_patient():
    zero = make_phantom_preview_fig(_snapshot())
    shifted = make_phantom_preview_fig(_snapshot(d_lon=10.0, d_ver=5.0, d_lat=-7.0))
    assert zero is not None and shifted is not None
    zp, sp = _patient_trace(zero), _patient_trace(shifted)
    # position_patient_phantom_on_table translate order is [d_lon, d_ver, d_lat]
    # mapped onto phantom r columns [x, y, z] after placement.
    z_cent = np.mean(np.asarray(zp["x"])), np.mean(np.asarray(zp["y"])), np.mean(np.asarray(zp["z"]))
    s_cent = np.mean(np.asarray(sp["x"])), np.mean(np.asarray(sp["y"])), np.mean(np.asarray(sp["z"]))
    # Lon/ver/lat map to translate dr = [d_lon, d_ver, d_lat] on (x,y,z) in this codebase.
    assert s_cent[0] - z_cent[0] == pytest.approx(10.0, abs=0.5)
    assert s_cent[1] - z_cent[1] == pytest.approx(5.0, abs=0.5)
    assert s_cent[2] - z_cent[2] == pytest.approx(-7.0, abs=0.5)


def test_make_phantom_preview_fig_feet_first_differs_from_head_first():
    head = make_phantom_preview_fig(_snapshot(patient_orientation="head_first_supine"))
    feet = make_phantom_preview_fig(_snapshot(patient_orientation="feet_first_supine"))
    assert head is not None and feet is not None
    hp, fp = _patient_trace(head), _patient_trace(feet)
    assert not np.allclose(np.asarray(hp["z"]), np.asarray(fp["z"]))


def test_make_phantom_preview_fig_uirevision_is_logical_stem():
    fig = make_phantom_preview_fig(_snapshot(human_mesh="hudfrid"))
    assert fig is not None
    assert fig["layout"]["uirevision"] == "hudfrid"


def test_capture_phantom_preview_snapshot_uses_active_exam_offsets_in_multi_exam():
    app_state = AppState(
        is_multi_exam=True,
        active_exam_index=1,
        d_lon=1.0,
        d_ver=2.0,
        d_lat=3.0,
        loaded_exam_meta=[
            {"d_lon": 0.0, "d_ver": 0.0, "d_lat": 0.0},
            {"d_lon": 11.0, "d_ver": 22.0, "d_lat": 33.0},
        ],
        human_mesh="hudfrid",
        phantom_model="human",
        patient_orientation="head_first_supine",
        phantom_scale_lat=1.1,
        phantom_scale_ap=1.2,
        phantom_scale_lon=1.3,
    )
    snap = capture_phantom_preview_snapshot(app_state)
    assert snap.d_lon == pytest.approx(11.0)
    assert snap.d_ver == pytest.approx(22.0)
    assert snap.d_lat == pytest.approx(33.0)
    assert snap.scale_lat == pytest.approx(1.1)
    assert snap.human_mesh == "hudfrid"


def test_make_phantom_preview_fig_non_human_returns_none():
    assert make_phantom_preview_fig(_snapshot(phantom_model="cylinder")) is None
