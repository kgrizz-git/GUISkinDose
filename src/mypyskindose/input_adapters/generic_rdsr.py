"""Adapter for tables whose columns match rdsr_parser() output (raw RDSR-like schema).

Calls rdsr_normalizer() (via the shared pipeline in ``base.py``) to produce the
23-column normalized DataFrame consumed by analyze_data(). Unlike the normalized
schema adapter, this requires PyskindoseSettings for NormalizationSettings lookup
by manufacturer/model.

This is Phase 2 of the tabular input plan.
"""

from __future__ import annotations

import pandas as pd

from mypyskindose.input_adapters.base import (
    AdapterContext,
    coerce_numeric_columns,
    run_normalizer_pipeline,
)
from mypyskindose.input_adapters.models import InputAdapterResult
from mypyskindose.input_adapters.tabular_loader import _RawLoad
from mypyskindose.settings import PyskindoseSettings

# Lowercase versions of key rdsr_parser() output column names.
# Used by detect_header_row() (via the shared pipeline) for header location.
GENERIC_RDSR_COLUMN_NAMES: frozenset[str] = frozenset(
    {
        "manufacturer",
        "manufacturermodelname",
        "acquisitionplane",
        "irradiationeventtype",
        "distancesourcetodetector_mm",
        "distancesourcetoisocenter_mm",
        "positionerprimaryangle_deg",
        "positionersecondaryangle_deg",
        "tablelongitudinalposition_mm",
        "tablelateralposition_mm",
        "tableheightposition_mm",
        "xrayfiltermaterial",
        "xrayfilterthicknessminimum_mm",
        "xrayfilterthicknessmaximum_mm",
        "kvp_kv",
        "doserp_gy",
        "collimatedfieldarea_m2",
    }
)

# Maps rdsr_parser() column name → patterns that match it in source headers.
# Keys are the exact names rdsr_normalizer() expects.
# Patterns use _normalize_str() form (lowercase, underscores→spaces).
# The first pattern in each list is the self-match for exact rdsr_parser export names.
GENERIC_RDSR_PATTERNS: dict[str, list[str]] = {
    "Manufacturer": ["manufacturer", "vendor"],
    "ManufacturerModelName": [
        "manufacturermodelname",
        "manufacturer model name",
        "device model",
        "model name",
        "device",           # Radimetrics and some custom exports use bare "Device"
    ],
    "IrradiationEventType": [
        "irradiationeventtype",
        "irradiation event type",
        "event type",
    ],
    "AcquisitionPlane": ["acquisitionplane", "acquisition plane"],
    "DistanceSourcetoDetector_mm": [
        "distancesourcetodetector mm",
        "distance source to detector",
        "source to detector distance",  # alternate word order (some custom exports)
        "source detector distance",
    ],
    "DistanceSourcetoIsocenter_mm": [
        "distancesourcetoisocenter mm",
        "distance source to isocenter",
        "source to isocenter distance",  # alternate word order
        "source isocenter distance",
    ],
    "FinalDistanceSourcetoDetector_mm": [
        "finaldistancesourcetodetector mm",
        "final distance source to detector",
        "final dsd",
    ],
    "TableLongitudinalPosition_mm": [
        "tablelongitudinalposition mm",
        "table longitudinal position",
        "longitudinal position",
    ],
    "TableLateralPosition_mm": [
        "tablelateralposition mm",
        "table lateral position",
        "lateral position",
    ],
    "TableHeightPosition_mm": [
        "tableheightposition mm",
        "table height position",
        "table height",
    ],
    "XRayFilterMaterial": [
        "xrayfiltermaterial",
        "x ray filter material",
        "filter material",
    ],
    "XRayFilterThicknessMinimum_mm": [
        "xrayfilterthicknessminimum mm",
        "filter thickness minimum",
        "filter min",
    ],
    "XRayFilterThicknessMaximum_mm": [
        "xrayfilterthicknessmaximum mm",
        "filter thickness maximum",
        "filter max",
    ],
    "PositionerPrimaryAngle_deg": [
        "positionerprimaryangle deg",
        "positioner primary angle",
        "primary angle",
    ],
    "PositionerSecondaryAngle_deg": [
        "positionersecondaryangle deg",
        "positioner secondary angle",
        "secondary angle",
    ],
    "KVP_kV": ["kvp kv", "kvp", "tube voltage"],
    "DoseRP_Gy": [
        "doserp gy",
        "dose rp gy",
        "reference point dose gy",
        "reference point dose",     # without unit suffix (some custom exports)
        "air kerma gy",
        "air kerma",
    ],
    "CollimatedFieldArea_m2": [
        "collimatedfieldarea m2",
        "collimated field area",
        "field area",
    ],
    "DoseAreaProduct_Gym2": [
        "doseareaproduct gym2",
        "dose area product gy",
        "dap gy",
    ],
}

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


def _transform(data_df: pd.DataFrame, ctx: AdapterContext) -> pd.DataFrame:
    """Coerce numeric columns to float (CSV reads all cells as strings)."""
    coerce_numeric_columns(data_df, _NUMERIC_COLUMNS, ctx.warnings)
    return data_df


def adapt(
    loaded: _RawLoad,
    original_filename: str,
    settings: PyskindoseSettings,
) -> InputAdapterResult:
    """Convert a raw-loaded file to a normalized InputAdapterResult via rdsr_normalizer().

    Raises ValueError on blocking errors: missing required columns, duplicate
    mappings, or rdsr_normalizer() failure (e.g. unknown manufacturer/model).
    """
    return run_normalizer_pipeline(
        loaded,
        schema_name="generic_rdsr_like",
        known_names=GENERIC_RDSR_COLUMN_NAMES,
        patterns=GENERIC_RDSR_PATTERNS,
        required_columns=REQUIRED_COLUMNS,
        transform=_transform,
        original_filename=original_filename,
        settings=settings,
    )
