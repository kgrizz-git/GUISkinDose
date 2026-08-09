"""Unit tests for Part V Calculate/Settings summary formatters."""

from __future__ import annotations

import pytest

pytest.importorskip("nicegui")

from types import SimpleNamespace

import pandas as pd

from mypyskindose.gui.geometry_preview import clamp_geometry_event_index
from mypyskindose.gui.helpers import EXAM_INDEX_COLUMN, rebuild_rdsr_df
from mypyskindose.gui.offset_handlers import bump_per_exam_offsets_version
from mypyskindose.gui.state import AppState
from mypyskindose.gui.summary_formatters import format_patient_offsets, format_table_offset_line


def _meta(d_lon: float = 0.0, d_ver: float = 0.0, d_lat: float = 0.0) -> dict:
    return {"d_lon": d_lon, "d_ver": d_ver, "d_lat": d_lat}


def test_format_patient_offsets_empty_exams():
    st = AppState()
    assert format_patient_offsets(st) == "—"


def test_format_patient_offsets_single_exam_uses_lon_ver_lat():
    st = AppState()
    st.loaded_exams = [SimpleNamespace(normalized_data=pd.DataFrame({"kVp": [70.0]}))]
    st.loaded_exam_meta = [_meta(1.0, 2.0, 3.0)]
    st.is_multi_exam = False
    st.d_lon, st.d_ver, st.d_lat = 4.0, 5.0, 6.0
    text = format_patient_offsets(st)
    assert "lon: 4.0" in text
    assert "ver: 5.0" in text
    assert "lat: 6.0" in text
    assert "X:" not in text


def test_format_patient_offsets_multi_exam_two_exams():
    st = AppState()
    st.loaded_exams = [
        SimpleNamespace(normalized_data=pd.DataFrame({"kVp": [70.0]})),
        SimpleNamespace(normalized_data=pd.DataFrame({"kVp": [80.0]})),
    ]
    st.loaded_exam_meta = [_meta(1.0, 2.0, 3.0), _meta(4.0, 5.0, 6.0)]
    st.is_multi_exam = True
    text = format_patient_offsets(st)
    assert "Exam #1: lon=1.0" in text
    assert "Exam #2: lon=4.0" in text
    assert "and" not in text


def test_format_patient_offsets_multi_exam_truncates_after_three():
    st = AppState()
    st.loaded_exams = [SimpleNamespace(normalized_data=pd.DataFrame({"kVp": [70.0]}))] * 4
    st.loaded_exam_meta = [_meta(float(i), 0.0, 0.0) for i in range(4)]
    st.is_multi_exam = True
    text = format_patient_offsets(st)
    assert "Exam #3:" in text
    assert "Exam #4:" not in text
    assert "and 1 more" in text


def test_format_table_offset_line_multi_exam():
    st = AppState()
    st.is_multi_exam = True
    st.normalization_method = "Vendor"
    assert format_table_offset_line(st) == "Per-exam: see Per-exam corrections below."


def test_format_table_offset_line_single_vendor_unchanged():
    st = AppState()
    st.is_multi_exam = False
    st.normalization_method = "Vendor"
    st.table_offset_x, st.table_offset_y, st.table_offset_z = 1.0, 2.0, 3.0
    assert "X: 1.0" in format_table_offset_line(st)


def test_format_table_offset_line_tabular_branch_unchanged():
    st = AppState()
    st.is_multi_exam = False
    st.normalization_method = "Tabular"
    assert "tabular" in format_table_offset_line(st)


def test_bump_per_exam_offsets_version_increments():
    st = AppState()
    assert st.per_exam_offsets_version == 0
    bump_per_exam_offsets_version(st)
    assert st.per_exam_offsets_version == 1


def test_clamp_geometry_event_index_to_active_slice():
    st = AppState()
    st.loaded_exams = [
        SimpleNamespace(normalized_data=pd.DataFrame({"kVp": [70.0] * 5})),
        SimpleNamespace(normalized_data=pd.DataFrame({"kVp": [80.0] * 2})),
    ]
    st.loaded_exam_meta = [{"file_name": "a.dcm"}, {"file_name": "b.csv"}]
    rebuild_rdsr_df(st)
    st.is_multi_exam = True
    st.active_exam_index = 1
    assert clamp_geometry_event_index(st, 9, active_exam_index=1, composite=False) == 1
    assert st.rdsr_df is not None
    assert EXAM_INDEX_COLUMN in st.rdsr_df.columns
