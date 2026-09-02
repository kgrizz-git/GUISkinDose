"""Adapter for DoseTrack XLSX/CSV exports (Phase 4).

Maps DoseTrack column headers to rdsr_parser()-compatible names, infers
Manufacturer/ManufacturerModelName from the Equipment Name column, applies unit
conversions (Air Kerma mGy→Gy, DAP Gy·cm²→Gy·m², Tube Current µA→mA), derives
CollimatedFieldArea_m2 from the DAP formula, and passes through rdsr_normalizer()
via the shared pipeline in ``base.py``.

Column map derived from dhen2714/PySkinDose DOSETRACK2PSD dict and dosetrack.py
vendor transforms (saved in dev-docs/references/dhen2714_dosetrack.py). Validated
against Siemens AXIOM-Artis column names. Philips path is implemented but untested
against a real DoseTrack XLSX.
"""

from __future__ import annotations

import pandas as pd

from guiskindose.input_adapters.base import (
    AdapterContext,
    coerce_numeric_columns,
    convert_dap_series_to_gym2,
    convert_field_with_header_units,
    run_normalizer_pipeline,
)
from guiskindose.input_adapters.models import InputAdapterResult
from guiskindose.input_adapters.tabular_loader import _RawLoad
from guiskindose.privacy import exception_class_name
from guiskindose.settings import PyskindoseSettings

# Lowercase versions of key DoseTrack export column headers (for header detection).
# Source: dhen2714/PySkinDose DOSETRACK2PSD dict (dev-docs/references/).
DOSETRACK_COLUMN_NAMES: frozenset[str] = frozenset(
    {
        "plane code",
        "air kerma (mgy)",
        "tube voltage peak (kv)",
        "positioner primary angle (deg)",
        "positioner secondary angle (deg)",
        "distance source to detector (mm)",
        "distance source to isocenter (mm)",
        "table longitudinal position (mm)",
        "table lateral position (mm)",
        "table height position (mm)",
        "collimated field area (m2)",
        "equipment name",
        "filter material",
    }
)

# Maps rdsr_parser() column name → DoseTrack header patterns (lowercase).
# Notes:
#  - "Equipment Name" is a special sentinel (→ _dt_equipment_name) used by the adapter
#    to infer Manufacturer/ManufacturerModelName; it is not a real rdsr_parser column.
#  - DAP (Gy*cm2) is not mapped to DoseAreaProduct_Gym2 here; the adapter derives
#    CollimatedFieldArea_m2 from the DAP/dose formula and stores DAP separately.
DOSETRACK_PATTERNS: dict[str, list[str]] = {
    "_dt_equipment_name": ["equipment name"],
    "AcquisitionPlane": ["plane code"],
    "IrradiationEventType": ["acquisition type", "irradiation event type"],
    "PositionerPrimaryAngle_deg": ["positioner primary angle (deg)", "positioner primary angle"],
    "PositionerSecondaryAngle_deg": ["positioner secondary angle (deg)", "positioner secondary angle"],
    # "tube voltage peak" distinguishes DoseTrack from Radimetrics "kvp kv"
    "KVP_kV": ["tube voltage peak (kv)", "tube voltage peak", "tube voltage (kv)", "kvp kv", "kvp"],
    # Air Kerma is in mGy in DoseTrack; the adapter divides by 1000 → Gy
    "DoseRP_Gy": ["air kerma (mgy)", "air kerma"],
    # Collimated Field Area is in m² in DoseTrack (no conversion needed)
    "CollimatedFieldArea_m2": ["collimated field area (m2)", "collimated field area"],
    # DAP is Gy*cm²; adapter divides by 10000 → Gy*m²
    "_dt_dap": ["dap (gy*cm2)", "dap (gy cm2)", "dap", "dose area product"],
    "DistanceSourcetoDetector_mm": [
        "distance source to detector (mm)",
        "distance source to detector",
    ],
    "DistanceSourcetoIsocenter_mm": [
        "distance source to isocenter (mm)",
        "distance source to isocenter",
    ],
    "TableLongitudinalPosition_mm": ["table longitudinal position (mm)", "table longitudinal position"],
    "TableLateralPosition_mm": ["table lateral position (mm)", "table lateral position"],
    "TableHeightPosition_mm": ["table height position (mm)", "table height position"],
    "XRayFilterMaterial": ["filter material"],
    "XRayFilterThicknessMinimum_mm": ["filter thickness"],
    "PulseRate_{pulse}/s": ["pulse rate (pulse/s)", "pulse rate"],
    "PulseWidth_ms": ["pulse width (ms)", "pulse width"],
    # Tube Current in DoseTrack is µA; adapter divides by 1000 → mA
    "XRayTubeCurrent_mA": ["tube current (ua)", "tube current"],
    "FocalSpotSize_mm": ["focal spot size (mm)", "focal spot size"],
    # mAs in DoseTrack; stored as-is (Exposure_uAs naming is approximate)
    "Exposure_uAs": ["mas (mas)"],
    "TargetRegion": ["target region"],
}

