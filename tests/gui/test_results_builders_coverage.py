"""Coverage for ``results_builders`` refresh paths and multi-exam UI logic."""

from __future__ import annotations

from types import SimpleNamespace
from typing import cast
from unittest.mock import MagicMock

import numpy as np
import pytest

from guiskindose.gui.state import state
from guiskindose.gui.tabs import results_builders as rb

pytest.importorskip("nicegui")


def _mock_exam_output(psd: float, dose_pairs: list[tuple[int, float]], num_cells: int = 4):
    patient_dict = {
        "patient": {
            "patient_skin_cells": {
                "x": [0.0] * num_cells,
                "y": [0.0] * num_cells,
                "z": [0.0] * num_cells,
            }
        }
    }
    output = SimpleNamespace(
        psd=psd,
        air_kerma=psd * 2,
        to_dict=MagicMock(return_value={"dose_map": dose_pairs, "patient": patient_dict}),
    )
    return SimpleNamespace(
        exam_id="Exam A",
        event_count=3,
        output=output,
    )


def _controller() -> rb.ResultsTabController:
    ctrl = rb.ResultsTabController()
    ctrl.refs.psd_metric = MagicMock()
    ctrl.refs.kerma_metric = MagicMock()
    ctrl.refs.events_metric = MagicMock()
    ctrl.refs.dap_metric = MagicMock()
    ctrl.refs.fluoro_metric = MagicMock()
    ctrl.refs.dosemap_plot = MagicMock()
    ctrl.refs.dosemap_spinner = MagicMock(visible=False)
    ctrl.refs.corr_table = MagicMock(rows=[], update=MagicMock())
    ctrl.refs.agg_psd_metric = MagicMock()
    ctrl.refs.rotational_badge = MagicMock(visible=False)
    ctrl.refs.agg_rotational_badge = MagicMock(visible=False)
    ctrl.refs.agg_events_metric = MagicMock()
    ctrl.refs.agg_totals_metric = MagicMock()
    ctrl.refs.run_warnings_label = MagicMock()
    ctrl.refs.agg_dosemap_plot = MagicMock()
    ctrl.refs.agg_dosemap_spinner = MagicMock(visible=False)
    ctrl.refs.multi_exam_accordion_container = MagicMock(clear=MagicMock())
    ctrl.refs.subset_checkboxes_container = MagicMock(clear=MagicMock())
    return ctrl


def test_refresh_metrics_single_exam() -> None:
    ctrl = _controller()
    state.is_multi_exam = False
    state.calculation_done = True
    state.psd = 12.34
    state.air_kerma = 56.7
    state.rdsr_df = MagicMock(__len__=lambda s: 8)

    ctrl.refresh_metrics()

    cast(MagicMock, ctrl.refs.psd_metric.set_text).assert_called_with("12.34 mGy")
    cast(MagicMock, ctrl.refs.kerma_metric.set_text).assert_called_with("56.7 mGy")
    cast(MagicMock, ctrl.refs.events_metric.set_text).assert_called_with("8")


def test_refresh_corr_table_populates_rows() -> None:
    ctrl = _controller()
    state.is_multi_exam = False
    state.calculation_done = True
    state.output = {
        "corrections": {
            "inverse_square_law": [0.9, 0.8],
            "backscatter": [1.0, 1.0],
            "table": [0.5, 0.6],
        }
    }

    ctrl.refresh_corr_table()

    assert len(ctrl.refs.corr_table.rows) == 2
    assert ctrl.refs.corr_table.rows[0]["event"] == 1
    cast(MagicMock, ctrl.refs.corr_table.update).assert_called_once()


