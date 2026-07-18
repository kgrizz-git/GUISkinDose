"""Calculate tab — run dose calculation with settings summary and progress.

Refactor plan Phase 3.3f. ``do_calculate`` touches drawer chrome (``psd_label``,
``run_btn_drawer``) and ``tabs`` via ``PageContext``. The drawer run button's
click handler is wired here even though the button is built in the drawer.
"""

from __future__ import annotations

from dataclasses import dataclass

from nicegui import run, ui

from ..components import HelpButton
from ..concurrency import operation_guard, require_io_result
from ..helpers import below_floor_event_count, run_calculation
from ..page_context import PageContext
from ..summary_formatters import format_patient_offsets
from ..state import state
from .settings import BELOW_FLOOR_KVP_OPTIONS, _format_table_offset_line

_MAX_TOASTS: int = 5
_SUMMARY_LABEL_CLASSES = "text-grey-5 font-normal text-[11px] uppercase tracking-tighter"
_SUMMARY_VALUE_CLASSES = "font-bold text-[13px]"
_SUMMARY_ROW_CLASSES = "items-baseline gap-2"


def _format_patient_offsets() -> str:
    return format_patient_offsets(state)


async def below_floor_prompt(n_below: int) -> bool:
    """Confirm below-floor kVp handling before a calculation.

    Shows the count of sub-floor events and the policy choice (pre-filled from the
    Settings default). Writes the chosen policy (and manual kVp) back to ``state``
    so the run — and optionally the persistent default — uses it. Returns ``True``
    to proceed with the calculation, ``False`` if the user cancels.
    """
    with ui.dialog() as dialog, ui.card().classes("w-full max-w-lg gap-3"):
        ui.label("Events below the 25 kV HVL floor").classes("text-lg font-bold")
        ui.label(
            f"{n_below} loaded event(s) have a kVp below the 25 kV HVL table floor. "
            "Choose how to handle them for this calculation."
        ).classes("text-sm text-grey-7")

        policy_select = ui.select(
            BELOW_FLOOR_KVP_OPTIONS,
            label="Handling policy",
            value=state.below_floor_kvp_policy,
        ).classes("w-full")

        manual_kvp = ui.number(
            label="Manual kVp", value=state.below_floor_kvp_manual, min=25.0, max=175.0, step=1.0
        ).classes("w-full")
        manual_kvp.bind_visibility_from(policy_select, "value", backward=lambda v: v == "manual")

        dont_ask = ui.checkbox("Don't ask again this session")

        with ui.row().classes("w-full justify-end gap-2"):
            ui.button("Cancel", on_click=lambda: dialog.submit("cancel")).props("flat")
            ui.button("Run", on_click=lambda: dialog.submit("run")).classes("modern-btn modern-btn-teal")

    result = await dialog
    if result != "run":
        return False

    state.below_floor_kvp_policy = policy_select.value
    state.below_floor_kvp_manual = float(manual_kvp.value or state.below_floor_kvp_manual)
    if dont_ask.value:
        state.below_floor_prompt_suppressed = True
    return True


@dataclass
class _CalculationControls:
    button: ui.button
    progress: ui.linear_progress
    status_label: ui.label


