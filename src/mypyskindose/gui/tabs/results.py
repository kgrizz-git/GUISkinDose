"""Results tab — metrics, dose map, and per-event correction factors.

Refactor plan Phase 3.3a. All three refreshers are timer-driven and read only
``state`` (plus ``make_dosemap_fig``), so this tab needs no members of
``PageContext``; ``ctx`` is accepted for a uniform ``build(ctx)`` interface.
"""

from __future__ import annotations

from typing import Any

from nicegui import ui

from ..components import HelpButton
from ..constants import COLORSCALES, MAX_INLINE_MAPS
from ..figures import extract_exam_dose_map, make_dosemap_fig
from ..page_context import PageContext
from ..state import state

_METRIC_ROW_CLASSES = "w-full gap-6"
_METRIC_CARD_CLASSES = "modern-card grow q-pa-lg text-center"
_MUTED_CAPTION_CLASSES = "text-caption text-grey-6"
_EXAM_METRIC_LABEL_CLASSES = "text-[10px] text-grey-5 font-bold tracking-widest uppercase"


def multi_exam_results_ui_stale(last_run_id: int | None, calc_run_id: int) -> bool:
    """True when the per-exam Results accordion must be rebuilt."""
    return last_run_id != calc_run_id


def can_show_more_inline(visible: list[bool]) -> bool:
    """Return True if another inline dose map can be shown without exceeding MAX_INLINE_MAPS."""
    return sum(visible) < MAX_INLINE_MAPS


def compute_subset_aggregate(res: Any, selected_mask: list[bool]) -> tuple[Any, float]:
    """Sum dose maps for selected exams. Returns (combined_ndarray, subset_psd) or (None, 0.0)."""
    import numpy as np

    selected_indices = [i for i, s in enumerate(selected_mask) if s]
    if not selected_indices:
        return None, 0.0
    first_output = res.exams[selected_indices[0]].output.to_dict()
    patient_data = first_output["patient"]["patient"]
    num_cells = len(patient_data["patient_skin_cells"]["x"])
    combined = np.zeros(num_cells)
    for idx in selected_indices:
        dose_map, _ = extract_exam_dose_map(res.exams[idx].output)
        assert len(dose_map) == num_cells, "All exams in subset must have matching skin cell counts"
        combined += dose_map
    subset_psd = float(np.max(combined)) if combined.size else 0.0
    return combined, subset_psd