def test_refresh_multi_exam_results_updates_metrics(monkeypatch: pytest.MonkeyPatch) -> None:
    ctrl = _controller()
    exam0 = _mock_exam_output(10.0, [(0, 5.0)], num_cells=3)
    exam1 = _mock_exam_output(20.0, [(1, 8.0)], num_cells=3)
    state.is_multi_exam = True
    state.calculation_done = True
    state.calc_run_id = 1
    state.multi_exam_result = SimpleNamespace(
        aggregate_psd=20.0,
        aggregate_dose_map=np.array([5.0, 8.0, 0.0]),
        exams=[exam0, exam1],
        warnings=[],
        exams_attempted=2,
        exams_excluded=0,
    )
    state.rdsr_df = MagicMock()
    state.visible_exam_dosemaps = []
    state.aggregate_subset_exams = []
    built = {"accordion": 0, "checkboxes": 0}

    monkeypatch.setattr(
        ctrl, "_build_multi_exam_accordion", lambda res: built.__setitem__("accordion", built["accordion"] + 1)
    )
    monkeypatch.setattr(
        ctrl, "_build_subset_checkboxes", lambda res: built.__setitem__("checkboxes", built["checkboxes"] + 1)
    )
    monkeypatch.setattr(ctrl, "refresh_aggregate_dosemap_subset", lambda: None)

    ctrl.refresh_multi_exam_results()

    cast(MagicMock, ctrl.refs.agg_psd_metric.set_text).assert_called_with("20.00 mGy")
    cast(MagicMock, ctrl.refs.agg_events_metric.set_text).assert_called_with("across 2 exams")
    cast(MagicMock, ctrl.refs.run_warnings_label.set_visibility).assert_called_with(False)
    assert ctrl.last_rendered_run_id == 1
    assert built["accordion"] == 1
    assert built["checkboxes"] == 1
    assert len(state.visible_exam_dosemaps) == 2