class _CalculationController:
    """Own Calculate-tab references while application state remains in ``state``."""

    def __init__(self, ctx: PageContext) -> None:
        self.ctx = ctx
        self.controls: _CalculationControls | None = None

    async def do_calculate(self) -> None:
        if state.rdsr_df is None:
            ui.notify("Load a file first (tab 1)", color="warning")
            return
        if state.import_has_errors:
            ui.notify("Fix import errors before calculating (tab 1)", color="warning")
            return
        if not await self._below_floor_policy_is_ready():
            return

        with operation_guard("starting a calculation") as proceed:
            if not proceed:
                return
            ok, message = await self._run_calculation()
        self._finish_calculation(ok, message)

    async def _below_floor_policy_is_ready(self) -> bool:
        if state.below_floor_prompt_suppressed:
            return True
        n_below = below_floor_event_count(state)
        return n_below <= 0 or await below_floor_prompt(n_below)

    async def _run_calculation(self) -> tuple[bool, str]:
        controls = self._require_controls()
        controls.button.disable()
        self.ctx.run_btn_drawer.disable()
        self.ctx.flush_geometry_pending()
        controls.progress.visible = True
        controls.progress.set_value(0)
        controls.status_label.set_text("Starting...")
        try:
            return require_io_result(await run.io_bound(run_calculation, state, self._update_progress))
        finally:
            controls.progress.set_value(1.0)
            controls.button.enable()
            self.ctx.run_btn_drawer.enable()

    def _update_progress(self, fraction: float, label: str) -> None:
        controls = self._require_controls()
        controls.progress.set_value(fraction)
        controls.status_label.set_text(label)

    def _finish_calculation(self, ok: bool, message: str) -> None:
        if ok:
            self._show_success(message)
            return
        state.calculation_done = False
        state.output = None
        state.multi_exam_result = None
        state.psd = None
        state.air_kerma = None
        state.dosemap_fig = None
        self.ctx.psd_label.set_text("PSD: 0.00 mGy")
        self._require_controls().status_label.set_text("Calculation failed")
        ui.notify(f"Error: {message[:300]}", type="negative", timeout=10000)

    def _show_success(self, message: str) -> None:
        self.ctx.psd_label.set_text(f"PSD: {state.psd:.2f} mGy")
        self.ctx.clear_offset_stale_caption()
        ui.notify(f"✓ {message}", color="positive")
        self.ctx.tabs.set_value("results")
        controls = self._require_controls()
        if not state.calc_warnings:
            controls.status_label.set_text(f"Done — {message}")
            return

        controls.status_label.set_text(f"Done — {message} · {len(state.calc_warnings)} warning(s), see notifications")
        self._show_calculation_warnings()

    def _show_calculation_warnings(self) -> None:
        for index, warning in enumerate(state.calc_warnings):
            if index < _MAX_TOASTS:
                ui.notify(warning, type="warning", timeout=12000, multi_line=True)
                continue
            ui.notify(
                f"... and {len(state.calc_warnings) - _MAX_TOASTS} more warnings. See Results tab for the full list.",
                type="warning",
                timeout=12000,
            )
            break

    def _require_controls(self) -> _CalculationControls:
        if self.controls is None:
            raise RuntimeError("Calculate controls are not initialized.")
        return self.controls


def _build_input_data_summary() -> None:
    with ui.column().classes("gap-2"):
        ui.label("INPUT DATA").classes(
            "text-sm text-aurora-teal font-bold tracking-widest border-b border-white/10 w-full q-pb-xs"
        )
        with ui.column().classes("gap-1"):
            with ui.column().classes("gap-0"):
                ui.label("File:").classes(_SUMMARY_LABEL_CLASSES)
                ui.label().bind_text_from(
                    state, "file_name", backward=lambda v: "Loaded" if v else "None"
                ).classes(f"{_SUMMARY_VALUE_CLASSES} truncate w-full")
            with ui.row().classes(_SUMMARY_ROW_CLASSES):
                ui.label("Events:").classes(_SUMMARY_LABEL_CLASSES)
                ui.label().bind_text_from(
                    state, "rdsr_df", backward=lambda v: f"{len(v) if v is not None else 0}"
                ).classes(_SUMMARY_VALUE_CLASSES)
            with ui.column().classes("gap-0"):
                ui.label("Scanner:").classes(_SUMMARY_LABEL_CLASSES)
                ui.label().bind_text_from(
                    state, "manufacturer", backward=lambda v: f"{v} {state.model}"
                ).classes(_SUMMARY_VALUE_CLASSES)
                ui.label().bind_text_from(
                    state, "normalization_method", backward=lambda v: f"({v})"
                ).classes("text-[10px] opacity-40 italic")


