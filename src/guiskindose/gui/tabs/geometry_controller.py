"""Geometry tab controller — state, callbacks, and preview orchestration."""

from __future__ import annotations

from typing import TYPE_CHECKING

from nicegui import run, ui

from ..constants import (
    GEOMETRY_DEBOUNCE_SEC,
    TABLE_ORIGIN_SLIDER_MAX,
    TABLE_ORIGIN_SLIDER_MIN,
)
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
from .geometry_view_refs import GeometryViewRefs

if TYPE_CHECKING:
    from ..page_context import PageContext

_LOAD_DATA_FIRST_MESSAGE = "Load data first"



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
        """Active exam index."""
        if state.is_multi_exam and state.active_exam_index is not None:
            return state.active_exam_index
        return 0

    def current_load_signature(self) -> tuple | None:
        """Current load signature."""
        if state.rdsr_df is None or not state.loaded_exam_meta:
            return None
        return (
            len(state.loaded_exam_meta),
            tuple(m.get("file_name", "") for m in state.loaded_exam_meta),
        )

    def middle_event_index(self, active_idx: int | None, composite: bool) -> int:
        """Middle event index."""
        count = (
            preview_event_count(state, active_exam_index=active_idx, composite=composite)
            if state.is_multi_exam
            else event_count()
        )
        return count // 2 if count > 0 else 0

    def live_preview_allowed(self) -> bool:
        """Live preview allowed."""
        if state.busy:
            return False
        return not procedure_live_preview_paused(
            state,
            last_preview_mode=self.last_preview_mode,
            composite_preview=self.composite_preview,
            last_table_origin_scrub=self.last_table_origin_scrub,
        )

    def exam_select_value(self, options: dict[int, str] | None = None) -> int | None:
        """Exam select value."""
        opts = options if options is not None else exam_selector_options(state)
        return exam_select_value(state.active_exam_index, set(opts.keys()))

    def update_preview_caption(self) -> None:
        """Update preview caption."""
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
        """Stale caption visible."""
        return bool(state.calculation_done and self.offset_changed_since_calc)

    def update_stale_caption(self) -> None:
        """Update stale caption."""
        self.refs.stale_caption.set_visibility(self.stale_caption_visible())

    def override_active_for_active_exam(self, _m=None) -> bool:
        """Override active for active exam."""
        idx = self.active_exam_index
        if idx >= len(state.loaded_exam_meta):
            return False
        return state.loaded_exam_meta[idx].get("table_origin_override") is not None

    def schedule_debounced_render(self) -> None:
        """Schedule debounced render."""
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

    def flush_pending_table_origin(self) -> None:
        """Cancel pending debounce timer and commit table-origin transform synchronously.

        Called before calculation starts to prevent a race between the debounced
        render and run_calculation reading loaded_exams.
        """
        if self._slider_timer is not None:
            self._slider_timer.cancel()
            self._slider_timer = None
        if self.table_origin_pending:
            commit_table_origin_transform(state, self.active_exam_index)
            self.table_origin_pending = False
            self.last_table_origin_scrub = False
            reset_results()

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
        from guiskindose.gui.tabs import geometry_builders as gb

        fig = await run.io_bound(
            gb.make_geometry_fig,
            mode,
            event_idx,
            active_exam_index=active_idx,
            composite=composite,
        )
        self.refs.spinner.visible = False
        self.refs.plot.update_figure(fig or {})

    def _resolve_composite_for_render(self) -> bool:
        return resolve_composite_for_render(
            composite_preview=self.composite_preview,
            last_table_origin_scrub=self.last_table_origin_scrub,
        )

    def update_event_context(self) -> None:
        """Update event context."""
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
        """Render event preview debounced."""
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
        """Step."""
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
        self.render_event_preview_debounced()

    def set_stepper_enabled(self, enabled: bool) -> None:
        """Set stepper enabled."""
        self.refs.geom_event_select.set_enabled(enabled)
        self.refs.prev_btn.set_enabled(enabled)
        self.refs.next_btn.set_enabled(enabled)

    def on_event_select_change(self, _e) -> None:
        """Handle event select change."""
        if self.event_select_guard["suppress"]:
            return
        if self.last_preview_mode != "plot_event":
            return
        self.update_event_context()
        self.schedule_debounced_render()

    def on_exam_select_change(self, e) -> None:
        """Handle exam select change."""
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
        """Rebuild exam selector."""
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
        """Handle composite toggle."""
        self.composite_preview = bool(e.value)
        self.update_preview_caption()
        self.update_event_context()
        self._update_paused_badge()
        if self.last_preview_mode:
            self.live_preview_requested = True
            self.schedule_debounced_render()

    def sync_patient_sliders_from_meta(self, active_index: int | None = None) -> None:
        """Sync patient sliders from meta."""
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
        """Sync table sliders from meta."""
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
        """Handle patient slider change."""
        if self.patient_guard["suppress"]:
            return
        apply_patient_offset_slider_tick(state, attr, float(slider.value or 0.0))
        self.refs.patient_val_labels[attr].set_text(f"{float(slider.value or 0.0):.1f} cm")
        self.last_table_origin_scrub = False
        self.offset_changed_since_calc = True
        self.update_stale_caption()
        self.update_preview_caption()
        self.schedule_debounced_render()
        self.ctx.refresh_phantom_preview()

    def handle_table_slider_change(self, key: str, slider: ui.slider) -> None:
        """Handle table slider change."""
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
        """Reset patient offset."""
        reset_patient_offset_for_active(state)
        if not state.is_multi_exam:
            on_global_patient_offset_change(self.ctx)
        else:
            reset_results()
            self.ctx.refresh_per_exam()
            self.ctx.refresh_phantom_preview()
        self.sync_patient_sliders_from_meta()
        self.offset_changed_since_calc = True
        self.update_stale_caption()
        self.refs.plot.update_figure({})
        ui.notify("Patient offset reset to 0", color="info")

    def reset_table_origin(self) -> None:
        """Reset table origin."""
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
        """Clear offset stale caption."""
        self.offset_changed_since_calc = False
        self.update_stale_caption()

    def request_geometry_preview_refresh(self) -> None:
        """Request geometry preview refresh."""
        if self.last_preview_mode:
            self.schedule_debounced_render()

    def register_context_hooks(self) -> None:
        """Register context hooks."""
        self.ctx.clear_offset_stale_caption = self.clear_offset_stale_caption
        self.ctx.refresh_geometry_preview = self.request_geometry_preview_refresh
        self.ctx.flush_geometry_pending = self.flush_pending_table_origin
        original_refresh_per_exam = self.ctx.refresh_per_exam

        def _refresh_per_exam_with_sliders() -> None:
            original_refresh_per_exam()
            self.refresh_geometry_sliders()

        self.ctx.refresh_per_exam = _refresh_per_exam_with_sliders
        self.ctx.refresh_geometry_tab = self.refresh_geometry_sliders

    def refresh_geometry_sliders(self) -> None:
        """Refresh geometry sliders."""
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
        """Preview setup."""
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
        """Preview event."""
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
        """Preview procedure."""
        if state.rdsr_df is None:
            ui.notify(_LOAD_DATA_FIRST_MESSAGE, type="warning")
            return
        self.last_preview_mode = "plot_procedure"
        self.set_stepper_enabled(False)
        self.live_preview_requested = True
        self.last_table_origin_scrub = False
        await self._render_preview("plot_procedure")
        self._update_paused_badge()
