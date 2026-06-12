"""Geometry preview tab — setup / single-event / full-procedure 3D views.

Refactor plan Phase 3.3d. Renders over the already-extracted ``make_geometry_fig``
and reads only ``state``; ``ctx`` is accepted for a uniform ``build(ctx)`` interface.
"""

from __future__ import annotations

from nicegui import run, ui

from ..components import HelpButton
from ..figures import make_geometry_fig
from ..page_context import PageContext
from ..state import state


def build(ctx: PageContext) -> None:
    with ui.tab_panel("geometry"):
        with ui.column().classes("max-w-6xl mx-auto w-full gap-6"):
            with ui.row().classes("w-full items-center justify-between"):
                ui.label("Geometry Preview").classes("text-2xl font-bold tracking-tight")
                HelpButton(
                    title="Geometry Workflow",
                    content_path="geometry_workflow.md"
                )

            # controls in a row above the plot
            with ui.row().classes("w-full items-end gap-4"):
                with ui.card().classes("modern-card w-48 p-2"):
                    ui.label("Event selection").classes("text-xs uppercase opacity-70")
                    geom_event_input = ui.number(
                        value=0, min=0, step=1
                    ).classes("w-full mono-text").props("dense flat")

                ui.button("Setup view", on_click=lambda: preview_setup()).classes("modern-btn-teal h-12 px-6")
                ui.button("Single event", on_click=lambda: preview_event()).classes("modern-btn-teal h-12 px-6")
                ui.button("Full procedure", on_click=lambda: preview_procedure()).classes("modern-btn-teal h-12 px-6")

                geom_spinner = ui.spinner(size="lg", color="indigo").classes("ml-4")
                geom_spinner.visible = False

            with ui.card().classes("w-full modern-card p-0 overflow-hidden"):
                geom_plot = ui.plotly({}).classes("w-full").style("height:700px")

            async def preview_setup():
                if state.rdsr_df is None:
                    ui.notify("Load data first", type="warning")
                    return
                geom_spinner.visible = True
                fig = await run.io_bound(make_geometry_fig, "plot_setup", 0)
                geom_spinner.visible = False
                if fig:
                    geom_plot.update_figure(fig)

            async def preview_event():
                if state.rdsr_df is None:
                    ui.notify("Load data first", type="warning")
                    return
                geom_spinner.visible = True
                fig = await run.io_bound(make_geometry_fig, "plot_event", int(geom_event_input.value or 0))
                geom_spinner.visible = False
                if fig:
                    geom_plot.update_figure(fig)

            async def preview_procedure():
                if state.rdsr_df is None:
                    ui.notify("Load data first", type="warning")
                    return
                geom_spinner.visible = True
                fig = await run.io_bound(make_geometry_fig, "plot_procedure", 0)
                geom_spinner.visible = False
                if fig:
                    geom_plot.update_figure(fig)
