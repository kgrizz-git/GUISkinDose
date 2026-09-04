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

from guiskindose.constants import (
    KEY_NORMALIZATION_ACQUISITION_PLANE,
    KEY_NORMALIZATION_DEVICE_SERIAL,
    KEY_NORMALIZATION_STATION_NAME,
)
from guiskindose.kerma_correction import (
    load_correction_table,
    merge_tables,
    normalize_equipment_label,
    normalize_tube,
    resolve_correction_factors,
    resolve_correction_keys,
    unique_equipment_tube_keys,
)


def _frame(**cols) -> pd.DataFrame:
    """Build a small DataFrame from keyword columns."""
    return pd.DataFrame(cols)


def test_normalize_tube_aliases():
    """Acquisition-plane strings map to single/A/B."""
    assert normalize_tube("Single Plane") == "single"
    assert normalize_tube("Plane A") == "A"
    assert normalize_tube("plane b") == "B"
    assert normalize_tube(None) == "single"
    assert normalize_tube("") == "single"


def test_normalize_equipment_casefold_nfkc():
    """Equipment labels are stripped, NFKC-normalized, and casefolded."""
    assert normalize_equipment_label("  Unit-01  ") == "unit-01"
    assert normalize_equipment_label(None) is None
    assert normalize_equipment_label("") is None


def test_precedence_explicit_then_serial_then_station():
    """Key resolution prefers explicit label, then serial, then station."""
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
    """Unresolved identity and table misses use default_factor without leaking labels."""
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
    """CSV CF tables load into (equipment, tube) keys."""
    path = tmp_path / "cf.csv"
    path.write_text(
        "equipment,tube,correction_factor\nunit-01,single,1.05\nunit-01,A,0.97\n",
        encoding="utf-8",
    )
    table = load_correction_table(path)
    assert table[("unit-01", "single")] == pytest.approx(1.05)
    assert table[("unit-01", "A")] == pytest.approx(0.97)


def test_load_json(tmp_path: Path):
    """JSON CF tables with a factors list load correctly."""
    path = tmp_path / "cf.json"
    path.write_text(
        json.dumps({"factors": [{"equipment": "unit-01", "tube": "single", "correction_factor": 1.03}]}),
        encoding="utf-8",
    )
    table = load_correction_table(path)
    assert table[("unit-01", "single")] == pytest.approx(1.03)


def test_reject_nonpositive_factor(tmp_path: Path):
    """Non-positive correction_factor values raise ValueError."""
    path = tmp_path / "bad.csv"
    path.write_text("equipment,tube,correction_factor\nunit-01,single,0\n", encoding="utf-8")
    with pytest.raises(ValueError, match="finite float > 0"):
        load_correction_table(path)


def test_empty_table_fails(tmp_path: Path):
    """Header-only CF tables are rejected as empty."""
    path = tmp_path / "empty.csv"
    path.write_text("equipment,tube,correction_factor\n", encoding="utf-8")
    with pytest.raises(ValueError, match="empty"):
        load_correction_table(path)


def test_memory_overrides_file():
    """In-memory CF keys win over file keys on merge."""
    file_table = {("unit-01", "single"): 1.05}
    memory = {("unit-01", "single"): 1.20, ("unit-02", "single"): 1.10}
    merged = merge_tables(file_table, memory)
    assert merged is not None
    assert merged[("unit-01", "single")] == pytest.approx(1.20)
    assert merged[("unit-02", "single")] == pytest.approx(1.10)


def test_duplicate_rows_first_wins(tmp_path: Path):
    """Duplicate CF keys keep the first value and warn (handler, not caplog).

    Suite-wide ``guiskindose`` logging / propagate state can leave WARNING on
    stderr without landing in pytest ``caplog`` (seen on CI Python 3.14).
    """
    path = tmp_path / "dup.csv"
    path.write_text(
        "equipment,tube,correction_factor\nunit-01,single,1.05\nunit-01,single,1.50\n",
        encoding="utf-8",
    )
    messages: list[str] = []

    class _Capture(logging.Handler):
        """Collect log record messages for assertions."""
        def emit(self, record: logging.LogRecord) -> None:
            """Append the formatted log message to the capture list."""
            messages.append(record.getMessage())

    logger = logging.getLogger("guiskindose.kerma_correction")
    handler = _Capture(level=logging.WARNING)
    logger.addHandler(handler)
    try:
        table = load_correction_table(path)
    finally:
        logger.removeHandler(handler)

    assert table[("unit-01", "single")] == pytest.approx(1.05)
    assert any("duplicate" in msg for msg in messages)


def test_column_aliases_device_serial_number_and_acquisitionplane(tmp_path: Path):
    """Device Serial Number / AcquisitionPlane headers normalize to equipment/tube."""
    path = tmp_path / "cf.csv"
    path.write_text(
        "Device Serial Number,AcquisitionPlane,correction_factor\n"
        "unit-01,Single Plane,1.08\n",
        encoding="utf-8",
    )
    table = load_correction_table(path)
    assert table[("unit-01", "single")] == pytest.approx(1.08)


