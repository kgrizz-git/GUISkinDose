"""Validation for correction-data CSVs and explicit legacy SQLite databases.

Phase A of the correction-data packaging plan: pure, side-effect-free checks
with no runtime wiring (wiring the explicit-DB adapter into calculation is
Phase B). All findings are returned as :class:`ValidationIssue` values with an
``error`` / ``advisory`` severity split: errors can change dose, advisories
(provenance gaps, known-invalid inherited classes) cannot.

Only stdlib + pandas are imported so the package layering stays trivial.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import pandas as pd

Severity = Literal["error", "advisory"]

_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _quoted_identifier(name: str) -> str:
    """Quote a table name for SQL after strict allowlist validation.

    Table names cannot be bound as query parameters, and explicit-DB names
    originate from the database file itself — so interpolation is only safe
    behind this guard (letters/digits/underscore, no quotes or whitespace).
    """
    if not _IDENTIFIER_RE.match(name):
        raise ValueError(f"Unsafe SQL identifier: {name!r}")
    return f'"{name}"'


@dataclass(frozen=True)
class ValidationIssue:
    """One validation finding: where, what rule, and how bad."""

    table: str
    column: str
    code: str
    message: str
    severity: Severity


@dataclass(frozen=True)
class ColumnSpec:
    """Checkable contract for one manifest column."""

    name: str
    dtype: str  # "float" | "string"
    physical_range: tuple[float | None, float | None] | None = None


def check_frame(
    df: pd.DataFrame,
    columns: list[ColumnSpec],
    *,
    table_name: str,
    key_columns: tuple[str, ...] = (),
) -> list[ValidationIssue]:
    """Required columns, dtypes, finite values, ranges, and duplicate keys."""
    issues: list[ValidationIssue] = []
    for spec in columns:
        if spec.name not in df.columns:
            issues.append(
                ValidationIssue(table_name, spec.name, "missing_column", f"Required column {spec.name!r} is absent.", "error")
            )
            continue
        series = df[spec.name]
        if spec.dtype == "string":
            if len(series) == 0:
                issues.append(
                    ValidationIssue(table_name, spec.name, "empty_column", f"Column {spec.name!r} has no rows.", "error")
                )
            elif bool(series.isna().any()):
                issues.append(
                    ValidationIssue(table_name, spec.name, "missing_value", f"Column {spec.name!r} holds missing values.", "error")
                )
            elif bool(series.map(lambda value: not isinstance(value, str)).any()):
                issues.append(
                    ValidationIssue(
                        table_name, spec.name, "wrong_dtype", f"Column {spec.name!r} holds non-string values.", "error"
                    )
                )
            continue
        if spec.dtype != "float":
            issues.append(
                ValidationIssue(
                    table_name, spec.name, "unknown_dtype", f"Column {spec.name!r} declares unknown dtype {spec.dtype!r}.", "error"
                )
            )
            continue
        if spec.dtype == "float":
            if len(series) == 0:
                issues.append(
                    ValidationIssue(table_name, spec.name, "empty_column", f"Column {spec.name!r} has no rows.", "error")
                )
                continue
            numeric = pd.to_numeric(series, errors="coerce")
            if numeric.isna().all():
                if series.isna().all():
                    issues.append(
                        ValidationIssue(
                            table_name, spec.name, "non_finite", f"Column {spec.name!r} holds no usable numeric values.", "error"
                        )
                    )
                else:
                    issues.append(
                        ValidationIssue(
                            table_name, spec.name, "wrong_dtype", f"Column {spec.name!r} holds non-numeric values.", "error"
                        )
                    )
                continue
            if bool(numeric.isna().any()):
                if bool(((~series.isna()) & (numeric.isna())).any()):
                    issues.append(
                        ValidationIssue(
                            table_name, spec.name, "wrong_dtype", f"Column {spec.name!r} holds non-numeric values.", "error"
                        )
                    )
                else:
                    issues.append(
                        ValidationIssue(
                            table_name, spec.name, "non_finite", f"Column {spec.name!r} holds missing values.", "error"
                        )
                    )
                continue
            if not bool(numeric.map(math.isfinite).all()):
                issues.append(
                    ValidationIssue(
                        table_name, spec.name, "non_finite", f"Column {spec.name!r} holds non-finite values.", "error"
                    )
                )
            if spec.physical_range is not None:
                low, high = spec.physical_range
                values = numeric.dropna()
                if low is not None and bool((values < low).any()):
                    issues.append(
                        ValidationIssue(
                            table_name, spec.name, "out_of_range", f"Column {spec.name!r} holds values below {low}.", "error"
                        )
                    )
                if high is not None and bool((values > high).any()):
                    issues.append(
                        ValidationIssue(
                            table_name, spec.name, "out_of_range", f"Column {spec.name!r} holds values above {high}.", "error"
                        )
                    )
    for key in key_columns:
        if key not in df.columns:
            continue
        if bool(df[key].isna().any()):
            # pandas treats NaN as not-equal-to-NaN, so null keys would slip
            # past the duplicate check below: keys must be complete.
            issues.append(
                ValidationIssue(table_name, key, "null_key", f"Lookup key {key!r} holds null values.", "error")
            )
    # Per-column duplicates are only meaningful for single-column keys: in
    # a composite key the individual axes legitimately repeat (grid tables).
    if len(key_columns) == 1 and key_columns[0] in df.columns and bool(df.duplicated(subset=[key_columns[0]]).any()):
        issues.append(
            ValidationIssue(table_name, key_columns[0], "duplicate_key", f"Lookup key {key_columns[0]!r} has duplicate entries.", "error")
        )
    if len(key_columns) > 1 and all(k in df.columns for k in key_columns) and bool(df.duplicated(subset=list(key_columns)).any()):
        issues.append(
            ValidationIssue(
                table_name,
                ",".join(key_columns),
                "duplicate_key",
                f"Composite lookup key {key_columns!r} has duplicate entries.",
                "error",
            )
        )
    return issues


def check_support_transmission(
    df: pd.DataFrame,
    *,
    table_name: str = "correction_table_and_pad_attenuation",
    value_column: str = "k_patient_support",
) -> list[ValidationIssue]:
    """Range policy for patient-support transmission values.

    Non-finite, negative, and above-1.0 values are hard errors (unphysical,
    dose-inflating). Exact zeros are a known-invalid inherited class (304
    AlluraClarity Plane B rows) handled as warned-neutral at runtime, so they
    are advisory here — not a dataset error.
    """
    issues: list[ValidationIssue] = []
    if value_column not in df.columns:
        issues.append(ValidationIssue(table_name, value_column, "missing_column", f"Required column {value_column!r} is absent.", "error"))
        return issues
    values = pd.to_numeric(df[value_column], errors="coerce")
    if bool(values.isna().any()):
        issues.append(
            ValidationIssue(table_name, value_column, "non_finite", f"Column {value_column!r} holds non-numeric values.", "error")
        )
        return issues
    if not bool(values.map(math.isfinite).all()):
        issues.append(
            ValidationIssue(table_name, value_column, "non_finite", f"Column {value_column!r} holds non-finite values.", "error")
        )
        return issues
    if bool((values < 0).any()):
        issues.append(
            ValidationIssue(table_name, value_column, "out_of_range", f"Column {value_column!r} holds negative values.", "error")
        )
    if bool((values > 1.0).any()):
        issues.append(
            ValidationIssue(
                table_name, value_column, "out_of_range", f"Column {value_column!r} holds values above 1.0 (unphysical).", "error"
            )
        )
    if bool((values == 0.0).any()):
        issues.append(
            ValidationIssue(
                table_name,
                value_column,
                "zero_transmission",
                f"Column {value_column!r} holds {(values == 0.0).sum()} exact-zero rows (known-invalid inherited class; warned-neutral at runtime).",
                "advisory",
            )
        )
    return issues


def check_manifest_consistency(manifest: dict, table_dir: Path) -> list[ValidationIssue]:
    """Every CSV is covered, declared columns match headers, hashes match, keys exist."""
    issues: list[ValidationIssue] = []
    tables = manifest.get("tables", [])
    covered = {entry.get("file") for entry in tables}
    actual = set()
    for path in sorted(table_dir.glob("*.csv")):
        actual.add(path.name)
    for path in sorted((table_dir / "hvl_tables").glob("*.csv")):
        actual.add(f"hvl_tables/{path.name}")
    for missing in sorted(actual - covered):
        issues.append(ValidationIssue("manifest", missing, "uncovered_csv", f"CSV {missing!r} has no manifest entry.", "error"))
    for entry in tables:
        name = entry.get("file", "?")
        if "file" not in entry:
            issues.append(ValidationIssue("manifest", name, "missing_key", "A manifest entry lacks its 'file' field.", "error"))
            continue
        for key in ("sqlite_table", "role", "source_type", "provenance_confidence", "sha256"):
            if key not in entry:
                issues.append(ValidationIssue("manifest", name, "missing_key", f"Manifest entry {name!r} lacks {key!r}.", "error"))
        for key in ("upstream_history", "literature", "generation_method"):
            if entry.get(key) in (None, ""):
                issues.append(
                    ValidationIssue("manifest", name, "missing_key", f"Manifest entry {name!r} lacks provenance field {key!r}.", "advisory")
                )
        if entry.get("role") == "runtime_lookup" and not entry.get("runtime_consumer"):
            issues.append(
                ValidationIssue("manifest", name, "missing_key", f"Runtime table {name!r} names no consumer.", "error")
            )
        declared = [col.get("name", "?") for col in entry.get("columns", [])]
        for key in entry.get("lookup_keys", []):
            if key not in declared:
                issues.append(
                    ValidationIssue("manifest", name, "column_mismatch", f"Lookup key {key!r} is not a declared column of {name!r}.", "error")
                )
        lookup_value = entry.get("lookup_value")
        if lookup_value is not None and lookup_value not in declared:
            issues.append(
                ValidationIssue("manifest", name, "column_mismatch", f"Lookup value {lookup_value!r} is not a declared column of {name!r}.", "error")
            )
        candidate = table_dir / name
        if not candidate.is_file():
            issues.append(
                ValidationIssue("manifest", name, "missing_file", f"Declared CSV {name!r} is absent.", "error")
            )
            continue
        with candidate.open(encoding="utf-8", newline="") as fh:
            header = next(csv.reader(fh), [])
        if set(declared) != set(header) or len(declared) != len(header):
            issues.append(
                ValidationIssue(
                    "manifest", name, "column_mismatch", f"Manifest columns for {name!r} do not match the CSV header.", "error"
                )
            )
        expected = entry.get("sha256")
        if expected:
            digest = hashlib.sha256(candidate.read_bytes()).hexdigest()
            if digest != expected:
                issues.append(
                    ValidationIssue("manifest", name, "hash_mismatch", f"CSV {name!r} drifted from its manifest hash.", "error")
                )
    return issues


def check_explicit_db(
    db_path: Path,
    *,
    expected_version: str,
    table_specs: dict[str, list[ColumnSpec]],
    table_keys: dict[str, tuple[str, ...]] | None = None,
    version_table: str = "schema_version",
    legacy_unversioned: bool = False,
    _conn: sqlite3.Connection | None = None,
) -> list[ValidationIssue]:
    """Fail-closed validation for an explicitly configured legacy SQLite DB.

    Pure read-only checks: the file must be readable SQLite, every required
    table/column must exist, and each required column is type/finite/range/
    duplicate checked. Findings are value-free (table/column/code only — never
    the database path) so they are safe to surface in errors and logs. Never
    creates or bootstraps a replacement file.

    Version policy: when the schema-version table exists, its single version
    must equal ``expected_version``. When absent, the DB is classified as
    ``legacy`` (advisory) iff ``legacy_unversioned`` is set — otherwise it is
    an error. Real bootstrap databases carry no version table.

    ``_conn`` is internal: an already-open read connection to reuse (shared
    snapshot with the subsequent read). When given, it is left open for the
    caller; otherwise it is opened and closed here.
    """
    issues: list[ValidationIssue] = []
    own_connection = _conn is None
    if own_connection:
        try:
            # mode=ro: validate read-only and never create a replacement file.
            # as_uri keeps Windows drive letters and backslashes intact.
            conn = sqlite3.connect(f"{Path(db_path).resolve().as_uri()}?mode=ro", uri=True)
        except sqlite3.Error:
            return [ValidationIssue("", "", "unreadable_db", "File is not a readable SQLite database.", "error")]
    else:
        conn = _conn
    try:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    except sqlite3.Error:
        if own_connection:
            conn.close()
        return [ValidationIssue("", "", "unreadable_db", "File is not a readable SQLite database.", "error")]
    if version_table not in tables:
        if legacy_unversioned:
            issues.append(
                ValidationIssue(
                    version_table, version_table, "legacy_unversioned", "No schema-version table; treating as legacy.", "advisory"
                )
            )
        else:
            issues.append(
                ValidationIssue(version_table, version_table, "missing_table", f"Schema-version table {version_table!r} is absent.", "error")
            )
    else:
        # Table names cannot be bound parameters; the allowlist guard above makes
        # this interpolation safe. nosec: the identifier is regex-validated.
        try:
            versions = [str(row[0]) for row in conn.execute(f"SELECT version FROM {_quoted_identifier(version_table)}")]  # nosec B608
        except sqlite3.Error:
            versions = []
        except ValueError:
            if own_connection:
                conn.close()
            return [ValidationIssue(version_table, version_table, "unsafe_identifier", f"Table name {version_table!r} is not a safe identifier.", "error")]
        if versions != [expected_version]:
            issues.append(
                ValidationIssue(
                    version_table,
                    version_table,
                    "schema_version_mismatch",
                    "Schema version does not match the expected version.",
                    "error",
                )
            )
    try:
        for table, columns in table_specs.items():
            if table == version_table:
                continue
            if table not in tables:
                issues.append(ValidationIssue(table, table, "missing_table", f"Required table {table!r} is absent.", "error"))
                continue
            try:
                frame = pd.read_sql_query(f"SELECT * FROM {_quoted_identifier(table)}", conn)  # nosec B608
            except (sqlite3.Error, ValueError, pd.errors.DatabaseError) as exc:
                code = "unsafe_identifier" if isinstance(exc, ValueError) else "unreadable_table"
                issues.append(
                    ValidationIssue(table, table, code, f"Table {table!r} could not be read safely.", "error")
                )
                continue
            for issue in check_frame(frame, columns, table_name=table, key_columns=(table_keys or {}).get(table, ())):
                issues.append(issue)
    finally:
        if own_connection:
            conn.close()
    return issues


def load_manifest(table_dir: Path) -> dict:
    """Read the packaged manifest JSON beside the CSVs."""
    return json.loads((table_dir / "correction_data_manifest.json").read_text(encoding="utf-8"))
