"""Tests for correction-data dataset validators and explicit-DB checks."""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

import pandas as pd

from guiskindose.correction_validation import (
    ColumnSpec,
    ValidationIssue,
    check_explicit_db,
    check_frame,
    check_manifest_consistency,
    check_support_transmission,
)

FLOAT_COLS = [ColumnSpec("kvp_kv", "float", (25.0, 175.0)), ColumnSpec("hvl_mmal", "float", (0.0, None))]
KEYS = ("kvp_kv",)


def _codes(issues: list[ValidationIssue], severity: str = "error") -> set[str]:
    return {i.code for i in issues if i.severity == severity}


def _frame(**overrides) -> pd.DataFrame:
    data = {"kvp_kv": [50.0, 60.0], "hvl_mmal": [2.0, 3.0]}
    data.update(overrides)
    return pd.DataFrame(data)


def test_valid_frame_is_clean():
    assert check_frame(_frame(), FLOAT_COLS, table_name="t", key_columns=KEYS) == []


def test_missing_column_is_error():
    issues = check_frame(_frame().drop(columns=["hvl_mmal"]), FLOAT_COLS, table_name="t")
    assert _codes(issues) == {"missing_column"}


def test_wrong_dtype_is_error():
    issues = check_frame(_frame(hvl_mmal=["a", "b"]), FLOAT_COLS, table_name="t")
    assert _codes(issues) == {"wrong_dtype"}


def test_non_finite_is_error():
    issues = check_frame(_frame(hvl_mmal=[1.0, float("inf")]), FLOAT_COLS, table_name="t")
    assert _codes(issues) == {"non_finite"}


def test_all_null_and_empty_columns_are_errors():
    all_null = check_frame(_frame(hvl_mmal=[None, None]), FLOAT_COLS, table_name="t")
    assert _codes(all_null) == {"non_finite"}
    empty = check_frame(pd.DataFrame({"kvp_kv": [], "hvl_mmal": []}), FLOAT_COLS, table_name="t")
    assert _codes(empty) == {"empty_column"}
    genuine_missing = check_frame(_frame(hvl_mmal=[1.0, float("nan")]), FLOAT_COLS, table_name="t")
    assert _codes(genuine_missing) == {"non_finite"}
    mixed_types = check_frame(_frame(hvl_mmal=["a", 1.0]), FLOAT_COLS, table_name="t")
    assert _codes(mixed_types) == {"wrong_dtype"}


def test_out_of_range_both_sides_is_error():
    low = check_frame(_frame(kvp_kv=[10.0, 60.0]), FLOAT_COLS, table_name="t")
    high = check_frame(_frame(kvp_kv=[60.0, 200.0]), FLOAT_COLS, table_name="t")
    assert _codes(low) == {"out_of_range"}
    assert _codes(high) == {"out_of_range"}


def test_duplicate_keys_are_errors():
    single = check_frame(_frame(kvp_kv=[50.0, 50.0]), FLOAT_COLS, table_name="t", key_columns=KEYS)
    assert _codes(single) == {"duplicate_key"}
    nulls = check_frame(_frame(kvp_kv=[50.0, None]), FLOAT_COLS, table_name="t", key_columns=KEYS)
    assert "null_key" in _codes(nulls)
    composite = check_frame(
        _frame(), FLOAT_COLS, table_name="t", key_columns=("kvp_kv", "hvl_mmal")
    )
    assert _codes(composite) == set()
def test_composite_keys_allow_repeating_single_axes():
    grid = pd.DataFrame({"kvp_kv": [50.0, 50.0, 60.0, 60.0], "hvl_mmal": [2.0, 3.0, 2.0, 3.0]})
    issues = check_frame(grid, FLOAT_COLS, table_name="t", key_columns=("kvp_kv", "hvl_mmal"))
    assert issues == []
    dup = pd.DataFrame({"kvp_kv": [50.0, 50.0], "hvl_mmal": [2.0, 2.0]})
    issues = check_frame(dup, FLOAT_COLS, table_name="t", key_columns=("kvp_kv", "hvl_mmal"))
    assert _codes(issues) == {"duplicate_key"}
    assert all(i.column == "kvp_kv,hvl_mmal" for i in issues if i.code == "duplicate_key")


