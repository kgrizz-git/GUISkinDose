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
from dataclasses import dataclass, field
from pathlib import Path
from collections.abc import Mapping, Sequence
from typing import Any, cast

import pandas as pd

from mypyskindose.constants import (
    KEY_NORMALIZATION_ACQUISITION_PLANE,
    KEY_NORMALIZATION_DEVICE_SERIAL,
    KEY_NORMALIZATION_STATION_NAME,
)
from mypyskindose.grid_interp import format_event_indices

logger = logging.getLogger(__name__)

# Suspicious band for CF values — warn but accept.
_CF_SUSPICIOUS_LO = 0.5
_CF_SUSPICIOUS_HI = 2.0
_MAX_TABLE_ROWS = 10_000

_REQUIRED_COLUMNS = frozenset({"equipment", "tube", "correction_factor"})
_CF_MUST_BE_POSITIVE_FINITE = (
    "Kerma-meter correction table: correction_factor must be a finite float > 0."
)
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


def normalize_equipment_label(raw: str | None) -> str | None:
    """Strip, NFKC-normalize, and casefold an equipment label; empty → None."""
    if raw is None:
        return None
    try:
        if isinstance(raw, float) and math.isnan(raw):
            return None
    except TypeError:
        pass
    text = unicodedata.normalize("NFKC", str(raw)).strip()
    if not text or text.lower() in {"nan", "none", "<na>"}:
        return None
    return text.casefold()


def normalize_tube(acquisition_plane: str | None) -> str:
    """Map acquisition_plane to ``single`` | ``A`` | ``B`` (default ``single``)."""
    if acquisition_plane is None:
        return "single"
    try:
        if isinstance(acquisition_plane, float) and math.isnan(acquisition_plane):
            return "single"
    except TypeError:
        pass
    text = unicodedata.normalize("NFKC", str(acquisition_plane)).strip().casefold()
    if not text:
        return "single"
    return _TUBE_ALIASES.get(text, "single")


