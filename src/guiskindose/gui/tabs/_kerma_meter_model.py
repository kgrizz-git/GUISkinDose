"""Kerma-meter factor model: detection, per-exam resolution, follow-previous pre-fill.

No UI imports, so every decision is unit-testable. Factors are resolved per exam:
manual entry for that exam > file row for the exam's calibration period >
``default_factor``. Manual entries are keyed ``(exam label, equipment, tube)``; a
legacy ``(equipment, tube)`` key applies to every exam.

Dialog pre-fill: Exam 2 and later start from the value the same pair has in the
previous exam and keep *following* it until the user edits that row. The same
holds for the calibration-period choice. A row follows only an entered (or
itself following) value; file and default values simply resolve per exam.

Privacy: equipment labels and calibration dates are never logged here.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

from guiskindose.constants import TUBE_IDENTITY_UNKNOWN
from guiskindose.kerma_correction import (
    UNRESOLVED_EQUIPMENT,
    load_correction_periods,
    manual_for_exam,
    merge_tables,
    missing_keys,
    unique_equipment_tube_keys,
)
from guiskindose.kerma_periods import Periods, dated_pairs, file_table_for_exam, period_options
from guiskindose.privacy import opaque_exam_label

if TYPE_CHECKING:
    import pandas as pd

    from guiskindose.gui.state import AppState
    from guiskindose.kerma_periods import PeriodOption

SOURCE_ENTERED = "manual"
SOURCE_FILE = "file"
SOURCE_DEFAULT = "default"
SOURCE_FOLLOWS = "follows"

Pair = tuple[str, str]


@dataclass(frozen=True)
class DialogRow:
    """One ``(equipment, tube)`` row of one exam with its resolved value and source."""

    exam: str
    equipment: str
    tube: str
    value: float | None
    source: str
    follows: str | None = None

    @property
    def editable(self) -> bool:
        """False for pairs the engine never looks up (no identity or unknown tube)."""
        return self.equipment != UNRESOLVED_EQUIPMENT and self.tube != TUBE_IDENTITY_UNKNOWN


def labelled_frames(app_state: AppState) -> list[tuple[str, pd.DataFrame]]:
    """Return ``(opaque exam label, normalized frame)`` pairs for identity discovery.

    Loaded exams win when present (``rdsr_df`` is their concatenation); a
    single-file session labels its frame ``"Exam 1"``.
    """
    pairs = [
        (opaque_exam_label(i), exam.normalized_data)
        for i, exam in enumerate(app_state.loaded_exams)
        if getattr(exam, "normalized_data", None) is not None
    ]
    if not pairs and app_state.rdsr_df is not None:
        pairs.append((opaque_exam_label(0), app_state.rdsr_df))
    return pairs


def detect_by_exam(app_state: AppState, labels: dict[str, str] | None = None) -> dict[str, list[Pair]]:
    """Detected ``(equipment, tube)`` pairs per exam, honouring identity overrides."""
    overrides = app_state.kerma_meter_unresolved_labels if labels is None else labels
    return {
        exam: unique_equipment_tube_keys(
            [frame],
            explicit_label=app_state.kerma_meter_explicit_label,
            exam_labels=[exam],
            unresolved_labels=overrides,
        )
        for exam, frame in labelled_frames(app_state)
    }


def file_periods(app_state: AppState) -> Periods | None:
    """Load the calibration file with its periods, or ``None`` when unset or unreadable."""
    if not app_state.kerma_meter_file:
        return None
    try:
        return load_correction_periods(app_state.kerma_meter_file, app_state.kerma_meter_file_sheet or None)
    except (OSError, ValueError, TypeError):
        return None


def exam_table(app_state: AppState, exam: str, periods: Periods | None = None) -> dict[Pair, float] | None:
    """Merged manual + file table for one exam (manual wins; file uses the exam's stored period)."""
    periods = file_periods(app_state) if periods is None else periods
    file_part = (
        file_table_for_exam(periods, period_key=app_state.kerma_meter_periods.get(exam))
        if periods is not None
        else None
    )
    return merge_tables(file_part, manual_for_exam(app_state.kerma_meter_in_memory_table, exam))


def missing_by_exam(app_state: AppState, labels: dict[str, str] | None = None) -> dict[str, list[Pair]]:
    """Detected pairs per exam that the exam's merged table cannot supply."""
    periods = file_periods(app_state)
    out: dict[str, list[Pair]] = {}
    for exam, pairs in detect_by_exam(app_state, labels).items():
        miss = missing_keys(pairs, exam_table(app_state, exam, periods))
        if miss:
            out[exam] = miss
    return out


def missing_pairs(app_state: AppState, labels: dict[str, str] | None = None) -> list[Pair]:
    """Pairs missing in at least one exam (flat, sorted, de-duplicated)."""
    return sorted({pair for pairs in missing_by_exam(app_state, labels).values() for pair in pairs})


def needs_prompt(app_state: AppState) -> bool:
    """True when correction is enabled, asking is on and not suppressed, and an exam misses a pair."""
    return (
        app_state.kerma_meter_enable
        and app_state.kerma_meter_ask_for_missing
        and not app_state.kerma_meter_prompt_suppressed
        and bool(missing_by_exam(app_state))
    )


def valid_factor(value: object) -> bool:
    """True for a finite number greater than zero (what a correction factor must be)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return math.isfinite(value) and value > 0


class FactorModel:
    """Editable per-exam factor and calibration-period state behind the dialog.

    Parameters
    ----------
    app_state : AppState
        Session state: detection frames, stored manual table, file, defaults.
    labels : dict[str, str] | None
        Working copy of the per-exam unresolved-equipment overrides.
    """

    def __init__(self, app_state: AppState, labels: dict[str, str] | None = None) -> None:
        self.app_state = app_state
        self.labels = dict(app_state.kerma_meter_unresolved_labels) if labels is None else labels
        self.periods = file_periods(app_state)
        self.options: list[PeriodOption] = period_options(self.periods) if self.periods else []
        self._dated = dated_pairs(self.periods) if self.periods else set()
        self._edits: dict[tuple[str, Pair], float | None] = {}
        self._period_edits: dict[str, str] = {}
        self._cache: dict[str | None, dict[Pair, float]] = {}
        self.exams: list[str] = []
        self.detected: dict[str, list[Pair]] = {}
        self.set_labels(self.labels)

    def set_labels(self, labels: dict[str, str]) -> None:
        """Re-detect with new identity overrides, keeping edits and period choices."""
        self.labels = labels
        self.detected = detect_by_exam(self.app_state, labels)
        self.exams = list(self.detected)

    # ── calibration periods ────────────────────────────────────────────────

    def has_selector(self, exam: str) -> bool:
        """Whether *exam* has a detected pair with dated rows in the file."""
        return bool(self.options) and any(pair in self._dated for pair in self.detected.get(exam, []))

    def _selector_exams(self) -> list[str]:
        return [e for e in self.exams if self.has_selector(e)]

    def period_of(self, exam: str) -> str | None:
        """Calibration period key for *exam*: its own choice, else the previous exam's, else the most recent."""
        if not self.has_selector(exam):
            return None
        if exam in self._period_edits:
            return self._period_edits[exam]
        stored = self.app_state.kerma_meter_periods.get(exam)
        if stored:
            return stored
        earlier = [e for e in self._selector_exams() if self.exams.index(e) < self.exams.index(exam)]
        return self.period_of(earlier[-1]) if earlier else self.options[0].key

    def period_follows(self, exam: str) -> str | None:
        """Label of the exam whose period *exam* follows, or ``None`` when it has its own choice."""
        if not self.has_selector(exam) or exam in self._period_edits or self.app_state.kerma_meter_periods.get(exam):
            return None
        earlier = [e for e in self._selector_exams() if self.exams.index(e) < self.exams.index(exam)]
        return earlier[-1] if earlier else None

    def set_period(self, exam: str, key: str) -> None:
        """Record an explicit period choice for *exam* (later exams that follow it update)."""
        self._period_edits[exam] = key

    def _file_value(self, exam: str, pair: Pair) -> float | None:
        if self.periods is None:
            return None
        key = self.period_of(exam)
        if key not in self._cache:
            self._cache[key] = file_table_for_exam(self.periods, period_key=key)
        return self._cache[key].get(pair)

    # ── factors ────────────────────────────────────────────────────────────

    def _previous(self, exam: str, pair: Pair) -> str | None:
        earlier = [e for e in self.exams[: self.exams.index(exam)] if pair in self.detected.get(e, [])]
        return earlier[-1] if earlier else None

    def resolve(self, exam: str, pair: Pair) -> tuple[float | None, str, str | None]:
        """Return ``(value, source, followed exam)`` for one exam's pair."""
        if (exam, pair) in self._edits:
            return self._edits[(exam, pair)], SOURCE_ENTERED, None
        manual = manual_for_exam(self.app_state.kerma_meter_in_memory_table, exam)
        if pair in manual:
            return manual[pair], SOURCE_ENTERED, None
        prev = self._previous(exam, pair)
        if prev is not None and self.period_of(exam) == self.period_of(prev):
            value, source, _ = self.resolve(prev, pair)
            if source in (SOURCE_ENTERED, SOURCE_FOLLOWS):
                return value, SOURCE_FOLLOWS, prev
        file_value = self._file_value(exam, pair)
        if file_value is not None:
            return file_value, SOURCE_FILE, None
        return self.app_state.kerma_meter_default_factor, SOURCE_DEFAULT, None

    def set_value(self, exam: str, pair: Pair, value: float | None) -> None:
        """Record a user edit (``None`` for a blank field); later exams that follow it update."""
        self._edits[(exam, pair)] = value

    def rows(self) -> list[DialogRow]:
        """Resolved rows in exam order."""
        out: list[DialogRow] = []
        for exam in self.exams:
            for pair in self.detected[exam]:
                value, source, follows = self.resolve(exam, pair)
                out.append(DialogRow(exam, pair[0], pair[1], value, source, follows))
        return out

    def invalid(self) -> list[tuple[str, Pair]]:
        """Editable ``(exam, pair)`` rows whose value is blank, non-finite, or not above zero."""
        return [(r.exam, (r.equipment, r.tube)) for r in self.rows() if r.editable and not valid_factor(r.value)]

    def commit(self, dont_ask: bool) -> None:
        """Store entered factors per exam, identity overrides, period choices, and suppression.

        A row is written as a manual entry for its exam unless it resolved to the
        file value for that exam's period (file values keep following the file).
        Confirming a default or followed row records it as an explicit answer.

        Raises
        ------
        ValueError
            If any editable row has a blank, non-finite, or non-positive factor.
        """
        if self.invalid():
            raise ValueError("Every correction factor must be a finite number above zero.")
        state = self.app_state
        table = dict(state.kerma_meter_in_memory_table or {})
        for row in self.rows():
            if not row.editable:
                continue
            file_value = self._file_value(row.exam, (row.equipment, row.tube))
            if row.source == SOURCE_FILE or (
                row.source == SOURCE_FOLLOWS and file_value is not None and math.isclose(row.value, file_value)  # type: ignore[arg-type]
            ):
                continue
            table[(row.exam, row.equipment, row.tube)] = float(row.value)  # type: ignore[arg-type]
        state.kerma_meter_in_memory_table = table or None
        state.kerma_meter_unresolved_labels = {k: v.strip() for k, v in self.labels.items() if v and v.strip()}
        state.kerma_meter_periods = {e: k for e in self._selector_exams() if (k := self.period_of(e))}
        if dont_ask:
            state.kerma_meter_prompt_suppressed = True


def build_rows(app_state: AppState, labels: dict[str, str] | None = None) -> list[DialogRow]:
    """Rows grouped by exam with their initial values (manual > follow > file > default)."""
    return FactorModel(app_state, labels).rows()


def commit_cancel(app_state: AppState, dont_ask: bool) -> None:
    """Cancel: write nothing, so file values and earlier entries stay and the
    unanswered missing pairs resolve to ``default_factor`` in the engine."""
    if dont_ask:
        app_state.kerma_meter_prompt_suppressed = True


def unit_options(app_state: AppState) -> list[str]:
    """Selectable units for an unresolved exam: detected units plus file units."""
    units = {eq for pairs in detect_by_exam(app_state).values() for eq, _ in pairs if eq != UNRESOLVED_EQUIPMENT}
    units |= {eq for eq, _ in (file_periods(app_state) or {})}
    return sorted(units)
