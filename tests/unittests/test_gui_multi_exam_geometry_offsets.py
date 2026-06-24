"""Unit tests for multi-exam Geometry preview helpers (Part II)."""

from __future__ import annotations

from types import SimpleNamespace

import pandas as pd
import pytest

pytest.importorskip("nicegui")

from mypyskindose.gui.geometry_preview import (
    adjust_active_exam_index_after_remove,
    clamp_active_exam_index,
    effective_patient_offset_for_preview,
    preview_event_count,
    rdsr_df_for_geometry_preview,
)
from mypyskindose.gui.helpers import EXAM_COLUMN, EXAM_INDEX_COLUMN, rebuild_rdsr_df
from mypyskindose.gui.state import AppState, reset_results


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
