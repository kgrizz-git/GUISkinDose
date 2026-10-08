"""Kerma-meter correction factor (CF) resolution.

CF = (real measured dose) / (unit reported dose). Resolved per (equipment, tube)
from a user-supplied lookup table or in-memory override. Fail-soft to
``default_factor`` when identity cannot be resolved or the table misses a key.

Privacy: INFO/WARNING logs never include raw station/serial strings — only
counts and event-index lists.
"""

from __future__ import annotations

import json
import logging
import math
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

import pandas as pd

from guiskindose.constants import (
    CID_10003_CANONICAL,
    KEY_NORMALIZATION_ACQUISITION_PLANE,
    KEY_NORMALIZATION_ACQUISITION_PLANE_CANONICAL,
    KEY_NORMALIZATION_DEVICE_SERIAL,
    KEY_NORMALIZATION_STATION_NAME,
    TUBE_IDENTITY_UNKNOWN,
)
from guiskindose.grid_interp import format_event_indices

logger = logging.getLogger(__name__)

# Display sentinel for events with no equipment identity (never a table key).
UNRESOLVED_EQUIPMENT = "unresolved"

# Suspicious band for CF values — warn but accept.
_CF_SUSPICIOUS_LO = 0.5
_CF_SUSPICIOUS_HI = 2.0
_MAX_TABLE_ROWS = 10_000

_REQUIRED_COLUMNS = frozenset({"equipment", "tube", "correction_factor"})
_CF_MUST_BE_POSITIVE_FINITE = "Kerma-meter correction table: correction_factor must be a finite float > 0."
_TUBE_ALIASES = {
    "single": "single",
    "single plane": "single",
    "a": "A",
    "plane a": "A",
    "b": "B",
    "plane b": "B",
}


@dataclass(frozen=True)
class KermaMeterCorrection:
    """Resolved per-event kerma-meter correction factors."""

    factors: list[float]
    resolved_keys: list[tuple[str | None, str]]
    unresolved_event_indices: list[int] = field(default_factory=list)
    table_miss_event_indices: list[int] = field(default_factory=list)
    table_metadata: dict[str, Any] | None = None


def normalize_equipment_label(raw: str | float | None) -> str | None:
    """Strip, NFKC-normalize, and casefold an equipment label; empty → None."""
    if raw is None:
        return None
    if isinstance(raw, float) and math.isnan(raw):
        return None
    text = unicodedata.normalize("NFKC", str(raw)).strip()
    if not text or text.lower() in {"nan", "none", "<na>"}:
        return None
    return text.casefold()


def normalize_tube(acquisition_plane: str | float | None) -> str:
    """Map acquisition_plane to ``single`` | ``A`` | ``B`` | ``unknown``.

    Unrecognized or absent values return ``unknown`` so they cannot silently
    match a real single-plane calibration in the correction table.
    """
    if acquisition_plane is None:
        return TUBE_IDENTITY_UNKNOWN
    if isinstance(acquisition_plane, float) and math.isnan(acquisition_plane):
        return TUBE_IDENTITY_UNKNOWN
    text = unicodedata.normalize("NFKC", str(acquisition_plane)).strip().casefold()
    if not text:
        return TUBE_IDENTITY_UNKNOWN
    return _TUBE_ALIASES.get(text, TUBE_IDENTITY_UNKNOWN)


def resolve_canonical_plane_identity(raw_code: object) -> str:
    """Map a raw plane-identity code to ``single`` | ``A`` | ``B`` | ``unknown``.

    Uses DICOM CID 10003 as the authoritative source.  Non-CID or missing codes
    return ``unknown`` so callers never silently apply a real calibration to
    ambiguous input.
    """
    if raw_code is None:
        return TUBE_IDENTITY_UNKNOWN
    if raw_code is pd.NA:
        return TUBE_IDENTITY_UNKNOWN
    if isinstance(raw_code, float) and math.isnan(raw_code):
        return TUBE_IDENTITY_UNKNOWN
    try:
        if isinstance(raw_code, str):
            key = raw_code.strip()
            if key.endswith(".0") and key[:-2].isdigit():
                key = str(int(float(key)))
        elif isinstance(raw_code, bool):
            return TUBE_IDENTITY_UNKNOWN
        elif isinstance(raw_code, int):
            key = str(raw_code)
        elif isinstance(raw_code, float):
            key = str(int(raw_code))
        else:
            text = str(raw_code).strip()
            if text.endswith(".0") and text[:-2].isdigit():
                key = str(int(float(text)))
            elif text.isdigit():
                key = text
            else:
                return TUBE_IDENTITY_UNKNOWN
    except (TypeError, ValueError):
        return TUBE_IDENTITY_UNKNOWN
    return CID_10003_CANONICAL.get(key, TUBE_IDENTITY_UNKNOWN)


