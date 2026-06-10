"""Column mapping infrastructure for tabular input adapters.

Phase 1: provides NORMALIZED_COLUMN_NAMES and detect_header_row for the
normalized schema (near-exact name matching).

Phase 2+: COLUMN_PATTERNS and map_columns provide word-boundary fuzzy
matching for raw vendor exports.
"""

from __future__ import annotations

import re

import pandas as pd

# ── Normalized schema ──────────────────────────────────────────────────────────

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
}

# Columns that must be present; all others are also required but separated for
# clarity if optional columns are added later.
NORMALIZED_REQUIRED_COLUMNS: frozenset[str] = NORMALIZED_COLUMN_NAMES

# ── Generic raw-RDSR-like schema (Phase 2) ────────────────────────────────────

# Lowercase versions of key rdsr_parser() output column names.
# Used by detect_header_row() for score-based header location.
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


# ── Radimetrics schema (Phase 3) ──────────────────────────────────────────────
#
# Lowercase versions of key Radimetrics export column headers.
# Used by detect_header_row() for score-based header location.
# Source: dhen2714/PySkinDose RADIMETRICS2PSD dict (dev-docs/references/).
RADIMETRICS_COLUMN_NAMES: frozenset[str] = frozenset(
    {
        "manufacturer",
        "device",
        "kvp kv",
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
    }
)

