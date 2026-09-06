"""Geometry tab layout builders and tab wiring."""

from __future__ import annotations

from typing import TYPE_CHECKING

from nicegui import ui

from ..components import HelpButton
from ..constants import (
    PATIENT_OFFSET_SLIDER_RANGE_CM,
    TABLE_ORIGIN_SLIDER_MAX,
    TABLE_ORIGIN_SLIDER_MIN,
)
from ..geometry_preview import event_select_options, exam_selector_options
from ..helpers import (
    detected_table_origin,
    effective_table_origin,
    exam_supports_table_origin,
    read_patient_offset_value,
)
from ..state import state
from .geometry_controller import GeometryTabController

if TYPE_CHECKING:
    from ..page_context import PageContext

_VIEW_BUTTON_CLASSES = "modern-btn-teal h-12 px-6"
_C1_BANNER = (
    "Multiple exams loaded. Sliders edit the selected exam below. "
    "Calculate uses each exam's own patient offset and table-origin settings. "
    "The 3D preview is for positioning only — it may not show every exam at once. "
    "Geometry and Settings → Per-exam corrections edit the same per-exam data; "
    "Geometry is the interactive 3D surface."
)
_C4_TABLE_ORIGIN_CAPTION = (
    "Table shift applies to the selected exam. Preview shows all exams; "
    "you will see this exam's table move relative to the others."
)



def _build_header(ctrl: GeometryTabController) -> None:
    with ui.row().classes("w-full items-center justify-between"):
        ui.label("Geometry Preview").classes("text-2xl font-bold tracking-tight")
        HelpButton(
            title="Geometry Workflow",
            content_path="geometry_workflow.md",
            help_id="geometry",
        )
    ctrl.refs.vendor_notice = (
        ui.label("").classes("text-caption text-amber-6 italic q-pa-sm modern-card w-full")
    )
    ctrl.refs.vendor_notice.bind_visibility_from(
        state, "rdsr_df", backward=lambda v: v is not None
    )


def _build_multi_exam_controls(ctrl: GeometryTabController) -> None:
    multi_exam_header = ui.column().classes("w-full gap-2")
    multi_exam_header.bind_visibility_from(state, "is_multi_exam")
    with multi_exam_header:
        ui.label(_C1_BANNER).classes("text-caption text-amber-6 italic q-pa-sm modern-card w-full")
        ui.label("Patient and table-origin sliders apply to this exam.").classes(
            "text-caption text-grey-5"
        )
        _initial_exam_options = exam_selector_options(state)
        ctrl.refs.exam_select = ui.select(
            options=_initial_exam_options,
            value=ctrl.exam_select_value(_initial_exam_options),
            label="Selected exam",
        ).classes("w-full")


def _build_patient_offset_controls(ctrl: GeometryTabController) -> None:
    patient_offset_card = ui.card().classes("modern-card w-full q-pa-md")
    with patient_offset_card:
        ui.label("Patient offset (cm)").classes("text-subtitle2")
        ctrl.refs.paused_badge = ui.badge("PAUSED").props("color=amber")
        ctrl.refs.paused_badge.set_visibility(False)
        ctrl.refs.stale_caption = ui.label(
            "Offset changed — run Calculate again for an updated dose map."
        ).classes("text-caption text-amber-6 italic")
        ctrl.refs.stale_caption.set_visibility(False)
        for axis, lbl, attr in (
            ("lon", "Patient offset X (DICOM LON, PT L-R)", "d_lon"),
            ("ver", "Patient offset Y (DICOM VER, PT A-P)", "d_ver"),
            ("lat", "Patient offset Z (DICOM LAT, PT S-I)", "d_lat"),
        ):
            with ui.row().classes("w-full gap-2 items-center flex-nowrap"):
                ui.label(lbl).classes("w-72 text-caption text-grey-6")
                initial = read_patient_offset_value(state, attr)
                slider = ui.slider(
                    min=-PATIENT_OFFSET_SLIDER_RANGE_CM,
                    max=PATIENT_OFFSET_SLIDER_RANGE_CM,
                    step=0.5,
                    value=initial,
                ).classes("grow min-w-[100px]").mark(f"patient-slider-{axis}")
                val_label = ui.label(f"{initial:.1f} cm").classes(
                    "w-20 text-caption mono-text text-right"
                )
                ctrl.refs.patient_sliders[attr] = slider
                ctrl.refs.patient_val_labels[attr] = val_label
        ui.button(
            "Reset patient offset to 0",
            icon="restart_alt",
            on_click=lambda: ctrl.reset_patient_offset(),
        ).props("flat dense color=grey-5").classes("icon-outlined q-mt-sm")


