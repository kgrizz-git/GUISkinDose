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

from mypyskindose.input_adapters.base import extract_table
from mypyskindose.input_adapters.column_mapper import detect_header_row
from mypyskindose.input_adapters.models import InputAdapterResult, InputProvenance
from mypyskindose.input_adapters.tabular_loader import _RawLoad

# Canonical column names produced by rdsr_normalizer(), lowercased for comparison.
NORMALIZED_COLUMN_NAMES: frozenset[str] = frozenset(
    {
        "model",
        "dsd",
        "dsi",
        "did",
        "dsirp",
        "acquisition_type",
        "acquisition_plane",
        "tx",
        "ty",
        "tz",
        "at1",
        "at2",
        "at3",
        "filter_thickness_cu",
        "filter_thickness_al",
        "ap1",
        "ap2",
        "ap3",
        "dsl",
        "fs_lat",
        "fs_long",
        "kvp",
        "k_irp",
    }
)

# Optional per-unit identity columns for kerma-meter correction (not required).
NORMALIZED_OPTIONAL_IDENTITY_COLUMNS: frozenset[str] = frozenset(
    {
        "station_name",
        "device_serial",
        "stationname",  # alias for StationName-style headers
        "deviceserialnumber",
    }
)

# Maps lowercase canonical name → proper-case name expected by analyze_data().
# Matches the column names produced by rdsr_normalizer().
NORMALIZED_COLUMN_CANONICAL: dict[str, str] = {
    "model": "model",
    "dsd": "DSD",
    "dsi": "DSI",
    "did": "DID",
    "dsirp": "DSIRP",
    "acquisition_type": "acquisition_type",
    "acquisition_plane": "acquisition_plane",
    "tx": "Tx",
    "ty": "Ty",
    "tz": "Tz",
    "at1": "At1",
    "at2": "At2",
    "at3": "At3",
    "filter_thickness_cu": "filter_thickness_Cu",
    "filter_thickness_al": "filter_thickness_Al",
    "ap1": "Ap1",
    "ap2": "Ap2",
    "ap3": "Ap3",
    "dsl": "DSL",
    "fs_lat": "FS_lat",
    "fs_long": "FS_long",
    "kvp": "kVp",
    "k_irp": "K_IRP",
    "station_name": "station_name",
    "device_serial": "device_serial",
    "stationname": "station_name",
    "deviceserialnumber": "device_serial",
}

# Required columns only — identity columns are optional.
NORMALIZED_REQUIRED_COLUMNS: frozenset[str] = NORMALIZED_COLUMN_NAMES

# Names recognized during header detection (required + optional identity).
NORMALIZED_HEADER_NAMES: frozenset[str] = NORMALIZED_COLUMN_NAMES | NORMALIZED_OPTIONAL_IDENTITY_COLUMNS

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

# Priority order for study-identifier column detection (most canonical first).
_STUDY_ID_PRIORITY = ("studyinstanceuid", "study_id", "accession_number", "patient_id", "study_uid")


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
    _warnings: list[str],
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
        # Also accept compact aliases without underscores (StationName, etc.).
        compact = stripped.lower().replace(" ", "").replace("_", "")
        key = lower if lower in NORMALIZED_COLUMN_CANONICAL else (
            compact if compact in NORMALIZED_COLUMN_CANONICAL else None
        )
        if key is not None:
            proper = NORMALIZED_COLUMN_CANONICAL[key]
            if proper in column_map.values():
                existing_src = next(k for k, v in column_map.items() if v == proper)
                errors.append(
                    f"Duplicate mapping: both {existing_src!r} and {stripped!r} "
                    f"map to {proper!r}."
                )
            else:
                column_map[stripped] = proper

    mapped_required = {
        v.lower() for v in column_map.values() if v.lower() in NORMALIZED_REQUIRED_COLUMNS
    }
    missing = NORMALIZED_REQUIRED_COLUMNS - mapped_required
    if missing:
        errors.append(
            f"Missing required column(s): {sorted(missing)}. "
            f"Expected column names (case-insensitive): {sorted(NORMALIZED_COLUMN_NAMES)}."
        )

    return column_map, errors


def adapt(loaded: _RawLoad, original_filename: str) -> InputAdapterResult | list[InputAdapterResult]:
    """Convert a raw-loaded file to a normalized InputAdapterResult.

    Returns a list of InputAdapterResult when multiple study identifiers are
    detected (one per distinct study ID, in order of first appearance).
    Raises ValueError on blocking errors (missing required columns, duplicates).
    """
    warnings: list[str] = []
    raw_df = loaded.raw_df

    # 1. Detect header row
    header_idx = detect_header_row(raw_df, NORMALIZED_HEADER_NAMES)

    # 2. Extract headers and data (shared with the rdsr-normalizer pipeline)
    raw_headers, data_df = extract_table(raw_df, header_idx)

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

    # 4. Locate study-identifier column for multi-study split detection.
    #    Iterate in priority order; stop at the first match.
    raw_headers_lower = {h.strip().lower() for h in raw_headers}
    _sid_values: pd.Series | None = None
    for sid_col in _STUDY_ID_PRIORITY:
        if sid_col not in raw_headers_lower:
            continue
        actual_col = next(h for h in raw_headers if h.strip().lower() == sid_col)
        if actual_col in data_df.columns:
            _sid_values = data_df[actual_col].astype(str).str.strip()
        else:
            # Study-ID column was not mapped into canonical data_df.
            # Reconstruct from raw and align to data_df's (possibly non-contiguous) index.
            raw_data_df = raw_df.iloc[header_idx + 1 :].copy()
            raw_data_df.columns = pd.Index(raw_headers)
            raw_data_df = raw_data_df.reset_index(drop=True)
            sid_all = raw_data_df[actual_col].astype(str).str.strip()
            _sid_values = sid_all.loc[data_df.index]
        break

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

    # 7. Multi-study split: if >1 distinct study IDs, return one result per group.
    if _sid_values is not None and _sid_values.nunique() > 1:
        temp_col = "__study_id__"
        data_df = data_df.copy()
        data_df[temp_col] = _sid_values  # index-aligned; pandas aligns by index
        results: list[InputAdapterResult] = []
        for study_id_val, group_df in data_df.groupby(temp_col, sort=False):
            group_df = group_df.drop(columns=[temp_col]).reset_index(drop=True)
            results.append(
                InputAdapterResult(
                    normalized_data=group_df,
                    raw_data=None,
                    provenance=InputProvenance(
                        source_type=provenance.source_type,
                        schema_name=provenance.schema_name,
                        original_filename=provenance.original_filename,
                        header_row_index=provenance.header_row_index,
                        detected_encoding=provenance.detected_encoding,
                        detected_delimiter=provenance.detected_delimiter,
                        sheet_name=provenance.sheet_name,
                        column_map=dict(provenance.column_map),
                        unit_conversions=dict(provenance.unit_conversions),
                        warnings=list(warnings),
                    ),
                    warnings=list(warnings),
                    study_id=str(study_id_val),
                )
            )
        return results

    return InputAdapterResult(
        normalized_data=data_df,
        raw_data=raw_df,
        provenance=provenance,
        warnings=warnings,
    )
