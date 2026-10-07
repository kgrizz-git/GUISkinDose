"""Kerma-meter correction-factor dialog UI and load-time watcher.

The decisions live in :mod:`._kerma_meter_model` (no UI imports). This module
renders them: rows per exam with a "follows Exam N" state for Exam 2 and later, a
per-exam calibration-period selector when the file has dated rows, unit choosers
for exams without equipment identity, and inline validation. The dialog never
blocks a run: Cancel keeps file values and earlier entries, and unanswered pairs
use ``default_factor``.

Privacy: equipment labels and calibration dates are shown but never logged.
"""

from __future__ import annotations

from nicegui import ui

from guiskindose.constants import TUBE_IDENTITY_UNKNOWN
from guiskindose.gui.state import reset_results
from guiskindose.gui.ui_copy import copy_text

from ._kerma_meter_model import (
    SOURCE_DEFAULT,
    SOURCE_ENTERED,
    SOURCE_FILE,
    SOURCE_FOLLOWS,
    DialogRow,
    FactorModel,
    Pair,
    build_rows,
    commit_cancel,
    detect_by_exam,
    equipment_display_names,
    labelled_frames,
    missing_by_exam,
    missing_pairs,
    needs_prompt,
    unit_options,
    valid_factor,
)

__all__ = [
    "SOURCE_DEFAULT",
    "SOURCE_ENTERED",
    "SOURCE_FILE",
    "SOURCE_FOLLOWS",
    "DialogRow",
    "FactorModel",
    "Pair",
    "build_rows",
    "commit_cancel",
    "detect_by_exam",
    "kerma_meter_dialog",
    "labelled_frames",
    "maybe_prompt_after_load",
    "missing_by_exam",
    "missing_pairs",
    "needs_prompt",
    "open_review_dialog",
    "prompt_at_calculate",
    "valid_factor",
]

_TITLE = "text-lg font-bold"
_BODY = "text-sm text-grey-7"
_ACTIONS = "w-full justify-end gap-2"
_PRIMARY = "modern-btn modern-btn-teal"


def _source_text(row: DialogRow) -> str:
    """Badge text for a row source (a following row names the exam it follows)."""
    if row.source == SOURCE_FOLLOWS:
        return f"{copy_text('kerma.dialog.source.follows')} {row.follows}"
    if row.source == SOURCE_ENTERED:
        return copy_text("kerma.dialog.source.entered")
    if row.source == SOURCE_FILE:
        return copy_text("kerma.dialog.source.file")
    return copy_text("kerma.dialog.source.default")


class _DialogView:
    """Widgets of one open dialog, kept in sync with a :class:`FactorModel`."""

    def __init__(self, model: FactorModel, refresh) -> None:
        self.model = model
        self.refresh = refresh
        self.fields: dict[tuple[str, Pair], tuple[ui.number, ui.badge]] = {}
        self.selectors: dict[str, tuple[ui.select, ui.label]] = {}
        self.syncing = False
        self.display_names = equipment_display_names(model.app_state)

    def _shown(self, equipment: str) -> str:
        """Display spelling of an equipment label (matching stays casefolded)."""
        return self.display_names.get(equipment, equipment)

    def build_unit_choosers(self) -> None:
        """One unit chooser per exam with events that carry no equipment identity.

        The chooser stays after a unit was chosen (pre-selected, clearable), so the
        choice can be changed or removed.
        """
        for exam in self.model.unresolved_exams():
            ui.label(exam).classes("text-subtitle2 q-mt-sm")
            ui.label(copy_text("kerma.dialog.unresolved")).classes(_BODY)

            def _choose(event, exam_id: str = exam) -> None:
                labels = dict(self.model.labels)
                labels[exam_id] = str(event.value or "")
                self.model.set_labels(labels)
                self.refresh()

            # The current override must be an option, or the select rejects its own value.
            options = sorted({*unit_options(self.model.app_state), *(v for v in self.model.labels.values() if v)})
            ui.select(
                options,
                label=copy_text("kerma.dialog.unit_label"),
                value=self.model.labels.get(exam) or None,
                with_input=True,
                new_value_mode="add-unique",
                clearable=True,
                on_change=_choose,
            ).classes("w-full")

    def build_exam(self, exam: str, rows: list[DialogRow]) -> None:
        """Render one exam: optional calibration-period selector, then one row per pair."""
        ui.label(exam).classes("text-subtitle2 q-mt-sm")
        if self.model.has_selector(exam):
            self._build_selector(exam)
        for row in rows:
            self._build_row(row)

    def _build_selector(self, exam: str) -> None:
        options = {o.key: o.label for o in self.model.options}

        def _pick(event, exam_id: str = exam) -> None:
            if self.syncing or event.value is None:
                return
            self.model.set_period(exam_id, event.value)
            self.sync()

        with ui.row().classes("w-full items-center gap-2"):
            select = ui.select(
                options,
                label=copy_text("kerma.dialog.period_label"),
                value=self.model.period_of(exam),
                on_change=_pick,
            ).classes("grow")
            note = ui.label(self._period_note(exam)).classes("text-xs text-grey-6")
        self.selectors[exam] = (select, note)

    def _period_note(self, exam: str) -> str:
        followed = self.model.period_follows(exam)
        return f"{copy_text('kerma.dialog.source.follows')} {followed}" if followed else ""

    def _build_row(self, row: DialogRow) -> None:
        pair = (row.equipment, row.tube)
        with ui.row().classes("w-full items-center gap-2"):
            if not row.editable:
                ui.label(f"{self._shown(row.equipment)} / {row.tube}").classes("grow")
                note = "kerma.dialog.unknown_tube" if row.tube == TUBE_IDENTITY_UNKNOWN else "kerma.dialog.no_identity"
                ui.badge(copy_text(note), color="orange").props("outline")
                return

            def _set(event, key: tuple[str, Pair] = (row.exam, pair)) -> None:
                if self.syncing:
                    return
                self.model.set_value(key[0], key[1], event.value)  # None when blank: caught on Confirm
                self.sync()

            field = ui.number(
                label=f"{self._shown(row.equipment)} / {row.tube}", value=row.value, min=0.01, step=0.01, on_change=_set
            ).classes("grow")
            badge = ui.badge(_source_text(row))
            self._style_badge(badge, row)
        self.fields[(row.exam, pair)] = (field, badge)

    @staticmethod
    def _style_badge(badge: ui.badge, row: DialogRow) -> None:
        badge.set_text(_source_text(row))
        badge.props(f"color={'orange' if row.source == SOURCE_DEFAULT else 'primary'}")
        if row.source == SOURCE_DEFAULT:
            badge.props(remove="outline")
        else:
            badge.props("outline")

    def sync(self) -> None:
        """Push model values (followers, period notes) into the widgets without echoing edits."""
        self.syncing = True
        try:
            for row in self.model.rows():
                widgets = self.fields.get((row.exam, (row.equipment, row.tube)))
                if widgets is None:
                    continue
                field, badge = widgets
                if row.value != field.value and not (row.value is None and field.value is None):
                    field.set_value(row.value)
                self._style_badge(badge, row)
            for exam, (select, note) in self.selectors.items():
                if select.value != self.model.period_of(exam):
                    select.set_value(self.model.period_of(exam))
                note.set_text(self._period_note(exam))
        finally:
            self.syncing = False

    def mark_invalid(self, bad: list[tuple[str, Pair]]) -> None:
        """Flag the fields of invalid rows; clear the flag on the others."""
        bad_set = set(bad)
        for key, (field, _badge) in self.fields.items():
            if key in bad_set:
                field.props("error")
            else:
                field.props(remove="error")