def test_string_columns_accept_text():
    df = pd.DataFrame({"device_model": ["AXIOM-Artis", "AlluraClarity"]})
    specs = [ColumnSpec("device_model", "string")]
    assert check_frame(df, specs, table_name="t") == []


def test_string_columns_reject_empty_missing_and_non_string():
    specs = [ColumnSpec("device_model", "string")]
    assert _codes(check_frame(pd.DataFrame({"device_model": []}), specs, table_name="t")) == {"empty_column"}
    assert _codes(check_frame(pd.DataFrame({"device_model": ["a", None]}), specs, table_name="t")) == {"missing_value"}
    assert _codes(check_frame(pd.DataFrame({"device_model": ["a", 1]}), specs, table_name="t")) == {"wrong_dtype"}
    assert _codes(check_frame(pd.DataFrame({"device_model": ["a"]}), [ColumnSpec("device_model", "Float")], table_name="t")) == {
        "unknown_dtype"
    }


def test_support_transmission_valid_is_clean():
    df = pd.DataFrame({"k_patient_support": [0.5, 0.8]})
    assert check_support_transmission(df) == []


def test_support_transmission_zeros_are_advisory_not_errors():
    df = pd.DataFrame({"k_patient_support": [0.0, 0.5]})
    issues = check_support_transmission(df)
    assert _codes(issues) == set()
    assert _codes(issues, severity="advisory") == {"zero_transmission"}


def test_support_transmission_tiny_positive_is_not_zero_advisory():
    # Runtime neutralizes only <= 0; a tiny positive is used as-is, so the
    # advisory must not claim it is warned-neutral.
    df = pd.DataFrame({"k_patient_support": [1e-12, 0.5]})
    assert check_support_transmission(df) == []


def test_support_transmission_negative_zero_is_advisory():
    df = pd.DataFrame({"k_patient_support": [-0.0, 0.5]})
    assert _codes(check_support_transmission(df), severity="advisory") == {"zero_transmission"}


def test_support_transmission_tiny_negative_is_error_only():
    df = pd.DataFrame({"k_patient_support": [-1e-12, 0.5]})
    issues = check_support_transmission(df)
    assert _codes(issues) == {"out_of_range"}
    assert _codes(issues, severity="advisory") == set()


def test_support_transmission_negative_and_above_one_are_errors():
    assert _codes(check_support_transmission(pd.DataFrame({"k_patient_support": [-0.1, 0.5]}))) == {"out_of_range"}
    assert _codes(check_support_transmission(pd.DataFrame({"k_patient_support": [0.5, 1.5]}))) == {"out_of_range"}
    assert _codes(check_support_transmission(pd.DataFrame({"k_patient_support": ["x", 0.5]}))) == {"non_finite"}
    assert _codes(check_support_transmission(pd.DataFrame({"k_patient_support": [0.5, float("inf")]}))) == {"non_finite"}
    assert _codes(check_support_transmission(pd.DataFrame({"other": [1.0]}))) == {"missing_column"}


def test_manifest_flags_uncovered_csv(tmp_path: Path):
    (tmp_path / "stray.csv").write_text("a\n1\n", encoding="utf-8")
    manifest = {"tables": []}
    assert _codes(check_manifest_consistency(manifest, tmp_path)) == {"uncovered_csv"}


def test_manifest_flags_absent_declared_csv(tmp_path: Path):
    manifest = {
        "tables": [
            {
                "file": "ghost.csv",
                "sqlite_table": None,
                "role": "provenance_only",
                "source_type": "unknown",
                "provenance_confidence": "low",
                "sha256": "0" * 64,
                "columns": [],
            }
        ]
    }
    assert _codes(check_manifest_consistency(manifest, tmp_path)) == {"missing_file"}


