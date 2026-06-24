"""Unit tests for the multi-exam Data Table tag column (rebuild_rdsr_df).

The concatenated preview frame ``state.rdsr_df`` is the single source for the
Data Table and the single-exam calculation. In multi-exam mode each row is
tagged with a display-only ``EXAM_COLUMN`` so the table can show which exam a row
came from; single-exam frames must stay untagged so the calculation is
unaffected.
"""

from __future__ import annotations

from types import SimpleNamespace

import pandas as pd
import pytest

pytest.importorskip("nicegui")

from mypyskindose.gui.helpers import EXAM_COLUMN, EXAM_INDEX_COLUMN, rebuild_rdsr_df
from mypyskindose.gui.state import AppState


def _exam(n_events: int, kvp: float) -> SimpleNamespace:
    return SimpleNamespace(
        normalized_data=pd.DataFrame({"kVp": [kvp] * n_events, "Ap1": [0.0] * n_events})
    )


def test_single_exam_has_no_tag_column():
    st = AppState()
    st.loaded_exams = [_exam(3, 70)]
    st.loaded_exam_meta = [{"file_name": "a.dcm"}]

    rebuild_rdsr_df(st)

    assert st.rdsr_df is not None
    assert EXAM_COLUMN not in st.rdsr_df.columns
    assert len(st.rdsr_df) == 3


def test_multi_exam_tags_each_row_with_its_source():
    st = AppState()
    st.loaded_exams = [_exam(2, 70), _exam(3, 80)]
    st.loaded_exam_meta = [{"file_name": "a.dcm"}, {"file_name": "b.csv"}]

    rebuild_rdsr_df(st)

    assert st.rdsr_df is not None
    assert list(st.rdsr_df.columns)[0] == EXAM_INDEX_COLUMN
    assert st.rdsr_df.columns[1] == EXAM_COLUMN
    assert st.rdsr_df[EXAM_INDEX_COLUMN].tolist() == [0, 0, 1, 1, 1]
    assert st.rdsr_df[EXAM_COLUMN].tolist() == ["#1 · a.dcm"] * 2 + ["#2 · b.csv"] * 3
    # original per-exam frames are untouched (tag added on a copy)
    assert EXAM_COLUMN not in st.loaded_exams[0].normalized_data.columns


def test_no_exams_clears_frame():
    st = AppState()
    st.loaded_exams = []

    rebuild_rdsr_df(st)

    assert st.rdsr_df is None
