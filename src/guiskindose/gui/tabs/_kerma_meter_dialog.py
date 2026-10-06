"""Kerma-meter correction-factor dialog: detection, pre-fill, commit, and UI.

The factor table is resolved as manual entry (``state.kerma_meter_in_memory_table``)
over file rows over ``default_factor``. This module detects the ``(equipment,
tube)`` pairs of the loaded exams, compares them with that merged table via
:func:`guiskindose.kerma_correction.missing_keys`, and asks for the missing ones.

The model functions (``detect_by_exam``, ``build_rows``, ``commit_confirm``,
``commit_cancel``, ``needs_prompt``) hold all decisions and have no UI
dependency, so they are unit-testable. The dialog itself never blocks a run:
Cancel keeps file values and earlier entries, and unanswered pairs simply use
``default_factor``.

Privacy: equipment labels may be site identifiers. They are shown in the dialog
but never logged.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

from nicegui import ui

from guiskindose.constants import TUBE_IDENTITY_UNKNOWN
from guiskindose.gui.ui_copy import copy_text
from guiskindose.kerma_correction import (
    UNRESOLVED_EQUIPMENT,
    load_correction_table,
    merge_tables,
    missing_keys,
    unique_equipment_tube_keys,
)
from guiskindose.privacy import opaque_exam_label

if TYPE_CHECKING:
    import pandas as pd

    from guiskindose.gui.state import AppState

SOURCE_ENTERED = "manual"
SOURCE_FILE = "file"
SOURCE_DEFAULT = "default"

_TITLE = "text-lg font-bold"
_BODY = "text-sm text-grey-7"
_ACTIONS = "w-full justify-end gap-2"
_PRIMARY = "modern-btn modern-btn-teal"

Pair = tuple[str, str]


@dataclass(frozen=True)
class DialogRow:
    """One ``(equipment, tube)`` row of one exam, with its pre-filled value and source."""

    exam: str
    equipment: str
    tube: str
    value: float
    source: str

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
    """Detected ``(equipment, tube)`` pairs per exam, honouring identity overrides.

    Parameters
    ----------
    app_state : AppState
        Session state holding the loaded frames and ``explicit_label``.
    labels : dict[str, str] | None
        Per-exam identity overrides to apply; defaults to the stored ones.
    """
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


def file_table(app_state: AppState) -> dict[Pair, float] | None:
    """Load the calibration file table, or ``None`` when unset or unreadable."""
    if not app_state.kerma_meter_file:
        return None
    try:
        return load_correction_table(app_state.kerma_meter_file, app_state.kerma_meter_file_sheet or None)
    except (OSError, ValueError, TypeError):
        return None


def merged_table(app_state: AppState) -> dict[Pair, float] | None:
    """Merge file rows with manual entries (manual wins)."""
    return merge_tables(file_table(app_state), app_state.kerma_meter_in_memory_table)


def missing_pairs(app_state: AppState, labels: dict[str, str] | None = None) -> list[Pair]:
    """Detected pairs across all exams that the merged table cannot supply."""
    detected = sorted({pair for pairs in detect_by_exam(app_state, labels).values() for pair in pairs})
    return missing_keys(detected, merged_table(app_state))


def needs_prompt(app_state: AppState) -> bool:
    """True when correction is enabled, asking is on and not suppressed, and a pair is missing."""
    return (
        app_state.kerma_meter_enable
        and app_state.kerma_meter_ask_for_missing
        and not app_state.kerma_meter_prompt_suppressed
        and bool(missing_pairs(app_state))
    )


def build_rows(app_state: AppState, labels: dict[str, str] | None = None) -> list[DialogRow]:
    """Rows grouped by exam, pre-filled manual > file > ``default_factor``."""
    manual = app_state.kerma_meter_in_memory_table or {}
    from_file = file_table(app_state) or {}
    rows: list[DialogRow] = []
    for exam, pairs in detect_by_exam(app_state, labels).items():
        for pair in pairs:
            if pair in manual:
                value, source = manual[pair], SOURCE_ENTERED
            elif pair in from_file:
                value, source = from_file[pair], SOURCE_FILE
            else:
                value, source = app_state.kerma_meter_default_factor, SOURCE_DEFAULT
            rows.append(DialogRow(exam, pair[0], pair[1], float(value), source))
    return rows


def commit_confirm(
    app_state: AppState,
    rows: list[DialogRow],
    values: dict[Pair, float],
    labels: dict[str, str],
    dont_ask: bool,
) -> None:
    """Store the dialog result: entered factors, identity overrides, suppression.

    A row is written as a manual entry unless it came from the file and was left
    unchanged, so file values keep following the file and earlier manual entries
    are retained. Confirming a default row records it as an explicit answer.
    """
    table = dict(app_state.kerma_meter_in_memory_table or {})
    for row in rows:
        pair = (row.equipment, row.tube)
        if not row.editable or pair not in values:
            continue
        value = float(values[pair])
        if row.source == SOURCE_FILE and math.isclose(value, row.value):
            continue
        table[pair] = value
    app_state.kerma_meter_in_memory_table = table or None
    app_state.kerma_meter_unresolved_labels = {k: v.strip() for k, v in labels.items() if v and v.strip()}
    if dont_ask:
        app_state.kerma_meter_prompt_suppressed = True


def commit_cancel(app_state: AppState, dont_ask: bool) -> None:
    """Cancel: write nothing, so file values and earlier entries stay and the
    unanswered missing pairs resolve to ``default_factor`` in the engine."""
    if dont_ask:
        app_state.kerma_meter_prompt_suppressed = True


def _unit_options(app_state: AppState) -> list[str]:
    """Selectable units for an unresolved exam: detected units plus file entries."""
    units = {eq for pairs in detect_by_exam(app_state).values() for eq, _ in pairs if eq != UNRESOLVED_EQUIPMENT}
    units |= {eq for eq, _ in (file_table(app_state) or {})}
    return sorted(units)


def _build_exam_rows(
    exam: str,
    rows: list[DialogRow],
    values: dict[Pair, float],
    labels: dict[str, str],
    options: list[str],
    refresh,
) -> None:
    """Render one exam group: optional unit chooser, then one row per pair."""
    ui.label(exam).classes("text-subtitle2 q-mt-sm")
    if any(r.equipment == UNRESOLVED_EQUIPMENT for r in rows):
        ui.label(copy_text("kerma.dialog.unresolved")).classes(_BODY)

        def _choose(event, exam_id: str = exam) -> None:
            labels[exam_id] = str(event.value or "")
            refresh()

        ui.select(
            options,
            label=copy_text("kerma.dialog.unit_label"),
            value=labels.get(exam) or None,
            with_input=True,
            new_value_mode="add-unique",
            clearable=True,
            on_change=_choose,
        ).classes("w-full")
    for row in rows:
        _build_row(row, values)


def _source_text(source: str) -> str:
    """Badge text for a row source."""
    if source == SOURCE_ENTERED:
        return copy_text("kerma.dialog.source.entered")
    if source == SOURCE_FILE:
        return copy_text("kerma.dialog.source.file")
    return copy_text("kerma.dialog.source.default")


def _build_row(row: DialogRow, values: dict[Pair, float]) -> None:
    """Render one pair row with its source badge."""
    pair = (row.equipment, row.tube)
    with ui.row().classes("w-full items-center gap-2"):
        if not row.editable:
            ui.label(f"{row.equipment} / {row.tube}").classes("grow")
            note = "kerma.dialog.unknown_tube" if row.tube == TUBE_IDENTITY_UNKNOWN else "kerma.dialog.no_identity"
            ui.badge(copy_text(note), color="orange").props("outline")
            return
        values.setdefault(pair, row.value)

        def _set(event, key: Pair = pair) -> None:
            if event.value:
                values[key] = float(event.value)

        ui.number(
            label=f"{row.equipment} / {row.tube}", value=values[pair], min=0.01, step=0.01, on_change=_set
        ).classes("grow")
        is_default = row.source == SOURCE_DEFAULT
        ui.badge(_source_text(row.source), color="orange" if is_default else "primary").props(
            "" if is_default else "outline"
        )


async def kerma_meter_dialog() -> None:
    """Show the correction-factor dialog; apply Confirm or Cancel to ``state``.

    Rows are grouped by exam in a scrollable area. Choosing a unit for an exam
    with unresolved equipment re-detects, so that exam's rows switch to the
    chosen unit. Never blocks the run: the caller proceeds either way.
    """
    from guiskindose.gui.state import state

    labels = dict(state.kerma_meter_unresolved_labels)
    values: dict[Pair, float] = {}
    with ui.dialog() as dialog, ui.card().classes("w-full max-w-2xl gap-3"):
        ui.label(copy_text("kerma.dialog.title")).classes(_TITLE)
        ui.label(copy_text("kerma.dialog.body")).classes(_BODY)

        @ui.refreshable
        def rows_area() -> None:
            rows = build_rows(state, labels)
            options = _unit_options(state)
            for exam in dict.fromkeys(r.exam for r in rows):
                _build_exam_rows(exam, [r for r in rows if r.exam == exam], values, labels, options, rows_area.refresh)

        with ui.scroll_area().classes("w-full h-96"):
            rows_area()
        dont_ask = ui.checkbox(copy_text("kerma.dialog.dont_ask"))
        with ui.row().classes(_ACTIONS):
            ui.button("Cancel", on_click=lambda: dialog.submit("cancel")).props("flat")
            ui.button("Confirm", on_click=lambda: dialog.submit("ok")).classes(_PRIMARY)

    result = await dialog
    if result == "ok":
        commit_confirm(state, build_rows(state, labels), values, labels, bool(dont_ask.value))
    else:
        commit_cancel(state, bool(dont_ask.value))
    dialog.delete()


async def maybe_prompt_after_load() -> bool:
    """Load-time check: open the dialog once per ``(input_revision, enable)`` change.

    Returns True when the dialog was shown. Skips when correction is off, asking
    is off or suppressed, or nothing is missing.
    """
    from guiskindose.gui.state import state

    key = (state.input_revision, state.kerma_meter_enable)
    if state.kerma_meter_checked_key == key:
        return False
    state.kerma_meter_checked_key = key
    if not needs_prompt(state):
        return False
    await kerma_meter_dialog()
    return True


async def prompt_at_calculate() -> bool:
    """Calculate-time guard: re-open the dialog once if pairs are still unconfirmed.

    Never blocks the run. Returns True when the dialog was shown.
    """
    from guiskindose.gui.state import state

    if state.kerma_meter_calc_reprompted or not needs_prompt(state):
        return False
    state.kerma_meter_calc_reprompted = True
    await kerma_meter_dialog()
    return True