PROBE_SPECS = {"probe": [ColumnSpec("a", "float", (0.0, 10.0))]}


def _build_db(path: Path, *, version: str | None, rows: list[tuple] | None, columns: tuple[str, ...] = ("a",)) -> None:
    conn = sqlite3.connect(path)
    if version is not None:
        conn.execute("CREATE TABLE schema_version (version TEXT)")
        conn.execute("INSERT INTO schema_version VALUES (?)", (version,))
    if rows is not None:
        cols = ", ".join(f"{c} REAL" for c in columns)
        conn.execute(f"CREATE TABLE probe ({cols})")
        placeholders = ", ".join("?" for _ in columns)
        conn.executemany(f"INSERT INTO probe VALUES ({placeholders})", rows)
    conn.commit()
    conn.close()


def test_explicit_db_valid_is_clean(tmp_path: Path):
    db = tmp_path / "good.db"
    _build_db(db, version="1", rows=[(1.0,), (2.0,)])
    assert check_explicit_db(db, expected_version="1", table_specs=PROBE_SPECS) == []


def test_explicit_db_bad_version_fails(tmp_path: Path):
    db = tmp_path / "badver.db"
    _build_db(db, version="2", rows=[(1.0,)])
    assert _codes(check_explicit_db(db, expected_version="1", table_specs=PROBE_SPECS)) == {"schema_version_mismatch"}


def test_explicit_db_integer_version_matches_string_expectation(tmp_path: Path):
    db = tmp_path / "intver.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE schema_version (version INTEGER)")
    conn.execute("INSERT INTO schema_version VALUES (1)")
    conn.execute("CREATE TABLE probe (a REAL)")
    conn.execute("INSERT INTO probe VALUES (1.0)")
    conn.commit()
    conn.close()
    assert check_explicit_db(db, expected_version="1", table_specs=PROBE_SPECS) == []


def test_explicit_db_missing_version_table_fails(tmp_path: Path):
    db = tmp_path / "nover.db"
    _build_db(db, version=None, rows=[(1.0,)])
    assert _codes(check_explicit_db(db, expected_version="1", table_specs=PROBE_SPECS)) == {"missing_table"}


def test_explicit_db_legacy_unversioned_advisory_but_content_still_checked(tmp_path: Path):
    good = tmp_path / "legacy.db"
    _build_db(good, version=None, rows=[(1.0,)])
    issues = check_explicit_db(good, expected_version="1", table_specs=PROBE_SPECS, legacy_unversioned=True)
    assert _codes(issues) == set()
    assert {i.code for i in issues if i.severity == "advisory"} == {"legacy_unversioned"}
    bad = tmp_path / "legacy_bad.db"
    _build_db(bad, version=None, rows=[(99.0,)])
    assert _codes(check_explicit_db(bad, expected_version="1", table_specs=PROBE_SPECS, legacy_unversioned=True)) == {
        "out_of_range"
    }


def test_explicit_db_findings_are_value_free(tmp_path: Path):
    db = tmp_path / "leak.db"
    _build_db(db, version="9", rows=None)
    secret = tmp_path / "secret_dir"
    moved = secret / "leak.db"
    secret.mkdir()
    db.rename(moved)
    for issue in check_explicit_db(moved, expected_version="1", table_specs=PROBE_SPECS):
        assert "secret_dir" not in issue.table + issue.column + issue.message + issue.code


def test_explicit_db_missing_table_and_column_fail(tmp_path: Path):
    db = tmp_path / "notab.db"
    _build_db(db, version="1", rows=None)
    assert _codes(check_explicit_db(db, expected_version="1", table_specs=PROBE_SPECS)) == {"missing_table"}
    db2 = tmp_path / "nocol.db"
    _build_db(db2, version="1", rows=[(1.0,)], columns=("b",))
    specs = {"probe": [ColumnSpec("a", "float", (0.0, 10.0))]}
    assert _codes(check_explicit_db(db2, expected_version="1", table_specs=specs)) == {"missing_column"}


