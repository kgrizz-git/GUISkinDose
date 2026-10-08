"""Calibration periods for kerma-meter correction files.

A calibration file may carry optional ``valid_from`` / ``valid_to`` columns (ISO
dates, either blank for an open end). Rows without dates behave as a single
open-ended calibration, exactly as before. The same ``(equipment, tube)`` may
have several dated rows as long as their periods do not overlap.

GUISkinDose never reads dates from the exam data: the dates here are calibration
dates from the user's file, and the period for an exam is chosen by the user
(GUI selector) or by ``--kerma-meter-calibration-date`` (CLI). Dates are kept out
of logs.
"""

from __future__ import annotations

import itertools
import logging
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any

from guiskindose.constants import TUBE_IDENTITY_UNKNOWN

# Same logger as kerma_correction so table-load messages stay in one channel.
logger = logging.getLogger("guiskindose.kerma_correction")

Pair = tuple[str, str]

_CF_MUST_BE_POSITIVE_FINITE = "Kerma-meter correction table: correction_factor must be a finite float > 0."
_BAD_DATE = "Kerma-meter correction table: valid_from / valid_to must be ISO dates (YYYY-MM-DD) or blank."
_BAD_RANGE = "Kerma-meter correction table: valid_from must not be after valid_to."
_OVERLAP = "Kerma-meter correction table: calibration periods for the same equipment and tube must not overlap."


@dataclass(frozen=True)
class CalibrationRow:
    """One calibration factor with its (possibly open-ended) validity period."""

    valid_from: date | None
    valid_to: date | None
    factor: float

    @property
    def dated(self) -> bool:
        """True when either end of the period is set."""
        return self.valid_from is not None or self.valid_to is not None

    def contains(self, day: date) -> bool:
        """True when *day* lies inside the period (open ends are unbounded)."""
        return (self.valid_from is None or self.valid_from <= day) and (self.valid_to is None or day <= self.valid_to)


@dataclass(frozen=True)
class PeriodOption:
    """A distinct calibration period of the file, as offered by the GUI selector."""

    key: str
    label: str
    ref_date: date


Periods = dict[Pair, list[CalibrationRow]]


def parse_period_date(value: object) -> date | None:
    """Parse an ISO date cell; blank or missing gives ``None``.

    Accepts ``YYYY-MM-DD`` and the ``YYYY-MM-DD HH:MM:SS`` text spreadsheets produce.

    Raises
    ------
    ValueError
        If the cell is not blank and not an ISO date.
    """
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    text = str(value).strip()
    if not text or text.lower() in {"nan", "nat", "none"}:
        return None
    if len(text) > 10 and text[10] in " T":
        text = text[:10]
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(_BAD_DATE) from exc


def _recency(row: CalibrationRow) -> tuple[date, date]:
    """Sort key: current (no ``valid_to``) first, then the latest ending, then latest starting."""
    return (row.valid_to or date.max, row.valid_from or date.min)


def _check_overlaps(rows: list[CalibrationRow]) -> None:
    """Raise when two dated periods of one pair overlap."""
    ordered = sorted(rows, key=lambda r: (r.valid_from or date.min, r.valid_to or date.max))
    for earlier, later in itertools.pairwise(ordered):
        if earlier.valid_to is None or later.valid_from is None or earlier.valid_to >= later.valid_from:
            raise ValueError(_OVERLAP)


def _parse_row(row: Mapping[str, Any]) -> tuple[Pair, CalibrationRow]:
    """Validate one normalized row dict and return its pair and calibration row."""
    from guiskindose.kerma_correction import (
        _warn_suspicious_factor,
        normalize_equipment_label,
        normalize_tube,
    )

    equip = normalize_equipment_label(row.get("equipment"))
    tube = normalize_tube(row.get("tube"))
    if equip is None:
        raise ValueError("Kerma-meter correction table: equipment column has an empty value.")
    if tube == TUBE_IDENTITY_UNKNOWN:
        raise ValueError("Kerma-meter correction table: tube column has an empty or unrecognized value.")
    try:
        factor = float(row.get("correction_factor"))  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise ValueError(_CF_MUST_BE_POSITIVE_FINITE) from exc
    if not math.isfinite(factor) or factor <= 0:
        raise ValueError(_CF_MUST_BE_POSITIVE_FINITE)
    new = CalibrationRow(parse_period_date(row.get("valid_from")), parse_period_date(row.get("valid_to")), factor)
    if new.valid_from and new.valid_to and new.valid_from > new.valid_to:
        raise ValueError(_BAD_RANGE)
    _warn_suspicious_factor(factor)
    return (equip, tube), new