def resolve_correction_keys(
    data_norm: pd.DataFrame,
    *,
    explicit_label: str | None,
    fallback_label: str | None = None,
) -> list[tuple[str | None, str]]:
    """Resolve ``(equipment_label, tube)`` per event using fixed precedence.

    Order: explicit_label → device_serial → station_name → fallback_label →
    unresolved (None).

    Parameters
    ----------
    data_norm : pd.DataFrame
        Normalized events of one exam.
    explicit_label : str | None
        Forces every event to this label (wins over everything).
    fallback_label : str | None
        Per-exam identity override. Used only for events whose serial and station
        are both missing, so it never replaces a detected identity.

    Tube identity prefers ``acquisition_plane_canonical`` when it is a recognized
    CID-backed value (``single`` / ``A`` / ``B``); otherwise falls back to
    ``normalize_tube(acquisition_plane)`` so meaning-only inputs still resolve.
    """
    n = len(data_norm)
    plane_col = (
        data_norm[KEY_NORMALIZATION_ACQUISITION_PLANE]
        if KEY_NORMALIZATION_ACQUISITION_PLANE in data_norm.columns
        else pd.Series([None] * n)
    )
    canonical_col = (
        data_norm[KEY_NORMALIZATION_ACQUISITION_PLANE_CANONICAL]
        if KEY_NORMALIZATION_ACQUISITION_PLANE_CANONICAL in data_norm.columns
        else None
    )
    serial_col = (
        data_norm[KEY_NORMALIZATION_DEVICE_SERIAL]
        if KEY_NORMALIZATION_DEVICE_SERIAL in data_norm.columns
        else pd.Series([None] * n)
    )
    station_col = (
        data_norm[KEY_NORMALIZATION_STATION_NAME]
        if KEY_NORMALIZATION_STATION_NAME in data_norm.columns
        else pd.Series([None] * n)
    )

    forced = normalize_equipment_label(explicit_label)
    fallback = normalize_equipment_label(fallback_label)
    keys: list[tuple[str | None, str]] = []
    for i in range(n):
        tube = TUBE_IDENTITY_UNKNOWN
        if canonical_col is not None and i < len(canonical_col):
            cand = str(canonical_col.iloc[i]).strip()
            if cand in {"single", "A", "B"}:
                tube = cand
        if tube == TUBE_IDENTITY_UNKNOWN:
            tube = normalize_tube(plane_col.iloc[i] if i < len(plane_col) else None)
        if forced is not None:
            keys.append((forced, tube))
            continue
        equip = normalize_equipment_label(serial_col.iloc[i] if i < len(serial_col) else None)
        if equip is None:
            equip = normalize_equipment_label(station_col.iloc[i] if i < len(station_col) else None)
        keys.append((equip if equip is not None else fallback, tube))
    return keys


def distinct_auto_resolved_equipment_keys(data_norm: pd.DataFrame) -> set[str]:
    """Equipment labels that would be resolved without ``explicit_label``."""
    keys = resolve_correction_keys(data_norm, explicit_label=None)
    return {eq for eq, _ in keys if eq is not None}


