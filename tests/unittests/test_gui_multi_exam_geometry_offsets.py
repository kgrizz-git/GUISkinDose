"""Unit tests for multi-exam Geometry preview helpers and offset write-back."""

from __future__ import annotations

from types import SimpleNamespace

import pandas as pd
import pytest

pytest.importorskip("nicegui")

from guiskindose.gui.geometry_preview import (
    adjust_active_exam_index_after_remove,
    clamp_active_exam_index,
    composite_preview_after_exam_mode_change,
    effective_patient_offset_for_preview,
    event_context_caption,
    exam_select_value,
    geometry_preview_caption,
    preview_event_count,
    procedure_live_preview_paused,
    rdsr_df_for_geometry_preview,
    resolve_composite_for_render,
)
from guiskindose.gui.helpers import (
    EXAM_COLUMN,
    EXAM_INDEX_COLUMN,
    apply_patient_offset_slider_tick,
    read_patient_offset_value,
    rebuild_rdsr_df,
    reset_patient_offset_for_active,
)
from guiskindose.gui.state import AppState, reset_results


def _exam(n_events: int, kvp: float) -> SimpleNamespace:
    return SimpleNamespace(
        normalized_data=pd.DataFrame({"kVp": [kvp] * n_events, "Ap1": [0.0] * n_events})
    )


def _multi_exam_state() -> AppState:
    st = AppState()
    st.loaded_exams = [_exam(2, 70), _exam(3, 80)]
    st.loaded_exam_meta = [
        {"file_name": "a.dcm", "d_lon": 1.0, "d_ver": 2.0, "d_lat": 3.0},
        {"file_name": "b.csv", "d_lon": 4.0, "d_ver": 5.0, "d_lat": 6.0},
    ]
    rebuild_rdsr_df(st)
    st.is_multi_exam = True
    st.active_exam_index = 1
    return st


def test_exam_select_value_empty_options():
    assert exam_select_value(0, set()) is None
    assert exam_select_value(None, set()) is None


def test_exam_select_value_clamps_to_valid_option():
    assert exam_select_value(99, {0, 1}) == 0
    assert exam_select_value(1, {0, 1}) == 1
    assert exam_select_value(None, {0, 1}) == 0


def test_clamp_active_exam_index_defaults_and_clamps():
    st = AppState()
    st.loaded_exams = [_exam(1, 70), _exam(1, 80)]
    st.active_exam_index = 99
    clamp_active_exam_index(st)
    assert st.is_multi_exam is True
    assert st.active_exam_index == 1

    st.loaded_exams = []
    clamp_active_exam_index(st)
    assert st.active_exam_index is None
    assert st.is_multi_exam is False


def test_adjust_active_exam_index_after_remove():
    st = _multi_exam_state()
    adjust_active_exam_index_after_remove(st, removed_index=0)
    assert st.active_exam_index == 0

    st = _multi_exam_state()
    adjust_active_exam_index_after_remove(st, removed_index=1)
    assert st.active_exam_index == 0

    st = _multi_exam_state()
    st.active_exam_index = 0
    adjust_active_exam_index_after_remove(st, removed_index=0)
    assert st.active_exam_index == 0


def test_rdsr_df_for_geometry_preview_slices_by_exam_index():
    st = _multi_exam_state()
    sliced = rdsr_df_for_geometry_preview(st, active_exam_index=1, composite=False)
    assert sliced is not None
    assert len(sliced) == 3
    assert EXAM_INDEX_COLUMN not in sliced.columns
    assert EXAM_COLUMN not in sliced.columns

    all_exams = rdsr_df_for_geometry_preview(st, composite=True)
    assert all_exams is not None
    assert len(all_exams) == 5


def test_preview_event_count_matches_slice():
    st = _multi_exam_state()
    assert preview_event_count(st, active_exam_index=0, composite=False) == 2
    assert preview_event_count(st, composite=True) == 5


def test_effective_patient_offset_for_preview_uses_active_meta():
    st = _multi_exam_state()
    assert effective_patient_offset_for_preview(st, active_exam_index=1) == (4.0, 5.0, 6.0)

    st.is_multi_exam = False
    st.d_lon, st.d_ver, st.d_lat = 9.0, 8.0, 7.0
    assert effective_patient_offset_for_preview(st) == (9.0, 8.0, 7.0)


def test_reset_results_preserves_active_exam_index():
    st = _multi_exam_state()
    reset_results()
    assert st.active_exam_index == 1
    assert st.calculation_done is False