def build(_ctx: PageContext) -> None:
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
        with ui.column().bind_visibility_from(state, "is_multi_exam", backward=lambda v: not v).classes(_METRIC_ROW_CLASSES):
            with ui.row().classes(_METRIC_ROW_CLASSES):
                with ui.card().classes(_METRIC_CARD_CLASSES):
                    ui.label("Peak Skin Dose").classes(_MUTED_CAPTION_CLASSES)
                    psd_metric = ui.label("—").classes("text-4xl text-aurora-purple font-bold")

                with ui.card().classes(_METRIC_CARD_CLASSES):
                    ui.label("Total Air Kerma").classes(_MUTED_CAPTION_CLASSES)
                    kerma_metric = ui.label("—").classes("text-4xl text-white font-bold")

                with ui.card().classes(_METRIC_CARD_CLASSES):
                    ui.label("Events").classes(_MUTED_CAPTION_CLASSES)
                    events_metric = ui.label("—").classes("text-4xl text-aurora-teal font-bold")

            with ui.row().classes(_METRIC_ROW_CLASSES):
                with ui.card().classes(_METRIC_CARD_CLASSES):
                    ui.label("Total DAP").classes(_MUTED_CAPTION_CLASSES)
                    dap_metric = ui.label("—").classes("text-3xl text-white font-bold")

                with ui.card().classes(_METRIC_CARD_CLASSES):
                    ui.label("Total Fluoro Time").classes(_MUTED_CAPTION_CLASSES)
                    fluoro_metric = ui.label("—").classes("text-3xl text-white font-bold")

            with ui.row().classes(_METRIC_ROW_CLASSES):
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

                ui.label("Correction factors per event").classes(_MUTED_CAPTION_CLASSES)
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
        with ui.column().bind_visibility_from(state, "is_multi_exam").classes(_METRIC_ROW_CLASSES):
            # Aggregate PSD banner card
            with ui.card().classes("modern-card w-full text-center border border-aurora-purple/50 bg-aurora-purple/10 p-6"):
                ui.label("Aggregate Peak Skin Dose").classes("text-sm text-aurora-purple font-bold tracking-widest uppercase")
                agg_psd_metric = ui.label("—").classes("text-5xl text-white font-bold my-2")
                agg_events_metric = ui.label("across 0 exams").classes("text-sm text-grey-4")
                agg_totals_metric = ui.label("").classes("text-sm text-grey-4")

            # Per-exam accordion
            ui.label("Per-Exam Results").classes("text-xl font-bold tracking-tight q-mt-md")
            multi_exam_accordion_container = ui.column().classes("w-full gap-2")

            # Visible exams subset selector
            with ui.card().classes("w-full modern-card q-pa-md"):
                ui.label("Visible exams in aggregate plot").classes("text-subtitle2 q-mb-sm")
                with ui.row().classes("w-full items-center gap-2"):
                    ui.button("All", on_click=lambda: _set_subset_all(True)).classes("modern-btn size-sm")
                    ui.button("None", on_click=lambda: _set_subset_all(False)).classes("modern-btn size-sm")
                subset_checkboxes_container = ui.column().classes("w-full gap-1")

            # Aggregate dose map
            ui.label("Aggregate Dose Map").classes("text-xl font-bold tracking-tight q-mt-xl")
            with ui.card().classes("w-full modern-card p-0 overflow-hidden relative"):
                agg_dosemap_plot = ui.plotly({}).classes("w-full").style("height:700px")
                agg_dosemap_spinner = ui.spinner(size="lg", color="indigo").classes("absolute-center")
                agg_dosemap_spinner.visible = False

            last_rendered_run_id: int | None = None
            last_agg_map_run_id: int | None = None
            subset_checkboxes: list[Any] = []

            def _clear_multi_exam_accordion() -> None:
                multi_exam_accordion_container.clear()

            def _build_multi_exam_accordion(res) -> None:
                _inline_rendered: dict[int, bool] = {}

                def _render_inline_dosemap(exam_idx: int, container: Any) -> None:
                    if res is None or exam_idx >= len(res.exams):
                        return
                    with container:
                        spinner = ui.spinner(size="md", color="indigo").classes("absolute-center")
                        plot = ui.plotly({}).classes("w-full").style("height:500px")
                    _inline_rendered[exam_idx] = True

                    async def _build(
                        _idx=exam_idx, _plot=plot, _spinner=spinner
                    ):
                        from nicegui import run

                        dose_map, patient_dict = extract_exam_dose_map(res.exams[_idx].output)
                        fig = await run.io_bound(make_dosemap_fig, dose_map, patient_dict)
                        _spinner.visible = False
                        if fig:
                            _plot.update_figure(fig)

                    ui.timer(0.1, _build, once=True)

                with multi_exam_accordion_container:
                    for i, exam_res in enumerate(res.exams):
                        with ui.expansion(
                            exam_res.exam_id, icon="personal_video"
                        ).classes("w-full modern-card bg-zinc-900/50"):
                            with ui.row().classes("w-full items-center justify-between"):
                                with ui.row().classes("gap-4"):
                                    with ui.column().classes("gap-0"):
                                        ui.label("PSD").classes(_EXAM_METRIC_LABEL_CLASSES)
                                        ui.label(f"{exam_res.output.PSD:.2f} mGy").classes(
                                            "text-aurora-purple font-bold"
                                        )
                                    with ui.column().classes("gap-0"):
                                        ui.label("Air Kerma").classes(_EXAM_METRIC_LABEL_CLASSES)
                                        ui.label(f"{exam_res.output.AirKerma:.1f} mGy").classes(
                                            "text-white font-bold"
                                        )
                                    with ui.column().classes("gap-0"):
                                        ui.label("Events").classes(_EXAM_METRIC_LABEL_CLASSES)
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

                            with ui.row().classes("w-full items-center gap-2 q-mt-sm"):
                                inline_cb = ui.checkbox(
                                    "Show inline dose map",
                                    value=state.visible_exam_dosemaps[i] if i < len(state.visible_exam_dosemaps) else False,
                                ).classes("text-sm")

                            inline_plot_container = ui.column().classes("w-full")
                            inline_plot_container.visible = bool(inline_cb.value)

                            def _on_inline_toggle(
                                e,
                                idx=i,
                                cb=inline_cb,
                                container=inline_plot_container,
                            ):
                                is_on = bool(e.value)
                                state.visible_exam_dosemaps[idx] = is_on
                                container.visible = is_on

                                if not is_on:
                                    container.clear()
                                    _inline_rendered.pop(idx, None)
                                    return

                                visible_count = sum(state.visible_exam_dosemaps)
                                if visible_count > MAX_INLINE_MAPS:
                                    cb.set_value(False)
                                    state.visible_exam_dosemaps[idx] = False
                                    container.visible = False
                                    ui.notify(
                                        f"Max {MAX_INLINE_MAPS} inline maps simultaneously. Close another first.",
                                        color="warning",
                                    )
                                    return

                                if not _inline_rendered.get(idx):
                                    _render_inline_dosemap(idx, container)

                            inline_cb.on_value_change(_on_inline_toggle)
                            if inline_cb.value and not _inline_rendered.get(i):
                                _render_inline_dosemap(i, inline_plot_container)

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

            def _refresh_aggregate_dosemap_subset() -> None:
                nonlocal last_agg_map_run_id
                res = state.multi_exam_result
                if res is None or not res.exams:
                    agg_dosemap_plot.update_figure({})
                    last_agg_map_run_id = state.calc_run_id
                    return
                if all(state.aggregate_subset_exams):
                    _refresh_aggregate_dosemap(res)
                    agg_psd_metric.set_text(f"{res.aggregate_psd:.2f} mGy")
                else:
                    agg_dosemap_spinner.visible = True
                    combined, subset_psd = compute_subset_aggregate(res, state.aggregate_subset_exams)
                    if combined is None:
                        agg_dosemap_spinner.visible = False
                        agg_dosemap_plot.update_figure({})
                        agg_psd_metric.set_text("— mGy (no exams selected)")
                        last_agg_map_run_id = state.calc_run_id
                        return
                    first_exam_patient = res.exams[0].output.to_dict()["patient"]
                    fig = make_dosemap_fig(explicit_dose_map=combined, explicit_patient=first_exam_patient)
                    agg_dosemap_spinner.visible = False
                    if fig:
                        agg_dosemap_plot.update_figure(fig)
                        state.dosemap_fig = fig
                    agg_psd_metric.set_text(f"{subset_psd:.2f} mGy (subset)")
                    last_agg_map_run_id = state.calc_run_id

            def _on_subset_toggle(e: Any, idx: int) -> None:
                if idx < len(state.aggregate_subset_exams):
                    state.aggregate_subset_exams[idx] = bool(e.value)
                _refresh_aggregate_dosemap_subset()

            def _set_subset_all(value: bool) -> None:
                for i in range(len(state.aggregate_subset_exams)):
                    state.aggregate_subset_exams[i] = value
                for cb in subset_checkboxes:
                    cb.set_value(value)
                _refresh_aggregate_dosemap_subset()

            def _build_subset_checkboxes(res: Any) -> None:
                subset_checkboxes.clear()
                subset_checkboxes_container.clear()
                with subset_checkboxes_container:
                    for i, _exam_res in enumerate(res.exams):
                        cb = ui.checkbox(
                            f"Exam {i + 1}",
                            value=state.aggregate_subset_exams[i] if i < len(state.aggregate_subset_exams) else True,
                        ).classes("text-sm")
                        cb.on_value_change(lambda e, idx=i: _on_subset_toggle(e, idx))
                        subset_checkboxes.append(cb)

            def _refresh_multi_exam_results():
                nonlocal last_rendered_run_id, last_agg_map_run_id

                if not state.is_multi_exam or not state.calculation_done or state.multi_exam_result is None:
                    if last_rendered_run_id is not None:
                        _clear_multi_exam_accordion()
                        subset_checkboxes_container.clear()
                        subset_checkboxes.clear()
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
                    n = len(res.exams)
                    if len(state.visible_exam_dosemaps) != n:
                        state.visible_exam_dosemaps = [False] * n
                    if len(state.aggregate_subset_exams) != n:
                        state.aggregate_subset_exams = [True] * n
                    _clear_multi_exam_accordion()
                    _build_multi_exam_accordion(res)
                    _build_subset_checkboxes(res)
                    last_rendered_run_id = state.calc_run_id

                if multi_exam_results_ui_stale(last_agg_map_run_id, state.calc_run_id):
                    _refresh_aggregate_dosemap_subset()

            ui.timer(1.5, _refresh_multi_exam_results)

            def _show_exam_dosemap_dialog(exam_idx: int):
                """Show a per-exam dose map in a modal dialog (reads latest calc output)."""
                res = state.multi_exam_result
                if res is None or exam_idx < 0 or exam_idx >= len(res.exams):
                    ui.notify("No dose map for this exam", color="warning")
                    return

                dose_map_array, patient_for_fig = extract_exam_dose_map(res.exams[exam_idx].output)

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
