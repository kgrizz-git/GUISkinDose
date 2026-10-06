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

import re

import numpy as np
import pandas as pd

from guiskindose.input_adapters.base import (
    _UNIT_SPECS,
    DAP_INTERNAL_COL,
    FLUORO_TIME_COL,
    AdapterContext,
    _read_unit_factor,
    attach_procedure_dose_totals,
    coerce_numeric_columns,
    convert_dap_series_to_gym2,
    convert_field_with_header_units,
    run_normalizer_pipeline,
)
from guiskindose.input_adapters.models import InputAdapterResult
from guiskindose.input_adapters.tabular_loader import _RawLoad
from guiskindose.settings import PyskindoseSettings
from guiskindose.settings.normalization_settings import normalize_manufacturer_key

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
        "equipment",
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
# Equipment = room/unit identity (CF key); Device = model. Do not collapse them.
RADIMETRICS_PATTERNS: dict[str, list[str]] = {
    "Manufacturer": ["manufacturer", "vendor"],
    "ManufacturerModelName": ["device model", "device"],
    "StationName": ["equipment"],
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

# Per-plane columns of a biplane export (header text after separator folding), e.g.
# "Reference Point Dose (A) mGy" / "Reference_Point_Dose_(B)_mGy" / "DAP (A) Gy-cm2".
_PER_PLANE_DOSE_RE = re.compile(r"^reference point dose ([ab])(?: |$)")
_PER_PLANE_DAP_RE = re.compile(r"^dap ([ab])(?: |$)")
# A + B kerma must reproduce the exported total to within this relative tolerance
# (export rounding); rows that disagree are not split.
_SPLIT_RTOL = 0.01
_PLANE_MEANING = {"A": "Plane A", "B": "Plane B"}

_KNOWN_MODELS = {"AXIOM-Artis", "Artis", "Artis Q", "Artis Zee"}
_GE_VARIANTS = {"ge medical systems", "ge healthcare", "general electric", "ge", "gems"}


def _per_plane_columns(columns: list[str], pattern: re.Pattern[str]) -> dict[str, str]:
    """Map plane letter (``"A"``/``"B"``) to the raw header that matches *pattern*.

    Parameters
    ----------
    columns : list[str]
        Column names of the renamed Radimetrics DataFrame.
    pattern : re.Pattern[str]
        Regex applied to each header after lowercasing and folding every run of
        non-alphanumeric characters to one space.

    Returns
    -------
    dict[str, str]
        ``{"A": header, "B": header}`` for the planes found (first match wins).
    """
    found: dict[str, str] = {}
    for col in columns:
        match = pattern.match(re.sub(r"[^a-z0-9]+", " ", str(col).lower()).strip())
        if match:
            found.setdefault(match.group(1).upper(), col)
    return found


def _per_plane_kerma_gy(data_df: pd.DataFrame, dose_cols: dict[str, str]) -> dict[str, pd.Series]:
    """Return per-plane reference-point kerma in Gy, unit read from each header."""
    out: dict[str, pd.Series] = {}
    for plane, col in dose_cols.items():
        factor, _confident, _unit = _read_unit_factor(col, _UNIT_SPECS["dose"])
        out[plane] = pd.to_numeric(data_df[col], errors="coerce") * factor
    return out


def _splittable_mask(total: pd.Series, a: pd.Series, b: pd.Series) -> pd.Series:
    """True where A and B kerma are valid and sum to the total within tolerance."""
    valid = a.notna() & b.notna() & (a >= 0) & (b >= 0) & ((a + b) > 0)
    consistent = pd.Series(np.isclose(a + b, total, rtol=_SPLIT_RTOL, atol=1e-12), index=total.index)
    return valid & consistent & total.notna()


def _has_text(series: pd.Series) -> pd.Series:
    """True where *series* holds a non-blank, non-null value."""
    return series.notna() & series.astype(str).str.strip().ne("")


def _kept_plane_codes(series: pd.Series) -> pd.Series:
    """Keep recognised plane codes (``Plane A`` / ``Plane B`` / ``Single Plane``); others become None."""
    from guiskindose.kerma_correction import normalize_tube

    recognised = series.map(lambda v: normalize_tube(v) != "unknown")
    return series.where(recognised, other=None)


def _plane_events(
    data_df: pd.DataFrame,
    plane: str,
    kerma: dict[str, pd.Series],
    total: pd.Series,
    mask: pd.Series,
    dap_per_plane: dict[str, pd.Series],
) -> pd.DataFrame:
    """Build the events of one plane from the splittable rows of *data_df*.

    Kerma is rescaled so the A and B parts add up exactly to the exported total.
    DAP comes from the per-plane DAP column when present, otherwise the total DAP
    is shared in proportion to kerma. Fluoro time stays on the first emitted
    plane of a row so procedure totals are not double counted.
    """
    emitted = mask & (kerma[plane] > 0)
    # Divide only on splittable rows so zero or missing rows never produce
    # inf/nan or a RuntimeWarning.
    scale = pd.Series(0.0, index=data_df.index)
    scale[mask] = total[mask] / (kerma["A"][mask] + kerma["B"][mask])
    share = pd.Series(0.0, index=data_df.index)
    share[mask] = kerma[plane][mask] * scale[mask] / total[mask]
    part = data_df[emitted].copy()
    part["DoseRP_Gy"] = (kerma[plane] * scale)[emitted]
    part["AcquisitionPlane"] = _PLANE_MEANING[plane]
    if plane in dap_per_plane:
        part[DAP_INTERNAL_COL] = dap_per_plane[plane][emitted]
    elif DAP_INTERNAL_COL in data_df.columns:
        part[DAP_INTERNAL_COL] = (data_df[DAP_INTERNAL_COL] * share)[emitted]
    if plane == "B" and FLUORO_TIME_COL in part.columns:
        also_a = (mask & (kerma["A"] > 0))[emitted]
        part.loc[also_a, FLUORO_TIME_COL] = np.nan
    return part


def split_biplane_events(data_df: pd.DataFrame, ctx: AdapterContext) -> tuple[pd.DataFrame, bool]:
    """Split Radimetrics total-kerma rows into separate tube A and tube B events.

    A biplane export lists one row per irradiation event with the reference-point
    dose of the whole event (``Reference Point Dose (Total)``) plus per-plane
    columns (``Reference Point Dose (A)`` / ``(B)``). Reading only the total hides
    which tube produced the dose. When both per-plane columns exist and at least
    one row has non-zero plane B kerma, each splittable row is *replaced* by up
    to two events (``Plane A``, ``Plane B``); a row with kerma on one plane only
    becomes a single event of that plane. A file whose plane B column is all
    zero or empty is not treated as biplane. Kerma is rescaled to the
    exported total, so A + B equals the original total and nothing is added on top
    of it. Rows whose per-plane kerma is missing or disagrees with the total
    beyond ``_SPLIT_RTOL`` stay as one total row. They keep a valid explicit
    plane code from the export (``Plane A`` / ``Plane B`` / ``Single Plane``);
    with no valid code the plane is unknown.

    Per-plane DAP columns (``DAP (A)`` / ``(B)``) are used when present; otherwise
    each event receives the total DAP in proportion to its kerma.

    Parameters
    ----------
    data_df : pd.DataFrame
        Renamed frame after unit conversion and ``attach_procedure_dose_totals``.
    ctx : AdapterContext
        Receives a warning describing the split (counts only).

    Returns
    -------
    tuple[pd.DataFrame, bool]
        The (possibly expanded) frame and whether biplane evidence was found. When
        ``False`` the frame is returned unchanged and callers keep the legacy
        single-plane default.
    """
    dose_cols = _per_plane_columns(list(data_df.columns), _PER_PLANE_DOSE_RE)
    if set(dose_cols) != {"A", "B"} or "DoseRP_Gy" not in data_df.columns:
        return data_df, False
    kerma = _per_plane_kerma_gy(data_df, dose_cols)
    # An empty cell on one plane next to a value on the other means "no dose on
    # that plane"; a row with both empty stays missing (unsplittable).
    any_value = kerma["A"].notna() | kerma["B"].notna()
    kerma = {p: values.mask(values.isna() & any_value, 0.0) for p, values in kerma.items()}
    if not bool((kerma["B"] > 0).any()):
        return data_df, False

    total = pd.to_numeric(data_df["DoseRP_Gy"], errors="coerce")
    mask = _splittable_mask(total, kerma["A"], kerma["B"])
    dap_cols = _per_plane_columns(list(data_df.columns), _PER_PLANE_DAP_RE)
    dap_per_plane = (
        {p: convert_dap_series_to_gym2(data_df[c], c, ctx) for p, c in dap_cols.items()}
        if set(dap_cols) == {"A", "B"}
        else {}
    )
    order = pd.Series(np.arange(len(data_df)) * 2, index=data_df.index)
    rest = data_df[~mask].copy()
    explicit = data_df["AcquisitionPlane"] if "AcquisitionPlane" in data_df.columns else None
    rest["AcquisitionPlane"] = _kept_plane_codes(rest["AcquisitionPlane"]) if explicit is not None else None
    n_overwritten = 0 if explicit is None else int((_has_text(explicit) & mask).sum())
    frames = [rest.assign(_sort_key=order[rest.index])]
    for offset, plane in enumerate(("A", "B")):
        part = _plane_events(data_df, plane, kerma, total, mask, dap_per_plane)
        frames.append(part.assign(_sort_key=order[part.index] + offset))
    out = pd.concat(frames).sort_values("_sort_key", kind="stable")
    out = out.drop(columns="_sort_key").reset_index(drop=True)
    n_unsplit = int((~mask).sum())
    message = (
        f"Radimetrics biplane export: split {int(mask.sum())} event(s) into plane A/B events using the "
        f"per-plane reference-point dose columns; {n_unsplit} event(s) kept as one total row (plane taken "
        "from the export when valid, otherwise unknown). Positioner angles, kVp and table positions come "
        "from the single (RF) columns and are shared by both planes."
    )
    if n_overwritten:
        message += f" {n_overwritten} split event(s) replaced a plane code present in the export."
    ctx.warnings.append(message)
    return out, True


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
                "positions in the opposite convention to GUISkinDose. "
                "The normalization layer applies the GE lateral/longitudinal correction; "
                "do not also enable the GUI swap unless validating a site-specific export."
            )

    # Biplane exports: replace each total-kerma row by per-plane A/B events. DAP /
    # fluoro time are derived first so the split can apportion them per event.
    attach_procedure_dose_totals(data_df, ctx)
    data_df, is_biplane = split_biplane_events(data_df, ctx)

    # Radimetrics exports may omit these; rdsr_normalizer accepts the defaults. A
    # missing plane column is only defaulted to "Single Plane" when there is no
    # biplane evidence; otherwise the split has already assigned plane identity.
    defaults = [("IrradiationEventType", "Fluoroscopy")]
    if not is_biplane:
        defaults.append(("AcquisitionPlane", "Single Plane"))
    for col, default in defaults:
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
