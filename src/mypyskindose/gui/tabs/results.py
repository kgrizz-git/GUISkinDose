"""Results tab — metrics, dose map, and per-event correction factors.

Refactor plan Phase 3.3a. All three refreshers are timer-driven and read only
``state`` (plus ``make_dosemap_fig``), so this tab needs no members of
``PageContext``; ``ctx`` is accepted for a uniform ``build(ctx)`` interface.
"""

from __future__ import annotations

from nicegui import ui

from ..components import HelpButton
from ..constants import COLORSCALES
from ..figures import make_dosemap_fig
from ..page_context import PageContext
from ..state import state


def multi_exam_results_ui_stale(last_run_id: int | None, calc_run_id: int) -> bool:
    """True when the per-exam Results accordion must be rebuilt."""
    return last_run_id != calc_run_id


def build(ctx: PageContext) -> None:
    with ui.tab_panel("results"):
        with ui.column().classes("max-w-6xl mx-auto w-full gap-6"):
            with ui.row().classes("w-full items-center justify-between"):
                ui.label("Results").classes("text-2xl font-bold tracking-tight")
                HelpButton(
                    title="Results help",
                    content_path="results_workflow.md",
                    help_id="results",
                )

            # metric cards
        with ui.column().bind_visibility_from(state, "is_multi_exam", backward=lambda v: not v).classes("w-full gap-6"):
            with ui.row().classes("w-full gap-6"):
                with ui.card().classes("modern-card grow q-pa-lg text-center"):
                    ui.label("Peak Skin Dose").classes("text-caption text-grey-6")
                    psd_metric = ui.label("—").classes("text-4xl text-aurora-purple font-bold")

                with ui.card().classes("modern-card grow q-pa-lg text-center"):
                    ui.label("Total Air Kerma").classes("text-caption text-grey-6")
                    kerma_metric = ui.label("—").classes("text-4xl text-white font-bold")

                with ui.card().classes("modern-card grow q-pa-lg text-center"):
                    ui.label("Events").classes("text-caption text-grey-6")
                    events_metric = ui.label("—").classes("text-4xl text-aurora-teal font-bold")

            with ui.row().classes("w-full gap-6"):
                with ui.card().classes("modern-card grow q-pa-lg text-center"):
                    ui.label("Total DAP").classes("text-caption text-grey-6")
                    dap_metric = ui.label("—").classes("text-3xl text-white font-bold")

                with ui.card().classes("modern-card grow q-pa-lg text-center"):
                    ui.label("Total Fluoro Time").classes("text-caption text-grey-6")
                    fluoro_metric = ui.label("—").classes("text-3xl text-white font-bold")

            with ui.row().classes("w-full gap-6"):
                # dose map plot
                with ui.card().classes("grow modern-card p-0 overflow-hidden relative"):
                    dosemap_plot = ui.plotly({}).classes("w-full").style("height:700px")
                    dosemap_spinner = ui.spinner(size="lg", color="indigo").classes("absolute-center")
                    dosemap_spinner.visible = False

            # Controls & Correction factors
            with ui.column().classes("w-80 gap-6"):
                with ui.card().classes("modern-card w-full"):
                    ui.label("Visual settings").classes("text-subtitle2 q-mb-sm")
                    ui.select(COLORSCALES, label="Colorscale", value=state.colorscale).bind_value(state, "colorscale").on(
                        "update:model-value", lambda: _refresh_dosemap()
                    ).classes("w-full")

                    ui.button("REGENERATE PLOT", on_click=lambda: _refresh_dosemap()).classes("full-width modern-btn modern-btn-teal q-mt-md")

                ui.label("Correction factors per event").classes("text-caption text-grey-6")
                corr_table = ui.table(
                    columns=[
                        {"name": "event", "label": "EV", "field": "event", "align": "right"},
                        {"name": "k_isq", "label": "ISQ", "field": "k_isq", "align": "right"},
                        {"name": "k_bs", "label": "BS", "field": "k_bs", "align": "right"},
                        {"name": "k_tab", "label": "TAB", "field": "k_tab", "align": "right"},
                    ],
                    rows=[],
                    row_key="event",
                ).classes("w-full modern-card")

        def _refresh_metrics():
            if not state.is_multi_exam and state.calculation_done and state.psd is not None:
                from mypyskindose.export._format import fmt_duration
                from mypyskindose.export.metrics import total_dap_gycm2, total_fluoro_time_s

                psd_metric.set_text(f"{state.psd:.2f} mGy")
                kerma_metric.set_text(f"{state.air_kerma:.1f} mGy")
                events_metric.set_text(str(len(state.rdsr_df) if state.rdsr_df is not None else 0))

                dap = total_dap_gycm2(state.rdsr_df)
                dap_metric.set_text(f"{dap:.2f} Gy·cm²" if dap is not None else "N/A")
                fluoro = total_fluoro_time_s(state.rdsr_df)
                fluoro_metric.set_text(fmt_duration(fluoro) if fluoro is not None else "N/A")

        ui.timer(1.0, _refresh_metrics)

        def _refresh_dosemap():
            if state.is_multi_exam or not state.calculation_done:
                return
            dosemap_spinner.visible = True
            fig = make_dosemap_fig()
            dosemap_spinner.visible = False
            if fig:
                dosemap_plot.update_figure(fig)

        ui.timer(1.5, lambda: _refresh_dosemap() if not state.is_multi_exam and state.calculation_done and state.dosemap_fig is None else None)

        def _refresh_corr_table():
            if state.is_multi_exam or not state.calculation_done or state.output is None:
                return
            out = state.output
            corrections = out.get("corrections", {})
            k_isq_list = corrections.get("inverse_square_law", [])
            k_bs_list = corrections.get("backscatter", [])
            k_tab_list = corrections.get("table", [])

            import numpy as np
            rows = []
            n = len(k_isq_list)
            for i in range(n):
                def _mean(lst, i):
                    try:
                        if not lst or i >= len(lst):
                            return "—"
                        v = lst[i]
                        if hasattr(v, "__len__") and len(v):
                            return round(float(np.mean(v)), 3)
                        return round(float(v), 3) if v is not None else "—"
                    except Exception:
                        return "—"

                rows.append({
                    "event": i + 1,
                    "k_isq": _mean(k_isq_list, i),
                    "k_bs": _mean(k_bs_list, i),
                    "k_tab": _mean(k_tab_list, i),
                })
            corr_table.rows = rows
            corr_table.update()

        ui.timer(2.0, _refresh_corr_table)

        # ── Multi-exam section ────────────────────────────────────────────────
        with ui.column().bind_visibility_from(state, "is_multi_exam").classes("w-full gap-6"):
            # Aggregate PSD banner card
            with ui.card().classes("modern-card w-full text-center border border-aurora-purple/50 bg-aurora-purple/10 p-6"):
                ui.label("Aggregate Peak Skin Dose").classes("text-sm text-aurora-purple font-bold tracking-widest uppercase")
                agg_psd_metric = ui.label("—").classes("text-5xl text-white font-bold my-2")
                agg_events_metric = ui.label("across 0 exams").classes("text-sm text-grey-4")
                agg_totals_metric = ui.label("").classes("text-sm text-grey-4")

            # Per-exam accordion
            ui.label("Per-Exam Results").classes("text-xl font-bold tracking-tight q-mt-md")
            multi_exam_accordion_container = ui.column().classes("w-full gap-2")

            # Aggregate dose map
            ui.label("Aggregate Dose Map").classes("text-xl font-bold tracking-tight q-mt-xl")
            with ui.card().classes("w-full modern-card p-0 overflow-hidden relative"):
                agg_dosemap_plot = ui.plotly({}).classes("w-full").style("height:700px")
                agg_dosemap_spinner = ui.spinner(size="lg", color="indigo").classes("absolute-center")
                agg_dosemap_spinner.visible = False

            last_rendered_run_id: int | None = None
            last_agg_map_run_id: int | None = None

            def _clear_multi_exam_accordion() -> None:
                multi_exam_accordion_container.clear()

            def _build_multi_exam_accordion(res) -> None:
                with multi_exam_accordion_container:
                    for i, exam_res in enumerate(res.exams):
                        study_str = f"Exam {i + 1}"

                        with ui.expansion(
                            f"{study_str} — {exam_res.exam_id}", icon="personal_video"
                        ).classes("w-full modern-card bg-zinc-900/50"):
                            with ui.row().classes("w-full items-center justify-between"):
                                with ui.row().classes("gap-4"):
                                    with ui.column().classes("gap-0"):
                                        ui.label("PSD").classes(
                                            "text-[10px] text-grey-5 font-bold tracking-widest uppercase"
                                        )
                                        ui.label(f"{exam_res.output.PSD:.2f} mGy").classes(
                                            "text-aurora-purple font-bold"
                                        )
                                    with ui.column().classes("gap-0"):
                                        ui.label("Air Kerma").classes(
                                            "text-[10px] text-grey-5 font-bold tracking-widest uppercase"
                                        )
                                        ui.label(f"{exam_res.output.AirKerma:.1f} mGy").classes(
                                            "text-white font-bold"
                                        )
                                    with ui.column().classes("gap-0"):
                                        ui.label("Events").classes(
                                            "text-[10px] text-grey-5 font-bold tracking-widest uppercase"
                                        )
                                        ui.label(str(exam_res.event_count)).classes("text-white font-bold")

                                with ui.button(
                                    "Show Dose Map", icon="3d_rotation"
                                ).classes("modern-btn modern-btn-teal size-sm") as btn:
                                    if len(res.exams) > 10:
                                        btn.disable()
                                        btn.tooltip(
                                            "Dose map rendering disabled for >10 exams to save memory"
                                        )
                                    else:
                                        btn.on_click(lambda _e, idx=i: _show_exam_dosemap_dialog(idx))

            def _refresh_aggregate_dosemap(res) -> None:
                nonlocal last_agg_map_run_id
                if not res.exams:
                    agg_dosemap_plot.update_figure({})
                    last_agg_map_run_id = state.calc_run_id
                    return

                agg_dosemap_spinner.visible = True
                first_exam_output_dict = res.exams[0].output.to_dict()
                first_exam_patient = first_exam_output_dict["patient"]

                fig = make_dosemap_fig(
                    explicit_dose_map=res.aggregate_dose_map,
                    explicit_patient=first_exam_patient,
                )
                agg_dosemap_spinner.visible = False
                if fig:
                    agg_dosemap_plot.update_figure(fig)
                    state.dosemap_fig = fig
                last_agg_map_run_id = state.calc_run_id

            def _refresh_multi_exam_results():
                nonlocal last_rendered_run_id, last_agg_map_run_id

                if not state.is_multi_exam or not state.calculation_done or state.multi_exam_result is None:
                    if last_rendered_run_id is not None:
                        _clear_multi_exam_accordion()
                        last_rendered_run_id = None
                        last_agg_map_run_id = None
                        agg_dosemap_plot.update_figure({})
                    return

                res = state.multi_exam_result
                agg_psd_metric.set_text(f"{res.aggregate_psd:.2f} mGy")
                agg_events_metric.set_text(f"across {len(res.exams)} exams")

                from mypyskindose.export._format import fmt_duration
                from mypyskindose.export.metrics import total_dap_gycm2, total_fluoro_time_s

                dap = total_dap_gycm2(state.rdsr_df)
                fluoro = total_fluoro_time_s(state.rdsr_df)
                parts = []
                if dap is not None:
                    parts.append(f"Total DAP {dap:.2f} Gy·cm²")
                if fluoro is not None:
                    parts.append(f"Fluoro {fmt_duration(fluoro)}")
                agg_totals_metric.set_text("  ·  ".join(parts))

                if multi_exam_results_ui_stale(last_rendered_run_id, state.calc_run_id):
                    _clear_multi_exam_accordion()
                    _build_multi_exam_accordion(res)
                    last_rendered_run_id = state.calc_run_id

                if multi_exam_results_ui_stale(last_agg_map_run_id, state.calc_run_id):
                    _refresh_aggregate_dosemap(res)

            ui.timer(1.5, _refresh_multi_exam_results)

            def _show_exam_dosemap_dialog(exam_idx: int):
                """Show a per-exam dose map in a modal dialog (reads latest calc output)."""
                import numpy as np

                res = state.multi_exam_result
                if res is None or exam_idx < 0 or exam_idx >= len(res.exams):
                    ui.notify("No dose map for this exam", color="warning")
                    return

                exam_output = res.exams[exam_idx].output
                output_dict = exam_output.to_dict()
                patient_for_fig = output_dict["patient"]

                patient_data = patient_for_fig["patient"]
                num_cells = len(patient_data["patient_skin_cells"]["x"])
                dose_map_array = np.zeros(num_cells)
                for idx, dose in output_dict["dose_map"]:
                    dose_map_array[int(idx)] = dose

                with ui.dialog() as dialog, ui.card().classes("modern-card w-[80vw] max-w-[1200px] p-6"):
                    with ui.row().classes("w-full justify-between items-center mb-4"):
                        ui.label(f"Exam {exam_idx + 1} Dose Map").classes("text-xl font-bold")
                        ui.button(icon="close", on_click=dialog.close).props("flat round dense").classes(
                            "text-grey-4"
                        )

                    dialog_spinner = ui.spinner(size="lg", color="indigo").classes("absolute-center")
                    dialog_plot = ui.plotly({}).classes("w-full").style("height:600px")

                    dialog.open()

                    async def _build_and_render(
                        _dm=dose_map_array, _pat=patient_for_fig
                    ):
                        from nicegui import run

                        fig = await run.io_bound(make_dosemap_fig, _dm, _pat)
                        dialog_spinner.visible = False
                        if fig:
                            dialog_plot.update_figure(fig)

                    ui.timer(0.1, _build_and_render, once=True)