def unique_equipment_tube_keys(
    frames: Sequence[pd.DataFrame],
    *,
    explicit_label: str | None = None,
    exam_labels: Sequence[str] | None = None,
    unresolved_labels: Mapping[str, str] | None = None,
) -> list[tuple[str, str]]:
    """Sorted unique ``(equipment, tube)`` pairs across frames for prompt/UI.

    Uses the same precedence as dose resolution (``explicit_label`` → serial →
    station → per-exam override). The sentinel ``"unresolved"`` appears only for
    events that are still unresolved after overrides.

    Parameters
    ----------
    frames : Sequence[pd.DataFrame]
        One normalized frame per exam.
    explicit_label : str | None
        Run-wide forced label.
    exam_labels : Sequence[str] | None
        Opaque exam label (``"Exam N"``) per frame, parallel to *frames*.
    unresolved_labels : Mapping[str, str] | None
        Per-exam identity overrides keyed by opaque exam label.
    """
    keys: set[tuple[str, str]] = set()
    for i, df in enumerate(frames):
        label = unresolved_labels.get(exam_labels[i]) if unresolved_labels and exam_labels else None
        for equip, tube in resolve_correction_keys(df, explicit_label=explicit_label, fallback_label=label):
            keys.add((equip or UNRESOLVED_EQUIPMENT, tube))
    return sorted(keys)


def missing_keys(
    detected: Sequence[tuple[str, str]],
    table: Mapping[tuple[str, str], float] | None,
) -> list[tuple[str, str]]:
    """Detected ``(equipment, tube)`` pairs that the table cannot supply a factor for.

    A pair is missing when it is absent from *table* (or no table exists). Pairs
    whose equipment is the ``"unresolved"`` sentinel or whose tube is ``unknown``
    are always missing: the engine never consults the table for them.

    Parameters
    ----------
    detected : Sequence[tuple[str, str]]
        Pairs from :func:`unique_equipment_tube_keys`.
    table : Mapping[tuple[str, str], float] | None
        Merged manual + file table (see :func:`merge_tables`).

    Returns
    -------
    list[tuple[str, str]]
        Missing pairs, sorted and de-duplicated.
    """
    lookup = table or {}
    return sorted(
        {
            (equip, tube)
            for equip, tube in detected
            if equip == UNRESOLVED_EQUIPMENT or tube == TUBE_IDENTITY_UNKNOWN or (equip, tube) not in lookup
        }
    )


def _warn_suspicious_factor(factor: float) -> None:
    """Warn when a CF falls outside the typical band (privacy: no equipment labels)."""
    if not (_CF_SUSPICIOUS_LO <= factor <= _CF_SUSPICIOUS_HI):
        logger.warning(
            "kerma-meter correction: factor %.4g for one (equipment, tube) pair "
            "is outside the typical [%.1f, %.1f] band.",
            factor,
            _CF_SUSPICIOUS_LO,
            _CF_SUSPICIOUS_HI,
        )


