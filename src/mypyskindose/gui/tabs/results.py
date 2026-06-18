"""Results tab — metrics, dose map, and per-event correction factors.

Refactor plan Phase 3.3a. All three refreshers are timer-driven and read only
``state`` (plus ``make_dosemap_fig``), so this tab needs no members of
``PageContext``; ``ctx`` is accepted for a uniform ``build(ctx)`` interface.
"""

from __future__ import annotations

from nicegui import ui

from ..constants import COLORSCALES
from ..figures import make_dosemap_fig
from ..page_context import PageContext
from ..state import state


def build(ctx: PageContext) -> None:
    with ui.tab_panel("results"):
        with ui.column().classes("max-w-6xl mx-auto w-full gap-6"):
            ui.label("Results").classes("text-2xl font-bold tracking-tight")

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
                psd_metric.set_text(f"{state.psd:.2f} mGy")
                kerma_metric.set_text(f"{state.air_kerma:.1f} mGy")
                events_metric.set_text(str(len(state.rdsr_df) if state.rdsr_df is not None else 0))

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

            # Per-exam accordion
            ui.label("Per-Exam Results").classes("text-xl font-bold tracking-tight q-mt-md")
            multi_exam_accordion_container = ui.column().classes("w-full gap-2")

            # Aggregate dose map
            ui.label("Aggregate Dose Map").classes("text-xl font-bold tracking-tight q-mt-xl")
            with ui.card().classes("w-full modern-card p-0 overflow-hidden relative"):
                agg_dosemap_plot = ui.plotly({}).classes("w-full").style("height:700px")
                agg_dosemap_spinner = ui.spinner(size="lg", color="indigo").classes("absolute-center")
                agg_dosemap_spinner.visible = False

            def _refresh_multi_exam_results():
                if not state.is_multi_exam or not state.calculation_done or state.multi_exam_result is None:
                    return

                res = state.multi_exam_result
                agg_psd_metric.set_text(f"{res.aggregate_psd:.2f} mGy")
                agg_events_metric.set_text(f"across {len(res.exams)} exams")

                # If we've already built the accordion for this calculation, don't rebuild it
                # We can check this by seeing if the container has children
                if len(multi_exam_accordion_container.default_slot.children) > 0:
                    return

                # Build the accordion
                with multi_exam_accordion_container:
                    for i, exam_res in enumerate(res.exams):
                        # Default title string if we don't have study_id metadata mapped here
                        study_str = f"Exam {i+1}"
                        # In the multi-exam API, exam_res is an ExamResult containing output and optional input_result ref
                        
                        with ui.expansion(f"{study_str}", icon="personal_video").classes("w-full modern-card bg-zinc-900/50"):
                            with ui.row().classes("w-full items-center justify-between"):
                                with ui.row().classes("gap-4"):
                                    # PSD
                                    with ui.column().classes("gap-0"):
                                        ui.label("PSD").classes("text-[10px] text-grey-5 font-bold tracking-widest uppercase")
                                        ui.label(f"{exam_res.output.get('psd', 0):.2f} mGy").classes("text-aurora-purple font-bold")
                                    # Air Kerma
                                    with ui.column().classes("gap-0"):
                                        ui.label("Air Kerma").classes("text-[10px] text-grey-5 font-bold tracking-widest uppercase")
                                        ui.label(f"{exam_res.output.get('air_kerma', 0):.1f} mGy").classes("text-white font-bold")
                                    
                                with ui.button("Show Dose Map", icon="3d_rotation").classes("modern-btn modern-btn-teal size-sm") as btn:
                                    if len(res.exams) > 10:
                                        btn.disable()
                                        btn.tooltip("Dose map rendering disabled for >10 exams to save memory")
                                    else:
                                        # Bind the click handler to this specific exam's data
                                        btn.on_click(lambda e, idx=i, out=exam_res.output: _show_exam_dosemap_dialog(idx, out))

                # Build aggregate dose map if not built
                if state.dosemap_fig is None:
                    agg_dosemap_spinner.visible = True
                    # Use the first exam's phantom as the topology template
                    first_exam_patient = res.exams[0].output
                    import numpy as np
                    
                    # Convert the aggregate dose map dict mapping back to an array
                    # The length of r is the number of skin cells
                    patient_data = first_exam_patient["patient"]["patient"]
                    num_cells = len(patient_data["patient_skin_cells"]["x"])
                    dose_map_array = np.zeros(num_cells)
                    for idx, dose in res.aggregate_dose_map.items():
                        dose_map_array[int(idx)] = dose

                    fig = make_dosemap_fig(explicit_dose_map=dose_map_array, explicit_patient=first_exam_patient)
                    agg_dosemap_spinner.visible = False
                    if fig:
                        agg_dosemap_plot.update_figure(fig)
                        state.dosemap_fig = fig  # flag that it's built

            ui.timer(1.5, _refresh_multi_exam_results)

            def _show_exam_dosemap_dialog(exam_idx: int, exam_output: dict):
                with ui.dialog() as dialog, ui.card().classes("modern-card w-[80vw] max-w-[1200px] p-6"):
                    with ui.row().classes("w-full justify-between items-center mb-4"):
                        ui.label(f"Exam {exam_idx+1} Dose Map").classes("text-xl font-bold")
                        ui.button(icon="close", on_click=dialog.close).props("flat round dense").classes("text-grey-4")
                    
                    dialog_spinner = ui.spinner(size="lg", color="indigo").classes("absolute-center")
                    dialog_plot = ui.plotly({}).classes("w-full").style("height:600px")
                    
                    dialog.open()
                    
                    # Build and render the figure asynchronously
                    async def build_and_render():
                        import numpy as np
                        
                        patient_data = exam_output["patient"]["patient"]
                        num_cells = len(patient_data["patient_skin_cells"]["x"])
                        dose_map_array = np.zeros(num_cells)
                        for idx, dose in exam_output["dose_map"]:
                            dose_map_array[int(idx)] = dose
                            
                        # Need to run in executor to not block UI thread
                        from nicegui import run
                        fig = await run.io_bound(make_dosemap_fig, dose_map_array, exam_output)
                        
                        dialog_spinner.visible = False
                        if fig:
                            dialog_plot.update_figure(fig)
                            
                    ui.timer(0.1, build_and_render, once=True)
