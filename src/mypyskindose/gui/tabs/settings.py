"""Settings tab — phantom, physics, and visual calculation settings.

Refactor plan Phase 3.3e. Almost entirely two-way ``state`` binds with
``reset_results`` on change; the only handler is ``_update_mesh_visibility``
(its own timer). Reads only ``state`` + constants, so ``ctx`` is accepted only
for a uniform ``build(ctx)`` interface.
"""

from __future__ import annotations

from nicegui import ui

from ..components import HelpButton
from ..constants import (
    COLORSCALES,
    HUMAN_MESHES,
    ORIENTATIONS,
    PATIENT_OFFSET_SLIDER_RANGE_CM,
    PHANTOM_MODELS,
)
from ..helpers import (
    any_table_origin_override,
    fallback_normalization_exam_count,
    get_mesh_baseline_extents,
    on_global_patient_offset_change,
)
from ..page_context import PageContext
from ..summary_formatters import format_scale_cm_label, format_table_offset_line, multi_exam_phantom_offset_caption
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

BEAM_MISS_WARN_OPTIONS = {
    "per_event": "Per event (one warning per missed event)",
    "summary": "Summary (one warning per run)",
    "off": "Off (only all-miss sentinel)",
}


def _format_table_offset_line() -> str:
    return format_table_offset_line(state)


def _format_scale_cm(scale_factor: float, axis: int) -> str:
    extents = get_mesh_baseline_extents(state.human_mesh)
    return format_scale_cm_label(scale_factor, axis, extents)


