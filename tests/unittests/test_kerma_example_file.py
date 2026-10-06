"""The bundled example kerma-meter calibration file loads and drives the engine."""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from guiskindose import get_path_to_example_kerma_meter_file, load_settings_example_json
from guiskindose.calculate_dose.calculate_dose import _resolve_kerma_meter_cf
from guiskindose.kerma_correction import load_correction_periods, load_correction_table
from guiskindose.kerma_periods import period_options
from guiskindose.settings import PyskindoseSettings

_OLD = "1901-01-01|1901-12-31"


def test_example_file_and_readme_are_packaged_beside_each_other() -> None:
    path = get_path_to_example_kerma_meter_file()
    assert path.is_file()
    assert (path.parent / "README.md").is_file()


def test_example_file_loads_as_a_table() -> None:
    table = load_correction_table(get_path_to_example_kerma_meter_file())
    assert table[("demo-room-1", "single")] == pytest.approx(1.02)
    assert table[("demo-room-2", "A")] == pytest.approx(1.03)  # current period
    assert table[("demo-room-2", "B")] == pytest.approx(1.01)


def test_example_file_has_one_dated_pair_with_two_periods() -> None:
    periods = load_correction_periods(get_path_to_example_kerma_meter_file())
    assert [o.label for o in period_options(periods)] == ["1902-01-01 → (open)", "1901-01-01 → 1901-12-31"]
    dated = {pair for pair, rows in periods.items() if any(r.dated for r in rows)}
    assert dated == {("demo-room-2", "A")}


def test_example_file_uses_only_fictional_labels() -> None:
    labels = {equipment for equipment, _tube in load_correction_periods(get_path_to_example_kerma_meter_file())}
    assert all(label.startswith("demo-") for label in labels)


def _settings(**km) -> PyskindoseSettings:
    base = load_settings_example_json()
    base["kerma_meter_correction"].update(
        {"enable": True, "file": str(get_path_to_example_kerma_meter_file()), "explicit_label": "DEMO-ROOM-2", **km}
    )
    return PyskindoseSettings(settings=base)


def _frame() -> pd.DataFrame:
    return pd.DataFrame({"acquisition_plane": ["Plane A", "Plane B"]})


def test_engine_resolves_factors_from_the_example_file() -> None:
    assert _resolve_kerma_meter_cf(_frame(), _settings(), "Exam 1") == pytest.approx([1.03, 1.01])


def test_engine_uses_the_chosen_period_of_the_example_file() -> None:
    settings = _settings()
    settings.kerma_meter_correction.calibration_periods = {"Exam 1": _OLD}
    assert _resolve_kerma_meter_cf(_frame(), settings, "Exam 1") == pytest.approx([0.98, 1.01])
    assert _resolve_kerma_meter_cf(_frame(), settings, "Exam 2") == pytest.approx([1.03, 1.01])


def test_engine_uses_a_cli_calibration_date_with_the_example_file() -> None:
    settings = _settings()
    settings.kerma_meter_correction.calibration_date = date(1901, 6, 1)
    assert _resolve_kerma_meter_cf(_frame(), settings, "Exam 1") == pytest.approx([0.98, 1.01])
