"""Adapter for Radimetrics CSV exports (Phase 3).

Maps Radimetrics column headers to rdsr_parser()-compatible names, applies
required unit conversions, then passes through rdsr_normalizer() via the shared
pipeline in ``base.py``.

Column map and unit conversions derived from dhen2714/PySkinDose radimetrics.py
(saved in dev-docs/references/dhen2714_radimetrics.py). Only validated against
Siemens AXIOM-Artis exports via Radimetrics v6/v7. Unknown models produce a
warning but are not blocked.
"""

from __future__ import annotations

import pandas as pd

from mypyskindose.input_adapters.base import (
    AdapterContext,
    coerce_numeric_columns,
    convert_field_with_header_units,
    run_normalizer_pipeline,
)
from mypyskindose.input_adapters.models import InputAdapterResult
from mypyskindose.input_adapters.tabular_loader import _RawLoad
from mypyskindose.settings import PyskindoseSettings
from mypyskindose.settings.normalization_settings import normalize_manufacturer_key

# Lowercase versions of key Radimetrics export column headers (for header detection).
# Source: dhen2714/PySkinDose RADIMETRICS2PSD dict (dev-docs/references/).
# Header matching normalizes "_"/"-"/whitespace to a single space (see
# column_mapper._normalize_str), so these need only cover the spacing-independent
# spelling. They are split into the current export (unit suffixes in brackets) and
# an older Radimetrics export that uses underscores and omits the unit suffixes
# (e.g. "Primary_Angle_(RF)" rather than "Primary Angle (RF) [°]"). Both are listed
# so auto-detection recognises either generation.
RADIMETRICS_COLUMN_NAMES: frozenset[str] = frozenset(
    {
        # shared (no unit suffix in either generation)
        "manufacturer",
        "device",
        "kvp kv",
        # current export — unit suffixes present
        "dap (total) gy-cm2",
        "reference point dose (total) mgy",
        "primary angle (rf) [°]",
        "secondary angle (rf) [°]",
        "collimated field area (rf) [cm²]",
        "source to detector distance (rf) [mm]",
        "source to isocenter distance (rf) [mm]",
        "table longitudinal position [mm]",
        "table lateral position [mm]",
        "table height position [mm]",
        # older export — underscored, no unit suffix
        "primary angle (rf)",
        "secondary angle",
        "collimated field area",
        "source to detector distance",
        "source to isocenter distance",
        "table longitudinal position",
        "table lateral position",
        "table height position",
        "reference point dose",
        "dap gy cm2",
    }
)

# Maps rdsr_parser() column name → Radimetrics header patterns (lowercase).
RADIMETRICS_PATTERNS: dict[str, list[str]] = {
    "Manufacturer": ["manufacturer", "vendor"],
    "ManufacturerModelName": ["device", "device model", "equipment name"],
    "AcquisitionPlane": ["acquisition plane code", "acquisition plane"],
    "IrradiationEventType": ["irradiation event type"],
    "PositionerPrimaryAngle_deg": ["primary angle (rf)", "primary angle"],
    "PositionerSecondaryAngle_deg": ["secondary angle (rf)", "secondary angle"],
    # "kvp kv" only — bare "kvp" would also match per-plane "kVp (A) kV", "kVp (B) kV"
    "KVP_kV": ["kvp kv"],
    # Current exports label the total "Reference Point Dose (Total) mGy"; the older
    # export names the total bare "Reference_Point_Dose" alongside per-plane
    # "Reference_Point_Dose_(A/B)_mGy". The bare "reference point dose" pattern is
    # safe against the per-plane columns: map_columns resolves the resulting
    # duplicate by coverage (2*len(pattern) - len(header)), and the bare total
    # header is shorter than the "(a)/(b) mgy" variants, so the total always wins.
    "DoseRP_Gy": [
        "reference point dose (total) mgy",
        "reference point dose (total)",
        "reference point dose",
        "air kerma (total)",
    ],
    # DoseAreaProduct_Gym2 intentionally omitted — both "DAP (Total)" and "Fluoro DAP (Total)"
    # match the same pattern, causing a duplicate mapping error. Not required for dose calc.
    "CollimatedFieldArea_m2": [
        "collimated field area (rf) [cm²]",
        "collimated field area (rf)",
        "collimated field area",
    ],
    "DistanceSourcetoDetector_mm": [
        "source to detector distance (rf) [mm]",
        "source to detector distance (rf)",
        "source to detector distance",
    ],
    "DistanceSourcetoIsocenter_mm": [
        "source to isocenter distance (rf) [mm]",
        "source to isocenter distance (rf)",
        "source to isocenter distance",
    ],
    "TableLongitudinalPosition_mm": ["table longitudinal position [mm]", "table longitudinal position"],
    "TableLateralPosition_mm": ["table lateral position [mm]", "table lateral position"],
    "TableHeightPosition_mm": ["table height position [mm]", "table height position"],
    "XRayFilterMaterial": ["xray filter material codes", "filter material"],
    "XRayFilterThicknessMinimum_mm": ["xray filter min thicknesses", "filter thickness minimum"],
    "XRayFilterThicknessMaximum_mm": ["xray filter max thicknesses", "filter thickness maximum"],
    # "mas mas" only — bare "mas" matches per-plane "mAs (A) mAs" and "Max mAs mAs" variants
    "Exposure_uAs": ["mas mas"],
    "XRayTubeCurrent_mA": ["ma (rf)", "tube current"],
    "PulseRate_{pulse}/s": ["pulse rate (rf)", "pulse rate"],
    "PulseWidth_ms": ["pulse width (rf)", "pulse width"],
    "FocalSpotSize_mm": ["focal spots (rf)", "focal spot"],
    "TargetRegion": ["target region (rf)", "target region"],
}

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
        "XRayTubeCurrent_mA",
    }
)