def test_explicit_db_out_of_range_and_duplicates_fail(tmp_path: Path):
    db = tmp_path / "range.db"
    _build_db(db, version="1", rows=[(99.0,)])
    assert _codes(check_explicit_db(db, expected_version="1", table_specs=PROBE_SPECS)) == {"out_of_range"}
    db2 = tmp_path / "dup.db"
    _build_db(db2, version="1", rows=[(1.0,), (1.0,)])
    issues = check_explicit_db(db2, expected_version="1", table_specs=PROBE_SPECS, table_keys={"probe": ("a",)})
    assert _codes(issues) == {"duplicate_key"}
    assert all(i.table == "probe" and i.column == "a" for i in issues)


def test_explicit_db_unreadable_and_missing_fail_without_creating(tmp_path: Path):
    junk = tmp_path / "junk.db"
    junk.write_text("not sqlite", encoding="utf-8")
    assert _codes(check_explicit_db(junk, expected_version="1", table_specs=PROBE_SPECS)) == {"unreadable_db"}
    missing = tmp_path / "absent.db"
    assert _codes(check_explicit_db(missing, expected_version="1", table_specs=PROBE_SPECS)) == {"unreadable_db"}
    assert not missing.exists()


def test_explicit_db_check_is_read_only(tmp_path: Path):
    db = tmp_path / "ro.db"
    _build_db(db, version="1", rows=[(1.0,)])
    before = hashlib.sha256(db.read_bytes()).hexdigest()
    check_explicit_db(db, expected_version="1", table_specs=PROBE_SPECS)
    assert hashlib.sha256(db.read_bytes()).hexdigest() == before


def test_explicit_db_unsafe_version_table_closes_owned_connection(tmp_path, monkeypatch):
    import sqlite3

    db = tmp_path / "evilver.db"
    conn = sqlite3.connect(db)
    conn.execute('CREATE TABLE "a""b" (a REAL)')
    conn.execute("CREATE TABLE probe (a REAL)")
    conn.commit()
    conn.close()
    closed = []
    real_connect = sqlite3.connect

    class SpyConn:
        def __init__(self, *args, **kwargs):
            self._conn = real_connect(*args, **kwargs)

        def execute(self, *args, **kwargs):
            return self._conn.execute(*args, **kwargs)

        def close(self):
            closed.append(True)
            return self._conn.close()

    monkeypatch.setattr(sqlite3, "connect", lambda *args, **kwargs: SpyConn(*args, **kwargs))
    issues = check_explicit_db(
        db, expected_version="1", table_specs={"probe": [ColumnSpec("a", "float")]}, version_table='a"b'
    )
    assert [i.code for i in issues if i.severity == "error"] == ["unsafe_identifier"]
    assert closed == [True]


def test_explicit_db_malicious_table_name_fails_closed(tmp_path: Path):
    db = tmp_path / "evil.db"
    _build_db(db, version="1", rows=[(1.0,)])
    evil = 'probe"; DROP TABLE probe; --'
    conn = sqlite3.connect(db)
    conn.execute('CREATE TABLE "probe""; DROP TABLE probe; --" (a REAL)')
    conn.commit()
    conn.close()
    issues = check_explicit_db(db, expected_version="1", table_specs={evil: [ColumnSpec("a", "float")]})
    assert _codes(issues) == {"unsafe_identifier"}
    issues = check_explicit_db(db, expected_version="1", table_specs={}, version_table=evil)
    assert _codes(issues) == {"unsafe_identifier"}
    # The probe table survives the attempt.
    conn = sqlite3.connect(db)
    assert conn.execute("SELECT count(*) FROM probe").fetchone()[0] == 1
    conn.close()


def test_explicit_db_error_names_table_and_column(tmp_path: Path):
    db = tmp_path / "named.db"
    _build_db(db, version="9", rows=None)
    issues = check_explicit_db(db, expected_version="1", table_specs=PROBE_SPECS)
    by_code = {i.code: i for i in issues}
    assert by_code["schema_version_mismatch"].column == "schema_version"
    assert by_code["missing_table"].column == "probe"
