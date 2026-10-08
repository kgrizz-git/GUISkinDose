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
from collections.abc import Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from guiskindose.constants import TUBE_IDENTITY_UNKNOWN
from guiskindose.kerma_correction import (
    UNRESOLVED_EQUIPMENT,
    effective_period,
    load_correction_periods,
    manual_for_exam,
    merge_tables,
    missing_keys,
    normalize_equipment_label,
    resolve_manual,
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


def equipment_display_names(app_state: AppState, extra_labels: Iterable[object] = ()) -> dict[str, str]:
    """Map each casefolded equipment label to its first-seen original spelling.

    Matching always uses the casefolded label; this only restores the user's
    spelling (``DEMO-ROOM-2`` rather than ``demo-room-2``) for display. Sources are
    the loaded frames' serial and station columns, the explicit label, and the
    per-exam unit overrides, plus ``extra_labels`` (labels typed in an open dialog).
    Labels with no known original (for example from a
    calibration file) are not in the map.
    """
    seen: dict[str, str] = {}

    def _note(raw: object) -> None:
        key = normalize_equipment_label(raw) if isinstance(raw, str) else None
        if key is not None:
            seen.setdefault(key, str(raw).strip())

    _note(app_state.kerma_meter_explicit_label)
    for value in (*app_state.kerma_meter_unresolved_labels.values(), *extra_labels):
        _note(value)
    for _exam, frame in labelled_frames(app_state):
        for column in ("device_serial", "station_name"):
            if column in frame.columns:
                for raw in frame[column].dropna().unique():
                    _note(raw)
    return seen


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
        file_table_for_exam(periods, period_key=effective_period(app_state.kerma_meter_periods, exam))
        if periods is not None
        else None
    )
    manual = manual_for_exam(app_state.kerma_meter_in_memory_table, exam, periods=app_state.kerma_meter_periods)
    return merge_tables(file_part, manual)


def missing_by_exam(app_state: AppState, labels: dict[str, str] | None = None) -> dict[str, list[Pair]]:
    """Detected pairs per exam that the exam's merged table cannot supply."""
    periods = file_periods(app_state)
    out: dict[str, list[Pair]] = {}
    for exam, pairs in detect_by_exam(app_state, labels).items():
        miss = [
            pair
            for pair in missing_keys(pairs, exam_table(app_state, exam, periods))
            if (exam, *pair) not in app_state.kerma_meter_acknowledged
        ]
        if miss:
            out[exam] = miss
    return out


def missing_pairs(app_state: AppState, labels: dict[str, str] | None = None) -> list[Pair]:
    """Pairs missing in at least one exam (flat, sorted, de-duplicated)."""
    return sorted({pair for pairs in missing_by_exam(app_state, labels).values() for pair in pairs})


def periods_unchosen(app_state: AppState) -> list[str]:
    """Exams with a detected pair that has dated rows in the file but no stored period choice.

    Such an exam would silently use the current or most recent period, so the
    dialog asks even when every factor is already covered.
    """
    periods = file_periods(app_state)
    if not periods or not period_options(periods):
        return []
    dated = dated_pairs(periods)
    return [
        exam
        for exam, pairs in detect_by_exam(app_state).items()
        if any(pair in dated for pair in pairs)
        and exam not in app_state.kerma_meter_periods
        and exam not in app_state.kerma_meter_periods_acknowledged
    ]


