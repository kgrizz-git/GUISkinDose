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

        def _refresh_metrics():
            if state.calculation_done and state.psd is not None:
                psd_metric.set_text(f"{state.psd:.2f} mGy")
                kerma_metric.set_text(f"{state.air_kerma:.1f} mGy")
                events_metric.set_text(str(len(state.rdsr_df) if state.rdsr_df is not None else 0))

        ui.timer(1.0, _refresh_metrics)

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

        def _refresh_dosemap():
            if not state.calculation_done:
                return
            dosemap_spinner.visible = True
            fig = make_dosemap_fig()
            dosemap_spinner.visible = False
            if fig:
                dosemap_plot.update_figure(fig)

        ui.timer(1.5, lambda: _refresh_dosemap() if state.calculation_done and state.dosemap_fig is None else None)

        def _refresh_corr_table():
            if not state.calculation_done or state.output is None:
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
