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
        if spec.dtype == "float":
            numeric = pd.to_numeric(series, errors="coerce")
            if numeric.isna().any() and not series.isna().all():
                issues.append(
                    ValidationIssue(
                        table_name, spec.name, "wrong_dtype", f"Column {spec.name!r} holds non-numeric values.", "error"
                    )
                )
                continue
            if not numeric.isna().all() and not bool(numeric.dropna().map(math.isfinite).all()):
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
        if key in df.columns and bool(df.duplicated(subset=[key]).any()):
            issues.append(
                ValidationIssue(table_name, key, "duplicate_key", f"Lookup key {key!r} has duplicate entries.", "error")
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
        candidate = table_dir / name
        if candidate.is_file():
            with candidate.open(encoding="utf-8", newline="") as fh:
                header = next(csv.reader(fh), [])
            declared = [col.get("name", "?") for col in entry.get("columns", [])]
            if set(declared) != set(header) or len(declared) != len(header):
                issues.append(
                    ValidationIssue(
                        "manifest", name, "column_mismatch", f"Manifest columns for {name!r} do not match the CSV header.", "error"
                    )
                )
        expected = entry.get("sha256")
        candidate = table_dir / name
        if expected and candidate.is_file():
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
) -> list[ValidationIssue]:
    """Fail-closed validation for an explicitly configured legacy SQLite DB.

    Pure read-only checks: the file must be readable SQLite, its schema
    version must match exactly, every required table/column must exist, and
    each required column is type/finite/range/duplicate checked. Never creates
    or bootstraps a replacement file.
    """
    issues: list[ValidationIssue] = []
    try:
        # mode=ro: validate read-only and never create a replacement file.
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    except sqlite3.Error:
        return [ValidationIssue(str(db_path), "", "unreadable_db", f"File {db_path} is not a readable SQLite database.", "error")]
    if version_table not in tables:
        issues.append(
            ValidationIssue(str(db_path), version_table, "missing_table", f"Schema-version table {version_table!r} is absent.", "error")
        )
    else:
        # Table names cannot be bound parameters; the allowlist guard above makes
        # this interpolation safe. nosec: the identifier is regex-validated.
        try:
            versions = [row[0] for row in conn.execute(f"SELECT version FROM {_quoted_identifier(version_table)}")]  # nosec B608
        except sqlite3.Error:
            versions = []
        except ValueError:
            conn.close()
            return [ValidationIssue(str(db_path), version_table, "unsafe_identifier", f"Table name {version_table!r} is not a safe identifier.", "error")]
        if versions != [expected_version]:
            issues.append(
                ValidationIssue(
                    str(db_path),
                    version_table,
                    "schema_version_mismatch",
                    f"Schema version {versions!r} does not match expected {expected_version!r}.",
                    "error",
                )
            )
    for table, columns in table_specs.items():
        if table == version_table:
            continue
        if table not in tables:
            issues.append(ValidationIssue(str(db_path), table, "missing_table", f"Required table {table!r} is absent.", "error"))
            continue
        try:
            frame = pd.read_sql_query(f"SELECT * FROM {_quoted_identifier(table)}", conn)  # nosec B608
        except (sqlite3.Error, ValueError, pd.errors.DatabaseError) as exc:
            code = "unsafe_identifier" if isinstance(exc, ValueError) else "unreadable_table"
            issues.append(
                ValidationIssue(str(db_path), table, code, f"Table {table!r} could not be read safely.", "error")
            )
            continue
        for issue in check_frame(frame, columns, table_name=f"{db_path}::{table}", key_columns=(table_keys or {}).get(table, ())):
            issues.append(issue)
    conn.close()
    return issues


def load_manifest(table_dir: Path) -> dict:
    """Read the packaged manifest JSON beside the CSVs."""
    return json.loads((table_dir / "correction_data_manifest.json").read_text(encoding="utf-8"))
