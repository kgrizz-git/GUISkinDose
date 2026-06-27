"""Unit tests for interactive offset reset, sync, and table-origin staging (Phase 0–2b)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

pytest.importorskip("nicegui")

from mypyskindose import get_path_to_example_rdsr_files
from mypyskindose.gui.helpers import (
    build_settings,
    commit_table_origin_transform,
    detected_table_origin,
    effective_patient_offset_for_preview,
    effective_table_origin,
    load_rdsr,
    load_tabular,
    on_global_patient_offset_change,
    on_global_patient_offset_scrub,
    reset_global_offsets_on_new_load,
    restore_globals_from_exam_meta,
    stage_table_origin_axis,
    sync_global_patient_offset_to_single_exam_meta,
)
from mypyskindose.gui.tabs.geometry import geometry_vendor_notice
from mypyskindose.gui.page_context import PageContext
from mypyskindose.gui.state import AppState


def _minimal_ctx() -> PageContext:
    return PageContext(
        tabs=MagicMock(),
        file_label=MagicMock(),
        events_label=MagicMock(),
        psd_label=MagicMock(),
        run_btn_drawer=MagicMock(),
    )


_EXAMPLE_RDSR = get_path_to_example_rdsr_files() / "siemens_axiom_artis.dcm"
_FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "tabular_inputs"


def test_load_rdsr_resets_global_patient_offset():
    st = AppState()
    st.d_lon = 12.0
    st.d_ver = 3.0
    st.d_lat = -4.0
    ok, _ = load_rdsr(_EXAMPLE_RDSR, st)
    assert ok
    assert st.d_lon == 0.0
    assert st.d_ver == 0.0
    assert st.d_lat == 0.0


def test_load_tabular_resets_global_patient_offset():
    st = AppState()
    st.d_lon = 5.0
    st.input_schema = "normalized"
    ok, _ = load_tabular(_FIXTURES / "normalized_events.csv", st)
    assert ok
    assert st.d_lon == 0.0


def test_load_tabular_replace_existing_preserves_global_patient_offset():
    st = AppState()
    st.input_schema = "normalized"
    load_tabular(_FIXTURES / "normalized_events.csv", st)
    st.d_lon = 8.0
    st.d_ver = 1.0
    st.d_lat = 2.0
    ok, _ = load_tabular(_FIXTURES / "normalized_events.csv", st, replace_existing=True)
    assert ok
    assert st.d_lon == 8.0
    assert st.d_ver == 1.0
    assert st.d_lat == 2.0


def test_new_load_resets_coordinate_flags_not_replace_existing():
    st = AppState()
    st.swap_lat_lon = True
    st.flip_ap1 = True
    st.input_schema = "normalized"
    load_tabular(_FIXTURES / "normalized_events.csv", st)
    assert st.swap_lat_lon is False
    assert st.flip_ap1 is False


def test_clear_all_exams_resets_global_patient_offset():
    st = AppState()
    st.d_lon = 9.0
    reset_global_offsets_on_new_load(st)
    assert st.d_lon == 0.0
    assert st.swap_lat_lon is False


def test_sync_global_patient_offset_to_single_exam_meta():
    st = AppState()
    st.d_lon, st.d_ver, st.d_lat = 1.0, 2.0, 3.0
    st.loaded_exams = [SimpleNamespace()]
    st.loaded_exam_meta = [{"d_lon": 0.0, "d_ver": 0.0, "d_lat": 0.0}]
    sync_global_patient_offset_to_single_exam_meta(st)
    assert st.loaded_exam_meta[0]["d_lon"] == 1.0
    assert st.loaded_exam_meta[0]["d_ver"] == 2.0
    assert st.loaded_exam_meta[0]["d_lat"] == 3.0


def test_sync_does_not_touch_meta_when_multi_exam():
    st = AppState()
    st.d_lon = 5.0
    st.loaded_exams = [SimpleNamespace(), SimpleNamespace()]
    st.loaded_exam_meta = [
        {"d_lon": 0.0, "d_ver": 0.0, "d_lat": 0.0},
        {"d_lon": 0.0, "d_ver": 0.0, "d_lat": 0.0},
    ]
    sync_global_patient_offset_to_single_exam_meta(st)
    assert st.loaded_exam_meta[0]["d_lon"] == 0.0


def test_build_settings_propagates_explicit_patient_offset():
    st = AppState()
    st.d_lon, st.d_ver, st.d_lat = 1.0, 2.0, 3.0
    settings = build_settings(st, patient_offset=(10.0, 20.0, 30.0))
    assert settings.phantom.patient_offset.d_lon == 10.0
    assert settings.phantom.patient_offset.d_ver == 20.0
    assert settings.phantom.patient_offset.d_lat == 30.0


def test_on_global_patient_offset_change_invokes_refresh_per_exam():
    st = AppState()
    st.loaded_exams = [SimpleNamespace()]
    st.loaded_exam_meta = [{"d_lon": 0.0, "d_ver": 0.0, "d_lat": 0.0}]
    ctx = _minimal_ctx()
    refreshed = {"called": False}

    def _refresh() -> None:
        refreshed["called"] = True

    ctx.refresh_per_exam = _refresh
    with patch("mypyskindose.gui.offset_handlers.state", st):
        st.d_lon = 7.0
        on_global_patient_offset_change(ctx)
    assert refreshed["called"]
    assert st.loaded_exam_meta[0]["d_lon"] == 7.0
    assert st.calculation_done is False


def test_remove_exam_restores_global_patient_offset_from_meta():
    st = AppState()
    st.d_lon = 99.0
    meta0 = {"d_lon": 1.0, "d_ver": 2.0, "d_lat": 3.0, "swap_lat_lon": False}
    restore_globals_from_exam_meta(st, meta0)
    assert st.d_lon == 1.0
    assert st.d_ver == 2.0
    assert st.d_lat == 3.0


def test_stage_table_origin_axis_does_not_call_apply():
    meta = {"table_origin_detected": {"x": 1.0, "y": 2.0, "z": 3.0}, "table_origin_override": None}
    with patch("mypyskindose.gui.helpers.apply_exam_transforms") as mock_apply:
        stage_table_origin_axis(meta, "x", 5.0)
    mock_apply.assert_not_called()
    assert meta["table_origin_override"]["x"] == 5.0


def test_table_origin_display_uses_final_frame_after_manual_swap():
    meta = {
        "table_origin_detected": {"x": 1.0, "y": 2.0, "z": 3.0},
        "table_origin_override": {"x": 5.0, "y": 2.0, "z": 7.0},
        "swap_lat_lon": True,
    }
    assert detected_table_origin(meta) == {"x": 3.0, "y": 2.0, "z": 1.0}
    assert effective_table_origin(meta) == {"x": 7.0, "y": 2.0, "z": 5.0}


def test_stage_table_origin_axis_inverse_maps_final_axis_after_manual_swap():
    meta = {
        "table_origin_detected": {"x": 1.0, "y": 2.0, "z": 3.0},
        "table_origin_override": None,
        "swap_lat_lon": True,
    }
    stage_table_origin_axis(meta, "x", 9.0)
    assert meta["table_origin_override"] == {"x": 1.0, "y": 2.0, "z": 9.0}
    assert effective_table_origin(meta)["x"] == 9.0


def test_staged_final_x_changes_plotted_tx_after_manual_swap():
    st = AppState()
    base = pd.DataFrame({"kVp": [70.0], "Tx": [1.0], "Ty": [0.0], "Tz": [2.0]})
    st.loaded_exams = [SimpleNamespace(normalized_data=base.copy())]
    meta = {
        "base_data": base,
        "schema": "generic_rdsr_like",
        "table_origin_detected": {"x": 0.0, "y": 0.0, "z": 0.0},
        "table_origin_override": None,
        "swap_lat_lon": True,
        "flip_ap1": False,
        "flip_ap2": False,
    }
    st.loaded_exam_meta = [meta]
    stage_table_origin_axis(meta, "x", 10.0)
    commit_table_origin_transform(st, 0)

    df = st.loaded_exams[0].normalized_data
    assert float(df["Tx"].iloc[0]) == pytest.approx(12.0)
    assert float(df["Tz"].iloc[0]) == pytest.approx(1.0)


def test_geometry_vendor_notice_warns_when_ge_manual_swap_is_active():
    notice = geometry_vendor_notice(
        {
            "warnings": ["GE manufacturer detected."],
            "swap_lat_lon": True,
            "schema": "radimetrics",
            "source_type": "csv",
            "normalization_method": "Tabular",
        },
        manufacturer="GE Healthcare",
    )
    assert "GE handling is already normalized" in notice
    assert "may double-correct" in notice


def test_geometry_vendor_notice_warns_for_fallback_and_manual_swap():
    notice = geometry_vendor_notice(
        {
            "swap_lat_lon": True,
            "flip_tx": True,
            "schema": "generic_rdsr_like",
            "source_type": "csv",
            "normalization_method": "Fallback",
        }
    )
    assert "Default normalization in use" in notice
    assert "Manual Tx/Tz swap is active" in notice
    assert "Axis-direction flip reverses table motion" in notice


def test_geometry_vendor_notice_warns_for_philips_large_offset_risk():
    notice = geometry_vendor_notice(
        {"normalization_method": "Matched", "schema": "dicom_rdsr"},
        manufacturer="Philips Medical Systems",
    )
    assert "Philips large table offsets" in notice


def test_commit_table_origin_transform_rebuilds_rdsr_df():
    st = AppState()
    base = pd.DataFrame({"kVp": [70.0], "Tx": [1.0], "Ty": [0.0], "Tz": [0.0]})
    st.loaded_exams = [SimpleNamespace(normalized_data=base.copy())]
    st.loaded_exam_meta = [
        {
            "base_data": base,
            "schema": "generic_rdsr_like",
            "table_origin_detected": {"x": 0.0, "y": 0.0, "z": 0.0},
            "table_origin_override": {"x": 10.0, "y": 0.0, "z": 0.0},
            "swap_lat_lon": False,
            "flip_ap1": False,
            "flip_ap2": False,
        }
    ]
    commit_table_origin_transform(st, 0)
    assert st.rdsr_df is not None
    assert float(st.loaded_exams[0].normalized_data["Tx"].iloc[0]) == pytest.approx(11.0)


def test_effective_table_origin_uses_override():
    meta = {
        "table_origin_detected": {"x": 1.0, "y": 2.0, "z": 3.0},
        "table_origin_override": {"x": 5.0, "y": 2.0, "z": 3.0},
    }
    origin = effective_table_origin(meta)
    assert origin["x"] == 5.0
    assert origin["y"] == 2.0


def test_effective_patient_offset_for_preview_uses_globals():
    st = AppState()
    st.d_lon, st.d_ver, st.d_lat = 4.0, 5.0, 6.0
    assert effective_patient_offset_for_preview(st) == (4.0, 5.0, 6.0)


def test_on_global_patient_offset_scrub_syncs_meta():
    st = AppState()
    st.d_lon = 3.0
    st.loaded_exams = [SimpleNamespace()]
    st.loaded_exam_meta = [{"d_lon": 0.0, "d_ver": 0.0, "d_lat": 0.0}]
    ctx = _minimal_ctx()
    with patch("mypyskindose.gui.offset_handlers.state", st):
        on_global_patient_offset_scrub(ctx)
    assert st.loaded_exam_meta[0]["d_lon"] == 3.0


def test_load_rdsr_stores_normalization_method_on_meta():
    st = AppState()
    ok, _ = load_rdsr(_EXAMPLE_RDSR, st)
    assert ok
    assert "normalization_method" in st.loaded_exam_meta[0]
    assert st.loaded_exam_meta[0]["normalization_method"] in ("Matched", "Fallback")
