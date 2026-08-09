"""Shared pipeline for rdsr_normalizer-bound tabular adapters.

The `generic_rdsr_like`, `radimetrics`, and `dosetrack` adapters all follow the
same skeleton:

    detect header → extract table → drop empty rows → map columns →
    duplicate-mapping check → rename → [vendor transform] →
    required-columns check → rdsr_normalizer() → build provenance/result

Only the *vendor transform* (numeric coercion, unit conversions, manufacturer
inference, etc.) and a handful of constants differ. `run_normalizer_pipeline`
owns the shared skeleton; each adapter supplies its known-names, patterns,
required-columns set, and a `transform` callback.

The `normalized` schema does not use this pipeline — it matches columns exactly
(case-insensitive), performs a multi-procedure check, and skips
rdsr_normalizer() entirely.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd

from mypyskindose.input_adapters.column_mapper import (
    check_duplicate_mappings,
    detect_header_row,
    map_columns,
    unmapped_columns_warning,
)
from mypyskindose.input_adapters.models import InputAdapterResult, InputProvenance
from mypyskindose.input_adapters.tabular_loader import _RawLoad
from mypyskindose.privacy import exception_class_name

if TYPE_CHECKING:
    from mypyskindose.settings import PyskindoseSettings


@dataclass
class AdapterContext:
    """Mutable working state handed to a vendor transform.

    The transform reads ``column_map``/``settings`` and may append to
    ``warnings`` and ``unit_conversions``; the pipeline picks both up afterwards
    for the provenance record.
    """

    column_map: dict[str, str]
    raw_headers: list[str]
    settings: PyskindoseSettings | None
    warnings: list[str]
    unit_conversions: dict[str, str] = field(default_factory=dict)


# A vendor transform takes the renamed DataFrame plus context and returns the
# DataFrame ready for rdsr_normalizer(). It may add/drop/coerce columns.
TransformFn = Callable[[pd.DataFrame, AdapterContext], pd.DataFrame]


def extract_table(raw_df: pd.DataFrame, header_idx: int) -> tuple[list[str], pd.DataFrame]:
    """Return (headers, data) for the table starting at *header_idx*.

    Headers are stripped strings; data has those headers as columns, the index
    reset, and wholly-empty rows dropped.
    """
    raw_headers = [str(c).strip() for c in raw_df.iloc[header_idx]]
    data_df = raw_df.iloc[header_idx + 1 :].copy()
    data_df.columns = pd.Index(raw_headers)
    data_df = data_df.reset_index(drop=True)
    data_df = data_df[~data_df.apply(lambda r: r.astype(str).str.strip().eq("").all(), axis=1)]
    return raw_headers, data_df


def coerce_numeric_columns(
    data_df: pd.DataFrame,
    numeric_columns: frozenset[str],
    warnings: list[str],
) -> None:
    """Coerce present numeric columns in place; warn on values set to NaN."""
    for col in numeric_columns:
        if col in data_df.columns:
            coerced = pd.to_numeric(data_df[col].astype(str).str.strip(), errors="coerce")
            n_bad = int(coerced.isna().sum()) - int(data_df[col].isna().sum())
            if n_bad > 0:
                warnings.append(
                    f"Column {col!r}: {n_bad} value(s) could not be parsed as numeric; set to NaN."
                )
            data_df[col] = coerced


# ── Procedure dose totals (DAP + fluoro time) ─────────────────────────────────
#
# Internal column names carried onto the normalized DataFrame so the export /
# results layers can sum them into procedure totals. ``DoseAreaProduct_Gym2``
# holds per-event DAP in Gy·m²; ``fluoro_time_s`` holds per-event fluoro time in
# seconds (NaN on non-fluoro events, so summing skips them).
DAP_INTERNAL_COL = "DoseAreaProduct_Gym2"
FLUORO_TIME_COL = "fluoro_time_s"

# Passed through rdsr_normalizer() (which builds a fresh frame) by copying from
# the pre-normalization DataFrame in run_normalizer_pipeline().
_PASSTHROUGH_DOSE_COLS = (DAP_INTERNAL_COL, FLUORO_TIME_COL)


def _norm_header(header: object) -> str:
    return re.sub(r"\s+", " ", str(header).strip().lower())


def _find_dap_total_column(columns: list[str]) -> str | None:
    """Locate the per-event *total* DAP column (both planes), excluding the
    fluoro-only DAP subset column (``Fluoro DAP (Total)``)."""
    for col in columns:
        n = _norm_header(col)
        if "dap" in n and "fluoro" not in n and "(total)" in n:
            return col
    # Fall back to a bare "dap" column (no per-plane split) but still skip fluoro.
    for col in columns:
        n = _norm_header(col)
        if "dap" in n and "fluoro" not in n and "(a)" not in n and "(b)" not in n:
            return col
    return None


def _find_fluoro_time_total_column(columns: list[str]) -> str | None:
    """Locate the per-event *total* fluoro time column (both planes)."""
    for col in columns:
        n = _norm_header(col)
        if "fluoro time" in n and "(total)" in n:
            return col
    return None


def _dap_to_gym2(header: str) -> tuple[float, bool, str | None]:
    """Return (factor_to_Gy·m², units_confident, canonical_unit) for a DAP header.

    Units are read from the header text. Recognised spellings are converted with
    confidence; an unrecognised unit is assumed to be Gy·cm² (the near-universal
    vendor default) but flagged so the operator can verify.
    """
    u = re.sub(r"\s+", " ", _norm_header(header).replace("·", " ").replace("*", " ").replace("-", " ").replace("^", ""))
    # Check cm² before m² ("m2" is a substring of "cm2").
    if "ugy cm2" in u or "µgy cm2" in u:
        return (1e-6 / 1e4, True, "µGy·cm²")
    if "mgy cm2" in u:
        return (1e-3 / 1e4, True, "mGy·cm²")
    if "cgy cm2" in u:
        return (1e-2 / 1e4, True, "cGy·cm²")
    if "gy cm2" in u or "gycm2" in u:
        return (1.0 / 1e4, True, "Gy·cm²")
    if "ugy m2" in u or "µgy m2" in u:
        return (1e-6, True, "µGy·m²")
    if "gy m2" in u or "gym2" in u:
        return (1.0, True, "Gy·m²")
    return (1.0 / 1e4, False, None)


def _fluoro_to_seconds(header: str) -> tuple[float, bool]:
    """Return (factor_to_seconds, units_confident) for a fluoro-time header."""
    n = _norm_header(header)
    if "ms" in n or "millisec" in n:
        return (1e-3, True)
    if "min" in n:
        return (60.0, True)
    if re.search(r"(\bs\b|\(s\)|\[s\]|sec)", n):
        return (1.0, True)
    return (1e-3, False)  # fluoro time is almost always exported in ms


def convert_dap_series_to_gym2(
    values: pd.Series, source_header: str | None, ctx: AdapterContext
) -> pd.Series:
    """Convert a DAP column to internal ``Gy·m²`` using the *source header* units.

    The unit is read from ``source_header`` (the vendor's original column name);
    a confident interpretation is recorded in ``ctx.unit_conversions``, and an
    unconfirmable unit is assumed to be Gy·cm² **and flagged** in ``ctx.warnings``
    so no silent assumption reaches the report. Shared by the generic capture
    helper and vendor adapters (e.g. DoseTrack) so unit handling is uniform.
    """
    factor, confident, unit = _dap_to_gym2(source_header or "")
    if confident:
        ctx.unit_conversions[DAP_INTERNAL_COL] = f"{unit} → Gy·m² (from {source_header!r})"
    else:
        ctx.warnings.append(
            f"DAP read from column {source_header!r}, but its units could not be confirmed; "
            "assuming Gy·cm². Verify the reported DAP before clinical use."
        )
    return pd.to_numeric(values, errors="coerce") * factor


# ── Generalized per-field header-unit conversion ──────────────────────────────
#
# DAP and fluoro time (above) already read their unit from the vendor header.
# The same idea generalizes to the other convertible quantities: rather than
# assume a fixed source unit, read the unit token from the column's original
# header and convert to the internal unit, recording a confident interpretation
# in ``ctx.unit_conversions`` and flagging (``ctx.warnings``) when the token
# cannot be read so no silent assumption reaches the report. See
# dev-docs/INPUT_SCHEMA_DETECTION.md ("Unit handling").


@dataclass(frozen=True)
class _UnitSpec:
    """Unit table for one physical quantity.

    ``tokens`` maps recognised unit spellings to ``(factor_to_internal, canonical
    label)`` and is tried in order, so a compound token (``cm2``) precedes its
    substring (``m2``). ``default_*`` is the assumed unit when no token is
    readable; ``warn_on_default`` flags that assumption for quantities whose unit
    genuinely varies between vendors (dose, area, current, exposure) but stays
    quiet for near-universal defaults (distance / table position in mm).
    """

    internal: str
    tokens: tuple[tuple[str, float, str], ...]
    default_factor: float
    default_unit: str
    warn_on_default: bool


# Keyed by a semantic quantity name used at the call site. ``distance`` also
# covers the table-position columns (all internal-mm).
_UNIT_SPECS: dict[str, _UnitSpec] = {
    "dose": _UnitSpec(
        internal="Gy",
        tokens=(("ugy", 1e-6, "µGy"), ("mgy", 1e-3, "mGy"), ("cgy", 1e-2, "cGy"), ("gy", 1.0, "Gy")),
        default_factor=1e-3,
        default_unit="mGy",
        warn_on_default=True,
    ),
    "distance": _UnitSpec(
        internal="mm",
        tokens=(("mm", 1.0, "mm"), ("cm", 10.0, "cm")),
        default_factor=1.0,
        default_unit="mm",
        warn_on_default=False,
    ),
    "area": _UnitSpec(
        internal="m²",
        tokens=(("cm2", 1e-4, "cm²"), ("m2", 1.0, "m²")),
        default_factor=1e-4,
        default_unit="cm²",
        warn_on_default=True,
    ),
    "tube_current": _UnitSpec(
        internal="mA",
        tokens=(("ua", 1e-3, "µA"), ("ma", 1.0, "mA")),
        default_factor=1e-3,
        default_unit="µA",
        warn_on_default=True,
    ),
    "exposure": _UnitSpec(
        internal="µAs",
        tokens=(("mas", 1e3, "mAs"), ("uas", 1.0, "µAs")),
        default_factor=1e3,
        default_unit="mAs",
        warn_on_default=True,
    ),
}


def _normalize_unit_text(header: str) -> str:
    """Lowercase, fold µ/μ→u and ²/^2→2, and reduce separators to single spaces."""
    u = str(header).lower().replace("µ", "u").replace("μ", "u").replace("²", "2").replace("^2", "2")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", u)).strip()


def _read_unit_factor(header: str, spec: _UnitSpec) -> tuple[float, bool, str]:
    """Return ``(factor_to_internal, units_confident, unit_label)`` for *header*.

    Tokens are matched on word boundaries so ``ma`` does not match inside
    ``mas`` and ``m2`` does not match inside ``cm2``. An unreadable header falls
    back to the quantity's vendor default (``units_confident=False``).
    """
    text = _normalize_unit_text(header)
    for token, factor, label in spec.tokens:
        if re.search(r"(?<![a-z0-9])" + re.escape(token) + r"(?![a-z0-9])", text):
            return factor, True, label
    return spec.default_factor, False, spec.default_unit


def source_header_for(ctx: AdapterContext, target_col: str) -> str | None:
    """Return the original vendor header that mapped to ``target_col`` (or None)."""
    return next((src for src, tgt in ctx.column_map.items() if tgt == target_col), None)


def convert_field_with_header_units(
    data_df: pd.DataFrame,
    target_col: str,
    kind: str,
    ctx: AdapterContext,
) -> None:
    """Convert ``data_df[target_col]`` to its internal unit using the unit token
    read from the column's original vendor header (via ``ctx.column_map``).

    A confident read is recorded in ``ctx.unit_conversions``; an unreadable token
    falls back to the quantity's vendor-default factor and — for quantities whose
    unit genuinely varies between vendors — is flagged in ``ctx.warnings`` so no
    silent assumption reaches the report. No-ops if the column is absent. Mirrors
    :func:`convert_dap_series_to_gym2`, which handles the DAP special case.
    """
    if target_col not in data_df.columns:
        return
    spec = _UNIT_SPECS[kind]
    source_header = source_header_for(ctx, target_col)
    factor, confident, unit = _read_unit_factor(source_header or "", spec)
    data_df[target_col] = pd.to_numeric(data_df[target_col], errors="coerce") * factor
    if confident:
        ctx.unit_conversions[target_col] = f"{unit} → {spec.internal} (from {source_header!r})"
    elif spec.warn_on_default:
        ctx.warnings.append(
            f"{target_col}: units could not be read from column {source_header!r}; "
            f"assuming {spec.default_unit}. Verify the value before clinical use."
        )


def attach_procedure_dose_totals(data_df: pd.DataFrame, ctx: AdapterContext) -> None:
    """Derive per-event DAP (Gy·m²) and fluoro time (s) columns in place.

    Reads the vendor *total* (both-plane) DAP and fluoro-time columns, converts
    them to internal units, and stores them under :data:`DAP_INTERNAL_COL` /
    :data:`FLUORO_TIME_COL`. Existing values (e.g. a DAP column already produced
    by a vendor transform) are left untouched. Confident unit interpretations are
    recorded in ``ctx.unit_conversions`` (audit trail); genuine unit *ambiguity*
    is appended to ``ctx.warnings`` so it surfaces in the report and GUI.
    """
    cols = list(data_df.columns)

    if DAP_INTERNAL_COL not in cols:
        dap_col = _find_dap_total_column(cols)
        if dap_col is not None:
            data_df[DAP_INTERNAL_COL] = convert_dap_series_to_gym2(data_df[dap_col], dap_col, ctx)

    if FLUORO_TIME_COL not in cols:
        ft_col = _find_fluoro_time_total_column(cols)
        if ft_col is not None:
            factor, confident = _fluoro_to_seconds(ft_col)
            data_df[FLUORO_TIME_COL] = pd.to_numeric(data_df[ft_col], errors="coerce") * factor
            if confident:
                ctx.unit_conversions[FLUORO_TIME_COL] = f"fluoro time → seconds (from {ft_col!r})"
            else:
                ctx.warnings.append(
                    f"Fluoro time read from column {ft_col!r}, but its units could not be confirmed; "
                    "assuming milliseconds. Verify the reported fluoro time."
                )


def run_normalizer_pipeline(
    loaded: _RawLoad,
    *,
    schema_name: str,
    known_names: frozenset[str],
    patterns: dict[str, list[str]],
    required_columns: frozenset[str],
    transform: TransformFn,
    original_filename: str,
    settings: PyskindoseSettings,
) -> InputAdapterResult:
    """Run the shared header→map→transform→normalize pipeline.

    Parameters
    ----------
    schema_name:
        Provenance schema label and the name used in error messages.
    known_names:
        Column-name set used for header-row detection.
    patterns:
        Substring patterns mapping source headers → internal column names.
    required_columns:
        Columns that must be present *after* the transform, before
        rdsr_normalizer() is called.
    transform:
        Vendor-specific callback applied to the renamed DataFrame.

    Raises
    ------
    ValueError
        On duplicate column mappings, missing required columns, or
        rdsr_normalizer() failure.
    """
    from mypyskindose.rdsr_normalizer import rdsr_normalizer

    warnings: list[str] = []
    raw_df = loaded.raw_df

    header_idx = detect_header_row(raw_df, known_names)
    raw_headers, data_df = extract_table(raw_df, header_idx)

    column_map, mapping_warnings = map_columns(raw_headers, patterns)
    warnings.extend(mapping_warnings)
    unmatched_msg = unmapped_columns_warning(raw_headers, column_map)
    if unmatched_msg:
        warnings.append(unmatched_msg)

    dup_errors = check_duplicate_mappings(column_map)
    if dup_errors:
        raise ValueError("\n".join(dup_errors))

    rename = {src: tgt for src, tgt in column_map.items() if src in data_df.columns}
    data_df = data_df.rename(columns=rename)

    ctx = AdapterContext(
        column_map=column_map,
        raw_headers=raw_headers,
        settings=settings,
        warnings=warnings,
    )
    data_df = transform(data_df, ctx)

    # Capture per-event DAP / fluoro-time totals before the required-column check
    # (they are optional) and before rdsr_normalizer() drops unmodelled columns.
    attach_procedure_dose_totals(data_df, ctx)

    missing = required_columns - set(data_df.columns)
    if missing:
        raise ValueError(
            f"Missing required column(s) for {schema_name} schema: {sorted(missing)}. "
            f"Column map attempted: {column_map}."
        )

    try:
        normalized_df = rdsr_normalizer(data_df, settings)
    except Exception as exc:
        raise ValueError(
            f"RDSR normalization failed (error_type={exception_class_name(exc)})."
        ) from exc

    # rdsr_normalizer() rebuilds the frame from scratch, so carry the optional
    # dosimetric columns across by position (row order is preserved).
    for col in _PASSTHROUGH_DOSE_COLS:
        if col in data_df.columns and len(data_df) == len(normalized_df):
            normalized_df[col] = pd.to_numeric(data_df[col], errors="coerce").to_numpy()

    # Sentinel _dt_* targets are adapter-internal; keep them out of the public map.
    public_column_map = {k: v for k, v in column_map.items() if not v.startswith("_dt_")}
    provenance = InputProvenance(
        source_type=Path(original_filename).suffix.lstrip(".").lower(),
        schema_name=schema_name,
        original_filename=original_filename,
        header_row_index=header_idx,
        detected_encoding=loaded.encoding,
        detected_delimiter=loaded.delimiter,
        sheet_name=None,
        column_map=public_column_map,
        unit_conversions=ctx.unit_conversions,
        warnings=warnings,
    )

    return InputAdapterResult(
        normalized_data=normalized_df,
        raw_data=raw_df,
        provenance=provenance,
        warnings=warnings,
    )