def _normalize_table_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Lowercase/strip column headers to canonical names."""
    rename: dict[str, str] = {}
    aliases = {
        "equipment": "equipment",
        "station": "equipment",
        "station_name": "equipment",
        "stationname": "equipment",
        "device_serial": "equipment",
        "device_serial_number": "equipment",
        "deviceserialnumber": "equipment",
        "tube": "tube",
        "acquisition_plane": "tube",
        "acquisitionplane": "tube",
        "plane": "tube",
        "correction_factor": "correction_factor",
        "valid_from": "valid_from",
        "valid_to": "valid_to",
        "cf": "correction_factor",
        "factor": "correction_factor",
        "notes": "notes",
        "source": "source",
    }
    for col in df.columns:
        key = unicodedata.normalize("NFKC", str(col)).strip().casefold().replace(" ", "_")
        if key in aliases:
            rename[col] = aliases[key]
    return df.rename(columns=rename)


def _rows_to_factor_dict(
    rows: Sequence[Mapping[str, Any]],
) -> dict[tuple[str, str], float]:
    """Build a first-wins ``(equipment, tube) → CF`` map from normalized row dicts.

    Dated rows resolve to the current (no ``valid_to``) or most recent period; use
    :func:`load_correction_periods` to choose a period explicitly.
    """
    from guiskindose.kerma_periods import resolve_period_table, rows_to_periods

    return resolve_period_table(rows_to_periods(rows))


def _ensure_row_budget(n_rows: int) -> None:
    """Raise when a CF table exceeds the hard row limit."""
    if n_rows > _MAX_TABLE_ROWS:
        raise ValueError(f"Kerma-meter correction table exceeds {_MAX_TABLE_ROWS} rows.")


def _load_json_correction_rows(path: Path) -> list[dict[str, Any]]:
    """Parse JSON CF payload into a non-empty list of row dicts."""
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if isinstance(payload, dict) and "factors" in payload:
        rows = payload["factors"]
    elif isinstance(payload, list):
        rows = payload
    else:
        raise ValueError('Kerma-meter correction JSON must be a list or {"factors": [...]}.')
    if not isinstance(rows, list) or len(rows) == 0:
        raise ValueError("Kerma-meter correction JSON has no factor rows.")
    _ensure_row_budget(len(rows))
    return cast(list[dict[str, Any]], rows)


def _load_tabular_correction_df(path: Path, sheet: str | int | None) -> pd.DataFrame:
    """Load CSV/TSV/XLSX into a DataFrame with required CF columns present."""
    suffix = path.suffix.lower()
    if suffix == ".xlsx":
        sheet_arg: str | int = 0 if sheet is None else sheet
        try:
            df = pd.read_excel(path, sheet_name=sheet_arg, dtype=str)
        except ValueError as exc:
            raise ValueError(f"Kerma-meter correction XLSX sheet {sheet_arg!r} could not be read.") from exc
    elif suffix in {".csv", ".tsv"}:
        sep = "\t" if suffix == ".tsv" else ","
        df = pd.read_csv(path, sep=sep, dtype=str, encoding="utf-8-sig")
    else:
        raise ValueError(f"Unsupported kerma-meter correction file type {suffix!r}; use .csv, .tsv, .xlsx, or .json.")

    if df.empty:
        raise ValueError("Kerma-meter correction table is empty (no data rows).")
    _ensure_row_budget(len(df))

    df = _normalize_table_columns(df)
    missing = _REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(f"Kerma-meter correction table missing required column(s): {sorted(missing)}.")
    return df


def _read_correction_rows(path: Path | str, sheet: str | int | None) -> Sequence[Mapping[str, Any]]:
    """Read the raw row dicts of a CF file (CSV/TSV/XLSX/JSON) after basic file checks."""
    path = Path(path)
    if not path.is_file():
        raise ValueError("Kerma-meter correction file not found or not a regular file.")
    if path.suffix.lower() == ".json":
        return _load_json_correction_rows(path)
    return cast(
        list[dict[str, Any]],
        _load_tabular_correction_df(path, sheet).to_dict(orient="records"),
    )


def load_correction_periods(path: Path | str, sheet: str | int | None = None) -> dict[tuple[str, str], list[Any]]:
    """Load a CF file keeping every calibration period (``valid_from`` / ``valid_to``).

    Returns ``(equipment, tube) -> list[CalibrationRow]``. Raises ValueError on a
    missing file, empty data, oversized tables, invalid values, or overlapping
    periods for one pair.
    """
    from guiskindose.kerma_periods import rows_to_periods

    return rows_to_periods(_read_correction_rows(path, sheet))


def load_correction_table(path: Path | str, sheet: str | int | None = None) -> dict[tuple[str, str], float]:
    """Load a CF lookup table from CSV/TSV/XLSX/JSON.

    Rows without dates behave as one open-ended calibration. For dated rows the
    current (no ``valid_to``) or most recent period is used; see
    :func:`load_correction_periods` to pick another.

    Raises ValueError on missing file, empty data, oversized tables, or invalid values.
    """
    return _rows_to_factor_dict(_read_correction_rows(path, sheet))


def _exam_number(label: str) -> int | None:
    """Zero-based index of an opaque ``Exam N`` label, or ``None`` for any other label."""
    from guiskindose.privacy import opaque_exam_index

    try:
        return opaque_exam_index(label)
    except ValueError:
        return None


def effective_period(periods: Mapping[str, str] | None, exam: str) -> str | None:
    """Calibration-period key in effect for *exam*.

    Only explicit choices are stored, so a follower never goes stale when an
    earlier exam changes. An exam without its own choice follows the nearest
    earlier exam that has one.

    Parameters
    ----------
    periods : Mapping[str, str] | None
        Explicit per-exam choices, ``{"Exam N": "<from>|<to>"}``.
    exam : str
        Opaque exam label.

    Returns
    -------
    str | None
        The period key, or ``None`` for the engine default (each pair's current or
        most recent calibration row).
    """
    if not periods:
        return None
    if exam in periods:
        return periods[exam]
    index = _exam_number(exam)
    if index is None:
        return None
    earlier = [(n, key) for label, key in periods.items() if (n := _exam_number(label)) is not None and n < index]
    return max(earlier)[1] if earlier else None


def _previous_exam(exam: str) -> str | None:
    """Label of the exam immediately before *exam* (``Exam N`` -> ``Exam N-1``), or ``None``."""
    from guiskindose.privacy import opaque_exam_label

    index = _exam_number(exam)
    return opaque_exam_label(index - 1) if index else None


def resolve_manual(
    table: Mapping[tuple[str, ...], float | None],
    periods: Mapping[str, str] | None,
    exam: str,
    pair: tuple[str, str],
) -> tuple[float | None, str | None] | None:
    """The single rule for a manual factor of one exam and pair, shared by the dialog and the engine.

    Order: an entry for the exam itself, then a legacy ``(equipment, tube)`` entry
    (applies to every exam), then *follow*: the exam immediately before takes
    precedence only while its effective calibration period equals this exam's, and
    its own manual-or-followed value is used. Otherwise ``None``, and the caller
    resolves the factor from the calibration file or the default.

    Why the period check: an old-period value must not silently apply to an exam
    that uses a newer calibration, and a different-period exam in between is not
    skipped over (old, new, old does not carry the first value to the third exam).
    The dialog and the engine both call this function, so what the dialog shows is
    what the calculation applies.

    Parameters
    ----------
    table : Mapping[tuple[str, ...], float | None]
        Manual entries keyed ``(exam, equipment, tube)`` or legacy ``(equipment, tube)``.
        A ``None`` value is an explicit but blank entry (the dialog's unsaved edit).
    periods : Mapping[str, str] | None
        Explicit calibration-period choices (see :func:`effective_period`).
    exam : str
        Opaque exam label.
    pair : tuple[str, str]
        ``(equipment, tube)``.

    Returns
    -------
    tuple[float | None, str | None] | None
        ``(value, followed exam label)``; the label is ``None`` for an explicit entry.
    """
    own = (exam, *pair)
    if own in table:
        return table[own], None
    if pair in table:
        return table[pair], None
    previous = _previous_exam(exam)
    if previous is not None and effective_period(periods, previous) == effective_period(periods, exam):
        resolved = resolve_manual(table, periods, previous, pair)
        if resolved is not None:
            return resolved[0], previous
    return None


def manual_for_exam(
    table: Mapping[tuple[str, ...], float] | None,
    exam: str,
    *,
    periods: Mapping[str, str] | None = None,
    follow: bool = True,
) -> dict[tuple[str, str], float]:
    """Manual entries that apply to one exam, resolved with :func:`resolve_manual`.

    Entries are keyed ``(exam label, equipment, tube)``; a legacy two-part key
    applies to every exam. With ``follow`` (default) a pair with no entry for this
    exam takes the immediately preceding exam's value while both use the same
    calibration period, so "follows Exam N" survives without copying values.
    This is the engine-side view of :func:`resolve_manual`.

    Parameters
    ----------
    table : Mapping[tuple[str, ...], float] | None
        The manual table (explicit entries only).
    exam : str
        Opaque exam label.
    periods : Mapping[str, str] | None
        Explicit per-exam calibration-period choices.
    follow : bool
        When ``False`` only the exam's own and the legacy entries are returned.

    Returns
    -------
    dict[tuple[str, str], float]
        ``{(equipment, tube): factor}`` for pairs with a usable (non-blank) value.
    """
    if not table:
        return {}
    pairs = {(k[-2], k[-1]) for k in table}
    out: dict[tuple[str, str], float] = {}
    for pair in pairs:
        if follow:
            resolved = resolve_manual(table, periods, exam, pair)
        elif (exam, *pair) in table or pair in table:
            resolved = (table.get((exam, *pair), table.get(pair)), None)
        else:
            resolved = None
        if resolved is not None and resolved[0] is not None:
            out[pair] = float(resolved[0])
    return out


def merge_tables(
    file_table: dict[tuple[str, str], float] | None,
    memory_table: dict[tuple[str, str], float] | None,
) -> dict[tuple[str, str], float] | None:
    """Merge file + in-memory tables; in-memory wins on overlapping keys."""
    if file_table is None and memory_table is None:
        return None
    merged: dict[tuple[str, str], float] = {}
    if file_table:
        merged.update(file_table)
    if memory_table:
        merged.update(memory_table)
    return merged


def _lookup_correction(
    equip: str | None,
    tube: str,
    lookup: dict[tuple[str, str], float],
    default_factor: float,
    index: int,
    unresolved: list[int],
    table_miss: list[int],
) -> float:
    """Per-event lookup: returns factor, appends to ``unresolved``/``table_miss`` as needed."""
    if equip is None or tube == TUBE_IDENTITY_UNKNOWN:
        unresolved.append(index)
        return default_factor
    cf = lookup.get((equip, tube))
    if cf is None:
        table_miss.append(index)
        return default_factor
    try:
        value = float(cf)
    except (TypeError, ValueError):
        value = float("nan")
    if not math.isfinite(value) or value <= 0:
        logger.warning(
            "kerma-meter correction: invalid factor for event index %d; using default_factor=%.4g.",
            index,
            default_factor,
        )
        return default_factor
    return value


def _log_kerma_warnings(
    n: int,
    table: dict[tuple[str, str], float] | None,
    unresolved: list[int],
    table_miss: list[int],
    default_factor: float,
) -> None:
    """Emit the unresolved / table_miss / no-table-supplied warnings."""
    if unresolved:
        logger.warning(
            "kerma-meter correction: %d of %d event(s) had unresolved equipment "
            "identity → default_factor=%.4g. Affected event index(es): %s.",
            len(unresolved),
            n,
            default_factor,
            format_event_indices(unresolved),
        )
    if table_miss:
        logger.warning(
            "kerma-meter correction: %d of %d event(s) had resolved identity but "
            "no matching table row → default_factor=%.4g. Affected event index(es): %s.",
            len(table_miss),
            n,
            default_factor,
            format_event_indices(table_miss),
        )
    if table is None and n:
        logger.warning(
            "kerma-meter correction: enabled but no table supplied; using default_factor=%.4g for all %d event(s).",
            default_factor,
            n,
        )


def resolve_correction_factors(
    data_norm: pd.DataFrame,
    table: dict[tuple[str, str], float] | None,
    *,
    explicit_label: str | None = None,
    default_factor: float = 1.0,
    table_metadata: dict[str, Any] | None = None,
    fallback_label: str | None = None,
) -> KermaMeterCorrection:
    """Resolve per-event CF list from keys + lookup table.

    Absent table or missing key → ``default_factor``. Never mutates ``data_norm``.
    ``fallback_label`` is the per-exam identity override for events with no
    serial/station; those events then reach the table instead of the
    unresolved branch (see :func:`resolve_correction_keys`).
    """
    if not math.isfinite(default_factor) or default_factor <= 0:
        raise ValueError("default_factor must be a finite float > 0.")

    keys = resolve_correction_keys(data_norm, explicit_label=explicit_label, fallback_label=fallback_label)
    lookup = table or {}
    unresolved: list[int] = []
    table_miss: list[int] = []
    factors = [
        _lookup_correction(equip, tube, lookup, default_factor, i, unresolved, table_miss)
        for i, (equip, tube) in enumerate(keys)
    ]

    _log_kerma_warnings(len(factors), table, unresolved, table_miss, default_factor)

    return KermaMeterCorrection(
        factors=factors,
        resolved_keys=keys,
        unresolved_event_indices=unresolved,
        table_miss_event_indices=table_miss,
        table_metadata=table_metadata,
    )


def all_ones_correction(n: int) -> KermaMeterCorrection:
    """Identity CF vector (feature disabled / CF=1.0)."""
    return KermaMeterCorrection(
        factors=[1.0] * n,
        resolved_keys=[(None, "single")] * n,
    )