def test_commit_table_origin_transform_uses_exam_index():
    from guiskindose.gui.helpers import commit_table_origin_transform

    st = _multi_exam_state()
    base = pd.DataFrame({"kVp": [70.0], "Tx": [1.0], "Ty": [0.0], "Tz": [0.0]})
    st.loaded_exams = [
        SimpleNamespace(normalized_data=base.copy()),
        SimpleNamespace(normalized_data=base.copy()),
    ]
    st.loaded_exam_meta = [
        {
            "base_data": base,
            "schema": "generic_rdsr_like",
            "table_origin_detected": {"x": 0.0, "y": 0.0, "z": 0.0},
            "table_origin_override": None,
            "swap_lat_lon": False,
            "flip_ap1": False,
            "flip_ap2": False,
        },
        {
            "base_data": base.copy(),
            "schema": "generic_rdsr_like",
            "table_origin_detected": {"x": 0.0, "y": 0.0, "z": 0.0},
            "table_origin_override": {"x": 20.0, "y": 0.0, "z": 0.0},
            "swap_lat_lon": False,
            "flip_ap1": False,
            "flip_ap2": False,
        },
    ]
    rebuild_rdsr_df(st)
    commit_table_origin_transform(st, 1)
    assert float(st.loaded_exams[1].normalized_data["Tx"].iloc[0]) == pytest.approx(21.0)
    assert float(st.loaded_exams[0].normalized_data["Tx"].iloc[0]) == pytest.approx(1.0)


def test_exam_index_column_avoids_display_tag_collision():
    """Filename '#1 · trap.dcm' must not break slicing (T30)."""
    st = AppState()
    st.loaded_exams = [_exam(2, 70), _exam(1, 80)]
    st.loaded_exam_meta = [
        {"file_name": "#1 · trap.dcm"},
        {"file_name": "real_second.csv"},
    ]
    rebuild_rdsr_df(st)
    st.is_multi_exam = True
    sliced = rdsr_df_for_geometry_preview(st, active_exam_index=1, composite=False)
    assert sliced is not None
    assert len(sliced) == 1


def test_apply_patient_offset_slider_tick_writes_meta_not_globals():
    st = _multi_exam_state()
    st.d_lon, st.d_ver, st.d_lat = 9.0, 8.0, 7.0
    apply_patient_offset_slider_tick(st, "d_lon", 11.0)
    assert st.loaded_exam_meta[1]["d_lon"] == pytest.approx(11.0)
    assert st.d_lon == pytest.approx(9.0)
    assert st.d_ver == pytest.approx(8.0)
    assert st.d_lat == pytest.approx(7.0)


def test_read_patient_offset_value_uses_active_meta_in_multi_exam():
    st = _multi_exam_state()
    assert read_patient_offset_value(st, "d_ver", active_index=1) == pytest.approx(5.0)
    st.is_multi_exam = False
    st.d_ver = 12.0
    assert read_patient_offset_value(st, "d_ver") == pytest.approx(12.0)


def test_reset_patient_offset_for_active_zeros_meta_in_multi_exam():
    st = _multi_exam_state()
    reset_patient_offset_for_active(st)
    assert st.loaded_exam_meta[1]["d_lon"] == 0.0
    assert st.loaded_exam_meta[1]["d_ver"] == 0.0
    assert st.loaded_exam_meta[1]["d_lat"] == 0.0
    assert st.loaded_exam_meta[0]["d_lon"] == pytest.approx(1.0)


def test_geometry_preview_caption_modes():
    st = _multi_exam_state()
    st.active_exam_index = 1
    assert "exam #2 events only" in geometry_preview_caption(
        st, composite_preview=False, last_table_origin_scrub=False
    )
    assert "all exams' events" in geometry_preview_caption(
        st, composite_preview=True, last_table_origin_scrub=False
    )
    assert "Table shift applies" in geometry_preview_caption(
        st, composite_preview=False, last_table_origin_scrub=True
    )
    st.is_multi_exam = False
    assert geometry_preview_caption(st, composite_preview=True, last_table_origin_scrub=False) == ""


def test_resolve_composite_for_render_table_scrub_wins():
    assert resolve_composite_for_render(composite_preview=False, last_table_origin_scrub=True) is True
    assert resolve_composite_for_render(composite_preview=True, last_table_origin_scrub=False) is True
    assert resolve_composite_for_render(composite_preview=False, last_table_origin_scrub=False) is False


def test_composite_preview_reset_on_multi_to_single():
    assert composite_preview_after_exam_mode_change(True, False, True) is False
    assert composite_preview_after_exam_mode_change(True, True, True) is True
    assert composite_preview_after_exam_mode_change(False, True, False) is False


def test_procedure_live_preview_paused_only_for_large_composite_procedure():
    st = _multi_exam_state()
    many = _exam(35, 70)
    st.loaded_exams = [many, _exam(1, 80)]
    st.loaded_exam_meta = [{"file_name": "big.dcm"}, {"file_name": "small.csv"}]
    rebuild_rdsr_df(st)
    assert procedure_live_preview_paused(
        st,
        last_preview_mode="plot_procedure",
        composite_preview=True,
        last_table_origin_scrub=False,
    )
    assert not procedure_live_preview_paused(
        st,
        last_preview_mode="plot_procedure",
        composite_preview=False,
        last_table_origin_scrub=False,
    )
    assert not procedure_live_preview_paused(
        st,
        last_preview_mode="plot_setup",
        composite_preview=True,
        last_table_origin_scrub=False,
    )


