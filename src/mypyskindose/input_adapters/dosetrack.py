"""Adapter for DoseTrack XLSX/CSV exports (Phase 4).

Maps DoseTrack column headers to rdsr_parser()-compatible names, infers
Manufacturer/ManufacturerModelName from the Equipment Name column,
applies unit conversions (Air Kerma mGy→Gy, DAP Gy·cm²→Gy·m²,
Tube Current µA→mA), derives CollimatedFieldArea_m2 from the DAP
formula, and passes through rdsr_normalizer().

Column map derived from dhen2714/PySkinDose DOSETRACK2PSD dict and
dosetrack.py vendor transforms (saved in dev-docs/references/dhen2714_dosetrack.py).
Validated against Siemens AXIOM-Artis column names. Philips path is
implemented but untested against a real DoseTrack XLSX.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from mypyskindose.input_adapters.column_mapper import (
    DOSETRACK_COLUMN_NAMES,
    DOSETRACK_PATTERNS,
    check_duplicate_mappings,
    detect_header_row,
    map_columns,
    unmapped_columns_warning,
)
from mypyskindose.input_adapters.models import InputAdapterResult, InputProvenance
from mypyskindose.input_adapters.tabular_loader import _RawLoad
from mypyskindose.settings import PyskindoseSettings

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
    from mypyskindose.rdsr_normalizer import rdsr_normalizer

    warnings: list[str] = []
    raw_df = loaded.raw_df

    # 1. Detect header row
    header_idx = detect_header_row(raw_df, DOSETRACK_COLUMN_NAMES)

    # 2. Extract headers and data rows
    raw_headers = [str(c).strip() for c in raw_df.iloc[header_idx]]
    data_df = raw_df.iloc[header_idx + 1 :].copy()
    data_df.columns = pd.Index(raw_headers)
    data_df = data_df.reset_index(drop=True)

    # Drop wholly-empty rows
    data_df = data_df[~data_df.apply(lambda r: r.astype(str).str.strip().eq("").all(), axis=1)]

    # 3. Map column names → internal names (sentinel _dt_* keys included)
    column_map, mapping_warnings = map_columns(raw_headers, DOSETRACK_PATTERNS)
    warnings.extend(mapping_warnings)
    unmatched_msg = unmapped_columns_warning(raw_headers, column_map)
    if unmatched_msg:
        warnings.append(unmatched_msg)

    dup_errors = check_duplicate_mappings(column_map)
    if dup_errors:
        raise ValueError("\n".join(dup_errors))

    # 4. Rename all mapped columns (sentinels get their _dt_* name temporarily)
    rename = {src: tgt for src, tgt in column_map.items() if src in data_df.columns}
    data_df = data_df.rename(columns=rename)

    # 5. Forward-fill: DoseTrack uses hierarchical rows where parent values
    #    are only written when they change (study/series level fields).
    data_df = data_df.ffill()

    # 6. Infer Manufacturer/ManufacturerModelName from Equipment Name sentinel
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
        data_df = data_df.drop(columns=["_dt_equipment_name"])
    elif "Manufacturer" not in data_df.columns:
        raise ValueError(
            "DoseTrack adapter requires an 'Equipment Name' column to infer Manufacturer/Model. "
            "Column not found in the export."
        )

    # 7. Normalize AcquisitionPlane from integer Plane Code values
    if "AcquisitionPlane" in data_df.columns:
        try:
            data_df["AcquisitionPlane"] = _normalize_plane_code(data_df["AcquisitionPlane"])
        except ValueError as exc:
            raise ValueError(f"DoseTrack plane code normalization failed: {exc}") from exc

    # 8. Coerce numeric columns
    for col in _NUMERIC_COLUMNS:
        if col in data_df.columns:
            coerced = pd.to_numeric(data_df[col].astype(str).str.strip(), errors="coerce")
            n_bad = int(coerced.isna().sum()) - int(data_df[col].isna().sum())
            if n_bad > 0:
                warnings.append(
                    f"Column {col!r}: {n_bad} value(s) could not be parsed as numeric; set to NaN."
                )
            data_df[col] = coerced

    # Coerce DAP sentinel separately
    if "_dt_dap" in data_df.columns:
        data_df["_dt_dap"] = pd.to_numeric(data_df["_dt_dap"].astype(str).str.strip(), errors="coerce")

    # 9. Unit conversions
    unit_conversions: dict[str, str] = {}
    if "DoseRP_Gy" in data_df.columns:
        data_df["DoseRP_Gy"] = data_df["DoseRP_Gy"] / 1000.0
        unit_conversions["DoseRP_Gy"] = "mGy → Gy"
    if "XRayTubeCurrent_mA" in data_df.columns:
        data_df["XRayTubeCurrent_mA"] = data_df["XRayTubeCurrent_mA"] / 1000.0
        unit_conversions["XRayTubeCurrent_mA"] = "µA → mA"

    # Convert DAP Gy·cm² → Gy·m²
    if "_dt_dap" in data_df.columns:
        data_df["DoseAreaProduct_Gym2"] = data_df["_dt_dap"] / 10000.0
        unit_conversions["DoseAreaProduct_Gym2"] = "Gy·cm² → Gy·m² (from DAP column)"
        data_df = data_df.drop(columns=["_dt_dap"])

    # 10. Filter thickness handling
    manufacturer_val = str(data_df["Manufacturer"].dropna().iloc[0]) if "Manufacturer" in data_df.columns else ""
    is_philips = manufacturer_val.lower() == "philips"

    if "XRayFilterThicknessMinimum_mm" in data_df.columns:
        if is_philips:
            # Philips: semicolon-separated "Al_mm;Cu_mm" string
            def _parse_philips_filter(val: object) -> tuple[float, float]:
                parts = str(val).split(";")
                try:
                    if len(parts) >= 2:
                        return float(parts[0].strip()), float(parts[1].strip())
                    v = float(parts[0].strip())
                    return 0.0, v
                except (ValueError, TypeError):
                    return float("nan"), float("nan")

            pairs = data_df["XRayFilterThicknessMinimum_mm"].apply(_parse_philips_filter)
            data_df["XRayFilterThicknessMinimum_mm"] = pairs.apply(lambda x: x[0])  # Al
            data_df["XRayFilterThicknessMaximum_mm"] = pairs.apply(lambda x: x[1])  # Cu
            unit_conversions["XRayFilterThicknessMinimum_mm"] = "Philips Al;Cu split → Min=Al, Max=Cu"
        else:
            # Siemens: single Cu filter value; Maximum mirrors Minimum
            data_df["XRayFilterThicknessMaximum_mm"] = data_df["XRayFilterThicknessMinimum_mm"]

    # 11. Derive CollimatedFieldArea_m2 from DAP formula (matches reference implementation)
    #     CFA = DAP / (DoseRP * ((DSI - 150) / DSD)^2)
    if (
        "DoseAreaProduct_Gym2" in data_df.columns
        and "DoseRP_Gy" in data_df.columns
        and "DistanceSourcetoDetector_mm" in data_df.columns
        and "DistanceSourcetoIsocenter_mm" in data_df.columns
    ):
        dsd = data_df["DistanceSourcetoDetector_mm"]
        dsi = data_df["DistanceSourcetoIsocenter_mm"]
        data_df["CollimatedFieldArea_m2"] = data_df["DoseAreaProduct_Gym2"] / (
            data_df["DoseRP_Gy"] * ((dsi - 150) / dsd) ** 2
        )

    # 12. Fallback values for columns rdsr_normalizer() requires but DoseTrack may omit
    if "IrradiationEventType" not in data_df.columns:
        data_df["IrradiationEventType"] = "Fluoroscopy"
        warnings.append("Column 'IrradiationEventType' not in DoseTrack export; defaulted to 'Fluoroscopy'.")
    if "XRayFilterMaterial" not in data_df.columns:
        data_df["XRayFilterMaterial"] = "Cu"
        warnings.append("Column 'XRayFilterMaterial' not in DoseTrack export; defaulted to 'Cu'.")

    # 13. Check required columns before calling rdsr_normalizer()
    missing = REQUIRED_COLUMNS - set(data_df.columns)
    if missing:
        raise ValueError(
            f"Missing required column(s) for dosetrack schema: {sorted(missing)}. "
            f"Column map attempted: {column_map}."
        )

    # 14. Run rdsr_normalizer()
    try:
        normalized_df = rdsr_normalizer(data_df, settings)
    except Exception as exc:
        raise ValueError(f"rdsr_normalizer() failed on dosetrack input: {exc}") from exc

    # 16. Build provenance (exclude _dt_* sentinel keys from public column_map)
    public_column_map = {k: v for k, v in column_map.items() if not v.startswith("_dt_")}
    provenance = InputProvenance(
        source_type=Path(original_filename).suffix.lstrip(".").lower(),
        schema_name="dosetrack",
        original_filename=original_filename,
        header_row_index=header_idx,
        detected_encoding=loaded.encoding,
        detected_delimiter=loaded.delimiter,
        sheet_name=None,
        column_map=public_column_map,
        unit_conversions=unit_conversions,
        warnings=warnings,
    )

    return InputAdapterResult(
        normalized_data=normalized_df,
        raw_data=raw_df,
        provenance=provenance,
        warnings=warnings,
    )