def build(ctx: PageContext) -> None:
    def _on_phantom_scale_change() -> None:
        reset_results()
        ctx.refresh_geometry_preview()

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

                    ui.label("Table Offsets (auto-detected, cm)").classes("text-caption text-grey-6 q-mt-sm")
                    table_offset_label = ui.label(_format_table_offset_line()).classes("text-body2 mono-text")
                    table_offset_label.bind_text_from(state, "table_offset_x", backward=lambda _v: _format_table_offset_line())
                    table_offset_label.bind_text_from(state, "table_offset_y", backward=lambda _v: _format_table_offset_line())
                    table_offset_label.bind_text_from(state, "table_offset_z", backward=lambda _v: _format_table_offset_line())
                    table_offset_label.bind_text_from(
                        state, "normalization_method", backward=lambda _v: _format_table_offset_line()
                    )
                    table_offset_label.bind_text_from(
                        state, "is_multi_exam", backward=lambda _v: _format_table_offset_line()
                    )

                    fallback_badge = ui.badge("Fallback normalization").props("color=amber")
                    fallback_badge.bind_visibility_from(
                        state, "normalization_method", backward=lambda v: v == "Fallback"
                    )
                    multi_fallback_caption = ui.label("").classes("text-caption text-amber-6 italic")
                    multi_fallback_caption.bind_text_from(
                        state,
                        "loaded_exam_meta",
                        backward=lambda _m: (
                            f"{fallback_normalization_exam_count(state)} exam(s) used fallback normalization"
                            if fallback_normalization_exam_count(state) > 0
                            else ""
                        ),
                    )
                    multi_fallback_caption.bind_visibility_from(
                        state,
                        "is_multi_exam",
                        backward=lambda v: v and fallback_normalization_exam_count(state) > 0,
                    )

                    override_caption = ui.label(
                        "Manual table origin in use — adjust in Geometry or Per-exam corrections."
                    ).classes("text-caption text-amber-6 italic")
                    override_caption.bind_visibility_from(
                        state,
                        "loaded_exam_meta",
                        backward=lambda _m: any_table_origin_override(state),
                    )

                    patient_offset_single = ui.column().classes("w-full gap-1")
                    patient_offset_single.bind_visibility_from(
                        state, "is_multi_exam", backward=lambda v: not v
                    )

                    with patient_offset_single:
                        ui.label("Patient Offsets (adjustable, cm)").classes("text-caption text-grey-6 q-mt-sm")

                        offset_range_hint = ui.label("").classes("text-caption text-grey-5 italic")

                        def _update_offset_range_hint() -> None:
                            mx = max(abs(state.d_lon), abs(state.d_ver), abs(state.d_lat))
                            if mx > PATIENT_OFFSET_SLIDER_RANGE_CM:
                                offset_range_hint.set_text(
                                    f"One or more offsets exceed the Geometry slider range "
                                    f"(±{PATIENT_OFFSET_SLIDER_RANGE_CM} cm)"
                                )
                            else:
                                offset_range_hint.set_text("")

                        def _on_patient_offset_change() -> None:
                            on_global_patient_offset_change(ctx)
                            _update_offset_range_hint()

                        with ui.row().classes("w-full gap-4"):
                            ui.number(label="Longitudinal", value=state.d_lon, step=1.0).bind_value(
                                state, "d_lon"
                            ).on("update:model-value", _on_patient_offset_change).classes("grow")
                            ui.number(label="Vertical", value=state.d_ver, step=1.0).bind_value(
                                state, "d_ver"
                            ).on("update:model-value", _on_patient_offset_change).classes("grow")
                            ui.number(label="Lateral", value=state.d_lat, step=1.0).bind_value(
                                state, "d_lat"
                            ).on("update:model-value", _on_patient_offset_change).classes("grow")

                        _update_offset_range_hint()

                    multi_exam_phantom_caption = ui.label(multi_exam_phantom_offset_caption()).classes(
                        "text-caption text-grey-5 italic q-mt-sm"
                    )
                    multi_exam_phantom_caption.bind_visibility_from(state, "is_multi_exam")

                    scale_section = ui.column().classes("w-full gap-2 q-mt-sm")
                    scale_section.bind_visibility_from(
                        state, "phantom_model", backward=lambda v: v == "human"
                    )
                    with scale_section:
                        ui.label("Body habitus scaling").classes("text-caption text-grey-6")
                        for label, attr, axis in (
                            ("Lateral / width", "phantom_scale_lat", 0),
                            ("AP / vertical thickness", "phantom_scale_ap", 1),
                            ("Longitudinal / head-foot", "phantom_scale_lon", 2),
                        ):
                            with ui.row().classes("w-full gap-4 items-center"):
                                ui.label(label).classes("w-48 text-caption")
                                ui.slider(
                                    min=0.5,
                                    max=2.0,
                                    step=0.05,
                                    value=getattr(state, attr),
                                ).bind_value(state, attr).on(
                                    "update:model-value", _on_phantom_scale_change
                                ).classes("grow min-w-[100px]")
                                scale_label = ui.label().classes("w-40 shrink-0 text-caption mono-text text-right")
                                scale_label.bind_text_from(
                                    state,
                                    attr,
                                    backward=lambda v, a=axis: _format_scale_cm(float(v), a),
                                )
                                scale_label.bind_text_from(
                                    state,
                                    "human_mesh",
                                    backward=lambda _v, a=attr, x=axis: _format_scale_cm(float(getattr(state, a)), x),
                                )

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

                    ui.select(
                        BEAM_MISS_WARN_OPTIONS,
                        label="Beam-miss warning verbosity",
                        value=state.beam_miss_warn,
                    ).bind_value(state, "beam_miss_warn").on(
                        "update:model-value", reset_results
                    ).classes("w-full")

            with ui.expansion("Visual Settings", icon="palette").classes("modern-card w-full"):
                with ui.column().classes("w-full gap-4 q-pa-md"):
                    ui.checkbox("Auto-render dose map on completion", value=state.plot_dosemap).bind_value(
                        state, "plot_dosemap"
                    )
                    ui.select(COLORSCALES, label="Dose map colorscale", value=state.colorscale).bind_value(
                        state, "colorscale"
                    ).classes("w-full")
