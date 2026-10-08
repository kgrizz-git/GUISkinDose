"""Calibration periods (valid_from / valid_to), per-exam manual tables, and the CLI date."""

from __future__ import annotations

import argparse
import logging
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from guiskindose import load_settings_example_json
from guiskindose.calculate_dose.calculate_dose import _resolve_kerma_meter_cf
from guiskindose.cli_kerma_meter import add_kerma_meter_cli_arguments, apply_kerma_meter_cli_flags
from guiskindose.kerma_correction import load_correction_periods, load_correction_table, manual_for_exam
from guiskindose.kerma_periods import (
    CalibrationRow,
    key_ref_date,
    period_options,
    resolve_period_table,
    select_row,
)
from guiskindose.settings import PyskindoseSettings

_HEADER = "equipment,tube,correction_factor,valid_from,valid_to\n"
_TWO_PERIODS = "room-1,A,1.10,2026-01-01,2026-06-30\nroom-1,A,1.25,2026-07-01,\nroom-1,B,0.95,,\n"


def _write(tmp_path: Path, body: str, header: str = _HEADER) -> Path:
    path = tmp_path / "cf.csv"
    path.write_text(header + body, encoding="utf-8")
    return path


def test_undated_file_is_unchanged(tmp_path: Path) -> None:
    path = _write(tmp_path, "unit,single,1.2\n", header="equipment,tube,correction_factor\n")
    assert load_correction_table(path) == {("unit", "single"): pytest.approx(1.2)}
    (row,) = load_correction_periods(path)[("unit", "single")]
    assert row.dated is False


def test_dated_rows_load_and_default_to_current_period(tmp_path: Path) -> None:
    path = _write(tmp_path, _TWO_PERIODS)
    periods = load_correction_periods(path)
    assert len(periods[("room-1", "A")]) == 2
    assert load_correction_table(path)[("room-1", "A")] == pytest.approx(1.25)  # no valid_to: current
    assert load_correction_table(path)[("room-1", "B")] == pytest.approx(0.95)


def test_overlapping_periods_are_a_load_error(tmp_path: Path) -> None:
    path = _write(tmp_path, "u,A,1.1,2026-01-01,2026-07-01\nu,A,1.2,2026-07-01,\n")
    with pytest.raises(ValueError, match="must not overlap"):
        load_correction_periods(path)


def test_two_open_ended_rows_overlap(tmp_path: Path) -> None:
    path = _write(tmp_path, "u,A,1.1,2026-01-01,\nu,A,1.2,2026-07-01,\n")
    with pytest.raises(ValueError, match="must not overlap"):
        load_correction_periods(path)


def test_dated_row_overlapping_an_undated_row_is_an_error(tmp_path: Path) -> None:
    path = _write(tmp_path, "u,A,1.1,,\nu,A,1.2,2026-07-01,\n")
    with pytest.raises(ValueError, match="must not overlap"):
        load_correction_periods(path)


def test_adjacent_periods_do_not_overlap(tmp_path: Path) -> None:
    path = _write(tmp_path, "u,A,1.1,2026-01-01,2026-06-30\nu,A,1.2,2026-07-01,2026-12-31\n")
    assert len(load_correction_periods(path)[("u", "A")]) == 2


def test_bad_date_and_reversed_period_are_errors(tmp_path: Path) -> None:
    bad_date = _write(tmp_path, "u,A,1.1,01/02/2026,\n")
    with pytest.raises(ValueError, match="ISO dates"):
        load_correction_periods(bad_date)
    reversed_period = _write(tmp_path, "u,A,1.1,2026-07-01,2026-01-01\n")
    with pytest.raises(ValueError, match="must not be after"):
        load_correction_periods(reversed_period)


def test_select_row_by_date_boundaries_and_gaps() -> None:
    rows = [
        CalibrationRow(date(2026, 1, 1), date(2026, 6, 30), 1.1),
        CalibrationRow(date(2026, 7, 1), None, 1.25),
    ]
    assert select_row(rows, date(2026, 6, 30)).factor == pytest.approx(1.1)  # type: ignore[union-attr]
    assert select_row(rows, date(2026, 7, 1)).factor == pytest.approx(1.25)  # type: ignore[union-attr]
    assert select_row(rows, date(2025, 12, 31)) is None
    assert select_row(rows, None).factor == pytest.approx(1.25)  # type: ignore[union-attr]
    assert resolve_period_table({("u", "A"): rows}, date(2025, 1, 1)) == {}


def test_period_options_are_most_recent_first_with_labels(tmp_path: Path) -> None:
    options = period_options(load_correction_periods(_write(tmp_path, _TWO_PERIODS)))
    assert [o.label for o in options] == ["2026-07-01 → (open)", "2026-01-01 → 2026-06-30"]
    assert key_ref_date(options[1].key) == date(2026, 1, 1)
    assert key_ref_date("|2026-03-01") == date(2026, 3, 1)


def test_manual_for_exam_prefers_exam_entry_over_legacy_global() -> None:
    table = {("u", "A"): 1.0, ("Exam 1", "u", "A"): 1.5, ("Exam 2", "u", "B"): 2.0}
    assert manual_for_exam(table, "Exam 1") == {("u", "A"): 1.5}
    assert manual_for_exam(table, "Exam 2") == {("u", "A"): 1.0, ("u", "B"): 2.0}
    assert manual_for_exam(None, "Exam 1") == {}


# ── engine ───────────────────────────────────────────────────────────────────


def _settings(**km) -> PyskindoseSettings:
    base = load_settings_example_json()
    base["kerma_meter_correction"].update({"enable": True, "explicit_label": "room-1", **km})
    return PyskindoseSettings(settings=base)


