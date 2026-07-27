"""Settings tab — phantom, physics, and visual calculation settings.

Refactor plan Phase 3.3e. Mostly two-way ``state`` binds with ``reset_results``
on change. Phantom model / mesh / orientation / habitus / offsets also refresh
the Settings phantom preview and (where needed) the Geometry preview.
"""

from __future__ import annotations

from nicegui import ui

from ..components import HelpButton
from ..constants import (
    COLORSCALES,
    ORIENTATIONS,
    PATIENT_OFFSET_SLIDER_RANGE_CM,
    PHANTOM_MODELS,
)
from ..helpers import (
    DEMO_MESH_SECTION_KEY,
    any_table_origin_override,
    canonicalize_human_mesh_selection,
    fallback_normalization_exam_count,
    get_human_mesh_options,
    get_mesh_baseline_extents,
    get_mesh_baseline_torso_width,
    on_global_patient_offset_change,
)
from ..page_context import PageContext
from ..phantom_preview_controller import PhantomPreviewController
from ..summary_formatters import format_scale_cm_label, format_table_offset_line, multi_exam_phantom_offset_caption
from ..state import reset_results, state
from ..ui_copy import copy_text
from ._per_exam import build_per_exam_section

# Shared Quasar/Tailwind row class for Settings section headers (python:S1192).
_SETTINGS_HEADER_ROW_CLASSES = "w-full items-center justify-between"

# Below-floor kVp policy → human-readable labels for the Settings select. Values
# match mypyskindose.constants.BELOW_FLOOR_KVP_POLICIES.
BELOW_FLOOR_KVP_OPTIONS = {
    "exam_average": "Substitute the exam-average kVp (default)",
    "snap": "Snap to grid edge",
    "skip": "Skip (drop the events)",
    "manual": "Substitute a manual kVp",
}

BEAM_MISS_WARN_OPTIONS = {
    "per_event": "Per event (one warning per missed event)",
    "summary": "Summary (one warning per run)",
    "off": "Off (only all-miss sentinel)",
}

_MODEL_VALUE_EVENT = "update:model-value"
_SETTINGS_EXPANSION_CLASSES = "modern-card w-full"
_SETTINGS_SECTION_CLASSES = "w-full gap-4 q-pa-md"

COMPACT_FULL_WIDTH_COLUMN_CLASSES = "w-full gap-1"


def _format_table_offset_line() -> str:
    """Format the table-offset summary line for Settings/Calculate."""
    return format_table_offset_line(state)


def _format_scale_cm(scale_factor: float, axis: int | None) -> str:
    """Format a habitus scale factor as centimetres for UI captions."""
    baseline_cm = (
        get_mesh_baseline_torso_width(state.human_mesh)
        if axis is None
        else get_mesh_baseline_extents(state.human_mesh)[axis]
    )
    return format_scale_cm_label(scale_factor, baseline_cm)


