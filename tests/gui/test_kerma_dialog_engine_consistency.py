"""What the correction dialog shows must be exactly what the dose calculation applies.

After Confirm, every dialog row's value and source equals the engine's applied factor and
source for that exam, pair, and event. Covers mixed calibration schedules, a manual entry
that must not skip over a differing period (old -> new -> old), follows chains, edits,
legacy global entries, and acknowledged defaults.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

pytest.importorskip("nicegui")

from guiskindose import load_settings_example_json
from guiskindose.calculate_dose.calculate_dose import _resolve_kerma_meter_cf_detail
from guiskindose.gui.state import state
from guiskindose.gui.tabs import _kerma_meter_dialog as dlg
from guiskindose.settings import PyskindoseSettings

_OLD = "1901-01-01|1901-12-31"
_NEW = "1902-01-01|"
_PLANES = {"A": "Plane A", "B": "Plane B"}
_SOURCE = {
    dlg.SOURCE_ENTERED: "manual",
    dlg.SOURCE_FOLLOWS: "manual",
    dlg.SOURCE_FILE: "file",
    dlg.SOURCE_DEFAULT: "default",
}

# Pair X has two periods; pair Y's only row ended before the file's newest period begins
# (the mixed schedule); pair Z is undated.
_FILE = (
    "equipment,tube,correction_factor,valid_from,valid_to\n"
    "x-room,A,1.10,1901-01-01,1901-12-31\n"
    "x-room,A,1.20,1902-01-01,\n"
    "y-room,A,0.80,1900-01-01,1901-12-31\n"
    "z-room,B,1.05,,\n"
)
_PAIRS = [("x-room", "A"), ("y-room", "A"), ("z-room", "B")]


def _frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "station_name": [eq.upper() for eq, _ in _PAIRS],
            "device_serial": [None] * len(_PAIRS),
            "acquisition_plane": [_PLANES[t] for _, t in _PAIRS],
        }
    )


def _setup(tmp_path: Path, n_exams: int, *, table=None, periods=None) -> None:
    path = tmp_path / "cf.csv"
    path.write_text(_FILE, encoding="utf-8")
    state.loaded_exams = [SimpleNamespace(normalized_data=_frame()) for _ in range(n_exams)]
    state.kerma_meter_enable = True
    state.kerma_meter_file = str(path)
    state.kerma_meter_in_memory_table = table
    state.kerma_meter_periods = dict(periods or {})


def _engine(exam: str) -> dict[tuple[str, str], tuple[float, str]]:
    base = load_settings_example_json()
    base["kerma_meter_correction"].update({"enable": True, "file": state.kerma_meter_file})
    settings = PyskindoseSettings(settings=base)
    km = settings.kerma_meter_correction
    km.in_memory_table = state.kerma_meter_in_memory_table
    km.calibration_periods = dict(state.kerma_meter_periods)
    factors, sources = _resolve_kerma_meter_cf_detail(_frame(), settings, exam)
    return {pair: (factors[i], sources[i]) for i, pair in enumerate(_PAIRS)}


def _assert_dialog_equals_engine() -> None:
    model = dlg.FactorModel(state)
    for row in model.rows():
        applied, source = _engine(row.exam)[(row.equipment, row.tube)]
        assert row.value == pytest.approx(applied), (row.exam, row.equipment, row.tube)
        assert _SOURCE[row.source] == source, (row.exam, row.equipment, row.tube)


def test_mixed_calibration_schedules_show_what_the_engine_applies(tmp_path: Path) -> None:
    _setup(tmp_path, 1)
    model = dlg.FactorModel(state)
    shown = {(r.equipment, r.tube): (r.value, r.source) for r in model.rows()}
    # Pair Y has no row in the displayed (newest) period, so the dialog shows the default.
    assert shown[("y-room", "A")] == (1.0, dlg.SOURCE_DEFAULT)
    model.commit(dont_ask=False)
    assert _engine("Exam 1")[("y-room", "A")] == (1.0, "default")  # not its own latest row (0.8)
    _assert_dialog_equals_engine()


def test_old_new_old_periods_do_not_inherit_across_a_different_period(tmp_path: Path) -> None:
    _setup(
        tmp_path,
        3,
        table={("Exam 1", "x-room", "A"): 0.9},
        periods={"Exam 1": _OLD, "Exam 2": _NEW, "Exam 3": _OLD},
    )
    rows = {
        r.exam: (r.value, r.source) for r in dlg.FactorModel(state).rows() if (r.equipment, r.tube) == ("x-room", "A")
    }
    assert rows["Exam 1"] == (0.9, dlg.SOURCE_ENTERED)
    assert rows["Exam 2"] == (1.2, dlg.SOURCE_FILE)
    assert rows["Exam 3"] == (1.1, dlg.SOURCE_FILE)  # not Exam 1's 0.9, whose period matches only non-adjacently
    _assert_dialog_equals_engine()


@pytest.mark.parametrize(
    "periods",
    [
        {},
        {"Exam 1": _OLD},
        {"Exam 2": _OLD},
        {"Exam 1": _OLD, "Exam 3": _NEW},
        {"Exam 1": _NEW, "Exam 2": _OLD, "Exam 3": _OLD},
    ],
)
@pytest.mark.parametrize(
    "table",
    [
        None,
        {("Exam 1", "x-room", "A"): 0.9},
        {("Exam 2", "x-room", "A"): 0.9, ("Exam 3", "z-room", "B"): 1.4},
        {("x-room", "A"): 0.7, ("Exam 2", "x-room", "A"): 0.9},
        {("Exam 1", "x-room", "A"): 0.9, ("Exam 1", "y-room", "A"): 0.6, ("Exam 2", "y-room", "A"): 0.5},
    ],
)
def test_dialog_equals_engine_for_manual_period_and_follow_combinations(tmp_path: Path, table, periods) -> None:
    _setup(tmp_path, 3, table=table, periods=periods)
    dlg.FactorModel(state).commit(dont_ask=False)  # Confirm what is shown
    _assert_dialog_equals_engine()


def test_dialog_equals_engine_after_edits_period_choices_and_reopen(tmp_path: Path) -> None:
    _setup(tmp_path, 3)
    model = dlg.FactorModel(state)
    model.set_value("Exam 1", ("x-room", "A"), 1.3)
    model.set_value("Exam 2", ("y-room", "A"), 0.55)
    model.set_period("Exam 2", _OLD)
    model.commit(dont_ask=False)
    _assert_dialog_equals_engine()
    reopened = dlg.FactorModel(state)
    reopened.set_value("Exam 1", ("x-room", "A"), 1.45)
    reopened.set_period("Exam 3", _NEW)
    reopened.commit(dont_ask=False)
    _assert_dialog_equals_engine()
