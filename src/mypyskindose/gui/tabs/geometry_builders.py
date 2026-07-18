"""Geometry tab controller, view references, and layout builders.

Sibling module to ``geometry.py``; owns the ``GeometryTabController`` (tab-local
state and callbacks), ``GeometryViewRefs`` (UI element handles), and the layout
builder functions.  ``geometry.py`` remains the thin public entry point that
``app.py`` imports.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from nicegui import run, ui

from ..components import HelpButton
from ..constants import (
    GEOMETRY_DEBOUNCE_SEC,
    PATIENT_OFFSET_SLIDER_RANGE_CM,
    TABLE_ORIGIN_SLIDER_MAX,
    TABLE_ORIGIN_SLIDER_MIN,
)
from ..figures import make_geometry_fig
from ..geometry_preview import (
    clamp_geometry_event_index,
    composite_preview_after_exam_mode_change,
    event_context_caption,
    event_select_options,
    exam_select_value,
    exam_selector_options,
    geometry_preview_caption,
    geometry_vendor_notice,
    preview_event_count,
    procedure_live_preview_paused,
    resolve_composite_for_render,
)
from ..helpers import (
    apply_patient_offset_slider_tick,
    commit_table_origin_transform,
    detected_table_origin,
    effective_table_origin,
    exam_supports_table_origin,
    on_global_patient_offset_change,
    read_patient_offset_value,
    reset_patient_offset_for_active,
    stage_table_origin_axis,
)
from ..state import event_count, reset_results, state

if TYPE_CHECKING:
    from ..page_context import PageContext

_VIEW_BUTTON_CLASSES = "modern-btn-teal h-12 px-6"
_LOAD_DATA_FIRST_MESSAGE = "Load data first"
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


class GeometryTabController:
    """Tab-local state and callbacks for the Geometry preview tab.

    Owns only UI references, guard flags, and timer state.  ``AppState``
    remains the source of truth for loaded data, offsets, and results.
    """

    def __init__(self, ctx: PageContext) -> None:
        self.ctx = ctx
        self.exam_selector_guard = {"suppress": False}
        self.event_select_guard = {"suppress": False}
        self.patient_guard = {"suppress": False}
        self.table_guard = {"suppress": False}
        self._in_render_chain = False
        self.last_preview_mode: str | None = None
        self.live_preview_requested = False
        self.offset_changed_since_calc = False
        self.table_origin_pending = False
        self.composite_preview = False
        self.last_table_origin_scrub = False
        self.was_multi_exam = state.is_multi_exam
        self.auto_initialized = False
        self.last_load_signature: tuple | None = None
        self.refs: GeometryViewRefs = GeometryViewRefs()
        self._slider_timer = None

    @property
    def active_exam_index(self) -> int:
        if state.is_multi_exam and state.active_exam_index is not None:
            return state.active_exam_index
        return 0

    def current_load_signature(self) -> tuple | None:
        if state.rdsr_df is None or not state.loaded_exam_meta:
            return None
        return (
            len(state.loaded_exam_meta),
            tuple(m.get("file_name", "") for m in state.loaded_exam_meta),
        )

    def middle_event_index(self, active_idx: int | None, composite: bool) -> int:
        count = (
            preview_event_count(state, active_exam_index=active_idx, composite=composite)
            if state.is_multi_exam
            else event_count()
        )
        return count // 2 if count > 0 else 0

    def live_preview_allowed(self) -> bool:
        if state.busy:
            return False
        return not procedure_live_preview_paused(
            state,
            last_preview_mode=self.last_preview_mode,
            composite_preview=self.composite_preview,
            last_table_origin_scrub=self.last_table_origin_scrub,
        )

    def exam_select_value(self, options: dict[int, str] | None = None) -> int | None:
        opts = options if options is not None else exam_selector_options(state)
        return exam_select_value(state.active_exam_index, set(opts.keys()))

    def update_preview_caption(self) -> None:
        self.refs.preview_caption.set_text(
            geometry_preview_caption(
                state,
                composite_preview=self.composite_preview,
                last_table_origin_scrub=self.last_table_origin_scrub,
            )
        )
        idx = self.active_exam_index
        meta = state.loaded_exam_meta[idx] if idx < len(state.loaded_exam_meta) else {}
        self.refs.vendor_notice.set_text(
            geometry_vendor_notice(
                meta,
                manufacturer=state.manufacturer,
                model=state.model,
                normalization_method=state.normalization_method,
            )
        )

    def stale_caption_visible(self) -> bool:
        return bool(state.calculation_done and self.offset_changed_since_calc)

    def update_stale_caption(self) -> None:
        self.refs.stale_caption.set_visibility(self.stale_caption_visible())

    def override_active_for_active_exam(self, _m=None) -> bool:
        idx = self.active_exam_index
        if idx >= len(state.loaded_exam_meta):
            return False
        return state.loaded_exam_meta[idx].get("table_origin_override") is not None

    def schedule_debounced_render(self) -> None:
        self.live_preview_requested = True
        self._update_paused_badge()
        if self._slider_timer is not None:
            self._slider_timer.cancel()
        self._slider_timer = ui.timer(GEOMETRY_DEBOUNCE_SEC, self._do_debounced_render, once=True)

    async def _do_debounced_render(self) -> None:
        self._slider_timer = None
        if self.table_origin_pending:
            commit_table_origin_transform(state, self.active_exam_index)
            self.table_origin_pending = False
            self.last_table_origin_scrub = False
            reset_results()
        self._in_render_chain = True
        try:
            self.ctx.refresh_per_exam()
        finally:
            self._in_render_chain = False
        self.update_preview_caption()
        if self.live_preview_requested and self.live_preview_allowed() and self.last_preview_mode:
            await self._render_preview(self.last_preview_mode)
        self.live_preview_requested = False
        self._update_paused_badge()

    async def _render_preview(self, mode: str) -> None:
        if state.rdsr_df is None:
            self.refs.plot.update_figure({})
            return
        active_idx = state.active_exam_index if state.is_multi_exam else None
        composite = self._resolve_composite_for_render() if state.is_multi_exam else False
        if state.is_multi_exam and composite:
            count = preview_event_count(state, active_exam_index=active_idx, composite=True)
            self.refs.spinner.visible = count > 100
        else:
            self.refs.spinner.visible = event_count() > 100
        event_idx = (
            max(0, int(self.refs.geom_event_select.value or 1) - 1)
            if mode == "plot_event"
            else 0
        )
        slice_count = (
            preview_event_count(state, active_exam_index=active_idx, composite=composite)
            if state.is_multi_exam
            else event_count()
        )
        if mode == "plot_event" and slice_count > 0:
            event_idx = min(max(0, event_idx), slice_count - 1)
        fig = await run.io_bound(
            make_geometry_fig,
            mode,
            event_idx,
            active_exam_index=active_idx,
            composite=composite,
        )
        self.refs.spinner.visible = False
        self.refs.plot.update_figure(fig if fig else {})

    def _resolve_composite_for_render(self) -> bool:
        return resolve_composite_for_render(
            composite_preview=self.composite_preview,
            last_table_origin_scrub=self.last_table_origin_scrub,
        )

    def update_event_context(self) -> None:
        composite = self._resolve_composite_for_render() if state.is_multi_exam else False
        self.refs.geom_event_context.set_text(
            event_context_caption(
                state,
                current_index=max(0, int(self.refs.geom_event_select.value or 1) - 1),
                active_exam_index=state.active_exam_index if state.is_multi_exam else None,
                composite=composite,
            )
        )

    def render_event_preview_debounced(self) -> None:
        if self.last_preview_mode != "plot_event":
            self.last_preview_mode = "plot_event"
        self.update_event_context()
        self.schedule_debounced_render()

    def _update_paused_badge(self) -> None:
        blocked = self.live_preview_requested and not self.live_preview_allowed()
        self.refs.paused_badge.set_visibility(blocked)

    def _preview_slice_count(self) -> int:
        if state.is_multi_exam:
            return preview_event_count(
                state,
                active_exam_index=state.active_exam_index,
                composite=self._resolve_composite_for_render(),
            )
        return event_count()

    def step(self, delta: int) -> None:
        if self.last_preview_mode != "plot_event":
            return
        count = self._preview_slice_count()
        if count <= 0:
            return
        current = int(self.refs.geom_event_select.value or 1)
        new_idx = min(max(1, current + delta), max(1, count))
        self.event_select_guard["suppress"] = True
        try:
            self.refs.geom_event_select.set_value(new_idx)
        finally:
            self.event_select_guard["suppress"] = False
        self._render_event_preview_debounced()

    def _render_event_preview_debounced(self) -> None:
        if self.last_preview_mode != "plot_event":
            self.last_preview_mode = "plot_event"
        self.update_event_context()
        self.schedule_debounced_render()

    def set_stepper_enabled(self, enabled: bool) -> None:
        self.refs.geom_event_select.set_enabled(enabled)
        self.refs.prev_btn.set_enabled(enabled)
        self.refs.next_btn.set_enabled(enabled)

    def on_event_select_change(self, _e) -> None:
        if self.event_select_guard["suppress"]:
            return
        if self.last_preview_mode != "plot_event":
            return
        self.update_event_context()
        self.schedule_debounced_render()

    def on_exam_select_change(self, e) -> None:
        if self.exam_selector_guard["suppress"]:
            return
        old_index = state.active_exam_index
        if self._slider_timer is not None:
            self._slider_timer.cancel()
            self._slider_timer = None
        if self.table_origin_pending and old_index is not None:
            commit_table_origin_transform(state, old_index)
            self.table_origin_pending = False
        new_index = int(
            e.value
            if e and hasattr(e, "value") and e.value is not None
            else (self.refs.exam_select.value or 0)
        )
        self.exam_selector_guard["suppress"] = True
        try:
            self.refs.exam_select.set_value(new_index)
            self.refs.geom_exam_select.set_value(new_index)
        finally:
            self.exam_selector_guard["suppress"] = False
        state.active_exam_index = new_index
        self.last_table_origin_scrub = False
        self.update_preview_caption()
        self.update_event_context()
        self.ctx.refresh_per_exam()

    def rebuild_exam_selector(self) -> None:
        if not state.is_multi_exam:
            return
        self.exam_selector_guard["suppress"] = True
        opts = exam_selector_options(state)
        val = self.exam_select_value(opts)
        self.refs.exam_select.set_options(opts)
        self.refs.exam_select.set_value(val)
        self.refs.geom_exam_select.set_options(opts)
        self.refs.geom_exam_select.set_value(val)
        self.exam_selector_guard["suppress"] = False

    def on_composite_toggle(self, e) -> None:
        self.composite_preview = bool(e.value)
        self.update_preview_caption()
        self.update_event_context()
        self._update_paused_badge()
        if self.last_preview_mode:
            self.live_preview_requested = True
            self.schedule_debounced_render()

    def sync_patient_sliders_from_meta(self, active_index: int | None = None) -> None:
        idx = active_index if active_index is not None else self.active_exam_index
        if idx >= len(state.loaded_exam_meta):
            return
        self.patient_guard["suppress"] = True
        for attr, slider in self.refs.patient_sliders.items():
            val = read_patient_offset_value(state, attr, active_index=idx)
            slider.set_value(val)
            self.refs.patient_val_labels[attr].set_text(f"{val:.1f} cm")
        self.patient_guard["suppress"] = False

    def sync_table_sliders_from_meta(self, active_index: int | None = None) -> None:
        idx = active_index if active_index is not None else self.active_exam_index
        if idx >= len(state.loaded_exam_meta):
            return
        meta = state.loaded_exam_meta[idx]
        if not exam_supports_table_origin(
            state.loaded_exams[idx] if idx < len(state.loaded_exams) else None,
            meta,
        ):
            return
        detected = detected_table_origin(meta)
        origin = effective_table_origin(meta)
        self.table_guard["suppress"] = True
        for key, slider in self.refs.table_sliders.items():
            lo = min(TABLE_ORIGIN_SLIDER_MIN, float(detected.get(key, 0.0)) - 50)
            hi = max(TABLE_ORIGIN_SLIDER_MAX, float(detected.get(key, 0.0)) + 50)
            slider._props["min"] = lo
            slider._props["max"] = hi
            slider.update()
            slider.set_value(origin[key])
            self.refs.table_val_labels[key].set_text(f"{origin[key]:.1f} cm")
        self.table_guard["suppress"] = False

    def handle_patient_slider_change(self, attr: str, slider: ui.slider) -> None:
        if self.patient_guard["suppress"]:
            return
        apply_patient_offset_slider_tick(state, attr, float(slider.value or 0.0))
        self.refs.patient_val_labels[attr].set_text(f"{float(slider.value or 0.0):.1f} cm")
        self.last_table_origin_scrub = False
        self.offset_changed_since_calc = True
        self.update_stale_caption()
        self.update_preview_caption()
        self.schedule_debounced_render()

    def handle_table_slider_change(self, key: str, slider: ui.slider) -> None:
        if self.table_guard["suppress"] or not state.loaded_exam_meta:
            return
        idx = self.active_exam_index
        if idx >= len(state.loaded_exam_meta):
            return
        stage_table_origin_axis(
            state.loaded_exam_meta[idx],
            key,
            float(slider.value or 0.0),
        )
        self.table_origin_pending = True
        self.last_table_origin_scrub = True
        self.offset_changed_since_calc = True
        self.update_stale_caption()
        self.update_preview_caption()
        self.refs.table_val_labels[key].set_text(f"{float(slider.value or 0.0):.1f} cm")
        self.schedule_debounced_render()

    def reset_patient_offset(self) -> None:
        reset_patient_offset_for_active(state)
        if not state.is_multi_exam:
            on_global_patient_offset_change(self.ctx)
        else:
            reset_results()
            self.ctx.refresh_per_exam()
        self.sync_patient_sliders_from_meta()
        self.offset_changed_since_calc = True
        self.update_stale_caption()
        self.refs.plot.update_figure({})
        ui.notify("Patient offset reset to 0", color="info")

    def reset_table_origin(self) -> None:
        if not state.loaded_exam_meta:
            return
        idx = state.active_exam_index if state.is_multi_exam else 0
        if idx is None or idx >= len(state.loaded_exam_meta):
            return
        meta = state.loaded_exam_meta[idx]
        meta["table_origin_override"] = None
        commit_table_origin_transform(state, idx)
        reset_results()
        self.ctx.refresh_per_exam()
        self.table_origin_pending = False
        self.last_table_origin_scrub = False
        self.offset_changed_since_calc = True
        self.update_stale_caption()
        self.sync_table_sliders_from_meta(idx)
        self.refs.plot.update_figure({})
        ui.notify("Table origin reset to auto-detected", color="info")

    def clear_offset_stale_caption(self) -> None:
        self.offset_changed_since_calc = False
        self.update_stale_caption()

    def request_geometry_preview_refresh(self) -> None:
        if self.last_preview_mode:
            self.schedule_debounced_render()

    def register_context_hooks(self) -> None:
        self.ctx.clear_offset_stale_caption = self.clear_offset_stale_caption
        self.ctx.refresh_geometry_preview = self.request_geometry_preview_refresh
        original_refresh_per_exam = self.ctx.refresh_per_exam

        def _refresh_per_exam_with_sliders() -> None:
            original_refresh_per_exam()
            self.refresh_geometry_sliders()

        self.ctx.refresh_per_exam = _refresh_per_exam_with_sliders
        self.ctx.refresh_geometry_tab = self.refresh_geometry_sliders

    def refresh_geometry_sliders(self) -> None:
        self.composite_preview = composite_preview_after_exam_mode_change(
            self.was_multi_exam,
            state.is_multi_exam,
            self.composite_preview,
        )
        if self.was_multi_exam and not state.is_multi_exam:
            self.last_table_origin_scrub = False
            self.refs.composite_checkbox.set_value(False)
        self.was_multi_exam = state.is_multi_exam
        self.rebuild_exam_selector()
        self.sync_table_sliders_from_meta()
        self.sync_patient_sliders_from_meta()
        self.update_preview_caption()
        active_idx = state.active_exam_index if state.is_multi_exam else None
        composite = self._resolve_composite_for_render() if state.is_multi_exam else False
        sig = self.current_load_signature()
        if sig != self.last_load_signature:
            self.last_load_signature = sig
            self.auto_initialized = False
        self.event_select_guard["suppress"] = True
        try:
            self.refs.geom_event_select.set_options(event_select_options(self._preview_slice_count()))
            if (
                not self.auto_initialized
                and state.rdsr_df is not None
                and state.active_tab == "geometry"
            ):
                self.auto_initialized = True
                self.last_preview_mode = "plot_event"
                self.refs.geom_event_select.set_value(
                    self.middle_event_index(active_idx, composite) + 1
                )
            clamped = clamp_geometry_event_index(
                state,
                max(0, int(self.refs.geom_event_select.value or 1) - 1),
                active_exam_index=active_idx,
                composite=composite,
            )
            self.refs.geom_event_select.set_value(clamped + 1)
        finally:
            self.event_select_guard["suppress"] = False
        self.set_stepper_enabled(self.last_preview_mode == "plot_event")
        self.update_event_context()
        if self.last_preview_mode and not self._in_render_chain:
            self.live_preview_requested = True
            self.schedule_debounced_render()

    async def preview_setup(self) -> None:
        if state.rdsr_df is None:
            ui.notify(_LOAD_DATA_FIRST_MESSAGE, type="warning")
            return
        self.last_preview_mode = "plot_setup"
        self.set_stepper_enabled(False)
        self.live_preview_requested = True
        if self.live_preview_allowed():
            await self._render_preview("plot_setup")
        else:
            self._update_paused_badge()

    async def preview_event(self) -> None:
        if state.rdsr_df is None:
            ui.notify(_LOAD_DATA_FIRST_MESSAGE, type="warning")
            return
        self.last_preview_mode = "plot_event"
        self.set_stepper_enabled(True)
        self.live_preview_requested = True
        if self.live_preview_allowed():
            await self._render_preview("plot_event")
        else:
            self._update_paused_badge()

    async def preview_procedure(self) -> None:
        if state.rdsr_df is None:
            ui.notify(_LOAD_DATA_FIRST_MESSAGE, type="warning")
            return
        self.last_preview_mode = "plot_procedure"
        self.set_stepper_enabled(False)
        self.live_preview_requested = True
        self.last_table_origin_scrub = False
        await self._render_preview("plot_procedure")
        self._update_paused_badge()


@dataclass
class GeometryViewRefs:
    """UI element references owned by the Geometry tab."""

    spinner: ui.spinner = None  # type: ignore[assignment]
    vendor_notice: ui.label = None  # type: ignore[assignment]
    preview_caption: ui.label = None  # type: ignore[assignment]
    exam_select: ui.select = None  # type: ignore[assignment]
    geom_exam_select: ui.select = None  # type: ignore[assignment]
    geom_event_select: ui.select = None  # type: ignore[assignment]
    geom_event_context: ui.label = None  # type: ignore[assignment]
    prev_btn: ui.button = None  # type: ignore[assignment]
    next_btn: ui.button = None  # type: ignore[assignment]
    composite_checkbox: ui.checkbox = None  # type: ignore[assignment]
    plot: ui.plotly = None  # type: ignore[assignment]
    paused_badge: ui.badge = None  # type: ignore[assignment]
    stale_caption: ui.label = None  # type: ignore[assignment]
    patient_sliders: dict[str, ui.slider] = field(default_factory=dict)
    patient_val_labels: dict[str, ui.label] = field(default_factory=dict)
    table_sliders: dict[str, ui.slider] = field(default_factory=dict)
    table_val_labels: dict[str, ui.label] = field(default_factory=dict)


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

    with ui.tab_panel("geometry"):
        with ui.column().classes("max-w-6xl mx-auto w-full gap-6"):
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
