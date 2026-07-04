"""Calculate tab — run dose calculation with settings summary and progress.

Refactor plan Phase 3.3f. ``do_calculate`` touches drawer chrome (``psd_label``,
``run_btn_drawer``) and ``tabs`` via ``PageContext``. The drawer run button's
click handler is wired here even though the button is built in the drawer.
"""

from __future__ import annotations

from nicegui import run, ui

from ..components import HelpButton
from ..concurrency import operation_guard
from ..helpers import below_floor_event_count, run_calculation
from ..page_context import PageContext
from ..summary_formatters import format_patient_offsets
from ..state import state
from .settings import BELOW_FLOOR_KVP_OPTIONS, _format_table_offset_line

_MAX_TOASTS: int = 5


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


def build(ctx: PageContext) -> None:
    with ui.tab_panel("calculate"):
        with ui.column().classes("max-w-4xl mx-auto w-full gap-6"):
            with ui.row().classes("w-full items-center justify-between"):
                ui.label("Run Dose Calculation").classes("text-2xl font-bold tracking-tight")
                HelpButton(
                    title="Calculation Workflow",
                    content_path="calculation_workflow.md",
                    help_id="calculate",
                )

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
                    with ui.column().classes("gap-2"):
                        ui.label("INPUT DATA").classes(
                            "text-sm text-aurora-teal font-bold tracking-widest border-b border-white/10 w-full q-pb-xs"
                        )
                        with ui.column().classes("gap-1"):
                            with ui.column().classes("gap-0"):
                                ui.label("File:").classes(
                                    "text-grey-5 font-normal text-[11px] uppercase tracking-tighter"
                                )
                                ui.label().bind_text_from(
                                    state, "file_name", backward=lambda v: f"{v if v else 'None'}"
                                ).classes("font-bold text-[13px] truncate w-full")
                            with ui.row().classes("items-baseline gap-2"):
                                ui.label("Events:").classes(
                                    "text-grey-5 font-normal text-[11px] uppercase tracking-tighter"
                                )
                                ui.label().bind_text_from(
                                    state, "rdsr_df", backward=lambda v: f"{len(v) if v is not None else 0}"
                                ).classes("font-bold text-[13px]")
                            with ui.column().classes("gap-0"):
                                ui.label("Scanner:").classes(
                                    "text-grey-5 font-normal text-[11px] uppercase tracking-tighter"
                                )
                                ui.label().bind_text_from(
                                    state, "manufacturer", backward=lambda v: f"{v} {state.model}"
                                ).classes("font-bold text-[13px]")
                                ui.label().bind_text_from(
                                    state, "normalization_method", backward=lambda v: f"({v})"
                                ).classes("text-[10px] opacity-40 italic")

                    with ui.column().classes("gap-2"):
                        ui.label("PHANTOM SETUP").classes(
                            "text-sm text-aurora-purple font-bold tracking-widest border-b border-white/10 w-full q-pb-xs"
                        )
                        with ui.column().classes("gap-1"):
                            with ui.row().classes("items-baseline gap-2"):
                                ui.label("Model:").classes(
                                    "text-grey-5 font-normal text-[11px] uppercase tracking-tighter"
                                )
                                ui.label().bind_text_from(
                                    state, "phantom_model", backward=lambda v: f"{v}"
                                ).classes("font-bold text-[13px]")
                            with ui.column().classes("gap-0"):
                                ui.label("Patient Offsets:").classes(
                                    "text-grey-5 font-normal text-[11px] uppercase tracking-tighter"
                                )
                                patient_offset_summary = ui.label(_format_patient_offsets()).classes(
                                    "font-bold text-[13px]"
                                )
                                patient_offset_summary.bind_text_from(
                                    state,
                                    "per_exam_offsets_version",
                                    backward=lambda _v: _format_patient_offsets(),
                                )
                                patient_offset_summary.bind_text_from(
                                    state, "is_multi_exam", backward=lambda _v: _format_patient_offsets()
                                )
                            with ui.column().classes("gap-0"):
                                ui.label("Table Offsets:").classes(
                                    "text-grey-5 font-normal text-[11px] uppercase tracking-tighter"
                                )
                                table_offset_summary = ui.label(_format_table_offset_line()).classes(
                                    "font-bold text-[13px]"
                                )
                                table_offset_summary.bind_text_from(
                                    state, "table_offset_x", backward=lambda _v: _format_table_offset_line()
                                )
                                table_offset_summary.bind_text_from(
                                    state, "table_offset_y", backward=lambda _v: _format_table_offset_line()
                                )
                                table_offset_summary.bind_text_from(
                                    state, "table_offset_z", backward=lambda _v: _format_table_offset_line()
                                )
                                table_offset_summary.bind_text_from(
                                    state, "normalization_method", backward=lambda _v: _format_table_offset_line()
                                )
                                table_offset_summary.bind_text_from(
                                    state, "is_multi_exam", backward=lambda _v: _format_table_offset_line()
                                )

                    with ui.column().classes("gap-2"):
                        ui.label("PHYSICS PARAMETERS").classes(
                            "text-sm text-aurora-pink font-bold tracking-widest border-b border-white/10 w-full q-pb-xs"
                        )
                        with ui.column().classes("gap-1"):
                            with ui.row().classes("items-baseline gap-2"):
                                ui.label("k_tab:").classes(
                                    "text-grey-5 font-normal text-[11px] uppercase tracking-tighter"
                                )
                                ui.label().bind_text_from(
                                    state, "estimate_k_tab", backward=lambda v: "Estimated" if v else "Measured"
                                ).classes("font-bold text-[13px]")
                            with ui.row().classes("items-baseline gap-2"):
                                ui.label("Filtration:").classes(
                                    "text-grey-5 font-normal text-[11px] uppercase tracking-tighter"
                                )
                                ui.label().bind_text_from(
                                    state, "inherent_filtration", backward=lambda v: f"{v} mmAl"
                                ).classes("font-bold text-[13px]")

            with ui.column().classes("w-full items-center gap-4 q-mt-xl"):
                calc_btn = ui.button(
                    "▶  Run Calculation", on_click=lambda: do_calculate(), icon="bolt"
                ).classes("modern-btn modern-btn-teal text-xl px-12 py-4 icon-outlined")
                ctx.run_btn_drawer.on("click", lambda: do_calculate())

                calc_progress = ui.linear_progress(value=0, color="indigo").classes("w-full")
                calc_progress.visible = False
                calc_status_label = ui.label("Waiting...").classes("text-caption text-grey-5")

        async def do_calculate():
            if state.rdsr_df is None:
                ui.notify("Load a file first (tab 1)", color="warning")
                return
            if state.import_has_errors:
                ui.notify("Fix import errors before calculating (tab 1)", color="warning")
                return

            if not state.below_floor_prompt_suppressed:
                n_below = below_floor_event_count(state)
                if n_below > 0 and not await below_floor_prompt(n_below):
                    return

            with operation_guard("starting a calculation") as proceed:
                if not proceed:
                    return

                calc_btn.disable()
                ctx.run_btn_drawer.disable()
                calc_progress.visible = True
                calc_progress.set_value(0)
                calc_status_label.set_text("Starting...")

                def progress_cb(fraction: float, label: str):
                    calc_progress.set_value(fraction)
                    calc_status_label.set_text(label)

                try:
                    ok, msg = await run.io_bound(run_calculation, state, progress_cb)
                finally:
                    calc_progress.set_value(1.0)
                    calc_btn.enable()
                    ctx.run_btn_drawer.enable()

                if ok:
                    ctx.psd_label.set_text(f"PSD: {state.psd:.2f} mGy")
                    ctx.clear_offset_stale_caption()
                    ui.notify(f"✓ {msg}", color="positive")
                    ctx.tabs.set_value("results")

                    if state.calc_warnings:
                        _status = (
                            f"Done — {msg} · {len(state.calc_warnings)} warning(s), see notifications"
                        )
                        calc_status_label.set_text(_status)
                        for i, warning in enumerate(state.calc_warnings):
                            if i < _MAX_TOASTS:
                                ui.notify(warning, type="warning", timeout=12000, multi_line=True)
                            else:
                                ui.notify(
                                    f"... and {len(state.calc_warnings) - _MAX_TOASTS} more warnings. "
                                    f"See Results tab for the full list.",
                                    type="warning",
                                    timeout=12000,
                                )
                                break
                    else:
                        calc_status_label.set_text(f"Done — {msg}")
                else:
                    calc_status_label.set_text("Calculation failed")
                    ui.notify(f"Error: {msg[:300]}", type="negative", timeout=10000)
