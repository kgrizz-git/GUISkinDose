"""Adapter for tables whose columns match rdsr_parser() output (raw RDSR-like schema).

Calls rdsr_normalizer() to produce the 23-column normalized DataFrame consumed
by analyze_data(). Unlike the normalized schema adapter, this requires
PyskindoseSettings for NormalizationSettings lookup by manufacturer/model.

This is Phase 2 of the tabular input plan.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from mypyskindose.input_adapters.column_mapper import (
    GENERIC_RDSR_COLUMN_NAMES,
    GENERIC_RDSR_PATTERNS,
    check_duplicate_mappings,
    detect_header_row,
    map_columns,
)
from mypyskindose.input_adapters.models import InputAdapterResult, InputProvenance
from mypyskindose.input_adapters.tabular_loader import _RawLoad
from mypyskindose.settings import PyskindoseSettings

# Columns rdsr_normalizer() always accesses, regardless of field_size_mode.
REQUIRED_COLUMNS: frozenset[str] = frozenset(
    {
        "Manufacturer",
        "ManufacturerModelName",
        "IrradiationEventType",
        "AcquisitionPlane",
        "DistanceSourcetoDetector_mm",
        "DistanceSourcetoIsocenter_mm",
        "TableLongitudinalPosition_mm",
        "TableLateralPosition_mm",
        "TableHeightPosition_mm",
        "XRayFilterMaterial",
        "XRayFilterThicknessMinimum_mm",
        "XRayFilterThicknessMaximum_mm",
        "PositionerPrimaryAngle_deg",
        "PositionerSecondaryAngle_deg",
        "KVP_kV",
        "DoseRP_Gy",
    }
)

# All numeric columns from rdsr_parser output. Must be float before rdsr_normalizer().
_NUMERIC_COLUMNS: frozenset[str] = frozenset(
    {
        "DistanceSourcetoDetector_mm",
        "FinalDistanceSourcetoDetector_mm",
        "DistanceSourcetoIsocenter_mm",
        "TableLongitudinalPosition_mm",
        "TableLateralPosition_mm",
        "TableHeightPosition_mm",
        "XRayFilterThicknessMinimum_mm",
        "XRayFilterThicknessMaximum_mm",
        "PositionerPrimaryAngle_deg",
        "PositionerSecondaryAngle_deg",
        "KVP_kV",
        "DoseRP_Gy",
        "CollimatedFieldArea_m2",
        "DoseAreaProduct_Gym2",
    }
)


def adapt(
    loaded: _RawLoad,
    original_filename: str,
    settings: PyskindoseSettings,
) -> InputAdapterResult:
    """Convert a raw-loaded file to a normalized InputAdapterResult via rdsr_normalizer().

    Raises ValueError on blocking errors: missing required columns, duplicate
    mappings, or rdsr_normalizer() failure (e.g. unknown manufacturer/model).
    """
    from mypyskindose.rdsr_normalizer import rdsr_normalizer

    warnings: list[str] = []
    raw_df = loaded.raw_df

    # 1. Detect header row
    header_idx = detect_header_row(raw_df, GENERIC_RDSR_COLUMN_NAMES)

    # 2. Extract headers and data rows
    raw_headers = [str(c).strip() for c in raw_df.iloc[header_idx]]
    data_df = raw_df.iloc[header_idx + 1 :].copy()
    data_df.columns = pd.Index(raw_headers)
    data_df = data_df.reset_index(drop=True)

    # Drop wholly-empty rows
    data_df = data_df[~data_df.apply(lambda r: r.astype(str).str.strip().eq("").all(), axis=1)]

    # 3. Map source column names → rdsr_parser column names
    column_map, mapping_warnings = map_columns(raw_headers, GENERIC_RDSR_PATTERNS)
    warnings.extend(mapping_warnings)

    dup_errors = check_duplicate_mappings(column_map)
    if dup_errors:
        raise ValueError("\n".join(dup_errors))

    # 4. Rename to rdsr_parser column names and check required set
    rename = {src: target for src, target in column_map.items() if src in data_df.columns}
    data_df = data_df.rename(columns=rename)

    missing = REQUIRED_COLUMNS - set(data_df.columns)
    if missing:
        raise ValueError(
            f"Missing required column(s) for generic_rdsr_like schema: {sorted(missing)}. "
            f"Column map attempted: {column_map}."
        )

    # 5. Coerce numeric columns to float (CSV reads all cells as strings)
    for col in _NUMERIC_COLUMNS:
        if col in data_df.columns:
            coerced = pd.to_numeric(data_df[col].astype(str).str.strip(), errors="coerce")
            n_bad = coerced.isna().sum() - data_df[col].isna().sum()
            if n_bad > 0:
                warnings.append(
                    f"Column {col!r}: {n_bad} value(s) could not be parsed as numeric; set to NaN."
                )
            data_df[col] = coerced

    # 6. Call rdsr_normalizer() to produce the 23-column normalized DataFrame
    try:
        normalized_df = rdsr_normalizer(data_df, settings)
    except Exception as exc:
        raise ValueError(f"rdsr_normalizer() failed on generic_rdsr_like input: {exc}") from exc

    # 7. Build provenance
    provenance = InputProvenance(
        source_type=Path(original_filename).suffix.lstrip(".").lower(),
        schema_name="generic_rdsr_like",
        original_filename=original_filename,
        header_row_index=header_idx,
        detected_encoding=loaded.encoding,
        detected_delimiter=loaded.delimiter,
        sheet_name=None,
        column_map=dict(column_map),
        unit_conversions={},
        warnings=warnings,
    )

    return InputAdapterResult(
        normalized_data=normalized_df,
        raw_data=raw_df,
        provenance=provenance,
        warnings=warnings,
    )