# Maps rdsr_parser() column name → Radimetrics header patterns (lowercase).
# Keys are the exact names rdsr_normalizer() expects.
RADIMETRICS_PATTERNS: dict[str, list[str]] = {
    "Manufacturer": ["manufacturer", "vendor"],
    "ManufacturerModelName": ["device", "device model", "equipment name"],
    "AcquisitionPlane": ["acquisition plane code", "acquisition plane"],
    "IrradiationEventType": ["irradiation event type"],
    "PositionerPrimaryAngle_deg": ["primary angle (rf)", "primary angle"],
    "PositionerSecondaryAngle_deg": ["secondary angle (rf)", "secondary angle"],
    # "kvp kv" only — bare "kvp" would also match per-plane "kVp (A) kV", "kVp (B) kV"
    "KVP_kV": ["kvp kv"],
    # "(total)" required — prevents matching per-plane "Reference Point Dose (A/B) mGy"
    "DoseRP_Gy": [
        "reference point dose (total) mgy",
        "reference point dose (total)",
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


# ── Vendor-schema pattern dictionary (Phase 2+) ────────────────────────────────
#
# Maps normalized internal variable name → list of lowercase patterns.
# Matching is word-boundary aware and best-match (longest pattern wins).
# See §Column mapping architecture in TABULAR_RDSR_INPUT_PLAN.md for rules.
#
# IMPORTANT: patterns must not use bare short tokens that collide.
# E.g. "dose a" must NOT match "dose area product" — word-boundary matching
# prevents this (after "dose a" comes "r" which is alphanumeric → no match).
# Use the most specific / longest patterns available.
COLUMN_PATTERNS: dict[str, list[str]] = {
    "manufacturer": ["manufacturer", "vendor", "make"],
    "model": ["device model", "station name", "model"],
    "primary_angle": ["positioner primary angle", "primary angle", "c-arm primary"],
    "secondary_angle": ["positioner secondary angle", "secondary angle", "c-arm secondary"],
    "table_lateral": ["table lateral", "lateral position", "table pos lat"],
    "table_longitudinal": ["table longitudinal", "longitudinal position", "table pos long"],
    "table_height": ["table height", "cradle height", "table pos height"],
    "kvp": ["kvp", "tube voltage"],  # bare "kv" excluded — too short/ambiguous
    "reference_dose_total": ["reference point dose", "dose area product", "air kerma", "kap"],
    "reference_dose_a": ["tube a dose", "reference dose a", "dose tube a", "dose a"],
    "reference_dose_b": ["tube b dose", "reference dose b", "dose tube b"],
}


# ── Header-row detection ───────────────────────────────────────────────────────


def _score_row(row: pd.Series, known_names: frozenset[str]) -> float:
    """Fraction of non-empty cells whose normalized value is in known_names.

    Uses _normalize_str so underscore/hyphen variants match space-separated names.
    """
    cells = [_normalize_str(str(c)) for c in row if pd.notna(c) and str(c).strip()]
    if not cells:
        return 0.0
    return sum(1 for c in cells if c in known_names) / len(cells)


def detect_header_row(
    raw_df: pd.DataFrame,
    known_names: frozenset[str],
    n: int = 10,
    min_score: float = 0.05,
) -> int:
    """Return the index of the header row in *raw_df* (all rows, header=None).

    Scans the first *n* rows and picks the one whose cells best match *known_names*.
    The default min_score of 0.05 is intentionally low — it is only a sanity check
    that the best candidate row has at least a few recognizable column names.  Do
    NOT use this threshold as a validation gate: file-wide column coverage is
    irrelevant when the export has many columns we don't need.  Adapter-level
    validation should check that required columns are present *after* mapping.

    Raises ValueError only if no row in the first *n* rows clears *min_score*.
    """
    best_idx = -1
    best_score = 0.0

    for i in range(min(n, len(raw_df))):
        score = _score_row(raw_df.iloc[i], known_names)
        if score > best_score:
            best_score = score
            best_idx = i

    if best_idx == -1 or best_score < min_score:
        raise ValueError(
            f"Could not locate a header row in the first {n} rows "
            f"(best match score {best_score:.2f}, minimum required {min_score:.2f}). "
            "Verify the file contains column names matching the expected schema."
        )

    return best_idx


# ── Vendor-schema fuzzy mapping (Phase 2+) ────────────────────────────────────


def _normalize_str(s: str) -> str:
    """Lowercase, collapse whitespace/underscores/hyphens to single space, strip."""
    return re.sub(r"[\s_\-]+", " ", s.strip().lower())


def _match_score(header_norm: str, pattern: str) -> int:
    """Return a coverage score if *pattern* appears in *header_norm* with word boundaries.

    Score = 2 * len(pattern) - len(header_norm).  This penalises matching a short
    pattern inside a much longer header, so "mAs mAs" scores higher than
    "Max mAs mAs" for the pattern "mas mas".  Any match yields at least 1.

    Word boundary = not preceded or followed by an alphanumeric character.
    This prevents "dose a" from matching inside "dose area product".
    """
    escaped = re.escape(pattern)
    rx = r"(?<![a-z0-9])" + escaped + r"(?![a-z0-9])"
    if not re.search(rx, header_norm):
        return 0
    return max(1, 2 * len(pattern) - len(header_norm))


def map_columns(
    headers: list[str],
    patterns: dict[str, list[str]],
) -> tuple[dict[str, str], list[str]]:
    """Map source column headers to normalized variable names using best-match.

    For each source column the variable whose matched pattern scores highest wins
    (score = 2*len(pattern) - len(header), favouring full-header matches).
    If two variables tie, the column is skipped with a warning.

    When multiple source columns map to the same target variable, the one with
    the highest coverage score is kept and the rest are dropped with a warning.
    This handles exports that include per-plane variants (e.g. "mAs mAs" vs
    "Max mAs mAs") alongside the total-column we actually want.

    Returns (column_map, warnings).
    column_map: {source_col → normalized_var}
    """
    # Pass 1: find the best variable for each source column, tracking score.
    raw_map: dict[str, tuple[str, int]] = {}  # src_col → (best_var, best_score)
    warnings: list[str] = []

    for header in headers:
        header_norm = _normalize_str(header)
        best_var: str | None = None
        best_score: int = 0
        tie: bool = False

        for var_name, var_patterns in patterns.items():
            for pattern in var_patterns:
                score = _match_score(header_norm, pattern)
                if score > best_score:
                    best_score = score
                    best_var = var_name
                    tie = False
                elif score == best_score and score > 0 and var_name != best_var:
                    tie = True

        if tie:
            warnings.append(
                f"Column {header!r} matched multiple variables with equal confidence; "
                "skipping — pass an explicit column override to resolve."
            )
        elif best_var is not None:
            raw_map[header] = (best_var, best_score)

    # Pass 2: resolve duplicates — multiple source columns → same target variable.
    # Keep the one with the highest score; drop the rest with a warning.
    target_to_candidates: dict[str, list[tuple[str, int]]] = {}
    for src, (tgt, score) in raw_map.items():
        target_to_candidates.setdefault(tgt, []).append((src, score))

    column_map: dict[str, str] = {}
    for tgt, candidates in target_to_candidates.items():
        if len(candidates) == 1:
            column_map[candidates[0][0]] = tgt
        else:
            sorted_cands = sorted(candidates, key=lambda x: (-x[1], len(x[0])))
            winner, _ = sorted_cands[0]
            losers = [c[0] for c in sorted_cands[1:]]
            column_map[winner] = tgt
            warnings.append(
                f"Multiple source columns mapped to {tgt!r}: "
                f"kept {winner!r} (best coverage), dropped {losers}. "
                "If this is wrong, pass an explicit column override."
            )

    return column_map, warnings


def check_duplicate_mappings(column_map: dict[str, str]) -> list[str]:
    """Return error messages for any normalized variable claimed by >1 source column."""
    seen: dict[str, list[str]] = {}
    for src_col, norm_var in column_map.items():
        seen.setdefault(norm_var, []).append(src_col)

    errors: list[str] = []
    for norm_var, src_cols in seen.items():
        if len(src_cols) > 1:
            errors.append(
                f"Duplicate mapping: columns {src_cols} all map to {norm_var!r}. "
                "Pass an explicit column override to resolve."
            )
    return errors


def unmapped_columns_warning(headers: list[str], column_map: dict[str, str]) -> str | None:
    """Return a warning string if any source columns could not be mapped, else None.

    This is informational — unmapped columns are not an error unless they contain
    a required variable.  The caller is responsible for the required-column check.
    """
    unmapped = [h for h in headers if h not in column_map]
    if not unmapped:
        return None
    return (
        f"{len(unmapped)} of {len(headers)} source column(s) were not mapped to any known variable "
        f"and will be ignored: {unmapped[:10]}{'...' if len(unmapped) > 10 else ''}."
    )