def _frame() -> pd.DataFrame:
    return pd.DataFrame({"acquisition_plane": ["Plane A"]})


def test_engine_resolves_manual_per_exam_then_file_then_default(tmp_path: Path) -> None:
    path = _write(tmp_path, "room-1,A,1.1,,\n")
    settings = _settings(file=str(path), default_factor=0.9)
    settings.kerma_meter_correction.in_memory_table = {("Exam 2", "room-1", "A"): 1.7}
    assert _resolve_kerma_meter_cf(_frame(), settings, "Exam 1") == pytest.approx([1.1])  # file
    assert _resolve_kerma_meter_cf(_frame(), settings, "Exam 2") == pytest.approx([1.7])  # manual
    settings_no_file = _settings(default_factor=0.9)
    assert _resolve_kerma_meter_cf(_frame(), settings_no_file, "Exam 1") == pytest.approx([0.9])  # default


def test_engine_uses_the_exams_calibration_period(tmp_path: Path) -> None:
    path = _write(tmp_path, _TWO_PERIODS)
    settings = _settings(file=str(path))
    settings.kerma_meter_correction.calibration_periods = {"Exam 1": "2026-01-01|2026-06-30"}
    assert _resolve_kerma_meter_cf(_frame(), settings, "Exam 1") == pytest.approx([1.10])
    # Exam 2 has no choice of its own and follows Exam 1's period.
    assert _resolve_kerma_meter_cf(_frame(), settings, "Exam 2") == pytest.approx([1.10])
    settings.kerma_meter_correction.calibration_periods = {"Exam 1": "2026-01-01|2026-06-30", "Exam 2": "2026-07-01|"}
    assert _resolve_kerma_meter_cf(_frame(), settings, "Exam 2") == pytest.approx([1.25])


def test_engine_uses_cli_calibration_date_for_every_exam(tmp_path: Path) -> None:
    settings = _settings(file=str(_write(tmp_path, _TWO_PERIODS)))
    settings.kerma_meter_correction.calibration_date = date(2026, 3, 1)
    assert _resolve_kerma_meter_cf(_frame(), settings, "Exam 1") == pytest.approx([1.10])
    assert _resolve_kerma_meter_cf(_frame(), settings, "Exam 2") == pytest.approx([1.10])


class _Capture(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=logging.WARNING)
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(record.getMessage())


def test_unselected_period_warns_with_count_only(tmp_path: Path) -> None:
    settings = _settings(file=str(_write(tmp_path, _TWO_PERIODS)))
    handler = _Capture()
    logger = logging.getLogger("guiskindose.calculate_dose.calculate_dose")
    logger.addHandler(handler)
    try:
        _resolve_kerma_meter_cf(_frame(), settings, "Exam 1")
    finally:
        logger.removeHandler(handler)
    dated = [m for m in handler.messages if "dated calibration rows" in m]
    assert len(dated) == 1
    assert "1 pair" in dated[0]
    assert "2026" not in dated[0]


def test_acknowledged_exam_skips_the_unselected_period_warning(tmp_path: Path) -> None:
    settings = _settings(file=str(_write(tmp_path, _TWO_PERIODS)))
    settings.kerma_meter_correction.periods_acknowledged = {"Exam 1"}
    handler = _Capture()
    logger = logging.getLogger("guiskindose.calculate_dose.calculate_dose")
    logger.addHandler(handler)
    try:
        _resolve_kerma_meter_cf(_frame(), settings, "Exam 1")
        _resolve_kerma_meter_cf(_frame(), settings, "Exam 2")
    finally:
        logger.removeHandler(handler)
    dated = [m for m in handler.messages if "dated calibration rows" in m]
    assert len(dated) == 1


# ── CLI ──────────────────────────────────────────────────────────────────────


def test_cli_calibration_date_is_parsed_and_applied() -> None:
    parser = argparse.ArgumentParser()
    add_kerma_meter_cli_arguments(parser)
    args = parser.parse_args(["--kerma-meter-calibration-date", "2026-03-01"])
    assert args.kerma_meter_calibration_date == date(2026, 3, 1)
    settings = PyskindoseSettings(settings=load_settings_example_json())
    apply_kerma_meter_cli_flags(settings, args)
    assert settings.kerma_meter_correction.calibration_date == date(2026, 3, 1)


def test_cli_rejects_non_iso_calibration_date() -> None:
    parser = argparse.ArgumentParser()
    add_kerma_meter_cli_arguments(parser)
    with pytest.raises(SystemExit):
        parser.parse_args(["--kerma-meter-calibration-date", "03/01/2026"])


def test_calibration_date_from_a_settings_dict_is_coerced_or_rejected() -> None:
    from guiskindose.settings.kerma_meter_correction_settings import KermaMeterCorrectionSettings

    assert KermaMeterCorrectionSettings({"calibration_date": "1901-06-01"}).calibration_date == date(1901, 6, 1)
    assert KermaMeterCorrectionSettings({"calibration_date": date(1902, 1, 2)}).calibration_date == date(1902, 1, 2)
    assert KermaMeterCorrectionSettings({"calibration_date": None}).calibration_date is None
    with pytest.raises(ValueError, match="ISO date"):
        KermaMeterCorrectionSettings({"calibration_date": "06/01/1901"})


def test_malformed_calibration_period_key_fails_soft_to_the_current_period(tmp_path: Path) -> None:
    settings = _settings(file=str(_write(tmp_path, _TWO_PERIODS)))
    settings.kerma_meter_correction.calibration_periods = {"Exam 1": "not-a-period-key"}
    assert _resolve_kerma_meter_cf(_frame(), settings, "Exam 1") == pytest.approx([1.25])
