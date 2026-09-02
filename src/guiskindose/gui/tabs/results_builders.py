"""Results tab controller, view references, and layout builders.

Sibling module to ``results.py``; owns the ``ResultsTabController`` (tab-local
state and timer callbacks), ``ResultsViewRefs`` (UI element handles), and the
layout builder functions.  ``results.py`` remains the thin public entry point.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from nicegui import run, ui

from ..components import HelpButton
from ..constants import COLORSCALES, MAX_INLINE_MAPS
from ..figures import extract_exam_dose_map, make_dosemap_fig
from ..state import state

if TYPE_CHECKING:
    from ..page_context import PageContext

_METRIC_ROW_CLASSES = "w-full gap-6"
_METRIC_CARD_CLASSES = "modern-card grow q-pa-lg text-center"
_MUTED_CAPTION_CLASSES = "text-caption text-grey-6"
_EXAM_METRIC_LABEL_CLASSES = "text-[10px] text-grey-5 font-bold tracking-widest uppercase"


def multi_exam_results_ui_stale(last_run_id: int | None, calc_run_id: int) -> bool:
    return last_run_id != calc_run_id


def can_show_more_inline(visible: list[bool]) -> bool:
    return sum(visible) < MAX_INLINE_MAPS


def compute_subset_aggregate(res: Any, selected_mask: list[bool]) -> tuple[Any, float]:
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


class ResultsTabController:
    """Tab-local state and timer callbacks for the Results tab."""

    def __init__(self) -> None:
        self.refs: ResultsViewRefs = ResultsViewRefs()
        self.last_rendered_run_id: int | None = None
        self.last_agg_map_run_id: int | None = None
        self.subset_checkboxes: list[Any] = []
        self._inline_rendered: dict[int, bool] = {}

    def refresh_metrics(self) -> None:
        if not state.is_multi_exam and state.calculation_done and state.psd is not None:
            from guiskindose.export._format import fmt_duration
            from guiskindose.export.metrics import total_dap_gycm2, total_fluoro_time_s

            self.refs.psd_metric.set_text(f"{state.psd:.2f} mGy")
            self.refs.kerma_metric.set_text(f"{state.air_kerma:.1f} mGy")
            self.refs.events_metric.set_text(
                str(len(state.rdsr_df) if state.rdsr_df is not None else 0)
            )
            dap = total_dap_gycm2(state.rdsr_df)
            self.refs.dap_metric.set_text(f"{dap:.2f} Gy·cm²" if dap is not None else "N/A")
            fluoro = total_fluoro_time_s(state.rdsr_df)
            self.refs.fluoro_metric.set_text(fmt_duration(fluoro) if fluoro is not None else "N/A")

    async def refresh_dosemap(self) -> None:
        if state.is_multi_exam or not state.calculation_done:
            return
        self.refs.dosemap_spinner.visible = True
        fig = await run.io_bound(make_dosemap_fig)
        self.refs.dosemap_spinner.visible = False
        if fig:
            self.refs.dosemap_plot.update_figure(fig)

    async def maybe_auto_refresh_dosemap(self) -> None:
        if not state.is_multi_exam and state.calculation_done and state.dosemap_fig is None:
            await self.refresh_dosemap()

    def refresh_corr_table(self) -> None:
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
            rows.append({
                "event": i + 1,
                "k_isq": _mean_correction(k_isq_list, i, np),
                "k_bs": _mean_correction(k_bs_list, i, np),
                "k_tab": _mean_correction(k_tab_list, i, np),
            })
        self.refs.corr_table.rows = rows
        self.refs.corr_table.update()

    def refresh_multi_exam_results(self) -> None:
        """Refresh aggregate metrics, run warnings, accordion, and dose-map subset."""
        if (
            not state.is_multi_exam
            or not state.calculation_done
            or state.multi_exam_result is None
        ):
            self._reset_multi_exam_view()
            return

        res = state.multi_exam_result
        self._set_multi_exam_summary(res)
        self._set_multi_exam_totals()
        self._rebuild_multi_exam_view_when_stale(res)
        if multi_exam_results_ui_stale(self.last_agg_map_run_id, state.calc_run_id):
            self.refresh_aggregate_dosemap_subset()

    def _reset_multi_exam_view(self) -> None:
        """Clear multi-exam controls after a completed multi-exam result disappears."""
        if self.last_rendered_run_id is None:
            return
        self._clear_multi_exam_accordion()
        self.refs.subset_checkboxes_container.clear()
        self.subset_checkboxes.clear()
        self.last_rendered_run_id = None
        self.last_agg_map_run_id = None
        self.refs.agg_dosemap_plot.update_figure({})
        self.refs.run_warnings_label.set_text("")
        self.refs.run_warnings_label.set_visibility(False)

    def _set_multi_exam_summary(self, res: Any) -> None:
        """Render aggregate dose, exam-count, and warning summaries."""
        self.refs.agg_psd_metric.set_text(f"{res.aggregate_psd:.2f} mGy")
        n_ok = len(res.exams)
        n_excluded = int(getattr(res, "exams_excluded", 0) or 0)
        if n_excluded > 0:
            self.refs.agg_events_metric.set_text(
                f"from {n_ok} exam(s); {n_excluded} excluded from aggregate"
            )
        else:
            self.refs.agg_events_metric.set_text(f"across {n_ok} exams")

        if res.warnings:
            self.refs.run_warnings_label.set_text("\n".join(res.warnings))
            self.refs.run_warnings_label.set_visibility(True)
        else:
            self.refs.run_warnings_label.set_text("")
            self.refs.run_warnings_label.set_visibility(False)

    def _set_multi_exam_totals(self) -> None:
        """Render DAP and fluoroscopy totals when those values are available."""
        from guiskindose.export._format import fmt_duration
        from guiskindose.export.metrics import total_dap_gycm2, total_fluoro_time_s

        dap = total_dap_gycm2(state.rdsr_df)
        fluoro = total_fluoro_time_s(state.rdsr_df)
        parts = []
        if dap is not None:
            parts.append(f"Total DAP {dap:.2f} Gy·cm²")
        if fluoro is not None:
            parts.append(f"Fluoro {fmt_duration(fluoro)}")
        self.refs.agg_totals_metric.set_text("  ·  ".join(parts))

    def _rebuild_multi_exam_view_when_stale(self, res: Any) -> None:
        """Recreate per-exam controls only for a new calculation run."""
        if multi_exam_results_ui_stale(self.last_rendered_run_id, state.calc_run_id):
            n = len(res.exams)
            if len(state.visible_exam_dosemaps) != n:
                state.visible_exam_dosemaps = [False] * n
            if len(state.aggregate_subset_exams) != n:
                state.aggregate_subset_exams = [True] * n
            self._clear_multi_exam_accordion()
            self._build_multi_exam_accordion(res)
            self._build_subset_checkboxes(res)
            self.last_rendered_run_id = state.calc_run_id

    def refresh_aggregate_dosemap(self, res: Any) -> None:
        if not res.exams:
            self.refs.agg_dosemap_plot.update_figure({})
            self.last_agg_map_run_id = state.calc_run_id
            return
        self.refs.agg_dosemap_spinner.visible = True
        first_exam_patient = res.exams[0].output.to_dict()["patient"]
        fig = make_dosemap_fig(
            explicit_dose_map=res.aggregate_dose_map,
            explicit_patient=first_exam_patient,
        )
        self.refs.agg_dosemap_spinner.visible = False
        if fig:
            self.refs.agg_dosemap_plot.update_figure(fig)
            state.dosemap_fig = fig
        self.last_agg_map_run_id = state.calc_run_id

    def refresh_aggregate_dosemap_subset(self) -> None:
        res = state.multi_exam_result
        if res is None or not res.exams:
            self.refs.agg_dosemap_plot.update_figure({})
            self.last_agg_map_run_id = state.calc_run_id
            return
        if all(state.aggregate_subset_exams):
            self.refresh_aggregate_dosemap(res)
            self.refs.agg_psd_metric.set_text(f"{res.aggregate_psd:.2f} mGy")
        else:
            self.refs.agg_dosemap_spinner.visible = True
            combined, subset_psd = compute_subset_aggregate(res, state.aggregate_subset_exams)
            if combined is None:
                self.refs.agg_dosemap_spinner.visible = False
                self.refs.agg_dosemap_plot.update_figure({})
                self.refs.agg_psd_metric.set_text("— mGy (no exams selected)")
                self.last_agg_map_run_id = state.calc_run_id
                return
            first_exam_patient = res.exams[0].output.to_dict()["patient"]
            fig = make_dosemap_fig(explicit_dose_map=combined, explicit_patient=first_exam_patient)
            self.refs.agg_dosemap_spinner.visible = False
            if fig:
                self.refs.agg_dosemap_plot.update_figure(fig)
                state.dosemap_fig = fig
            self.refs.agg_psd_metric.set_text(f"{subset_psd:.2f} mGy (subset)")
            self.last_agg_map_run_id = state.calc_run_id

    def on_subset_toggle(self, e: Any, idx: int) -> None:
        if idx < len(state.aggregate_subset_exams):
            state.aggregate_subset_exams[idx] = bool(e.value)
        self.refresh_aggregate_dosemap_subset()

    def set_subset_all(self, value: bool) -> None:
        for i in range(len(state.aggregate_subset_exams)):
            state.aggregate_subset_exams[i] = value
        for cb in self.subset_checkboxes:
            cb.set_value(value)
        self.refresh_aggregate_dosemap_subset()

    def show_exam_dosemap_dialog(self, exam_idx: int) -> None:
        res = state.multi_exam_result
        if res is None or exam_idx < 0 or exam_idx >= len(res.exams):
            ui.notify("No dose map for this exam", color="warning")
            return
        dose_map_array, patient_for_fig = extract_exam_dose_map(res.exams[exam_idx].output)
        with ui.dialog() as dialog, ui.card().classes(
            "modern-card w-[80vw] max-w-[1200px] p-6"
        ):
            with ui.row().classes("w-full justify-between items-center mb-4"):
                ui.label(f"Exam {exam_idx + 1} Dose Map").classes("text-xl font-bold")
                ui.button(icon="close", on_click=dialog.close).props(
                    "flat round dense"
                ).classes("text-grey-4")
            dialog_spinner = ui.spinner(size="lg", color="indigo").classes("absolute-center")
            dialog_plot = ui.plotly({}).classes("w-full").style("height:600px")
            dialog.open()

            async def _build_and_render(_dm=dose_map_array, _pat=patient_for_fig):
                from nicegui import run

                fig = await run.io_bound(make_dosemap_fig, _dm, _pat)
                dialog_spinner.visible = False
                if fig:
                    dialog_plot.update_figure(fig)

            ui.timer(0.1, _build_and_render, once=True)

    def _clear_multi_exam_accordion(self) -> None:
        self.refs.multi_exam_accordion_container.clear()

    def _build_subset_checkboxes(self, res: Any) -> None:
        self.subset_checkboxes.clear()
        self.refs.subset_checkboxes_container.clear()
        with self.refs.subset_checkboxes_container:
            for i, _exam_res in enumerate(res.exams):
                cb = ui.checkbox(
                    f"Exam {i + 1}",
                    value=(
                        state.aggregate_subset_exams[i]
                        if i < len(state.aggregate_subset_exams)
                        else True
                    ),
                ).classes("text-sm")
                cb.on_value_change(lambda e, idx=i: self.on_subset_toggle(e, idx))
                self.subset_checkboxes.append(cb)

    def _build_multi_exam_accordion(self, res: Any) -> None:
        self._inline_rendered.clear()
        with self.refs.multi_exam_accordion_container:
            for i, exam_res in enumerate(res.exams):
                self._build_exam_expansion(i, exam_res, res)

    def _build_exam_expansion(self, i: int, exam_res: Any, res: Any) -> None:
        with ui.expansion(exam_res.exam_id, icon="personal_video").classes(
            "w-full modern-card bg-zinc-900/50"
        ):
            with ui.row().classes("w-full items-center justify-between"):
                with ui.row().classes("gap-4"):
                    with ui.column().classes("gap-0"):
                        ui.label("PSD").classes(_EXAM_METRIC_LABEL_CLASSES)
                        ui.label(f"{exam_res.output.psd:.2f} mGy").classes(
                            "text-aurora-purple font-bold"
                        )
                    with ui.column().classes("gap-0"):
                        ui.label("Air Kerma").classes(_EXAM_METRIC_LABEL_CLASSES)
                        ui.label(f"{exam_res.output.air_kerma:.1f} mGy").classes(
                            "text-white font-bold"
                        )
                    with ui.column().classes("gap-0"):
                        ui.label("Events").classes(_EXAM_METRIC_LABEL_CLASSES)
                        ui.label(str(exam_res.event_count)).classes("text-white font-bold")
                with ui.button("Show Dose Map", icon="3d_rotation").classes(
                    "modern-btn modern-btn-teal size-sm"
                ) as btn:
                    if len(res.exams) > 10:
                        btn.disable()
                        btn.tooltip(
                            "Dose map rendering disabled for >10 exams to save memory"
                        )
                    else:
                        btn.on_click(
                            lambda _e, idx=i: self.show_exam_dosemap_dialog(idx)
                        )
            with ui.row().classes("w-full items-center gap-2 q-mt-sm"):
                inline_cb = ui.checkbox(
                    "Show inline dose map",
                    value=(
                        state.visible_exam_dosemaps[i]
                        if i < len(state.visible_exam_dosemaps)
                        else False
                    ),
                ).classes("text-sm")
            inline_plot_container = ui.column().classes("w-full")
            inline_plot_container.visible = bool(inline_cb.value)
            inline_cb.on_value_change(
                lambda e, idx=i, cb=inline_cb, ctr=inline_plot_container:
                    self._on_inline_toggle(e, idx, cb, ctr)
            )
            if inline_cb.value and not self._inline_rendered.get(i):
                self._render_inline_dosemap(i, inline_plot_container, res)

    def _on_inline_toggle(
        self, e: Any, idx: int, cb: ui.checkbox, container: ui.column
    ) -> None:
        is_on = bool(e.value)
        state.visible_exam_dosemaps[idx] = is_on
        container.visible = is_on
        if not is_on:
            container.clear()
            self._inline_rendered.pop(idx, None)
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
        if not self._inline_rendered.get(idx):
            res = state.multi_exam_result
            if res is not None:
                self._render_inline_dosemap(idx, container, res)

    def _render_inline_dosemap(self, exam_idx: int, container: Any, res: Any) -> None:
        if res is None or exam_idx >= len(res.exams):
            return
        with container:
            spinner = ui.spinner(size="md", color="indigo").classes("absolute-center")
            plot = ui.plotly({}).classes("w-full").style("height:500px")
        self._inline_rendered[exam_idx] = True

        async def _build(_idx=exam_idx, _plot=plot, _spinner=spinner):
            from nicegui import run

            dose_map, patient_dict = extract_exam_dose_map(res.exams[_idx].output)
            fig = await run.io_bound(make_dosemap_fig, dose_map, patient_dict)
            _spinner.visible = False
            if fig:
                _plot.update_figure(fig)

        ui.timer(0.1, _build, once=True)


@dataclass
class ResultsViewRefs:
    """UI element references for the Results tab."""

    psd_metric: ui.label = None  # type: ignore[assignment]
    kerma_metric: ui.label = None  # type: ignore[assignment]
    events_metric: ui.label = None  # type: ignore[assignment]
    dap_metric: ui.label = None  # type: ignore[assignment]
    fluoro_metric: ui.label = None  # type: ignore[assignment]
    dosemap_plot: ui.plotly = None  # type: ignore[assignment]
    dosemap_spinner: ui.spinner = None  # type: ignore[assignment]
    corr_table: ui.table = None  # type: ignore[assignment]
    agg_psd_metric: ui.label = None  # type: ignore[assignment]
    agg_events_metric: ui.label = None  # type: ignore[assignment]
    agg_totals_metric: ui.label = None  # type: ignore[assignment]
    run_warnings_label: ui.label = None  # type: ignore[assignment]
    agg_dosemap_plot: ui.plotly = None  # type: ignore[assignment]
    agg_dosemap_spinner: ui.spinner = None  # type: ignore[assignment]
    multi_exam_accordion_container: ui.column = None  # type: ignore[assignment]
    subset_checkboxes_container: ui.column = None  # type: ignore[assignment]


def _mean_correction(lst: list, i: int, np: Any) -> Any:
    try:
        if not lst or i >= len(lst):
            return "—"
        v = lst[i]
        if hasattr(v, "__len__") and len(v):
            return round(float(np.mean(v)), 3)
        return round(float(v), 3) if v is not None else "—"
    except Exception:
        return "—"


def _build_header() -> None:
    with ui.column().classes("max-w-6xl mx-auto w-full gap-6"):
        with ui.row().classes("w-full items-center justify-between"):
            ui.label("Results").classes("text-2xl font-bold tracking-tight")
            HelpButton(
                title="Results help",
                content_path="results_workflow.md",
                help_id="results",
            )


def _build_single_exam_section(ctrl: ResultsTabController) -> None:
    with ui.column().bind_visibility_from(
        state, "is_multi_exam", backward=lambda v: not v
    ).classes(_METRIC_ROW_CLASSES):
        with ui.row().classes(_METRIC_ROW_CLASSES):
            with ui.card().classes(_METRIC_CARD_CLASSES):
                ui.label("Peak Skin Dose").classes(_MUTED_CAPTION_CLASSES)
                ctrl.refs.psd_metric = ui.label("—").classes(
                    "text-4xl text-aurora-purple font-bold"
                )
            with ui.card().classes(_METRIC_CARD_CLASSES):
                ui.label("Total Air Kerma").classes(_MUTED_CAPTION_CLASSES)
                ctrl.refs.kerma_metric = ui.label("—").classes(
                    "text-4xl text-white font-bold"
                )
            with ui.card().classes(_METRIC_CARD_CLASSES):
                ui.label("Events").classes(_MUTED_CAPTION_CLASSES)
                ctrl.refs.events_metric = ui.label("—").classes(
                    "text-4xl text-aurora-teal font-bold"
                )
        with ui.row().classes(_METRIC_ROW_CLASSES):
            with ui.card().classes(_METRIC_CARD_CLASSES):
                ui.label("Total DAP").classes(_MUTED_CAPTION_CLASSES)
                ctrl.refs.dap_metric = ui.label("—").classes(
                    "text-3xl text-white font-bold"
                )
            with ui.card().classes(_METRIC_CARD_CLASSES):
                ui.label("Total Fluoro Time").classes(_MUTED_CAPTION_CLASSES)
                ctrl.refs.fluoro_metric = ui.label("—").classes(
                    "text-3xl text-white font-bold"
                )
        with ui.row().classes(_METRIC_ROW_CLASSES):
            with ui.card().classes("grow modern-card p-0 overflow-hidden relative"):
                ctrl.refs.dosemap_plot = ui.plotly({}).classes("w-full").style("height:700px")
                ctrl.refs.dosemap_spinner = ui.spinner(
                    size="lg", color="indigo"
                ).classes("absolute-center")
                ctrl.refs.dosemap_spinner.visible = False
        with ui.column().classes("w-80 gap-6"):
            with ui.card().classes("modern-card w-full"):
                ui.label("Visual settings").classes("text-subtitle2 q-mb-sm")
                ui.select(
                    COLORSCALES, label="Colorscale", value=state.colorscale
                ).bind_value(state, "colorscale").on(
                    "update:model-value", lambda: ctrl.refresh_dosemap()
                ).classes("w-full")
                ui.button(
                    "REGENERATE PLOT",
                    on_click=lambda: ctrl.refresh_dosemap(),
                ).classes("full-width modern-btn modern-btn-teal q-mt-md")
            ui.label("Correction factors per event").classes(_MUTED_CAPTION_CLASSES)
            ctrl.refs.corr_table = ui.table(
                columns=[
                    {"name": "event", "label": "EV", "field": "event", "align": "right"},
                    {"name": "k_isq", "label": "ISQ", "field": "k_isq", "align": "right"},
                    {"name": "k_bs", "label": "BS", "field": "k_bs", "align": "right"},
                    {"name": "k_tab", "label": "TAB", "field": "k_tab", "align": "right"},
                ],
                rows=[],
                row_key="event",
            ).classes("w-full modern-card")


def _build_multi_exam_section(ctrl: ResultsTabController) -> None:
    """Build aggregate PSD, run-warning, per-exam accordion, and dose-map controls."""
    with ui.column().bind_visibility_from(state, "is_multi_exam").classes(
        _METRIC_ROW_CLASSES
    ):
        with ui.card().classes(
            "modern-card w-full text-center border border-aurora-purple/50 "
            "bg-aurora-purple/10 p-6"
        ):
            ui.label("Aggregate Peak Skin Dose").classes(
                "text-sm text-aurora-purple font-bold tracking-widest uppercase"
            )
            ctrl.refs.agg_psd_metric = ui.label("—").classes(
                "text-5xl text-white font-bold my-2"
            )
            ctrl.refs.agg_events_metric = ui.label("across 0 exams").classes(
                "text-sm text-grey-4"
            )
            ctrl.refs.agg_totals_metric = ui.label("").classes("text-sm text-grey-4")

        ctrl.refs.run_warnings_label = ui.label("").classes(
            "text-sm text-orange-400 whitespace-pre-wrap w-full"
        )
        ctrl.refs.run_warnings_label.set_visibility(False)

        ui.label("Per-Exam Results").classes("text-xl font-bold tracking-tight q-mt-md")
        ctrl.refs.multi_exam_accordion_container = ui.column().classes("w-full gap-2")

        with ui.card().classes("w-full modern-card q-pa-md"):
            ui.label("Visible exams in aggregate plot").classes("text-subtitle2 q-mb-sm")
            with ui.row().classes("w-full items-center gap-2"):
                ui.button(
                    "All", on_click=lambda: ctrl.set_subset_all(True)
                ).classes("modern-btn size-sm")
                ui.button(
                    "None", on_click=lambda: ctrl.set_subset_all(False)
                ).classes("modern-btn size-sm")
            ctrl.refs.subset_checkboxes_container = ui.column().classes("w-full gap-1")

        ui.label("Aggregate Dose Map").classes("text-xl font-bold tracking-tight q-mt-xl")
        with ui.card().classes("w-full modern-card p-0 overflow-hidden relative"):
            ctrl.refs.agg_dosemap_plot = ui.plotly({}).classes("w-full").style("height:700px")
            ctrl.refs.agg_dosemap_spinner = ui.spinner(
                size="lg", color="indigo"
            ).classes("absolute-center")
            ctrl.refs.agg_dosemap_spinner.visible = False


def build_results_panel(_ctx: PageContext) -> None:
    """Construct and wire the complete Results tab."""
    ctrl = ResultsTabController()

    with ui.tab_panel("results"):
        _build_header()
        _build_single_exam_section(ctrl)
        _build_multi_exam_section(ctrl)

    ui.timer(1.0, ctrl.refresh_metrics)
    ui.timer(1.5, lambda: ctrl.maybe_auto_refresh_dosemap())
    ui.timer(2.0, ctrl.refresh_corr_table)
    ui.timer(1.5, ctrl.refresh_multi_exam_results)


def build(ctx: PageContext) -> None:
    """Public entry point — delegates to :func:`build_results_panel`."""
    build_results_panel(ctx)