def needs_prompt(app_state: AppState) -> bool:
    """True when correction is on, asking is on and not suppressed, and the dialog has something to settle.

    That is an exam missing a factor, or an exam with dated calibration rows and no
    period chosen yet.
    """
    return (
        app_state.kerma_meter_enable
        and app_state.kerma_meter_ask_for_missing
        and not app_state.kerma_meter_prompt_suppressed
        and (bool(missing_by_exam(app_state)) or bool(periods_unchosen(app_state)))
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

    def effective_periods(self) -> dict[str, str]:
        """Period choices exactly as Confirm stores them, so the dialog shows what the engine applies.

        Stored choices plus this session's edits, plus the displayed default (the file's
        most recent period) for the first selector exam that has no choice yet. Later
        exams follow through :func:`effective_period`, as they do in the engine.
        """
        selector_exams = self._selector_exams()
        periods = {e: k for e, k in self.app_state.kerma_meter_periods.items() if e not in self._period_edits}
        periods.update({e: k for e, k in self._period_edits.items() if e in selector_exams})
        for exam in selector_exams:
            if effective_period(periods, exam) is None and self.options:
                periods[exam] = self.options[0].key
        return periods

    def period_of(self, exam: str) -> str | None:
        """Calibration period key in effect for *exam* (own choice, else an earlier exam's, else the default)."""
        return effective_period(self.effective_periods(), exam)

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

    def _manual_table(self) -> dict[tuple[str, ...], float | None]:
        """Stored manual entries overlaid with this session's edits (``None`` = blank field)."""
        table: dict[tuple[str, ...], float | None] = dict(self.app_state.kerma_meter_in_memory_table or {})
        table.update({(exam, *pair): value for (exam, pair), value in self._edits.items()})
        return table

    def resolve(self, exam: str, pair: Pair) -> tuple[float | None, str, str | None]:
        """Return ``(value, source, followed exam)`` for one exam's pair.

        The manual part is :func:`resolve_manual`, the very function the engine uses.
        """
        resolved = resolve_manual(self._manual_table(), self.effective_periods(), exam, pair)
        if resolved is not None:
            value, followed = resolved
            return (value, SOURCE_ENTERED, None) if followed is None else (value, SOURCE_FOLLOWS, followed)
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

    def unresolved_exams(self) -> list[str]:
        """Exams with events that carry no equipment identity, judged without any override.

        The unit chooser stays available for these exams even after a unit was
        chosen, so the choice can be changed or cleared.
        """
        raw = detect_by_exam(self.app_state, {})
        return [exam for exam, pairs in raw.items() if any(eq == UNRESOLVED_EQUIPMENT for eq, _ in pairs)]

    def commit(self, dont_ask: bool) -> bool:
        """Store entered factors per exam, identity overrides, period choices, and suppression.

        Only explicit values are stored: a value the user entered or edited (for a
        followed or file row too) becomes a manual entry for its exam. Rows still
        following an earlier exam store nothing, so "follows Exam N" survives
        reopening and later edits of the earlier exam reach them. File rows store
        nothing, so they keep following the file. A default row left untouched is
        only recorded as acknowledged (it is not asked about again), so a file row
        added later still wins.

        Calibration periods: explicit choices are stored, plus the displayed default
        (the file's most recent period) for the first selector exam, so the engine
        applies exactly the period the dialog showed; later exams follow it. Confirm
        also acknowledges the period of every selector exam, so the dialog does not
        ask again.

        Returns
        -------
        bool
            True when the stored factors, identity overrides, or period choices
            changed, so the caller must invalidate calculation results.

        Raises
        ------
        ValueError
            If any editable row has a blank, non-finite, or non-positive factor.
        """
        if self.invalid():
            raise ValueError("Every correction factor must be a finite number above zero.")
        state = self.app_state
        before = self._snapshot()
        table = dict(state.kerma_meter_in_memory_table or {})
        acknowledged = set(state.kerma_meter_acknowledged)
        for row in self.rows():
            if not row.editable:
                continue
            key = (row.exam, row.equipment, row.tube)
            if row.source == SOURCE_ENTERED:
                table[key] = float(row.value)  # type: ignore[arg-type]
            elif row.source == SOURCE_DEFAULT:
                acknowledged.add(key)
        state.kerma_meter_in_memory_table = table or None
        state.kerma_meter_acknowledged = acknowledged
        state.kerma_meter_unresolved_labels = {k: v.strip() for k, v in self.labels.items() if v and v.strip()}
        state.kerma_meter_periods = self.effective_periods()
        state.kerma_meter_periods_acknowledged = set(state.kerma_meter_periods_acknowledged) | set(
            self._selector_exams()
        )
        if dont_ask:
            state.kerma_meter_prompt_suppressed = True
        return before != self._snapshot()

    def _snapshot(self) -> tuple[object, ...]:
        """Copy of everything ``commit`` can change, for change detection."""
        state = self.app_state
        return (
            dict(state.kerma_meter_in_memory_table or {}),
            dict(state.kerma_meter_unresolved_labels),
            dict(state.kerma_meter_periods),
            set(state.kerma_meter_acknowledged),
            set(state.kerma_meter_periods_acknowledged),
        )


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