def _build_phantom_setup_summary() -> None:
    with ui.column().classes("gap-2"):
        ui.label("PHANTOM SETUP").classes(
            "text-sm text-aurora-purple font-bold tracking-widest border-b border-white/10 w-full q-pb-xs"
        )
        with ui.column().classes("gap-1"):
            with ui.row().classes(_SUMMARY_ROW_CLASSES):
                ui.label("Model:").classes(_SUMMARY_LABEL_CLASSES)
                ui.label().bind_text_from(
                    state, "phantom_model", backward=lambda v: f"{v}"
                ).classes(_SUMMARY_VALUE_CLASSES)
            with ui.column().classes("gap-0"):
                ui.label("Patient Offsets:").classes(_SUMMARY_LABEL_CLASSES)
                patient_offset_summary = ui.label(_format_patient_offsets()).classes(
                    _SUMMARY_VALUE_CLASSES
                )
                patient_offset_summary.bind_text_from(
                    state, "per_exam_offsets_version", backward=lambda _v: _format_patient_offsets(),
                )
                patient_offset_summary.bind_text_from(
                    state, "is_multi_exam", backward=lambda _v: _format_patient_offsets()
                )
            with ui.column().classes("gap-0"):
                ui.label("Table Offsets:").classes(_SUMMARY_LABEL_CLASSES)
                table_offset_summary = ui.label(_format_table_offset_line()).classes(
                    _SUMMARY_VALUE_CLASSES
                )
                for attr in ("table_offset_x", "table_offset_y", "table_offset_z", "normalization_method", "is_multi_exam"):
                    table_offset_summary.bind_text_from(
                        state, attr, backward=lambda _v: _format_table_offset_line()
                    )


def _build_physics_summary() -> None:
    with ui.column().classes("gap-2"):
        ui.label("PHYSICS PARAMETERS").classes(
            "text-sm text-aurora-pink font-bold tracking-widest border-b border-white/10 w-full q-pb-xs"
        )
        with ui.column().classes("gap-1"):
            with ui.row().classes(_SUMMARY_ROW_CLASSES):
                ui.label("k_tab:").classes(_SUMMARY_LABEL_CLASSES)
                ui.label().bind_text_from(
                    state, "estimate_k_tab", backward=lambda v: "Estimated" if v else "Measured"
                ).classes(_SUMMARY_VALUE_CLASSES)
            with ui.row().classes(_SUMMARY_ROW_CLASSES):
                ui.label("Filtration:").classes(_SUMMARY_LABEL_CLASSES)
                ui.label().bind_text_from(
                    state, "inherent_filtration", backward=lambda v: f"{v} mmAl"
                ).classes(_SUMMARY_VALUE_CLASSES)


def _build_settings_summary_card() -> None:
    with ui.card().classes("modern-card w-full border border-blue-100 shadow-sm"):
        with ui.row().classes("items-center justify-between w-full"):
            ui.label("Current settings").classes("text-xl font-bold q-mb-md")
            with ui.row().classes("items-center gap-2").bind_visibility_from(state, "is_multi_exam"):
                ui.badge().bind_text_from(
                    state, "loaded_exams", backward=lambda v: f"{len(v)} EXAMS"
                ).classes("text-xs tracking-widest font-bold")
                ui.label("Per-exam patient offsets editable in Geometry and Settings tabs").classes(
                    "text-caption text-grey-5 italic"
                )
        with ui.grid(columns=3).classes("w-full gap-8 mono-text text-sm"):
            _build_input_data_summary()
            _build_phantom_setup_summary()
            _build_physics_summary()


def build(ctx: PageContext) -> None:
    controller = _CalculationController(ctx)
    with ui.tab_panel("calculate"):
        with ui.column().classes("max-w-4xl mx-auto w-full gap-6"):
            with ui.row().classes("w-full items-center justify-between"):
                ui.label("Run Dose Calculation").classes("text-2xl font-bold tracking-tight")
                HelpButton(
                    title="Calculation Workflow",
                    content_path="calculation_workflow.md",
                    help_id="calculate",
                )

            _build_settings_summary_card()

            with ui.column().classes("w-full items-center gap-4 q-mt-xl"):
                calc_btn = ui.button(
                    "▶  Run Calculation", on_click=controller.do_calculate, icon="bolt"
                ).classes("modern-btn modern-btn-teal text-xl px-12 py-4 icon-outlined")
                ctx.run_btn_drawer.on("click", controller.do_calculate)

                calc_progress = ui.linear_progress(value=0, color="indigo").classes("w-full")
                calc_progress.visible = False
                calc_status_label = ui.label("Waiting...").classes("text-caption text-grey-5")
                controller.controls = _CalculationControls(calc_btn, calc_progress, calc_status_label)
