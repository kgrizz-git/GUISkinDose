"""Unit tests for kerma-meter correction resolution (Phase 1).

CF lookup tables are built in tmp/ during tests (not committed fixtures) so
privacy scanners are not tripped by synthetic equipment/tube rows.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pandas as pd
import pytest

from mypyskindose.constants import (
    KEY_NORMALIZATION_ACQUISITION_PLANE,
    KEY_NORMALIZATION_DEVICE_SERIAL,
    KEY_NORMALIZATION_STATION_NAME,
)
from mypyskindose.kerma_correction import (
    load_correction_table,
    merge_tables,
    normalize_equipment_label,
    normalize_tube,
    resolve_correction_factors,
    resolve_correction_keys,
)


def _frame(**cols) -> pd.DataFrame:
    return pd.DataFrame(cols)


def test_normalize_tube_aliases():
    assert normalize_tube("Single Plane") == "single"
    assert normalize_tube("Plane A") == "A"
    assert normalize_tube("plane b") == "B"
    assert normalize_tube(None) == "single"
    assert normalize_tube("") == "single"


def test_normalize_equipment_casefold_nfkc():
    assert normalize_equipment_label("  Unit-01  ") == "unit-01"
    assert normalize_equipment_label(None) is None
    assert normalize_equipment_label("") is None


def test_precedence_explicit_then_serial_then_station():
    df = _frame(
        **{
            KEY_NORMALIZATION_DEVICE_SERIAL: ["serial-a", "serial-b"],
            KEY_NORMALIZATION_STATION_NAME: ["station-a", "station-b"],
            KEY_NORMALIZATION_ACQUISITION_PLANE: ["Single Plane", "Plane A"],
        }
    )
    keys = resolve_correction_keys(df, explicit_label=None)
    assert keys == [("serial-a", "single"), ("serial-b", "A")]

    keys_forced = resolve_correction_keys(df, explicit_label="forced-unit")
    assert keys_forced == [("forced-unit", "single"), ("forced-unit", "A")]


def test_unresolved_vs_table_miss(caplog):
    df = _frame(
        **{
            KEY_NORMALIZATION_STATION_NAME: [None, "unit-01", "unit-missing"],
            KEY_NORMALIZATION_ACQUISITION_PLANE: ["Single Plane", "Single Plane", "Single Plane"],
        }
    )
    table = {("unit-01", "single"): 1.05}
    result = resolve_correction_factors(df, table, default_factor=1.0)
    assert result.factors == [1.0, 1.05, 1.0]
    assert result.unresolved_event_indices == [0]
    assert result.table_miss_event_indices == [2]
    # Privacy: raw station strings must not appear at WARNING.
    warn_text = " ".join(r.message for r in caplog.records if r.levelname == "WARNING")
    assert "unit-01" not in warn_text
    assert "unit-missing" not in warn_text


def test_load_csv(tmp_path: Path):
    path = tmp_path / "cf.csv"
    path.write_text(
        "equipment,tube,correction_factor\nunit-01,single,1.05\nunit-01,A,0.97\n",
        encoding="utf-8",
    )
    table = load_correction_table(path)
    assert table[("unit-01", "single")] == pytest.approx(1.05)
    assert table[("unit-01", "A")] == pytest.approx(0.97)


def test_load_json(tmp_path: Path):
    path = tmp_path / "cf.json"
    path.write_text(
        json.dumps({"factors": [{"equipment": "unit-01", "tube": "single", "correction_factor": 1.03}]}),
        encoding="utf-8",
    )
    table = load_correction_table(path)
    assert table[("unit-01", "single")] == pytest.approx(1.03)


def test_reject_nonpositive_factor(tmp_path: Path):
    path = tmp_path / "bad.csv"
    path.write_text("equipment,tube,correction_factor\nunit-01,single,0\n", encoding="utf-8")
    with pytest.raises(ValueError, match="finite float > 0"):
        load_correction_table(path)


def test_empty_table_fails(tmp_path: Path):
    path = tmp_path / "empty.csv"
    path.write_text("equipment,tube,correction_factor\n", encoding="utf-8")
    with pytest.raises(ValueError, match="empty"):
        load_correction_table(path)


def test_memory_overrides_file():
    file_table = {("unit-01", "single"): 1.05}
    memory = {("unit-01", "single"): 1.20, ("unit-02", "single"): 1.10}
    merged = merge_tables(file_table, memory)
    assert merged is not None
    assert merged[("unit-01", "single")] == pytest.approx(1.20)
    assert merged[("unit-02", "single")] == pytest.approx(1.10)


def test_duplicate_rows_first_wins(tmp_path: Path, caplog):
    path = tmp_path / "dup.csv"
    path.write_text(
        "equipment,tube,correction_factor\nunit-01,single,1.05\nunit-01,single,1.50\n",
        encoding="utf-8",
    )
    with caplog.at_level(logging.WARNING, logger="mypyskindose.kerma_correction"):
        table = load_correction_table(path)
    assert table[("unit-01", "single")] == pytest.approx(1.05)
    assert any("duplicate" in r.message for r in caplog.records)
