"""Unit tests for multi-exam Results tab refresh helpers."""

from __future__ import annotations

from mypyskindose.gui.tabs.results import multi_exam_results_ui_stale


def test_multi_exam_results_ui_stale_first_render():
    assert multi_exam_results_ui_stale(None, 1) is True


def test_multi_exam_results_ui_stale_same_run():
    assert multi_exam_results_ui_stale(2, 2) is False


def test_multi_exam_results_ui_stale_after_recalc():
    assert multi_exam_results_ui_stale(2, 3) is True