def test_refresh_multi_exam_results_shows_exclusion_warnings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-empty run warnings must surface on Results and update the exam caption."""
    ctrl = _controller()
    exam0 = _mock_exam_output(10.0, [(0, 5.0)], num_cells=3)
    warning = (
        "Exam 2: calculation raised ValueError and was excluded from the "
        "aggregate peak skin dose. Review this exam's offsets, input data, "
        "and settings, then recalculate."
    )
    state.is_multi_exam = True
    state.calculation_done = True
    state.calc_run_id = 4
    state.multi_exam_result = SimpleNamespace(
        aggregate_psd=10.0,
        aggregate_dose_map=np.array([5.0, 0.0, 0.0]),
        exams=[exam0],
        warnings=[
            "1 of 2 exam(s) were excluded from the aggregate peak skin dose. Per-exam details follow.",
            warning,
        ],
        exams_attempted=2,
        exams_excluded=1,
    )
    state.rdsr_df = MagicMock()
    state.visible_exam_dosemaps = []
    state.aggregate_subset_exams = []
    monkeypatch.setattr(ctrl, "_build_multi_exam_accordion", lambda res: None)
    monkeypatch.setattr(ctrl, "_build_subset_checkboxes", lambda res: None)
    monkeypatch.setattr(ctrl, "refresh_aggregate_dosemap_subset", lambda: None)

    ctrl.refresh_multi_exam_results()

    cast(MagicMock, ctrl.refs.agg_events_metric.set_text).assert_called_with(
        "from 1 exam(s); 1 excluded from aggregate"
    )
    cast(MagicMock, ctrl.refs.run_warnings_label.set_visibility).assert_called_with(True)
    cast(MagicMock, ctrl.refs.run_warnings_label.set_text).assert_called()
    shown = cast(MagicMock, ctrl.refs.run_warnings_label.set_text).call_args.args[0]
    assert warning in shown


def test_subset_toggle_updates_aggregate_psd(monkeypatch: pytest.MonkeyPatch) -> None:
    ctrl = _controller()
    exam0 = _mock_exam_output(10.0, [(0, 15.0)], num_cells=3)
    exam1 = _mock_exam_output(40.0, [(1, 40.0)], num_cells=3)
    state.is_multi_exam = True
    state.calculation_done = True
    state.calc_run_id = 2
    state.multi_exam_result = SimpleNamespace(
        aggregate_psd=40.0,
        aggregate_dose_map=np.zeros(3),
        exams=[exam0, exam1],
        warnings=[],
    )
    state.aggregate_subset_exams = [True, True]
    ctrl.last_rendered_run_id = 2
    ctrl.last_agg_map_run_id = 2

    monkeypatch.setattr(rb, "make_dosemap_fig", lambda *a, **k: {"data": [], "layout": {}})

    event = SimpleNamespace(value=False)
    ctrl.on_subset_toggle(event, 0)

    cast(MagicMock, ctrl.refs.agg_psd_metric.set_text).assert_called_with("40.00 mGy (subset)")


def test_set_subset_all_refreshes_aggregate(monkeypatch: pytest.MonkeyPatch) -> None:
    ctrl = _controller()
    exam0 = _mock_exam_output(5.0, [(0, 5.0)], num_cells=2)
    state.is_multi_exam = True
    state.calculation_done = True
    state.calc_run_id = 3
    state.multi_exam_result = SimpleNamespace(
        aggregate_psd=5.0,
        aggregate_dose_map=np.array([5.0, 0.0]),
        exams=[exam0],
        warnings=[],
    )
    state.aggregate_subset_exams = [False]
    cb = MagicMock()
    ctrl.subset_checkboxes = [cb]
    ctrl.last_rendered_run_id = 3
    ctrl.last_agg_map_run_id = None

    monkeypatch.setattr(rb, "make_dosemap_fig", lambda *a, **k: {"data": [], "layout": {}})

    ctrl.set_subset_all(True)

    cb.set_value.assert_called_with(True)
    assert state.aggregate_subset_exams == [True]


def test_compute_subset_aggregate_empty_mask() -> None:
    res = SimpleNamespace(exams=[_mock_exam_output(1.0, [(0, 1.0)])])
    combined, psd = rb.compute_subset_aggregate(res, [False])
    assert combined is None
    assert psd == 0.0


@pytest.mark.asyncio
async def test_refresh_dosemap_skips_multi_exam(monkeypatch: pytest.MonkeyPatch) -> None:
    ctrl = _controller()
    state.is_multi_exam = True
    state.calculation_done = True
    called = {"n": 0}

    async def _boom():
        called["n"] += 1

    monkeypatch.setattr(ctrl, "refresh_dosemap", _boom)

    await ctrl.maybe_auto_refresh_dosemap()

    assert called["n"] == 0


@pytest.mark.asyncio
async def test_refresh_dosemap_updates_plot(monkeypatch: pytest.MonkeyPatch) -> None:
    ctrl = _controller()
    state.is_multi_exam = False
    state.calculation_done = True

    async def _fake_io_bound(fn, *args, **kwargs):
        return {"data": [], "layout": {}}

    monkeypatch.setattr(rb.run, "io_bound", _fake_io_bound)

    await ctrl.refresh_dosemap()

    assert ctrl.refs.dosemap_spinner.visible is False
    cast(MagicMock, ctrl.refs.dosemap_plot.update_figure).assert_called_once()


def test_refresh_aggregate_dosemap_empty_exams() -> None:
    ctrl = _controller()
    state.calc_run_id = 9
    ctrl.refresh_aggregate_dosemap(SimpleNamespace(exams=[]))
    cast(MagicMock, ctrl.refs.agg_dosemap_plot.update_figure).assert_called_with({})
    assert ctrl.last_agg_map_run_id == 9


def test_refresh_aggregate_subset_none_selected(monkeypatch: pytest.MonkeyPatch) -> None:
    ctrl = _controller()
    exam0 = _mock_exam_output(10.0, [(0, 5.0)], num_cells=2)
    state.multi_exam_result = SimpleNamespace(
        aggregate_psd=10.0,
        aggregate_dose_map=np.array([5.0, 0.0]),
        exams=[exam0],
        warnings=[],
    )
    state.aggregate_subset_exams = [False]
    state.calc_run_id = 11
    monkeypatch.setattr(rb, "compute_subset_aggregate", lambda *a, **k: (None, 0.0))

    ctrl.refresh_aggregate_dosemap_subset()

    cast(MagicMock, ctrl.refs.agg_psd_metric.set_text).assert_called_with("— mGy (no exams selected)")


def test_show_exam_dosemap_dialog_missing_notifies(monkeypatch: pytest.MonkeyPatch) -> None:
    from nicegui import ui

    messages: list[str] = []
    monkeypatch.setattr(ui, "notify", lambda msg, **k: messages.append(str(msg)))
    ctrl = _controller()
    state.multi_exam_result = None

    ctrl.show_exam_dosemap_dialog(0)

    assert any("No dose map" in m for m in messages)


def test_multi_exam_results_clears_when_incomplete() -> None:
    ctrl = _controller()
    ctrl.last_rendered_run_id = 5
    state.is_multi_exam = True
    state.calculation_done = False
    state.multi_exam_result = None

    ctrl.refresh_multi_exam_results()

    assert ctrl.last_rendered_run_id is None
    cast(MagicMock, ctrl.refs.agg_dosemap_plot.update_figure).assert_called_with({})
    cast(MagicMock, ctrl.refs.run_warnings_label.set_visibility).assert_called_with(False)


def test_rotational_badge_hidden_without_handling(monkeypatch):
    ctrl = _controller()
    monkeypatch.setattr(state, "output", {"psd": 1.0}, raising=False)
    ctrl._refresh_rotational_badge()
    cast(MagicMock, ctrl.refs.rotational_badge.set_text).assert_called_once_with("")
    assert ctrl.refs.rotational_badge.visible is False


def _handling_output(rows):
    return {"rotational_handling": {"rows": rows, "aggregate": {}}}


def test_rotational_badge_shows_envelope_summary(monkeypatch):
    ctrl = _controller()
    monkeypatch.setattr(
        state,
        "output",
        _handling_output(
            [
                {
                    "classification": "rotational",
                    "effective_handling": "coverage",
                }
            ]
        ),
        raising=False,
    )
    ctrl._refresh_rotational_badge()
    text = cast(MagicMock, ctrl.refs.rotational_badge.set_text).call_args[0][0]
    assert "1 envelope" in text
    assert ctrl.refs.rotational_badge.visible is True


def test_rotational_badge_static_run_shows_no_envelope(monkeypatch):
    ctrl = _controller()
    monkeypatch.setattr(
        state,
        "output",
        _handling_output(
            [
                {
                    "classification": "rotational",
                    "effective_handling": "static",
                }
            ]
        ),
        raising=False,
    )
    ctrl._refresh_rotational_badge()
    text = cast(MagicMock, ctrl.refs.rotational_badge.set_text).call_args[0][0]
    assert "envelope" not in text and "static fallback" in text
    assert ctrl.refs.rotational_badge.visible is True


def test_agg_rotational_badge_sums_across_exams(monkeypatch):
    from types import SimpleNamespace as _NS

    ctrl = _controller()
    res = _NS(
        exams=[
            _NS(output=_NS(rotational_handling={"rows": [{"classification": "rotational", "effective_handling": "coverage", "requested_handling": "Auto"}]})),
            _NS(output=_NS(rotational_handling={"rows": [{"classification": "positioner_motion", "effective_handling": "static", "requested_handling": "Auto"}]})),
        ]
    )
    ctrl._refresh_agg_rotational_badge(res)
    text = cast(MagicMock, ctrl.refs.agg_rotational_badge.set_text).call_args[0][0]
    assert "1 envelope" in text and "1 static" in text and "2 rotational/moving events" in text
    assert ctrl.refs.agg_rotational_badge.visible is True


def test_agg_rotational_badge_static_run_shows_no_envelope():
    from types import SimpleNamespace as _NS

    ctrl = _controller()
    res = _NS(
        exams=[
            _NS(output=_NS(rotational_handling={"rows": [{"classification": "rotational", "effective_handling": "static", "requested_handling": "Static"}]})),
        ]
    )
    ctrl._refresh_agg_rotational_badge(res)
    text = cast(MagicMock, ctrl.refs.agg_rotational_badge.set_text).call_args[0][0]
    assert "envelope" not in text and "1 static" in text


def test_agg_rotational_badge_hidden_without_handling(monkeypatch):
    from types import SimpleNamespace as _NS

    ctrl = _controller()
    ctrl._refresh_agg_rotational_badge(_NS(exams=[_NS(output=_NS(rotational_handling=None))]))
    cast(MagicMock, ctrl.refs.agg_rotational_badge.set_text).assert_called_once_with("")
    assert ctrl.refs.agg_rotational_badge.visible is False


def test_rotational_badge_notes_fallback(monkeypatch):
    ctrl = _controller()
    monkeypatch.setattr(
        state,
        "output",
        _handling_output(
            [
                {"classification": "positioner_motion", "effective_handling": "static"},
                {"classification": "positioner_motion", "effective_handling": "static"},
            ]
        ),
        raising=False,
    )
    ctrl._refresh_rotational_badge()
    text = cast(MagicMock, ctrl.refs.rotational_badge.set_text).call_args[0][0]
    assert "2 static fallback" in text