# Header-aware unit conversions (target column → quantity kind). The unit is read
# from each column's original vendor header; unreadable tokens fall back to the
# documented vendor default (mGy/cm²/mAs/mm) and are flagged. See
# dev-docs/INPUT_SCHEMA_DETECTION.md ("Unit handling").
_UNIT_FIELDS: list[tuple[str, str]] = [
    ("DoseRP_Gy", "dose"),
    ("CollimatedFieldArea_m2", "area"),
    ("Exposure_uAs", "exposure"),
    ("XRayTubeCurrent_mA", "tube_current"),
    ("DistanceSourcetoDetector_mm", "distance"),
    ("DistanceSourcetoIsocenter_mm", "distance"),
    ("TableLongitudinalPosition_mm", "distance"),
    ("TableLateralPosition_mm", "distance"),
    ("TableHeightPosition_mm", "distance"),
]

_KNOWN_MODELS = {"AXIOM-Artis", "Artis", "Artis Q", "Artis Zee"}
_GE_VARIANTS = {"ge medical systems", "ge healthcare", "general electric", "ge", "gems"}


def _transform(data_df: pd.DataFrame, ctx: AdapterContext) -> pd.DataFrame:
    """Radimetrics-specific steps: numeric coercion, unit conversion, warnings."""
    # Coerce numerics (CSV reads all cells as strings)
    coerce_numeric_columns(data_df, _NUMERIC_COLUMNS, ctx.warnings)

    # Convert each field to its internal unit, reading the unit from the header.
    for col, kind in _UNIT_FIELDS:
        convert_field_with_header_units(data_df, col, kind, ctx)

    # Warn on unvalidated models and GE lat/lon convention (non-blocking)
    if "ManufacturerModelName" in data_df.columns:
        unknown = set(data_df["ManufacturerModelName"].dropna().unique()) - _KNOWN_MODELS
        if unknown:
            ctx.warnings.append(
                f"Radimetrics adapter: unvalidated model(s) {unknown}. "
                "Column mapping and unit conversions may not be correct. "
                "Verify results against known-good RDSR output."
            )
    if "Manufacturer" in data_df.columns:
        seen_mfrs = {normalize_manufacturer_key(m) for m in data_df["Manufacturer"].dropna().unique()}
        if seen_mfrs & _GE_VARIANTS:
            ctx.warnings.append(
                "GE manufacturer detected. GE equipment stores lateral and longitudinal table "
                "positions in the opposite convention to MyPySkinDose. "
                "The normalization layer applies the GE lateral/longitudinal correction; "
                "do not also enable the GUI swap unless validating a site-specific export."
            )

    # Radimetrics exports may omit these; rdsr_normalizer accepts the defaults.
    for col, default in [("IrradiationEventType", "Fluoroscopy"), ("AcquisitionPlane", "Single Plane")]:
        if col not in data_df.columns:
            data_df[col] = default
            ctx.warnings.append(f"Column {col!r} not found in Radimetrics export; defaulted to {default!r}.")

    return data_df


def adapt(
    loaded: _RawLoad,
    original_filename: str,
    settings: PyskindoseSettings,
) -> InputAdapterResult:
    """Convert a Radimetrics CSV export to a normalized InputAdapterResult.

    Raises ValueError on blocking errors: missing required columns, duplicate
    mappings, or rdsr_normalizer() failure.
    """
    return run_normalizer_pipeline(
        loaded,
        schema_name="radimetrics",
        known_names=RADIMETRICS_COLUMN_NAMES,
        patterns=RADIMETRICS_PATTERNS,
        required_columns=REQUIRED_COLUMNS,
        transform=_transform,
        original_filename=original_filename,
        settings=settings,
    )
