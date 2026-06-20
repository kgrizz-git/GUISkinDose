"""Settings tab — phantom, physics, and visual calculation settings.

Refactor plan Phase 3.3e. Almost entirely two-way ``state`` binds with
``reset_results`` on change; the only handler is ``_update_mesh_visibility``
(its own timer). Reads only ``state`` + constants, so ``ctx`` is accepted only
for a uniform ``build(ctx)`` interface.
"""

from __future__ import annotations

from nicegui import ui

from ..components import HelpButton
from ..constants import COLORSCALES, HUMAN_MESHES, ORIENTATIONS, PHANTOM_MODELS
from ..page_context import PageContext
from ..state import reset_results, state
from ._per_exam import build_per_exam_section

# Below-floor kVp policy → human-readable labels for the Settings select. Values
# match mypyskindose.constants.BELOW_FLOOR_KVP_POLICIES.
BELOW_FLOOR_KVP_OPTIONS = {
    "snap": "Snap to grid edge (default)",
    "skip": "Skip (drop the events)",
    "manual": "Substitute a manual kVp",
    "exam_average": "Substitute the exam-average kVp",
}


def build(ctx: PageContext) -> None:
    with ui.tab_panel("settings"):
        with ui.column().classes("max-w-4xl mx-auto w-full gap-6"):
            ui.label("Calculation Settings").classes("text-2xl font-bold tracking-tight")

            with ui.expansion("Phantom Settings", icon="person", value=True).classes("modern-card w-full"):
                with ui.column().classes("w-full gap-4 q-pa-md"):
                    with ui.row().classes("w-full items-center justify-between"):
                        ui.label("Phantom model and positioning").classes("text-subtitle2")
                        HelpButton(
                            title="Phantom Positioning Offsets",
                            content_path="positioning_offsets.md"
                        )
                    with ui.row().classes("w-full gap-6"):
                        ui.select(PHANTOM_MODELS, label="Phantom model", value=state.phantom_model).bind_value(
                            state, "phantom_model"
                        ).on("update:model-value", reset_results).classes("grow")

                        mesh_select = ui.select(
                            HUMAN_MESHES, label="Human mesh", value=state.human_mesh
                        ).bind_value(state, "human_mesh").on("update:model-value", reset_results).classes("grow")

                    # show/hide mesh selector based on model
                    def _update_mesh_visibility():
                        mesh_select.visible = state.phantom_model == "human"

                    ui.timer(0.5, _update_mesh_visibility)

                    ui.select(ORIENTATIONS, label="Patient orientation", value=state.patient_orientation).bind_value(
                        state, "patient_orientation"
                    ).on("update:model-value", reset_results).classes("w-full")

                    ui.label("Patient offset (cm)").classes("text-caption text-grey-6 q-mt-sm")
                    with ui.row().classes("w-full gap-4"):
                        ui.number(label="Longitudinal", value=state.d_lon, step=1.0).bind_value(
                            state, "d_lon"
                        ).on("update:model-value", reset_results).classes("grow")
                        ui.number(label="Vertical", value=state.d_ver, step=1.0).bind_value(
                            state, "d_ver"
                        ).on("update:model-value", reset_results).classes("grow")
                        ui.number(label="Lateral", value=state.d_lat, step=1.0).bind_value(
                            state, "d_lat"
                        ).on("update:model-value", reset_results).classes("grow")

            # Per-exam corrections (offsets, coordinate fixes, table-origin) — one
            # editable block per loaded exam; registers ctx.refresh_per_exam.
            build_per_exam_section(ctx)

            with ui.expansion("Physics Settings", icon="science").classes("modern-card w-full"):
                with ui.column().classes("w-full gap-4 q-pa-md"):
                    ui.checkbox("Use estimated table transmission (k_tab)", value=state.estimate_k_tab).bind_value(
                        state, "estimate_k_tab"
                    ).on("update:model-value", reset_results)

                    with ui.column().classes("w-full gap-1"):
                        ui.label("TRANSMISSION FACTOR (k_tab)").classes("technical-label")
                        with ui.row().classes("items-center w-full gap-4"):
                            ui.slider(min=0.0, max=1.0, step=0.01, value=state.k_tab_val).bind_value(
                                state, "k_tab_val"
                            ).on("update:model-value", reset_results).classes("grow")
                            ui.label().bind_text_from(state, "k_tab_val", backward=lambda v: f"{v:.2f}").classes("mono-text font-bold")

                    ui.number(
                        label="Inherent filtration (mmAl)", value=state.inherent_filtration, min=0.0, step=0.1
                    ).bind_value(state, "inherent_filtration").on("update:model-value", reset_results).classes("w-full")

                    ui.checkbox("Remove invalid data (kVp = 0)", value=state.remove_invalid_rows).bind_value(
                        state, "remove_invalid_rows"
                    ).on("update:model-value", reset_results)

                    with ui.column().classes("w-full gap-2"):
                        with ui.row().classes("w-full items-center justify-between"):
                            ui.label("Below-floor kVp handling (< 25 kV)").classes("text-subtitle2")
                            HelpButton(
                                title="Below-floor kVp handling",
                                content_path="below_floor_kvp.md",
                            )
                        ui.select(
                            BELOW_FLOOR_KVP_OPTIONS,
                            label="Policy for events below the HVL table floor",
                            value=state.below_floor_kvp_policy,
                        ).bind_value(state, "below_floor_kvp_policy").on(
                            "update:model-value", reset_results
                        ).classes("w-full")

                        manual_kvp = ui.number(
                            label="Manual kVp", value=state.below_floor_kvp_manual, min=25.0, max=175.0, step=1.0
                        ).bind_value(state, "below_floor_kvp_manual").on(
                            "update:model-value", reset_results
                        ).classes("w-full")

                        def _update_manual_kvp_visibility():
                            manual_kvp.visible = state.below_floor_kvp_policy == "manual"

                        ui.timer(0.5, _update_manual_kvp_visibility)

            with ui.expansion("Visual Settings", icon="palette").classes("modern-card w-full"):
                with ui.column().classes("w-full gap-4 q-pa-md"):
                    ui.checkbox("Auto-render dose map on completion", value=state.plot_dosemap).bind_value(
                        state, "plot_dosemap"
                    )
                    ui.select(COLORSCALES, label="Dose map colorscale", value=state.colorscale).bind_value(
                        state, "colorscale"
                    ).classes("w-full")
