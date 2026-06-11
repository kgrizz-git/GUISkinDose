"""Shared pipeline for rdsr_normalizer-bound tabular adapters.

The `generic_rdsr_like`, `radimetrics`, and `dosetrack` adapters all follow the
same skeleton:

    detect header → extract table → drop empty rows → map columns →
    duplicate-mapping check → rename → [vendor transform] →
    required-columns check → rdsr_normalizer() → build provenance/result

Only the *vendor transform* (numeric coercion, unit conversions, manufacturer
inference, etc.) and a handful of constants differ. `run_normalizer_pipeline`
owns the shared skeleton; each adapter supplies its known-names, patterns,
required-columns set, and a `transform` callback.

The `normalized` schema does not use this pipeline — it matches columns exactly
(case-insensitive), performs a multi-procedure check, and skips
rdsr_normalizer() entirely.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Callable

import pandas as pd

from mypyskindose.input_adapters.column_mapper import (
    check_duplicate_mappings,
    detect_header_row,
    map_columns,
    unmapped_columns_warning,
)
from mypyskindose.input_adapters.models import InputAdapterResult, InputProvenance
from mypyskindose.input_adapters.tabular_loader import _RawLoad

if TYPE_CHECKING:
    from mypyskindose.settings import PyskindoseSettings


@dataclass
class AdapterContext:
    """Mutable working state handed to a vendor transform.

    The transform reads ``column_map``/``settings`` and may append to
    ``warnings`` and ``unit_conversions``; the pipeline picks both up afterwards
    for the provenance record.
    """

    column_map: dict[str, str]
    raw_headers: list[str]
    settings: PyskindoseSettings | None
    warnings: list[str]
    unit_conversions: dict[str, str] = field(default_factory=dict)


# A vendor transform takes the renamed DataFrame plus context and returns the
# DataFrame ready for rdsr_normalizer(). It may add/drop/coerce columns.
TransformFn = Callable[[pd.DataFrame, AdapterContext], pd.DataFrame]


def extract_table(raw_df: pd.DataFrame, header_idx: int) -> tuple[list[str], pd.DataFrame]:
    """Return (headers, data) for the table starting at *header_idx*.

    Headers are stripped strings; data has those headers as columns, the index
    reset, and wholly-empty rows dropped.
    """
    raw_headers = [str(c).strip() for c in raw_df.iloc[header_idx]]
    data_df = raw_df.iloc[header_idx + 1 :].copy()
    data_df.columns = pd.Index(raw_headers)
    data_df = data_df.reset_index(drop=True)
    data_df = data_df[~data_df.apply(lambda r: r.astype(str).str.strip().eq("").all(), axis=1)]
    return raw_headers, data_df


def coerce_numeric_columns(
    data_df: pd.DataFrame,
    numeric_columns: frozenset[str],
    warnings: list[str],
) -> None:
    """Coerce present numeric columns in place; warn on values set to NaN."""
    for col in numeric_columns:
        if col in data_df.columns:
            coerced = pd.to_numeric(data_df[col].astype(str).str.strip(), errors="coerce")
            n_bad = int(coerced.isna().sum()) - int(data_df[col].isna().sum())
            if n_bad > 0:
                warnings.append(
                    f"Column {col!r}: {n_bad} value(s) could not be parsed as numeric; set to NaN."
                )
            data_df[col] = coerced


def run_normalizer_pipeline(
    loaded: _RawLoad,
    *,
    schema_name: str,
    known_names: frozenset[str],
    patterns: dict[str, list[str]],
    required_columns: frozenset[str],
    transform: TransformFn,
    original_filename: str,
    settings: PyskindoseSettings,
) -> InputAdapterResult:
    """Run the shared header→map→transform→normalize pipeline.

    Parameters
    ----------
    schema_name:
        Provenance schema label and the name used in error messages.
    known_names:
        Column-name set used for header-row detection.
    patterns:
        Substring patterns mapping source headers → internal column names.
    required_columns:
        Columns that must be present *after* the transform, before
        rdsr_normalizer() is called.
    transform:
        Vendor-specific callback applied to the renamed DataFrame.

    Raises
    ------
    ValueError
        On duplicate column mappings, missing required columns, or
        rdsr_normalizer() failure.
    """
    from mypyskindose.rdsr_normalizer import rdsr_normalizer

    warnings: list[str] = []
    raw_df = loaded.raw_df

    header_idx = detect_header_row(raw_df, known_names)
    raw_headers, data_df = extract_table(raw_df, header_idx)

    column_map, mapping_warnings = map_columns(raw_headers, patterns)
    warnings.extend(mapping_warnings)
    unmatched_msg = unmapped_columns_warning(raw_headers, column_map)
    if unmatched_msg:
        warnings.append(unmatched_msg)

    dup_errors = check_duplicate_mappings(column_map)
    if dup_errors:
        raise ValueError("\n".join(dup_errors))

    rename = {src: tgt for src, tgt in column_map.items() if src in data_df.columns}
    data_df = data_df.rename(columns=rename)

    ctx = AdapterContext(
        column_map=column_map,
        raw_headers=raw_headers,
        settings=settings,
        warnings=warnings,
    )
    data_df = transform(data_df, ctx)

    missing = required_columns - set(data_df.columns)
    if missing:
        raise ValueError(
            f"Missing required column(s) for {schema_name} schema: {sorted(missing)}. "
            f"Column map attempted: {column_map}."
        )

    try:
        normalized_df = rdsr_normalizer(data_df, settings)
    except Exception as exc:
        raise ValueError(f"rdsr_normalizer() failed on {schema_name} input: {exc}") from exc

    # Sentinel _dt_* targets are adapter-internal; keep them out of the public map.
    public_column_map = {k: v for k, v in column_map.items() if not v.startswith("_dt_")}
    provenance = InputProvenance(
        source_type=Path(original_filename).suffix.lstrip(".").lower(),
        schema_name=schema_name,
        original_filename=original_filename,
        header_row_index=header_idx,
        detected_encoding=loaded.encoding,
        detected_delimiter=loaded.delimiter,
        sheet_name=None,
        column_map=public_column_map,
        unit_conversions=ctx.unit_conversions,
        warnings=warnings,
    )

    return InputAdapterResult(
        normalized_data=normalized_df,
        raw_data=raw_df,
        provenance=provenance,
        warnings=warnings,
    )