def test_missing_file_error_omits_path(tmp_path: Path):
    """Missing CF file errors must not include the user path/name."""
    missing = tmp_path / "secret-unit-cf.csv"
    with pytest.raises(ValueError, match="not found") as exc_info:
        load_correction_table(missing)
    assert "secret-unit-cf" not in str(exc_info.value)


def test_unique_keys_honor_explicit_label_across_units():
    """Prompt key collection collapses units when explicit_label is set."""
    df = _frame(
        **{
            KEY_NORMALIZATION_DEVICE_SERIAL: ["serial-a", "serial-b"],
            KEY_NORMALIZATION_ACQUISITION_PLANE: ["Single Plane", "Plane A"],
        }
    )
    keys = unique_equipment_tube_keys([df], explicit_label="site-lab-1")
    assert keys == [("site-lab-1", "A"), ("site-lab-1", "single")]


def test_invalid_lookup_factor_replaced_with_default():
    """Non-finite lookup CF values fall back to default_factor."""
    df = _frame(
        **{
            KEY_NORMALIZATION_STATION_NAME: ["unit-01"],
            KEY_NORMALIZATION_ACQUISITION_PLANE: ["Single Plane"],
        }
    )
    result = resolve_correction_factors(
        df,
        {("unit-01", "single"): float("nan")},
        default_factor=1.11,
    )
    assert result.factors == [pytest.approx(1.11)]


def test_json_factors_wrapper_and_list_payloads(tmp_path: Path):
    """JSON CF tables accept both a bare list and a {\"factors\": [...]} wrapper."""
    from guiskindose.kerma_correction import distinct_auto_resolved_equipment_keys

    wrapped = tmp_path / "wrapped.json"
    wrapped.write_text(
        json.dumps({"factors": [{"equipment": "unit-a", "tube": "single", "correction_factor": 1.2}]}),
        encoding="utf-8",
    )
    bare = tmp_path / "bare.json"
    bare.write_text(
        json.dumps([{"equipment": "unit-b", "tube": "A", "correction_factor": 0.9}]),
        encoding="utf-8",
    )
    assert load_correction_table(wrapped) == {("unit-a", "single"): pytest.approx(1.2)}
    assert load_correction_table(bare) == {("unit-b", "A"): pytest.approx(0.9)}

    df = _frame(
        **{
            KEY_NORMALIZATION_DEVICE_SERIAL: ["Unit-A", None],
            KEY_NORMALIZATION_STATION_NAME: [None, "Station-B"],
            KEY_NORMALIZATION_ACQUISITION_PLANE: ["Single Plane", "Plane B"],
        }
    )
    assert distinct_auto_resolved_equipment_keys(df) == {"unit-a", "station-b"}


def test_load_rejects_bad_json_shape_and_empty_equipment(tmp_path: Path):
    """Invalid JSON shape / empty equipment raise ValueError without leaking paths."""
    bad_shape = tmp_path / "bad-shape.json"
    bad_shape.write_text(json.dumps({"not_factors": []}), encoding="utf-8")
    with pytest.raises(ValueError, match="list or"):
        load_correction_table(bad_shape)

    empty_rows = tmp_path / "empty-rows.json"
    empty_rows.write_text(json.dumps({"factors": []}), encoding="utf-8")
    with pytest.raises(ValueError, match="no factor rows"):
        load_correction_table(empty_rows)

    empty_equip = tmp_path / "empty-equip.json"
    empty_equip.write_text(
        json.dumps([{"equipment": "  ", "tube": "single", "correction_factor": 1.0}]),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="empty value"):
        load_correction_table(empty_equip)

    unsupported = tmp_path / "factors.txt"
    unsupported.write_text("nope", encoding="utf-8")
    with pytest.raises(ValueError, match="Unsupported"):
        load_correction_table(unsupported)


def test_normalize_nan_inputs_and_suspicious_factor_warning(tmp_path: Path):
    """NaN equipment/tube normalize safely; out-of-band CF values warn.

    Use a dedicated handler (not ``caplog``) so suite-wide logging state cannot
    swallow the WARNING.
    """
    assert normalize_equipment_label(float("nan")) is None
    assert normalize_tube(float("nan")) == "single"

    path = tmp_path / "wide.json"
    path.write_text(
        json.dumps([{"equipment": "unit-01", "tube": "single", "correction_factor": 3.5}]),
        encoding="utf-8",
    )
    messages: list[str] = []

    class _Capture(logging.Handler):
        """Collect log record messages for assertions."""

        def emit(self, record: logging.LogRecord) -> None:
            """Append the formatted log message to the capture list."""
            messages.append(record.getMessage())

    logger = logging.getLogger("guiskindose.kerma_correction")
    handler = _Capture(level=logging.WARNING)
    logger.addHandler(handler)
    try:
        table = load_correction_table(path)
    finally:
        logger.removeHandler(handler)

    assert table[("unit-01", "single")] == pytest.approx(3.5)
    assert any("outside the typical" in msg for msg in messages)
