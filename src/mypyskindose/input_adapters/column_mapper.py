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
        "source detector distance",
    ],
    "DistanceSourcetoIsocenter_mm": [
        "distancesourcetoisocenter mm",
        "distance source to isocenter",
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
        "air kerma gy",
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
    """Fraction of non-empty cells whose lowercased, stripped value is in known_names."""
    cells = [str(c).strip().lower() for c in row if pd.notna(c) and str(c).strip()]
    if not cells:
        return 0.0
    return sum(1 for c in cells if c in known_names) / len(cells)


def detect_header_row(
    raw_df: pd.DataFrame,
    known_names: frozenset[str],
    n: int = 10,
    min_score: float = 0.25,
) -> int:
    """Return the index of the header row in *raw_df* (all rows, header=None).

    Scans the first *n* rows and picks the one whose cells best match *known_names*.
    Raises ValueError if no row clears *min_score*.
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
    """Return len(pattern) if *pattern* appears in *header_norm* with word boundaries, else 0.

    Word boundary = not preceded or followed by an alphanumeric character.
    This prevents "dose a" from matching inside "dose area product".
    """
    escaped = re.escape(pattern)
    rx = r"(?<![a-z0-9])" + escaped + r"(?![a-z0-9])"
    return len(pattern) if re.search(rx, header_norm) else 0


def map_columns(
    headers: list[str],
    patterns: dict[str, list[str]],
) -> tuple[dict[str, str], list[str]]:
    """Map source column headers to normalized variable names using best-match.

    For each source column the variable whose matched pattern is longest wins.
    If two variables tie with equal-length patterns, the column is skipped with
    a warning rather than mapping ambiguously.

    Returns (column_map, warnings).
    column_map: {source_col → normalized_var}
    """
    column_map: dict[str, str] = {}
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
            column_map[header] = best_var

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