def _single_exam_state(n_events: int) -> AppState:
    """A single-exam AppState with ``n_events`` events."""
    st = AppState()
    st.loaded_exams = [_exam(n_events, 70)]
    st.loaded_exam_meta = [{"file_name": f"{n_events}_events.dcm"}]
    rebuild_rdsr_df(st)
    st.is_multi_exam = False
    st.active_exam_index = 0
    return st


def test_event_context_caption_single_exam():
    st = _single_exam_state(23)
    assert event_context_caption(st, current_index=5) == "Event 6 / 23"


def test_event_context_caption_multi_exam_active():
    st = _multi_exam_state()
    st.active_exam_index = 1
    # exam #2 (idx 1) has 3 events in the fixture
    assert event_context_caption(st, current_index=2, active_exam_index=1) == "Event 3 / 3 · Exam #2"


def test_event_context_caption_multi_exam_composite():
    st = _multi_exam_state()
    num_total = preview_event_count(st, composite=True)
    assert event_context_caption(st, current_index=2, active_exam_index=None, composite=True) == (
        f"Event 3 / {num_total} · all exams"
    )


def test_event_context_caption_clamps_out_of_range_index():
    st = _multi_exam_state()
    st.active_exam_index = 1
    # exam #2 has 3 events; clamped to last valid index (2), displayed 1-based
    assert event_context_caption(st, current_index=999, active_exam_index=1) == "Event 3 / 3 · Exam #2"


def test_event_context_caption_empty_slice():
    st = AppState()
    st.loaded_exams = [_exam(0, 70)]
    st.loaded_exam_meta = [{"file_name": "empty.dcm"}]
    rebuild_rdsr_df(st)
    st.is_multi_exam = False
    assert event_context_caption(st, current_index=0) == "Event 0 / 0"


def test_procedure_pause_single_exam_large():
    st = _single_exam_state(50)
    assert procedure_live_preview_paused(
        st,
        last_preview_mode="plot_procedure",
        composite_preview=False,
        last_table_origin_scrub=False,
    )


def test_procedure_pause_single_exam_small():
    st = _single_exam_state(10)
    assert not procedure_live_preview_paused(
        st,
        last_preview_mode="plot_procedure",
        composite_preview=False,
        last_table_origin_scrub=False,
    )


def test_procedure_pause_multi_exam_non_composite_large():
    st = _multi_exam_state()
    st.loaded_exams = [_exam(40, 70)]
    st.loaded_exam_meta = [{"file_name": "big.dcm"}]
    rebuild_rdsr_df(st)
    st.is_multi_exam = True
    st.active_exam_index = 0
    assert procedure_live_preview_paused(
        st,
        last_preview_mode="plot_procedure",
        composite_preview=False,
        last_table_origin_scrub=False,
    )


def test_procedure_pause_multi_exam_composite_large():
    st = _multi_exam_state()
    st.loaded_exams = [_exam(20, 70), _exam(20, 80)]
    st.loaded_exam_meta = [{"file_name": "e1.dcm"}, {"file_name": "e2.dcm"}]
    rebuild_rdsr_df(st)
    assert procedure_live_preview_paused(
        st,
        last_preview_mode="plot_procedure",
        composite_preview=True,
        last_table_origin_scrub=False,
    )


def test_procedure_pause_plot_event_never_pauses():
    st = _single_exam_state(50)
    assert not procedure_live_preview_paused(
        st,
        last_preview_mode="plot_event",
        composite_preview=False,
        last_table_origin_scrub=False,
    )


def test_procedure_pause_plot_setup_never_pauses():
    st = _single_exam_state(50)
    assert not procedure_live_preview_paused(
        st,
        last_preview_mode="plot_setup",
        composite_preview=False,
        last_table_origin_scrub=False,
    )


def test_procedure_pause_threshold_param():
    st = _single_exam_state(20)
    assert procedure_live_preview_paused(
        st,
        last_preview_mode="plot_procedure",
        composite_preview=False,
        last_table_origin_scrub=False,
        pause_threshold=15,
    )


def test_geometry_vendor_notice_exported_from_preview():
    from guiskindose.gui.geometry_preview import geometry_vendor_notice as preview_notice
    from guiskindose.gui.tabs.geometry import geometry_vendor_notice as tab_notice

    assert preview_notice is tab_notice


def test_event_select_options():
    from guiskindose.gui.geometry_preview import event_select_options

    assert event_select_options(5) == {1: "1", 2: "2", 3: "3", 4: "4", 5: "5"}
    assert event_select_options(0) == {1: "1"}


def test_exam_selector_options():
    from guiskindose.gui.geometry_preview import exam_selector_options

    st = AppState()
    st.loaded_exam_meta = [{"file_name": "exam1.dcm"}, {"file_name": "exam2.dcm"}]
    assert exam_selector_options(st) == {0: "#1 · exam1.dcm", 1: "#2 · exam2.dcm"}