def _build_table_origin_controls(ctrl: GeometryTabController) -> None:
    table_origin_card = ui.card().classes("modern-card w-full q-pa-md")
    table_origin_card.bind_visibility_from(
        state, "loaded_exams", backward=lambda _exams: _table_origin_card_visible()
    )
    table_origin_card.bind_visibility_from(
        state, "active_exam_index", backward=lambda _idx: _table_origin_card_visible()
    )
    with table_origin_card:
        ui.label("Table origin override (cm)").classes("text-subtitle2")
        table_origin_hint = ui.label(_C4_TABLE_ORIGIN_CAPTION).classes(
            "text-caption text-grey-5 italic"
        )
        table_origin_hint.bind_visibility_from(state, "is_multi_exam")
        override_caption = ui.label("Override active").classes("text-caption text-amber-6 italic")
        override_caption.bind_visibility_from(
            state, "loaded_exam_meta", backward=ctrl.override_active_for_active_exam
        )
        override_caption.bind_visibility_from(
            state, "active_exam_index",
            backward=lambda _i: ctrl.override_active_for_active_exam(None),
        )
        idx0 = ctrl.active_exam_index
        meta0 = (
            state.loaded_exam_meta[idx0]
            if idx0 < len(state.loaded_exam_meta)
            else {}
        )
        detected0 = detected_table_origin(meta0) if meta0 else {"x": 0.0, "y": 0.0, "z": 0.0}
        origin0 = effective_table_origin(meta0) if meta0 else detected0
        for key in ("x", "y", "z"):
            with ui.row().classes("w-full gap-2 items-center flex-nowrap"):
                axis_label = {
                    "x": "Table origin X (DICOM LON, PT L-R)",
                    "y": "Table origin Y (DICOM VER, PT A-P)",
                    "z": "Table origin Z (DICOM LAT, PT S-I)",
                }[key]
                ui.label(axis_label).classes("w-72 text-caption text-grey-6")
                lo = min(TABLE_ORIGIN_SLIDER_MIN, float(detected0.get(key, 0.0)) - 50)
                hi = max(TABLE_ORIGIN_SLIDER_MAX, float(detected0.get(key, 0.0)) + 50)
                initial = float(origin0.get(key, 0.0))
                slider = ui.slider(
                    min=lo,
                    max=hi,
                    step=0.5,
                    value=initial,
                ).classes("grow min-w-[100px]").mark(f"table-slider-{key}")
                val_label = ui.label(f"{initial:.1f} cm").classes(
                    "w-20 text-caption mono-text text-right"
                )
                ctrl.refs.table_val_labels[key] = val_label
                ctrl.refs.table_sliders[key] = slider


def _build_event_controls(ctrl: GeometryTabController) -> None:
    with ui.card().classes("modern-card w-auto p-2"):
        ui.label("Event selection").classes("text-xs uppercase opacity-70")
        with ui.row().classes("w-full items-center gap-2"):
            ctrl.refs.geom_exam_select = ui.select(
                options=exam_selector_options(state),
                value=ctrl.exam_select_value(exam_selector_options(state)),
                with_input=True,
            ).classes("w-44 text-caption").mark("geom-exam-select")
            ctrl.refs.geom_exam_select.bind_visibility_from(state, "is_multi_exam")
            ctrl.refs.prev_btn = ui.button(
                icon="chevron_left",
                on_click=lambda: ctrl.step(-1),
            ).props("flat dense round size=sm color=grey-5").mark("geom-event-prev")
            ctrl.refs.geom_event_select = ui.select(
                options=event_select_options(1),
                value=1,
                with_input=True,
            ).classes("w-24 mono-text").mark("geom-event-select")
            ctrl.refs.next_btn = ui.button(
                icon="chevron_right",
                on_click=lambda: ctrl.step(1),
            ).props("flat dense round size=sm color=grey-5").mark("geom-event-next")
        ctrl.refs.geom_event_context = ui.label("").classes(
            "text-caption text-grey-5 q-mt-xs"
        ).mark("geom-event-context")