# Equipment Name value → Manufacturer (from dhen2714 reference DOSETRACK2PSD).
MODEL2MANUF: dict[str, str] = {
    "Azurion": "Philips",
    "AXIOM-Artis": "Siemens",
    "Allura Clarity": "Philips",
}

# Columns required before calling rdsr_normalizer() (after all adapter processing).
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
        "AcquisitionPlane",
        "XRayFilterThicknessMinimum_mm",
        "XRayFilterThicknessMaximum_mm",
    }
)

_NUMERIC_COLUMNS: frozenset[str] = frozenset(
    {
        "KVP_kV",
        "DoseRP_Gy",
        "CollimatedFieldArea_m2",
        "DistanceSourcetoDetector_mm",
        "DistanceSourcetoIsocenter_mm",
        "TableLongitudinalPosition_mm",
        "TableLateralPosition_mm",
        "TableHeightPosition_mm",
        "PositionerPrimaryAngle_deg",
        "PositionerSecondaryAngle_deg",
        "XRayFilterThicknessMinimum_mm",
        "XRayTubeCurrent_mA",
        "Exposure_uAs",
    }
)


def _normalize_plane_code(series: pd.Series) -> pd.Series:
    """Map integer plane codes to 'Single Plane', 'Plane A', or 'Plane B'."""
    try:
        numeric = pd.to_numeric(series, errors="coerce")
        codes = sorted(int(c) for c in numeric.dropna().unique())
    except (ValueError, TypeError):
        return series  # already string-coded

    if not codes:
        return series
    if len(codes) == 1:
        plane_map: dict[int, str] = {codes[0]: "Single Plane"}
    elif len(codes) == 2:
        plane_map = {codes[0]: "Plane A", codes[1]: "Plane B"}
    else:
        raise ValueError(
            f"DoseTrack Plane Code has {len(codes)} distinct values ({codes}); "
            "expected 1 (single-plane) or 2 (biplane)."
        )
    return numeric.map(plane_map).fillna(series)


def _parse_philips_filter(val: object) -> tuple[float, float]:
    """Parse a Philips semicolon-separated 'Al_mm;Cu_mm' filter string."""
    parts = str(val).split(";")
    try:
        if len(parts) >= 2:
            return float(parts[0].strip()), float(parts[1].strip())
        v = float(parts[0].strip())
        return 0.0, v
    except (ValueError, TypeError):
        return float("nan"), float("nan")


def _infer_manufacturer_from_equipment(data_df: pd.DataFrame, warnings: list[str]) -> pd.DataFrame:
    """Infer Manufacturer/Model/StationName from DoseTrack Equipment Name."""
    if "_dt_equipment_name" in data_df.columns:
        model_names = data_df["_dt_equipment_name"].dropna().unique()
        if len(model_names) == 0:
            raise ValueError("DoseTrack 'Equipment Name' column is empty; cannot infer manufacturer.")
        if len(model_names) > 1:
            warnings.append(
                f"DoseTrack export contains multiple equipment names: {list(model_names)}. "
                "Using the first for Manufacturer inference; rows may belong to different models."
            )
        model_name = str(model_names[0])
        manufacturer = MODEL2MANUF.get(model_name)
        if manufacturer is None:
            warnings.append(
                f"DoseTrack adapter: unknown equipment name {model_name!r}. "
                f"Known models: {sorted(MODEL2MANUF.keys())}. "
                "Manufacturer will be set to the model name; rdsr_normalizer may fail."
            )
            manufacturer = model_name
        data_df["Manufacturer"] = manufacturer
        data_df["ManufacturerModelName"] = model_name
        # Persist Equipment Name as StationName before drop so kerma-meter CF
        # can key on the tabular unit identity (often the model — see §6.1).
        data_df["StationName"] = data_df["_dt_equipment_name"]
        return data_df.drop(columns=["_dt_equipment_name"])
    if "Manufacturer" not in data_df.columns:
        raise ValueError(
            "DoseTrack adapter requires an 'Equipment Name' column to infer Manufacturer/Model. "
            "Column not found in the export."
        )
    return data_df


def _convert_dosetrack_units(data_df: pd.DataFrame, ctx: AdapterContext) -> pd.DataFrame:
    """Coerce numerics and apply header-aware DoseTrack unit conversions."""
    coerce_numeric_columns(data_df, _NUMERIC_COLUMNS, ctx.warnings)
    if "_dt_dap" in data_df.columns:
        data_df["_dt_dap"] = pd.to_numeric(data_df["_dt_dap"].astype(str).str.strip(), errors="coerce")

    # Header-aware unit conversions (unreadable tokens fall back to the DoseTrack
    # vendor defaults — mGy/µA/mm — and are flagged). Distances must be converted
    # before the CollimatedFieldArea_m2 derivation below, which assumes mm. The
    # DAP column and the derived CFA are handled separately further down.
    for col, kind in (
        ("DoseRP_Gy", "dose"),
        ("XRayTubeCurrent_mA", "tube_current"),
        ("DistanceSourcetoDetector_mm", "distance"),
        ("DistanceSourcetoIsocenter_mm", "distance"),
        ("TableLongitudinalPosition_mm", "distance"),
        ("TableLateralPosition_mm", "distance"),
        ("TableHeightPosition_mm", "distance"),
    ):
        convert_field_with_header_units(data_df, col, kind, ctx)

    if "_dt_dap" in data_df.columns:
        dap_src = next((s for s, t in ctx.column_map.items() if t == "_dt_dap"), None)
        data_df["DoseAreaProduct_Gym2"] = convert_dap_series_to_gym2(data_df["_dt_dap"], dap_src, ctx)
        data_df = data_df.drop(columns=["_dt_dap"])
    return data_df