def resolve_correction_keys(
    data_norm: pd.DataFrame,
    *,
    explicit_label: str | None,
) -> list[tuple[str | None, str]]:
    """Resolve ``(equipment_label, tube)`` per event using fixed precedence.

    Order: explicit_label → device_serial → station_name → unresolved (None).
    """
    n = len(data_norm)
    plane_col = (
        data_norm[KEY_NORMALIZATION_ACQUISITION_PLANE]
        if KEY_NORMALIZATION_ACQUISITION_PLANE in data_norm.columns
        else pd.Series([None] * n)
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
    keys: list[tuple[str | None, str]] = []
    for i in range(n):
        tube = normalize_tube(plane_col.iloc[i] if i < len(plane_col) else None)
        if forced is not None:
            keys.append((forced, tube))
            continue
        equip = normalize_equipment_label(serial_col.iloc[i] if i < len(serial_col) else None)
        if equip is None:
            equip = normalize_equipment_label(station_col.iloc[i] if i < len(station_col) else None)
        keys.append((equip, tube))
    return keys


def distinct_auto_resolved_equipment_keys(data_norm: pd.DataFrame) -> set[str]:
    """Equipment labels that would be resolved without ``explicit_label``."""
    keys = resolve_correction_keys(data_norm, explicit_label=None)
    return {eq for eq, _ in keys if eq is not None}


def unique_equipment_tube_keys(
    frames: Sequence[pd.DataFrame],
    *,
    explicit_label: str | None = None,
) -> list[tuple[str, str]]:
    """Sorted unique ``(equipment, tube)`` pairs across frames for prompt/UI.

    Uses the same precedence as dose resolution (``explicit_label`` → serial →
    station). Unresolved equipment becomes the sentinel ``\"unresolved\"``.
    """
    keys: set[tuple[str, str]] = set()
    for df in frames:
        for equip, tube in resolve_correction_keys(df, explicit_label=explicit_label):
            keys.add((equip or "unresolved", tube))
    return sorted(keys)


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
    """Build a first-wins ``(equipment, tube) → CF`` map from normalized row dicts."""
    table: dict[tuple[str, str], float] = {}
    duplicates = 0
    for row in rows:
        equip = normalize_equipment_label(row.get("equipment"))
        tube = normalize_tube(row.get("tube"))
        raw_cf = row.get("correction_factor")
        if equip is None:
            raise ValueError("Kerma-meter correction table: equipment column has an empty value.")
        if raw_cf is None:
            raise ValueError(_CF_MUST_BE_POSITIVE_FINITE)
        try:
            factor = float(raw_cf)
        except (TypeError, ValueError) as exc:
            raise ValueError(_CF_MUST_BE_POSITIVE_FINITE) from exc
        if not math.isfinite(factor) or factor <= 0:
            raise ValueError(_CF_MUST_BE_POSITIVE_FINITE)
        key = (equip, tube)
        if key in table:
            duplicates += 1
            continue
        table[key] = factor
        _warn_suspicious_factor(factor)
    if duplicates:
        logger.warning(
            "kerma-meter correction: %d duplicate (equipment, tube) row(s); first wins.",
            duplicates,
        )
    logger.debug("kerma-meter correction table loaded (%d rows)", len(table))
    return table


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
            raise ValueError(
                f"Kerma-meter correction XLSX sheet {sheet_arg!r} could not be read."
            ) from exc
    elif suffix in {".csv", ".tsv"}:
        sep = "\t" if suffix == ".tsv" else ","
        df = pd.read_csv(path, sep=sep, dtype=str, encoding="utf-8-sig")
    else:
        raise ValueError(
            f"Unsupported kerma-meter correction file type {suffix!r}; "
            "use .csv, .tsv, .xlsx, or .json."
        )

    if df.empty:
        raise ValueError("Kerma-meter correction table is empty (no data rows).")
    _ensure_row_budget(len(df))

    df = _normalize_table_columns(df)
    missing = _REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(
            f"Kerma-meter correction table missing required column(s): {sorted(missing)}."
        )
    return df


def load_correction_table(path: Path | str, sheet: str | int | None = None) -> dict[tuple[str, str], float]:
    """Load a CF lookup table from CSV/TSV/XLSX/JSON.

    Raises ValueError on missing file, empty data, oversized tables, or invalid values.
    """
    path = Path(path)
    if not path.is_file():
        raise ValueError("Kerma-meter correction file not found or not a regular file.")

    if path.suffix.lower() == ".json":
        rows: Sequence[Mapping[str, Any]] = _load_json_correction_rows(path)
    else:
        rows = cast(
            list[dict[str, Any]],
            _load_tabular_correction_df(path, sheet).to_dict(orient="records"),
        )
    return _rows_to_factor_dict(rows)


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


def resolve_correction_factors(
    data_norm: pd.DataFrame,
    table: dict[tuple[str, str], float] | None,
    *,
    explicit_label: str | None = None,
    default_factor: float = 1.0,
    table_metadata: dict[str, Any] | None = None,
) -> KermaMeterCorrection:
    """Resolve per-event CF list from keys + lookup table.

    Absent table or missing key → ``default_factor``. Never mutates ``data_norm``.
    """
    if not math.isfinite(default_factor) or default_factor <= 0:
        raise ValueError("default_factor must be a finite float > 0.")

    keys = resolve_correction_keys(data_norm, explicit_label=explicit_label)
    factors: list[float] = []
    unresolved: list[int] = []
    table_miss: list[int] = []
    lookup = table or {}

    for i, (equip, tube) in enumerate(keys):
        if equip is None:
            factors.append(default_factor)
            unresolved.append(i)
            continue
        cf = lookup.get((equip, tube))
        if cf is None:
            factors.append(default_factor)
            table_miss.append(i)
            continue
        try:
            value = float(cf)
        except (TypeError, ValueError):
            value = float("nan")
        if not math.isfinite(value) or value <= 0:
            logger.warning(
                "kerma-meter correction: invalid factor for event index %d; "
                "using default_factor=%.4g.",
                i,
                default_factor,
            )
            factors.append(default_factor)
        else:
            factors.append(value)

    n = len(factors)
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
            "kerma-meter correction: enabled but no table supplied; "
            "using default_factor=%.4g for all %d event(s).",
            default_factor,
            n,
        )

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