async def kerma_meter_dialog() -> None:
    """Show the correction-factor dialog; apply Confirm or Cancel to ``state``.

    Rows are shown per exam. Exam 2 and later follow the previous exam's value
    (and calibration period) until edited, and say so. Confirm is blocked while any
    factor is blank or not a number above zero. If the loaded data changes while the
    dialog is open, the result is discarded with a notice. Never blocks the run:
    Cancel is always allowed.
    """
    from guiskindose.gui.state import state

    revision = state.input_revision
    model = FactorModel(state)
    view: _DialogView | None = None
    with ui.dialog() as dialog, ui.card().classes("w-full max-w-2xl gap-3"):
        ui.label(copy_text("kerma.dialog.title")).classes(_TITLE)
        ui.label(copy_text("kerma.dialog.body")).classes(_BODY)

        @ui.refreshable
        def rows_area() -> None:
            nonlocal view
            view = _DialogView(model, rows_area.refresh)
            view.build_unit_choosers()
            rows = model.rows()
            for exam in model.exams:
                view.build_exam(exam, [r for r in rows if r.exam == exam])

        with ui.scroll_area().classes("w-full h-96"):
            rows_area()
        error = ui.label(copy_text("kerma.dialog.error_invalid")).classes("text-sm text-negative")
        error.visible = False
        dont_ask = ui.checkbox(copy_text("kerma.dialog.dont_ask"))

        def _confirm() -> None:
            bad = model.invalid()
            error.visible = bool(bad)
            if view is not None:
                view.mark_invalid(bad)
            if not bad:
                dialog.submit("ok")

        with ui.row().classes(_ACTIONS):
            ui.button("Cancel", on_click=lambda: dialog.submit("cancel")).props("flat")
            ui.button("Confirm", on_click=_confirm).classes(_PRIMARY)

    result = await dialog
    if state.input_revision != revision:
        ui.notify(copy_text("kerma.dialog.stale_discarded"), type="warning")
    elif result == "ok":
        if model.commit(bool(dont_ask.value)):
            reset_results()  # factors, units, or periods changed: earlier results are stale
    else:
        commit_cancel(state, bool(dont_ask.value))
    dialog.delete()


async def open_review_dialog() -> bool:
    """Open the dialog on demand (Settings button) so confirmed factors can be edited.

    The dialog lists every detected pair, not only missing ones. Returns False,
    with a notice, when correction is off or no events are loaded.
    """
    from guiskindose.gui.state import state

    if not state.kerma_meter_enable or not detect_by_exam(state):
        ui.notify(copy_text("kerma.review.unavailable"), type="info")
        return False
    await kerma_meter_dialog()
    return True


async def maybe_prompt_after_load() -> bool:
    """Load-time check: open the dialog once per change of the loaded events, the
    enable switch, the calibration file or sheet, or the ask-for-missing toggle.

    Returns True when the dialog was shown. Skips when correction is off, asking
    is off or suppressed, or nothing is missing.
    """
    from guiskindose.gui.state import state

    key = (
        state.input_revision,
        state.kerma_meter_enable,
        state.kerma_meter_file,
        state.kerma_meter_file_sheet,
        state.kerma_meter_ask_for_missing,
    )
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
