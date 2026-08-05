"""Column mapping engine for tabular input adapters.

Provides the schema-agnostic machinery used by every adapter:

* ``detect_header_row`` — score-based header-row location
* ``map_columns`` — word-boundary, best-match fuzzy mapping of source headers
  to internal column names
* ``check_duplicate_mappings`` / ``unmapped_columns_warning`` — validation helpers

The per-vendor column-name sets and pattern dictionaries live in their adapter
modules (``normalized.py``, ``generic_rdsr.py``, ``radimetrics.py``,
``dosetrack.py``). ``COLUMN_PATTERNS`` below is a generic example dictionary used
to exercise the matching engine in tests.
"""

from __future__ import annotations

import re

import pandas as pd

# ── Generic example pattern dictionary (engine test fixture) ───────────────────
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


def _score_row(row: pd.Series, known_names: frozenset[str]) -> int:
    """Number of non-empty cells whose normalized value is in known_names.

    Returns an absolute hit count so header detection is robust regardless of
    how many extra columns the export contains.  Both cells and known_names are
    normalized with _normalize_str so underscore, hyphen, and space variants all
    compare equal (e.g. "KVP_kV", "kvp kv", "KVP kV" all normalize to "kvp kv").
    """
    normalized_known = frozenset(_normalize_str(n) for n in known_names)
    cells = [_normalize_str(str(c)) for c in row if pd.notna(c) and str(c).strip()]
    return sum(1 for c in cells if c in normalized_known)


def detect_header_row(
    raw_df: pd.DataFrame,
    known_names: frozenset[str],
    n: int = 10,
    min_score: float = 5,
) -> int:
    """Return the index of the header row in *raw_df* (all rows, header=None).

    Scans the first *n* rows and picks the one with the most cells matching
    *known_names*.  The threshold *min_score* is an **absolute hit count** — the
    default of 5 means the best candidate row must contain at least 5 recognized
    column names.  Scale-independent: an export with 300 columns and 15 known
    names scores 15 regardless of the 285 extra columns, so large exports never
    fail here just because they carry many columns the adapter doesn't use.

    This function only locates the header row.  Required-column validation (did
    we find the columns the adapter actually needs?) is the adapter's
    responsibility, performed after column mapping.

    Raises ValueError only if no row in the first *n* rows reaches *min_score* hits.
    """
    best_idx = -1
    best_score = 0

    for i in range(min(n, len(raw_df))):
        score = _score_row(raw_df.iloc[i], known_names)
        if score > best_score:
            best_score = score
            best_idx = i

    if best_idx == -1 or best_score < min_score:
        raise ValueError(
            f"Could not locate a header row in the first {n} rows "
            f"(best row matched {best_score} known column name(s), minimum required {int(min_score)}). "
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
    warnings: list[str] = []
    raw_map = _best_matches(headers, patterns, warnings)
    column_map = _resolve_duplicate_matches(raw_map, warnings)
    return column_map, warnings


def _best_matches(
    headers: list[str], patterns: dict[str, list[str]], warnings: list[str]
) -> dict[str, tuple[str, int]]:
    """Return each unambiguous header's highest-scoring normalized variable."""
    raw_map: dict[str, tuple[str, int]] = {}
    for header in headers:
        best_var, best_score, tie = _best_variable(_normalize_str(header), patterns)
        if tie:
            warnings.append(
                f"Column {header!r} matched multiple variables with equal confidence; "
                "skipping — pass an explicit column override to resolve."
            )
        elif best_var is not None:
            raw_map[header] = (best_var, best_score)
    return raw_map


def _best_variable(header_norm: str, patterns: dict[str, list[str]]) -> tuple[str | None, int, bool]:
    """Return the best mapping candidate and whether an equal-score tie occurred."""
    best_var: str | None = None
    best_score = 0
    tie = False
    for var_name, var_patterns in patterns.items():
        for pattern in var_patterns:
            score = _match_score(header_norm, pattern)
            if score > best_score:
                best_var, best_score, tie = var_name, score, False
            elif score == best_score and score > 0 and var_name != best_var:
                tie = True
    return best_var, best_score, tie

def _resolve_duplicate_matches(
    raw_map: dict[str, tuple[str, int]], warnings: list[str]
) -> dict[str, str]:
    """Retain the best source header for each normalized target variable."""
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

    return column_map


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
