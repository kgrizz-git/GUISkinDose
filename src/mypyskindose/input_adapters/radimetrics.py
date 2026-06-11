"""Adapter for Radimetrics CSV exports (Phase 3).

Maps Radimetrics column headers to rdsr_parser()-compatible names, applies
required unit conversions, then passes through rdsr_normalizer().

Column map and unit conversions derived from dhen2714/PySkinDose radimetrics.py
(saved in dev-docs/references/dhen2714_radimetrics.py). Only validated against
Siemens AXIOM-Artis exports via Radimetrics v6/v7. Unknown models produce a
warning but are not blocked.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from mypyskindose.input_adapters.column_mapper import (
    RADIMETRICS_COLUMN_NAMES,
    RADIMETRICS_PATTERNS,
    check_duplicate_mappings,
    detect_header_row,
    map_columns,
    unmapped_columns_warning,
)
from mypyskindose.input_adapters.models import InputAdapterResult, InputProvenance
from mypyskindose.input_adapters.tabular_loader import _RawLoad
from mypyskindose.settings import PyskindoseSettings

# Columns required to proceed to rdsr_normalizer().
REQUIRED_COLUMNS: frozenset[str] = frozenset(
    {
        "Manufacturer",
        "ManufacturerModelName",
        "KVP_kV",
        "DoseRP_Gy",
        "DistanceSourcetoDetector_mm",
        "DistanceSourcetoIsocenter_mm",
        "TableLongitudinalPosition_mm",
        "TableLateralPosition_mm",
        "TableHeightPosition_mm",
        "PositionerPrimaryAngle_deg",
        "PositionerSecondaryAngle_deg",
    }
)

_NUMERIC_COLUMNS: frozenset[str] = frozenset(
    {
        "KVP_kV",
        "DoseRP_Gy",
        "CollimatedFieldArea_m2",
        "DoseAreaProduct_Gym2",
        "DistanceSourcetoDetector_mm",
        "DistanceSourcetoIsocenter_mm",
        "TableLongitudinalPosition_mm",
        "TableLateralPosition_mm",
        "TableHeightPosition_mm",
        "PositionerPrimaryAngle_deg",
        "PositionerSecondaryAngle_deg",
        "XRayFilterThicknessMinimum_mm",
        "XRayFilterThicknessMaximum_mm",
        "Exposure_uAs",
    }
)

# Unit conversions applied after column rename.
# Each entry: (column_name, operation, factor, description)
# source unit → internal unit
_UNIT_CONVERSIONS: list[tuple[str, str, float, str]] = [
    ("DoseRP_Gy", "divide", 1000.0, "mGy → Gy"),
    ("CollimatedFieldArea_m2", "divide", 10000.0, "cm² → m²"),
    ("Exposure_uAs", "multiply", 1000.0, "mAs → µAs"),
]


def adapt(
    loaded: _RawLoad,
    original_filename: str,
    settings: PyskindoseSettings,
) -> InputAdapterResult:
    """Convert a Radimetrics CSV export to a normalized InputAdapterResult.

    Raises ValueError on blocking errors: missing required columns, duplicate
    mappings, or rdsr_normalizer() failure.
    """
    from mypyskindose.rdsr_normalizer import rdsr_normalizer

    warnings: list[str] = []
    raw_df = loaded.raw_df

    # 1. Detect header row
    header_idx = detect_header_row(raw_df, RADIMETRICS_COLUMN_NAMES)

    # 2. Extract headers and data rows
    raw_headers = [str(c).strip() for c in raw_df.iloc[header_idx]]
    data_df = raw_df.iloc[header_idx + 1 :].copy()
    data_df.columns = pd.Index(raw_headers)
    data_df = data_df.reset_index(drop=True)

    # Drop wholly-empty rows
    data_df = data_df[~data_df.apply(lambda r: r.astype(str).str.strip().eq("").all(), axis=1)]

    # 3. Map source column names → rdsr_parser column names
    column_map, mapping_warnings = map_columns(raw_headers, RADIMETRICS_PATTERNS)
    warnings.extend(mapping_warnings)
    unmatched_msg = unmapped_columns_warning(raw_headers, column_map)
    if unmatched_msg:
        warnings.append(unmatched_msg)

    dup_errors = check_duplicate_mappings(column_map)
    if dup_errors:
        raise ValueError("\n".join(dup_errors))

    # 4. Rename to rdsr_parser column names and check required set
    rename = {src: target for src, target in column_map.items() if src in data_df.columns}
    data_df = data_df.rename(columns=rename)

    missing = REQUIRED_COLUMNS - set(data_df.columns)
    if missing:
        raise ValueError(
            f"Missing required column(s) for radimetrics schema: {sorted(missing)}. "
            f"Column map attempted: {column_map}."
        )

    # 5. Coerce numerics (CSV reads all cells as strings)
    for col in _NUMERIC_COLUMNS:
        if col in data_df.columns:
            coerced = pd.to_numeric(data_df[col].astype(str).str.strip(), errors="coerce")
            n_bad = int(coerced.isna().sum()) - int(data_df[col].isna().sum())
            if n_bad > 0:
                warnings.append(
                    f"Column {col!r}: {n_bad} value(s) could not be parsed as numeric; set to NaN."
                )
            data_df[col] = coerced

    # 6. Apply unit conversions
    unit_conversions: dict[str, str] = {}
    for col, op, factor, description in _UNIT_CONVERSIONS:
        if col in data_df.columns:
            if op == "divide":
                data_df[col] = data_df[col] / factor
            else:
                data_df[col] = data_df[col] * factor
            unit_conversions[col] = description

    # 7. Warn on unknown models and GE lat/lon swap (non-blocking)
    _KNOWN_MODELS = {"AXIOM-Artis", "Artis", "Artis Q", "Artis Zee"}
    _GE_VARIANTS = {"ge medical systems", "ge healthcare", "ge", "gems"}
    if "ManufacturerModelName" in data_df.columns:
        seen_models = set(data_df["ManufacturerModelName"].dropna().unique())
        unknown = seen_models - _KNOWN_MODELS
        if unknown:
            warnings.append(
                f"Radimetrics adapter: unvalidated model(s) {unknown}. "
                "Column mapping and unit conversions may not be correct. "
                "Verify results against known-good RDSR output."
            )
    if "Manufacturer" in data_df.columns:
        seen_mfrs = {str(m).strip().lower() for m in data_df["Manufacturer"].dropna().unique()}
        if seen_mfrs & _GE_VARIANTS:
            warnings.append(
                "GE manufacturer detected. GE equipment stores lateral and longitudinal table "
                "positions in the opposite convention to MyPySkinDose. "
                "Enable 'Swap lateral/longitudinal axes' in the GUI import options, or pass "
                "swap_lat_lon=True when calling load_tabular(), to correct this."
            )

    # 8. Ensure IrradiationEventType and AcquisitionPlane have fallback values
    # Radimetrics exports may not include these; rdsr_normalizer accepts empty strings.
    for col, default in [("IrradiationEventType", "Fluoroscopy"), ("AcquisitionPlane", "Single Plane")]:
        if col not in data_df.columns:
            data_df[col] = default
            warnings.append(f"Column {col!r} not found in Radimetrics export; defaulted to {default!r}.")

    # 9. Run rdsr_normalizer()
    try:
        normalized_df = rdsr_normalizer(data_df, settings)
    except Exception as exc:
        raise ValueError(f"rdsr_normalizer() failed on radimetrics input: {exc}") from exc

    # 10. Build provenance
    provenance = InputProvenance(
        source_type=Path(original_filename).suffix.lstrip(".").lower(),
        schema_name="radimetrics",
        original_filename=original_filename,
        header_row_index=header_idx,
        detected_encoding=loaded.encoding,
        detected_delimiter=loaded.delimiter,
        sheet_name=None,
        column_map=dict(column_map),
        unit_conversions=unit_conversions,
        warnings=warnings,
    )

    return InputAdapterResult(
        normalized_data=normalized_df,
        raw_data=raw_df,
        provenance=provenance,
        warnings=warnings,
    )
