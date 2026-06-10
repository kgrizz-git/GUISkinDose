"""Adapter for tables whose columns already match the internal normalized contract.

The normalized schema expects the 23 columns produced by rdsr_normalizer(),
already in internal units and coordinate frame. No vendor coordinate correction
is applied. See INPUT_DATA_FLOW_AND_OFFSETS.md for the contract.

This is Phase 1 of the tabular input plan. It exercises the full
loader → header-detection → column-mapping → analyze_data() pipeline
without any vendor-specific complexity.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from mypyskindose.input_adapters.column_mapper import (
    NORMALIZED_COLUMN_CANONICAL,
    NORMALIZED_COLUMN_NAMES,
    NORMALIZED_REQUIRED_COLUMNS,
    detect_header_row,
)
from mypyskindose.input_adapters.models import InputAdapterResult, InputProvenance
from mypyskindose.input_adapters.tabular_loader import _RawLoad

# Columns that should be numeric after loading.
_NUMERIC_COLUMNS = frozenset(
    {
        "DSD", "DSI", "DID", "DSIRP",
        "Tx", "Ty", "Tz",
        "At1", "At2", "At3",
        "filter_thickness_Cu", "filter_thickness_Al",
        "Ap1", "Ap2", "Ap3",
        "DSL", "FS_lat", "FS_long",
        "kVp", "K_IRP",
    }
)

# Columns that contain study/patient identifiers whose uniqueness implies
# multiple procedures were exported into a single file.
_STUDY_ID_COLUMNS = frozenset(
    {"study_id", "accession_number", "patient_id", "study_uid", "studyinstanceuid"}
)


def _coerce_numeric(
    col_series: pd.Series,
    col_name: str,
    warnings: list[str],
) -> pd.Series:
    """Try float coercion; fall back to decimal-comma replacement on failure."""
    coerced = pd.to_numeric(col_series, errors="coerce")
    failed = coerced.isna() & col_series.str.strip().ne("")
    if failed.any() and coerced.isna().all():
        # Try decimal-comma replacement
        replaced = col_series.str.replace(",", ".", regex=False)
        coerced2 = pd.to_numeric(replaced, errors="coerce")
        if coerced2.notna().any():
            warnings.append(
                f"Column {col_name!r}: decimal-comma formatting detected and normalized."
            )
            coerced = coerced2
            failed = coerced.isna() & col_series.str.strip().ne("")

    if failed.any():
        bad_rows = list(failed[failed].index)
        warnings.append(
            f"Column {col_name!r}: {failed.sum()} non-numeric value(s) at row(s) "
            f"{bad_rows[:5]}{'...' if len(bad_rows) > 5 else ''}; set to NaN."
        )
    return coerced


def _build_column_map(
    raw_headers: list[str],
    warnings: list[str],
) -> tuple[dict[str, str], list[str]]:
    """Case-insensitive exact match of raw headers against NORMALIZED_COLUMN_NAMES.

    Returns (column_map, errors).
    column_map: {raw_header → canonical_col_name}
    errors: blocking problems (duplicate mappings, missing required columns).
    """
    column_map: dict[str, str] = {}
    errors: list[str] = []

    for raw_h in raw_headers:
        stripped = raw_h.strip()
        lower = stripped.lower().replace(" ", "_")
        if lower in NORMALIZED_COLUMN_NAMES:
            proper = NORMALIZED_COLUMN_CANONICAL[lower]
            if proper in column_map.values():
                existing_src = next(k for k, v in column_map.items() if v == proper)
                errors.append(
                    f"Duplicate mapping: both {existing_src!r} and {stripped!r} "
                    f"map to {proper!r}."
                )
            else:
                column_map[stripped] = proper

    missing = NORMALIZED_REQUIRED_COLUMNS - {v.lower() for v in column_map.values()}
    if missing:
        errors.append(
            f"Missing required column(s): {sorted(missing)}. "
            f"Expected column names (case-insensitive): {sorted(NORMALIZED_COLUMN_NAMES)}."
        )

    return column_map, errors


def adapt(loaded: _RawLoad, original_filename: str) -> InputAdapterResult:
    """Convert a raw-loaded file to a normalized InputAdapterResult.

    Raises ValueError on blocking errors (missing required columns, duplicates,
    multiple procedures detected).
    """
    warnings: list[str] = []
    raw_df = loaded.raw_df

    # 1. Detect header row
    header_idx = detect_header_row(raw_df, NORMALIZED_COLUMN_NAMES)

    # 2. Extract headers and data
    raw_headers = [str(c).strip() for c in raw_df.iloc[header_idx]]
    data_df = raw_df.iloc[header_idx + 1 :].copy()
    data_df.columns = pd.Index(raw_headers)
    data_df = data_df.reset_index(drop=True)

    # Drop rows that are entirely empty
    data_df = data_df[~data_df.apply(lambda r: r.str.strip().eq("").all(), axis=1)]

    # 3. Map columns (case-insensitive exact match for normalized schema)
    column_map, errors = _build_column_map(raw_headers, warnings)
    if errors:
        raise ValueError("\n".join(errors))

    # Rename to canonical names
    rename = {src: canon for src, canon in column_map.items() if src in data_df.columns}
    data_df = data_df.rename(columns=rename)

    # Keep only mapped columns
    canonical_cols = list(column_map.values())
    data_df = data_df[[c for c in canonical_cols if c in data_df.columns]]

    # 4. Multi-study check (on original raw headers, case-insensitive)
    raw_headers_lower = {h.strip().lower() for h in raw_headers}
    for sid_col in _STUDY_ID_COLUMNS:
        if sid_col in raw_headers_lower:
            actual_col = next(h for h in raw_headers if h.strip().lower() == sid_col)
            if actual_col in data_df.columns:
                unique_ids = data_df[actual_col].str.strip().nunique()
            else:
                raw_data_df = raw_df.iloc[header_idx + 1 :].copy()
                raw_data_df.columns = pd.Index(raw_headers)
                raw_data_df = raw_data_df.reset_index(drop=True)
                unique_ids = raw_data_df[actual_col].str.strip().nunique()
            if unique_ids > 1:
                raise ValueError(
                    f"Column {actual_col!r} contains {unique_ids} distinct values — "
                    "this file appears to contain multiple procedures. "
                    "Filter the export to a single procedure before loading, or "
                    "see the 'support for multiple exams' item in TO_DO.md."
                )

    # 5. Coerce numeric columns
    for col in _NUMERIC_COLUMNS:
        if col in data_df.columns:
            data_df[col] = _coerce_numeric(data_df[col].astype(str), col, warnings)

    # 6. Build provenance
    provenance = InputProvenance(
        source_type=Path(original_filename).suffix.lstrip(".").lower(),
        schema_name="normalized",
        original_filename=original_filename,
        header_row_index=header_idx,
        detected_encoding=loaded.encoding,
        detected_delimiter=loaded.delimiter,
        sheet_name=None,
        column_map={src: canon for src, canon in column_map.items()},
        unit_conversions={},  # no conversions; data is already in internal units
        warnings=warnings,
    )

    return InputAdapterResult(
        normalized_data=data_df,
        raw_data=raw_df,
        provenance=provenance,
        warnings=warnings,
    )