def _apply_filter_thickness(data_df: pd.DataFrame, ctx: AdapterContext) -> None:
    """Normalize Philips Al;Cu or Siemens single-Cu filter thickness columns."""
    if "XRayFilterThicknessMinimum_mm" not in data_df.columns:
        return
    manufacturer_val = (
        str(data_df["Manufacturer"].dropna().iloc[0]) if "Manufacturer" in data_df.columns else ""
    )
    if manufacturer_val.lower() == "philips":
        pairs = data_df["XRayFilterThicknessMinimum_mm"].apply(_parse_philips_filter)
        data_df["XRayFilterThicknessMinimum_mm"] = pairs.apply(lambda x: x[0])  # Al
        data_df["XRayFilterThicknessMaximum_mm"] = pairs.apply(lambda x: x[1])  # Cu
        ctx.unit_conversions["XRayFilterThicknessMinimum_mm"] = "Philips Al;Cu split → Min=Al, Max=Cu"
    else:
        data_df["XRayFilterThicknessMaximum_mm"] = data_df["XRayFilterThicknessMinimum_mm"]


def _derive_collimated_field_area(data_df: pd.DataFrame) -> None:
    """Derive CollimatedFieldArea_m2 from the DoseTrack DAP formula when possible."""
    required = (
        "DoseAreaProduct_Gym2",
        "DoseRP_Gy",
        "DistanceSourcetoDetector_mm",
        "DistanceSourcetoIsocenter_mm",
    )
    if not all(col in data_df.columns for col in required):
        return
    dsd = data_df["DistanceSourcetoDetector_mm"]
    dsi = data_df["DistanceSourcetoIsocenter_mm"]
    data_df["CollimatedFieldArea_m2"] = data_df["DoseAreaProduct_Gym2"] / (
        data_df["DoseRP_Gy"] * ((dsi - 150) / dsd) ** 2
    )


def _fill_dosetrack_defaults(data_df: pd.DataFrame, warnings: list[str]) -> None:
    """Supply defaults for columns rdsr_normalizer requires but DoseTrack may omit."""
    if "IrradiationEventType" not in data_df.columns:
        data_df["IrradiationEventType"] = "Fluoroscopy"
        warnings.append("Column 'IrradiationEventType' not in DoseTrack export; defaulted to 'Fluoroscopy'.")
    if "XRayFilterMaterial" not in data_df.columns:
        data_df["XRayFilterMaterial"] = "Cu"
        warnings.append("Column 'XRayFilterMaterial' not in DoseTrack export; defaulted to 'Cu'.")


def _transform(data_df: pd.DataFrame, ctx: AdapterContext) -> pd.DataFrame:
    """DoseTrack-specific processing: ffill, manufacturer inference, units, CFA.

    Raises ValueError on blocking errors (missing Equipment Name, bad plane codes).
    """
    warnings = ctx.warnings

    # Forward-fill: DoseTrack uses hierarchical rows where parent values are only
    # written when they change (study/series level fields).
    data_df = data_df.ffill()
    data_df = _infer_manufacturer_from_equipment(data_df, warnings)

    # Normalize AcquisitionPlane from integer Plane Code values.
    if "AcquisitionPlane" in data_df.columns:
        try:
            data_df["AcquisitionPlane"] = _normalize_plane_code(data_df["AcquisitionPlane"])
        except ValueError as exc:
            raise ValueError(
                f"DoseTrack plane code normalization failed (error_type={exception_class_name(exc)})."
            ) from exc

    data_df = _convert_dosetrack_units(data_df, ctx)
    _apply_filter_thickness(data_df, ctx)
    _derive_collimated_field_area(data_df)
    _fill_dosetrack_defaults(data_df, warnings)
    return data_df


def adapt(
    loaded: _RawLoad,
    original_filename: str,
    settings: PyskindoseSettings,
) -> InputAdapterResult:
    """Convert a DoseTrack export to a normalized InputAdapterResult.

    Raises ValueError on blocking errors: missing Equipment Name (can't infer
    manufacturer), missing required columns, duplicate column mappings, or
    rdsr_normalizer() failure.
    """
    return run_normalizer_pipeline(
        loaded,
        schema_name="dosetrack",
        known_names=DOSETRACK_COLUMN_NAMES,
        patterns=DOSETRACK_PATTERNS,
        required_columns=REQUIRED_COLUMNS,
        transform=_transform,
        original_filename=original_filename,
        settings=settings,
    )