def rows_to_periods(rows: Sequence[Mapping[str, Any]]) -> Periods:
    """Build ``(equipment, tube) -> calibration rows`` from normalized row dicts.

    Equipment, tube and factor validation matches the undated loader. Undated
    duplicates keep the first row and log a count. Any other overlap raises.

    Raises
    ------
    ValueError
        On an empty equipment or tube, an invalid factor or date, a reversed
        period, or overlapping periods for one pair.
    """
    periods: Periods = {}
    duplicates = 0
    for row in rows:
        pair, new = _parse_row(row)
        existing = periods.setdefault(pair, [])
        if not new.dated and any(not r.dated for r in existing):
            duplicates += 1
            continue
        existing.append(new)
    for rows_for_pair in periods.values():
        if len(rows_for_pair) > 1:
            _check_overlaps(rows_for_pair)
    if duplicates:
        logger.warning("kerma-meter correction: %d duplicate (equipment, tube) row(s); first wins.", duplicates)
    logger.debug("kerma-meter correction table loaded (%d pairs)", len(periods))
    return periods


def select_row(rows: Sequence[CalibrationRow], ref_date: date | None) -> CalibrationRow | None:
    """Pick the row for a reference date, or the current/most recent row when it is ``None``.

    With a date, only a row whose period contains it qualifies (``None`` when
    there is none). Without one, the row with no ``valid_to`` wins, else the most
    recent.
    """
    if ref_date is not None:
        return next((r for r in rows if r.contains(ref_date)), None)
    return max(rows, key=_recency) if rows else None


def resolve_period_table(periods: Periods, ref_date: date | None = None) -> dict[Pair, float]:
    """Flatten *periods* to one factor per pair for a reference date (see :func:`select_row`)."""
    table: dict[Pair, float] = {}
    for pair, rows in periods.items():
        chosen = select_row(rows, ref_date)
        if chosen is not None:
            table[pair] = chosen.factor
    return table


def period_key(valid_from: date | None, valid_to: date | None) -> str:
    """Stable string key ``"<from>|<to>"`` for a period (blank for an open end)."""
    return f"{valid_from.isoformat() if valid_from else ''}|{valid_to.isoformat() if valid_to else ''}"


def key_ref_date(key: str) -> date | None:
    """Reference date of a period key: its start, else its end; ``None`` for a malformed key."""
    start, _, end = str(key).partition("|")
    try:
        return parse_period_date(start) or parse_period_date(end)
    except ValueError:
        return None


def period_label(valid_from: date | None, valid_to: date | None) -> str:
    """Human label such as ``2026-01-01 → 2026-06-30``; an open end reads ``(open)``."""
    start = valid_from.isoformat() if valid_from else "(open)"
    end = valid_to.isoformat() if valid_to else "(open)"
    return f"{start} → {end}"


def period_options(periods: Periods) -> list[PeriodOption]:
    """Distinct dated periods of the file, most recent first."""
    seen: dict[tuple[date | None, date | None], None] = {}
    for rows in periods.values():
        for row in rows:
            if row.dated:
                seen.setdefault((row.valid_from, row.valid_to), None)
    ordered = sorted(seen, key=lambda p: (p[1] or date.max, p[0] or date.min), reverse=True)
    return [
        PeriodOption(period_key(start, end), period_label(start, end), (start or end))  # type: ignore[arg-type]
        for start, end in ordered
    ]


def dated_pairs(periods: Periods) -> set[Pair]:
    """Pairs that have at least one dated row."""
    return {pair for pair, rows in periods.items() if any(r.dated for r in rows)}


def file_table_for_exam(
    periods: Periods,
    *,
    period_key: str | None = None,
    calibration_date: date | None = None,
) -> dict[Pair, float]:
    """One factor per pair for an exam's chosen calibration period.

    A GUI *period_key* wins, then a CLI *calibration_date*; with neither, the
    current (no ``valid_to``) or most recent period is used.
    """
    ref = key_ref_date(period_key) if period_key else calibration_date
    return resolve_period_table(periods, ref)