def build(ctx: PageContext) -> None:
    """Construct the Settings tab panel and wire control callbacks."""
    def _on_phantom_pose_change() -> None:
        """Reset results and refresh geometry/phantom previews after pose changes."""
        reset_results()
        ctx.refresh_geometry_preview()
        ctx.refresh_phantom_preview()

    with ui.tab_panel("settings"):
        with ui.column().classes("max-w-4xl mx-auto w-full gap-6"):
            ui.label("Calculation Settings").classes("text-2xl font-bold tracking-tight")

            with ui.expansion("Phantom Settings", icon="person", value=True).classes(_SETTINGS_EXPANSION_CLASSES):
                with ui.column().classes(_SETTINGS_SECTION_CLASSES):
                    with ui.row().classes(_SETTINGS_HEADER_ROW_CLASSES):
                        ui.label("Phantom model and positioning").classes("text-subtitle2")
                        HelpButton(
                            title="Phantom Positioning Offsets",
                            content_path="positioning_offsets.md",
                            help_id="settings_positioning",
                        )
                    with ui.row().classes("w-full gap-6"):
                        ui.select(PHANTOM_MODELS, label="Phantom model", value=state.phantom_model).bind_value(
                            state, "phantom_model"
                        ).on(_MODEL_VALUE_EVENT, _on_phantom_pose_change).classes("grow")

                        mesh_options = get_human_mesh_options()
                        state.human_mesh = canonicalize_human_mesh_selection(state.human_mesh, mesh_options)
                        mesh_select = (
                            ui.select(mesh_options, label="Human mesh", value=state.human_mesh)
                            .bind_value(state, "human_mesh")
                            .classes("grow")
                        )

                        def _on_human_mesh_change() -> None:
                            """Validate human-mesh selection and refresh the phantom preview."""
                            if state.human_mesh == DEMO_MESH_SECTION_KEY:
                                # Separator is not a mesh; snap back to a real stem.
                                state.human_mesh = next(
                                    (k for k in mesh_options if k != DEMO_MESH_SECTION_KEY),
                                    "hudfrid",
                                )
                                mesh_select.value = state.human_mesh
                            _on_phantom_pose_change()

                        mesh_select.on(_MODEL_VALUE_EVENT, _on_human_mesh_change)

                    # show/hide mesh selector based on model
                    def _update_mesh_visibility():
                        """Show the human-mesh selector only when phantom model is human."""
                        mesh_select.visible = state.phantom_model == "human"

                    ui.timer(0.5, _update_mesh_visibility)

                    ui.select(ORIENTATIONS, label="Patient orientation", value=state.patient_orientation).bind_value(
                        state, "patient_orientation"
                    ).on(_MODEL_VALUE_EVENT, _on_phantom_pose_change).classes("w-full")

                    with ui.row().classes(_SETTINGS_HEADER_ROW_CLASSES):
                        ui.label("Phantom preview").classes("text-subtitle2")
                        HelpButton(
                            title="Settings phantom preview",
                            content_path="phantom_preview.md",
                            help_id="settings_phantom_preview",
                        )
                    preview_plot = ui.plotly({}).classes("w-full").style("height: 360px")
                    preview_status = ui.label("").classes("text-caption text-grey-5 italic")
                    ui.label(copy_text("settings.phantom_preview.caption")).classes(
                        "text-caption text-grey-5"
                    )
                    preview_controller = PhantomPreviewController(preview_plot, preview_status)
                    ctx.refresh_phantom_preview = preview_controller.schedule_refresh

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

                    patient_offset_single = ui.column().classes(COMPACT_FULL_WIDTH_COLUMN_CLASSES)
                    patient_offset_single.bind_visibility_from(
                        state, "is_multi_exam", backward=lambda v: not v
                    )

                    with patient_offset_single:
                        ui.label("Patient Offsets (adjustable, cm)").classes("text-caption text-grey-6 q-mt-sm")

                        offset_range_hint = ui.label("").classes("text-caption text-grey-5 italic")

                        def _update_offset_range_hint() -> None:
                            """Warn when patient offsets exceed Geometry slider range."""
                            mx = max(abs(state.d_lon), abs(state.d_ver), abs(state.d_lat))
                            if mx > PATIENT_OFFSET_SLIDER_RANGE_CM:
                                offset_range_hint.set_text(
                                    f"One or more offsets exceed the Geometry slider range "
                                    f"(±{PATIENT_OFFSET_SLIDER_RANGE_CM} cm)"
                                )
                            else:
                                offset_range_hint.set_text("")

                        def _on_patient_offset_change() -> None:
                            """Propagate global patient-offset edits and refresh the range hint."""
                            on_global_patient_offset_change(ctx)
                            _update_offset_range_hint()

                        with ui.row().classes("w-full gap-4"):
                            ui.number(label="Longitudinal", value=state.d_lon, step=1.0).bind_value(
                                state, "d_lon"
                            ).on(_MODEL_VALUE_EVENT, _on_patient_offset_change).classes("grow")
                            ui.number(label="Vertical", value=state.d_ver, step=1.0).bind_value(
                                state, "d_ver"
                            ).on(_MODEL_VALUE_EVENT, _on_patient_offset_change).classes("grow")
                            ui.number(label="Lateral", value=state.d_lat, step=1.0).bind_value(
                                state, "d_lat"
                            ).on(_MODEL_VALUE_EVENT, _on_patient_offset_change).classes("grow")

                        _update_offset_range_hint()

                    multi_exam_phantom_caption = ui.label(multi_exam_phantom_offset_caption()).classes(
                        "text-caption text-grey-5 italic q-mt-sm"
                    )
                    multi_exam_phantom_caption.bind_visibility_from(state, "is_multi_exam")

                    scale_section = ui.column().classes("w-full gap-3 q-mt-sm")
                    scale_section.bind_visibility_from(
                        state, "phantom_model", backward=lambda v: v == "human"
                    )
                    with scale_section:
                        ui.label("Body habitus scaling").classes("text-subtitle2")
                        ui.label(
                            "Values show scaled patient dimensions. Width is measured at the torso, below the arms."
                        ).classes("text-caption text-grey-5")
                        for label, attr, axis in (
                            ("Left-right width scale", "phantom_scale_lat", None),
                            ("Anterior-posterior thickness scale", "phantom_scale_ap", 1),
                            ("Superior-inferior length scale", "phantom_scale_lon", 2),
                        ):
                            with ui.column().classes(COMPACT_FULL_WIDTH_COLUMN_CLASSES):
                                with ui.row().classes(f"{_SETTINGS_HEADER_ROW_CLASSES} gap-3"):
                                    ui.label(label).classes("text-body2 font-medium")
                                    scale_label = ui.label().classes("shrink-0 text-caption mono-text text-right")
                                    scale_label.bind_text_from(
                                        state,
                                        attr,
                                        backward=lambda v, a=axis: _format_scale_cm(float(v), a),
                                    )
                                    scale_label.bind_text_from(
                                        state,
                                        "human_mesh",
                                        backward=lambda _v, a=attr, x=axis: _format_scale_cm(
                                            float(getattr(state, a)), x
                                        ),
                                    )
                                ui.slider(
                                    min=0.5,
                                    max=2.0,
                                    step=0.05,
                                    value=getattr(state, attr),
                                ).bind_value(state, attr).on(
                                    _MODEL_VALUE_EVENT, _on_phantom_pose_change
                                ).classes("w-full")

            # Per-exam corrections (offsets, coordinate fixes, table-origin) — one
            # editable block per loaded exam; registers ctx.refresh_per_exam.
            build_per_exam_section(ctx)

            with ui.expansion("Physics Settings", icon="science").classes(_SETTINGS_EXPANSION_CLASSES):
                with ui.column().classes(_SETTINGS_SECTION_CLASSES):
                    ui.checkbox("Use estimated table transmission (k_tab)", value=state.estimate_k_tab).bind_value(
                        state, "estimate_k_tab"
                    ).on(_MODEL_VALUE_EVENT, reset_results)

                    with ui.column().classes(COMPACT_FULL_WIDTH_COLUMN_CLASSES):
                        ui.label("TRANSMISSION FACTOR (k_tab)").classes("technical-label")
                        with ui.row().classes("items-center w-full gap-4"):
                            ui.slider(min=0.0, max=1.0, step=0.01, value=state.k_tab_val).bind_value(
                                state, "k_tab_val"
                            ).on(_MODEL_VALUE_EVENT, reset_results).classes("grow")
                            ui.label().bind_text_from(state, "k_tab_val", backward=lambda v: f"{v:.2f}").classes("mono-text font-bold")

                    ui.number(
                        label="Inherent filtration (mmAl)", value=state.inherent_filtration, min=0.0, step=0.1
                    ).bind_value(state, "inherent_filtration").on(_MODEL_VALUE_EVENT, reset_results).classes("w-full")

                    ui.checkbox("Remove invalid data (kVp = 0)", value=state.remove_invalid_rows).bind_value(
                        state, "remove_invalid_rows"
                    ).on(_MODEL_VALUE_EVENT, reset_results)

                    with ui.column().classes("w-full gap-2"):
                        with ui.row().classes(_SETTINGS_HEADER_ROW_CLASSES):
                            ui.label("Below-floor kVp handling (< 25 kV)").classes("text-subtitle2")
                            HelpButton(
                                title="Below-floor kVp handling",
                                content_path="below_floor_kvp.md",
                                help_id="settings_below_floor_kvp",
                            )
                        ui.select(
                            BELOW_FLOOR_KVP_OPTIONS,
                            label="Policy for events below the HVL table floor",
                            value=state.below_floor_kvp_policy,
                        ).bind_value(state, "below_floor_kvp_policy").on(
                            _MODEL_VALUE_EVENT, reset_results
                        ).classes("w-full")

                        manual_kvp = ui.number(
                            label="Manual kVp", value=state.below_floor_kvp_manual, min=25.0, max=175.0, step=1.0
                        ).bind_value(state, "below_floor_kvp_manual").on(
                            _MODEL_VALUE_EVENT, reset_results
                        ).classes("w-full")

                        def _update_manual_kvp_visibility():
                            """Show the manual kVp field only when policy is manual."""
                            manual_kvp.visible = state.below_floor_kvp_policy == "manual"

                        ui.timer(0.5, _update_manual_kvp_visibility)

                    ui.select(
                        BEAM_MISS_WARN_OPTIONS,
                        label="Beam-miss warning verbosity",
                        value=state.beam_miss_warn,
                    ).bind_value(state, "beam_miss_warn").on(
                        _MODEL_VALUE_EVENT, reset_results
                    ).classes("w-full")

                    with ui.column().classes("w-full gap-2"):
                        with ui.row().classes(_SETTINGS_HEADER_ROW_CLASSES):
                            ui.label("Kerma-meter correction").classes("text-subtitle2")
                            HelpButton(
                                title="Kerma-meter correction",
                                content_path="kerma_meter_correction.md",
                                help_id="settings_kerma_meter_correction",
                            )
                        ui.checkbox(
                            "Enable kerma-meter correction factors",
                            value=state.kerma_meter_enable,
                        ).bind_value(state, "kerma_meter_enable").on(_MODEL_VALUE_EVENT, reset_results)
                        ui.select(
                            {"file": "Lookup file", "prompt": "Prompt before calculation"},
                            label="Correction mode",
                            value=state.kerma_meter_mode,
                        ).bind_value(state, "kerma_meter_mode").on(
                            _MODEL_VALUE_EVENT, reset_results
                        ).classes("w-full")
                        ui.input(
                            label="Correction table path (CSV/TSV/XLSX/JSON)",
                            value=state.kerma_meter_file or "",
                        ).bind_value(state, "kerma_meter_file").on(
                            _MODEL_VALUE_EVENT, reset_results
                        ).classes("w-full")
                        ui.number(
                            label="Default factor (unresolved / table miss)",
                            value=state.kerma_meter_default_factor,
                            min=0.01,
                            step=0.01,
                        ).bind_value(state, "kerma_meter_default_factor").on(
                            _MODEL_VALUE_EVENT, reset_results
                        ).classes("w-full")
                        ui.input(
                            label="Explicit equipment label (optional override)",
                            value=state.kerma_meter_explicit_label or "",
                        ).bind_value(state, "kerma_meter_explicit_label").on(
                            _MODEL_VALUE_EVENT, reset_results
                        ).classes("w-full")
                        ui.label(
                            "CF = (real measured dose) / (unit reported dose). "
                            "Radimetrics Equipment = room; DoseTrack Equipment Name is often the model."
                        ).classes("text-xs text-grey-6")

            with ui.expansion("Visual Settings", icon="palette").classes(_SETTINGS_EXPANSION_CLASSES):
                with ui.column().classes(_SETTINGS_SECTION_CLASSES):
                    ui.checkbox("Auto-render dose map on completion", value=state.plot_dosemap).bind_value(
                        state, "plot_dosemap"
                    )
                    ui.select(COLORSCALES, label="Dose map colorscale", value=state.colorscale).bind_value(
                        state, "colorscale"
                    ).classes("w-full")

    # Initial paint so Settings is not blank until the first control change.
    preview_controller.schedule_refresh()
