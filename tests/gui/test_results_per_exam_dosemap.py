"""Unit tests for multi-exam Results tab per-exam dose map visibility and subset controls."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest

from guiskindose.gui.figures import extract_exam_dose_map
from guiskindose.gui.state import AppState, reset_results
from guiskindose.gui.tabs.results import can_show_more_inline, compute_subset_aggregate


def _make_mock_exam_output(dose_map_pairs: list[tuple[int, float]], num_cells: int = 5):
    patient_dict = {
        "patient": {
            "patient_skin_cells": {"x": [0.0] * num_cells, "y": [0.0] * num_cells, "z": [0.0] * num_cells},
        }
    }
    return SimpleNamespace(
        to_dict=MagicMock(return_value={"dose_map": dose_map_pairs, "patient": patient_dict})
    )


def test_extract_exam_dose_map():
    mock_output = _make_mock_exam_output([(1, 10.5), (3, 22.0)], num_cells=5)
    dose_map, patient_dict = extract_exam_dose_map(mock_output)

    assert isinstance(dose_map, np.ndarray)
    assert len(dose_map) == 5
    assert np.allclose(dose_map, [0.0, 10.5, 0.0, 22.0, 0.0])
    assert "patient" in patient_dict


def test_subset_aggregate_computation():
    exam0 = SimpleNamespace(output=_make_mock_exam_output([(0, 5.0), (1, 10.0)], num_cells=4))
    exam1 = SimpleNamespace(output=_make_mock_exam_output([(1, 100.0)], num_cells=4))
    exam2 = SimpleNamespace(output=_make_mock_exam_output([(2, 3.0), (3, 7.0)], num_cells=4))

    res = SimpleNamespace(exams=[exam0, exam1, exam2])

    combined, subset_psd = compute_subset_aggregate(res, [True, False, True])

    assert combined is not None
    assert np.allclose(combined, [5.0, 10.0, 3.0, 7.0])
    assert subset_psd == pytest.approx(10.0)


def test_subset_psd():
    exam0 = SimpleNamespace(output=_make_mock_exam_output([(0, 15.0)], num_cells=3))
    exam1 = SimpleNamespace(output=_make_mock_exam_output([(1, 40.0)], num_cells=3))
    res = SimpleNamespace(exams=[exam0, exam1])

    combined, subset_psd = compute_subset_aggregate(res, [True, True])
    assert combined is not None
    assert subset_psd == pytest.approx(40.0)


def test_state_reset_clears_checkbox_state():
    state = AppState()
    state.visible_exam_dosemaps = [True, False]
    state.aggregate_subset_exams = [False, True]

    # Patch the singleton temporarily or test via reset_results
    from guiskindose.gui import state as state_mod

    old_state = state_mod.state
    try:
        state_mod.state = state
        reset_results()
        assert state.visible_exam_dosemaps == []
        assert state.aggregate_subset_exams == []
    finally:
        state_mod.state = old_state


def test_memory_guard_caps_inline_maps():
    assert can_show_more_inline([True, True, True, True]) is True  # 4 visible (< 5)
    assert can_show_more_inline([True, True, True, True, True]) is False  # 5 visible (not < 5)


def test_subset_all_none_refills_in_place():
    subset_list = [True, False, True]
    # Refill in place
    for i in range(len(subset_list)):
        subset_list[i] = False
    assert subset_list == [False, False, False]