def _build_preview_controls(ctrl: GeometryTabController) -> None:
    ui.button("Setup view", on_click=lambda: ctrl.preview_setup()).classes(_VIEW_BUTTON_CLASSES)
    ui.button("Single event", on_click=lambda: ctrl.preview_event()).classes(_VIEW_BUTTON_CLASSES)
    ui.button("Full procedure", on_click=lambda: ctrl.preview_procedure()).classes(
        _VIEW_BUTTON_CLASSES
    )
    preview_controls = ui.column().classes("gap-0 justify-center")
    preview_controls.bind_visibility_from(state, "is_multi_exam")
    with preview_controls:
        ctrl.refs.composite_checkbox = ui.checkbox(
            "Show all exams in preview",
            value=False,
        ).classes("text-caption")
        ctrl.refs.preview_caption = ui.label("").classes("text-caption text-grey-5 italic")
    ctrl.refs.spinner = ui.spinner(size="lg", color="indigo").classes("ml-4")
    ctrl.refs.spinner.visible = False


def _build_plot(ctrl: GeometryTabController) -> None:
    with ui.card().classes("w-full modern-card p-0 overflow-hidden"):
        ctrl.refs.plot = ui.plotly({}).classes("w-full").style("height:700px")


def _table_origin_card_visible() -> bool:
    if not state.loaded_exam_meta or not state.loaded_exams:
        return False
    if state.is_multi_exam:
        idx = state.active_exam_index
        if idx is None or idx >= len(state.loaded_exams):
            return False
        return exam_supports_table_origin(state.loaded_exams[idx], state.loaded_exam_meta[idx])
    if len(state.loaded_exams) != 1:
        return False
    return exam_supports_table_origin(state.loaded_exams[0], state.loaded_exam_meta[0])


def build_geometry_tab(ctx: PageContext) -> None:
    """Construct and wire the complete Geometry tab."""
    ctrl = GeometryTabController(ctx)

    with ui.tab_panel("geometry"), ui.column().classes("max-w-6xl mx-auto w-full gap-6"):
        _build_header(ctrl)
        _build_multi_exam_controls(ctrl)

        offset_controls = ui.column().classes("w-full gap-4")
        offset_controls.bind_visibility_from(
            state, "rdsr_df", backward=lambda v: v is not None
        )
        with offset_controls:
            _build_patient_offset_controls(ctrl)
            _build_table_origin_controls(ctrl)

        with ui.row().classes("w-full items-end gap-4"):
            _build_event_controls(ctrl)
            _build_preview_controls(ctrl)

        _build_plot(ctrl)

    ctrl.refs.geom_event_select.on_value_change(ctrl.on_event_select_change)
    ctrl.refs.exam_select.on_value_change(ctrl.on_exam_select_change)
    ctrl.refs.geom_exam_select.on_value_change(ctrl.on_exam_select_change)
    ctrl.refs.composite_checkbox.on_value_change(ctrl.on_composite_toggle)

    for attr, slider in ctrl.refs.patient_sliders.items():
        slider.on_value_change(
            lambda _e, a=attr, s=slider: ctrl.handle_patient_slider_change(a, s)
        )

    for key, slider in ctrl.refs.table_sliders.items():
        slider.on_value_change(
            lambda _e, k=key, s=slider: ctrl.handle_table_slider_change(k, s)
        )

    ctrl.register_context_hooks()
    ctrl.update_preview_caption()
    ctrl.set_stepper_enabled(False)

def build(ctx: PageContext) -> None:
    """Public entry point — delegates to :func:`build_geometry_tab`."""
    build_geometry_tab(ctx)