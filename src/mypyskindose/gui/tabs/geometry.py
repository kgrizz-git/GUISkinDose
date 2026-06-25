"""Geometry preview tab — setup / single-event / full-procedure 3D views.

Interactive patient-offset and table-origin sliders (single-exam) with debounced
live preview. Multi-exam mode: exam selector, C1 banner, and sliced/composite preview.
"""

from __future__ import annotations

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
    composite_live_preview_paused,
    composite_preview_after_exam_mode_change,
    exam_select_value,
    geometry_preview_caption,
    preview_event_count,
    resolve_composite_for_render,
)
from ..helpers import (
    apply_patient_offset_slider_tick,
    commit_table_origin_transform,
    effective_table_origin,
    exam_supports_table_origin,
    on_global_patient_offset_change,
    read_patient_offset_value,
    reset_patient_offset_for_active,
    stage_table_origin_axis,
)
from ..page_context import PageContext
from ..state import event_count, reset_results, state

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


def _table_origin_card_visible() -> bool:
    """Whether the Geometry table-origin card should show for the active exam."""
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


def build(ctx: PageContext) -> None:
    slider_timer = None
    _in_render_chain = False
    last_preview_mode: str | None = None
    live_preview_requested = False
    offset_changed_since_calc = False
    table_origin_pending = False
    composite_preview = False
    last_table_origin_scrub = False
    was_multi_exam = state.is_multi_exam
    exam_selector_guard = {"suppress": False}  # same pattern as table_guard below
    patient_guard = {"suppress": False}

    def _active_exam_index() -> int:
        if state.is_multi_exam and state.active_exam_index is not None:
            return state.active_exam_index
        return 0

    with ui.tab_panel("geometry"):
        with ui.column().classes("max-w-6xl mx-auto w-full gap-6"):
            with ui.row().classes("w-full items-center justify-between"):
                ui.label("Geometry Preview").classes("text-2xl font-bold tracking-tight")
                HelpButton(
                    title="Geometry Workflow",
                    content_path="geometry_workflow.md",
                )

            multi_exam_header = ui.column().classes("w-full gap-2")
            multi_exam_header.bind_visibility_from(state, "is_multi_exam")

            with multi_exam_header:
                ui.label(_C1_BANNER).classes("text-caption text-amber-6 italic q-pa-sm modern-card w-full")
                ui.label("Patient and table-origin sliders apply to this exam.").classes(
                    "text-caption text-grey-5"
                )

                def _exam_selector_options() -> dict[int, str]:
                    return {
                        i: f"#{i + 1} · {meta.get('file_name', '—')}"
                        for i, meta in enumerate(state.loaded_exam_meta)
                    }

                def _exam_select_value(options: dict[int, str] | None = None) -> int | None:
                    opts = options if options is not None else _exam_selector_options()
                    return exam_select_value(
                        state.active_exam_index,
                        set(opts.keys()),
                    )

                _initial_exam_options = _exam_selector_options()
                exam_select = ui.select(
                    options=_initial_exam_options,
                    value=_exam_select_value(_initial_exam_options),
                    label="Selected exam",
                ).classes("w-full")

            preview_controls = ui.column().classes("w-full gap-2")
            preview_controls.bind_visibility_from(state, "is_multi_exam")

            with preview_controls:
                composite_checkbox = ui.checkbox(
                    "Show all exams in preview",
                    value=False,
                ).classes("text-caption")
                preview_caption = ui.label("").classes("text-caption text-grey-5 italic")

            offset_controls = ui.column().classes("w-full gap-4")
            offset_controls.bind_visibility_from(state, "rdsr_df", backward=lambda v: v is not None)

            with offset_controls:
                patient_offset_card = ui.card().classes("modern-card w-full q-pa-md")

                with patient_offset_card:
                    ui.label("Patient offset (cm)").classes("text-subtitle2")
                    paused_badge = ui.badge("PAUSED").props("color=amber")
                    paused_badge.set_visibility(False)

                    stale_caption = ui.label(
                        "Offset changed — run Calculate again for an updated dose map."
                    ).classes("text-caption text-amber-6 italic")

                    def _stale_caption_visible() -> bool:
                        return bool(state.calculation_done and offset_changed_since_calc)

                    def _update_stale_caption() -> None:
                        stale_caption.set_visibility(_stale_caption_visible())

                    stale_caption.set_visibility(False)

                    patient_sliders: dict[str, ui.slider] = {}
                    patient_val_labels: dict[str, ui.label] = {}
                    with ui.row().classes("w-full gap-4 items-center"):
                        for axis, lbl, attr in (
                            ("lon", "Longitudinal", "d_lon"),
                            ("ver", "Vertical", "d_ver"),
                            ("lat", "Lateral", "d_lat"),
                        ):
                            with ui.column().classes("grow gap-1"):
                                ui.label(lbl).classes("text-caption text-grey-6")
                                initial = read_patient_offset_value(state, attr)
                                slider = ui.slider(
                                    min=-PATIENT_OFFSET_SLIDER_RANGE_CM,
                                    max=PATIENT_OFFSET_SLIDER_RANGE_CM,
                                    step=0.5,
                                    value=initial,
                                ).classes("w-full").mark(f"patient-slider-{axis}")
                                val_label = ui.label(f"{initial:.1f} cm").classes("text-caption mono-text")
                                patient_sliders[attr] = slider
                                patient_val_labels[attr] = val_label

                    def _sync_patient_sliders_from_meta(active_index: int | None = None) -> None:
                        idx = active_index if active_index is not None else _active_exam_index()
                        if idx >= len(state.loaded_exam_meta):
                            return
                        patient_guard["suppress"] = True
                        for attr, slider in patient_sliders.items():
                            val = read_patient_offset_value(state, attr, active_index=idx)
                            slider.set_value(val)
                            patient_val_labels[attr].set_text(f"{val:.1f} cm")
                        patient_guard["suppress"] = False

                    ui.button(
                        "Reset patient offset to 0",
                        icon="restart_alt",
                        on_click=lambda: _reset_patient_offset(),
                    ).props("flat dense color=grey-5").classes("icon-outlined q-mt-sm")

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
                    override_caption = ui.label("Override active").classes(
                        "text-caption text-amber-6 italic"
                    )

                    def _override_active_for_active_exam(_m) -> bool:
                        idx = _active_exam_index()
                        if idx >= len(state.loaded_exam_meta):
                            return False
                        return state.loaded_exam_meta[idx].get("table_origin_override") is not None

                    override_caption.bind_visibility_from(
                        state, "loaded_exam_meta", backward=_override_active_for_active_exam
                    )
                    override_caption.bind_visibility_from(
                        state, "active_exam_index", backward=lambda _i: _override_active_for_active_exam(None)
                    )

                    table_sliders: dict[str, ui.slider] = {}
                    table_guard = {"suppress": False}  # see exam_selector_guard above

                    def _table_slider_limits(detected: dict, key: str) -> tuple[float, float]:
                        lo = min(
                            TABLE_ORIGIN_SLIDER_MIN,
                            float(detected.get(key, 0.0)) - 50,
                        )
                        hi = max(
                            TABLE_ORIGIN_SLIDER_MAX,
                            float(detected.get(key, 0.0)) + 50,
                        )
                        return lo, hi

                    def _sync_table_sliders_from_meta(active_index: int | None = None) -> None:
                        idx = active_index if active_index is not None else _active_exam_index()
                        if idx >= len(state.loaded_exam_meta):
                            return
                        meta = state.loaded_exam_meta[idx]
                        if not exam_supports_table_origin(
                            state.loaded_exams[idx] if idx < len(state.loaded_exams) else None,
                            meta,
                        ):
                            return
                        detected = meta.get("table_origin_detected") or {
                            "x": 0.0,
                            "y": 0.0,
                            "z": 0.0,
                        }
                        origin = effective_table_origin(meta)
                        table_guard["suppress"] = True
                        for key, slider in table_sliders.items():
                            lo, hi = _table_slider_limits(detected, key)
                            slider._props["min"] = lo
                            slider._props["max"] = hi
                            slider.update()
                            slider.set_value(origin[key])
                        table_guard["suppress"] = False

                    with ui.row().classes("w-full gap-4 items-center"):
                        idx0 = _active_exam_index()
                        meta0 = (
                            state.loaded_exam_meta[idx0]
                            if idx0 < len(state.loaded_exam_meta)
                            else {}
                        )
                        detected0 = meta0.get("table_origin_detected") or {
                            "x": 0.0,
                            "y": 0.0,
                            "z": 0.0,
                        }
                        origin0 = effective_table_origin(meta0) if meta0 else detected0
                        for key in ("x", "y", "z"):
                            with ui.column().classes("grow gap-1"):
                                ui.label(key.upper()).classes("text-caption text-grey-6")
                                lo, hi = _table_slider_limits(detected0, key)
                                initial = float(origin0.get(key, 0.0))
                                slider = ui.slider(
                                    min=lo,
                                    max=hi,
                                    step=0.5,
                                    value=initial,
                                ).classes("w-full").mark(f"table-slider-{key}")

                                def _on_table_slider(e, k=key, s=slider) -> None:
                                    nonlocal table_origin_pending, offset_changed_since_calc, last_table_origin_scrub
                                    if table_guard["suppress"] or not state.loaded_exam_meta:
                                        return
                                    idx = _active_exam_index()
                                    if idx >= len(state.loaded_exam_meta):
                                        return
                                    stage_table_origin_axis(
                                        state.loaded_exam_meta[idx],
                                        k,
                                        float(s.value or 0.0),
                                    )
                                    table_origin_pending = True
                                    last_table_origin_scrub = True
                                    offset_changed_since_calc = True
                                    _update_stale_caption()
                                    _update_preview_caption()
                                    _schedule_debounced_render()

                                slider.on_value_change(_on_table_slider)
                                table_sliders[key] = slider

                    ui.button(
                        "Reset to auto-detected",
                        icon="restart_alt",
                        on_click=lambda: _reset_table_origin(),
                    ).props("flat dense color=grey-5").classes("icon-outlined q-mt-sm")

            with ui.row().classes("w-full items-end gap-4"):
                with ui.card().classes("modern-card w-48 p-2"):
                    ui.label("Event selection").classes("text-xs uppercase opacity-70")
                    geom_event_input = ui.number(value=0, min=0, step=1).classes(
                        "w-full mono-text"
                    ).props("dense flat")

                ui.button("Setup view", on_click=lambda: preview_setup()).classes(
                    "modern-btn-teal h-12 px-6"
                )
                ui.button("Single event", on_click=lambda: preview_event()).classes(
                    "modern-btn-teal h-12 px-6"
                )
                ui.button("Full procedure", on_click=lambda: preview_procedure()).classes(
                    "modern-btn-teal h-12 px-6"
                )

                geom_spinner = ui.spinner(size="lg", color="indigo").classes("ml-4")
                geom_spinner.visible = False

            with ui.card().classes("w-full modern-card p-0 overflow-hidden"):
                geom_plot = ui.plotly({}).classes("w-full").style("height:700px")

    def _resolve_composite_for_render() -> bool:
        return resolve_composite_for_render(
            composite_preview=composite_preview,
            last_table_origin_scrub=last_table_origin_scrub,
        )

    def _update_preview_caption() -> None:
        preview_caption.set_text(
            geometry_preview_caption(
                state,
                composite_preview=composite_preview,
                last_table_origin_scrub=last_table_origin_scrub,
            )
        )

    def live_preview_allowed() -> bool:
        if state.busy:
            return False
        if composite_live_preview_paused(
            state,
            last_preview_mode=last_preview_mode,
            composite_preview=composite_preview,
            last_table_origin_scrub=last_table_origin_scrub,
        ):
            return False
        return True

    def _update_paused_badge() -> None:
        blocked = live_preview_requested and not live_preview_allowed()
        paused_badge.set_visibility(blocked)

    def _schedule_debounced_render() -> None:
        nonlocal slider_timer, live_preview_requested
        live_preview_requested = True
        _update_paused_badge()
        if slider_timer is not None:
            slider_timer.cancel()
        slider_timer = ui.timer(GEOMETRY_DEBOUNCE_SEC, _do_debounced_render, once=True)

    def _request_geometry_preview_refresh() -> None:
        if last_preview_mode:
            _schedule_debounced_render()

    ctx.refresh_geometry_preview = _request_geometry_preview_refresh

    async def _do_debounced_render() -> None:
        nonlocal slider_timer, table_origin_pending, live_preview_requested
        nonlocal last_table_origin_scrub, _in_render_chain
        slider_timer = None
        if table_origin_pending:
            commit_table_origin_transform(state, _active_exam_index())
            table_origin_pending = False
            last_table_origin_scrub = False
            reset_results()
        _in_render_chain = True
        try:
            ctx.refresh_per_exam()
        finally:
            _in_render_chain = False
        _update_preview_caption()
        if live_preview_requested and live_preview_allowed() and last_preview_mode:
            await _render_preview(last_preview_mode)
        live_preview_requested = False
        _update_paused_badge()

    async def _render_preview(mode: str) -> None:
        if state.rdsr_df is None:
            geom_plot.update_figure({})
            return
        active_idx = state.active_exam_index if state.is_multi_exam else None
        composite = _resolve_composite_for_render() if state.is_multi_exam else False
        if state.is_multi_exam and composite:
            count = preview_event_count(state, active_exam_index=active_idx, composite=True)
            geom_spinner.visible = count > 100
        else:
            geom_spinner.visible = event_count() > 100
        event_idx = int(geom_event_input.value or 0) if mode == "plot_event" else 0
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
        geom_spinner.visible = False
        if fig:
            geom_plot.update_figure(fig)
        else:
            geom_plot.update_figure({})

    def _on_patient_slider_change(attr: str, slider: ui.slider) -> None:
        nonlocal offset_changed_since_calc, last_table_origin_scrub
        if patient_guard["suppress"]:
            return
        apply_patient_offset_slider_tick(state, attr, float(slider.value or 0.0))
        patient_val_labels[attr].set_text(f"{float(slider.value or 0.0):.1f} cm")
        last_table_origin_scrub = False
        offset_changed_since_calc = True
        _update_stale_caption()
        _update_preview_caption()
        _schedule_debounced_render()

    for attr, slider in patient_sliders.items():
        slider.on_value_change(lambda _e, a=attr, s=slider: _on_patient_slider_change(a, s))

    def _reset_patient_offset() -> None:
        nonlocal offset_changed_since_calc
        reset_patient_offset_for_active(state)
        if not state.is_multi_exam:
            on_global_patient_offset_change(ctx)
        else:
            reset_results()
            ctx.refresh_per_exam()
        _sync_patient_sliders_from_meta()
        offset_changed_since_calc = True
        _update_stale_caption()
        geom_plot.update_figure({})
        ui.notify("Patient offset reset to 0", color="info")

    def _reset_table_origin() -> None:
        nonlocal table_origin_pending, offset_changed_since_calc, last_table_origin_scrub
        if not state.loaded_exam_meta:
            return
        idx = state.active_exam_index if state.is_multi_exam else 0
        if idx is None or idx >= len(state.loaded_exam_meta):
            return
        meta = state.loaded_exam_meta[idx]
        meta["table_origin_override"] = None
        commit_table_origin_transform(state, idx)
        reset_results()
        ctx.refresh_per_exam()
        table_origin_pending = False
        last_table_origin_scrub = False
        offset_changed_since_calc = True
        _update_stale_caption()
        _sync_table_sliders_from_meta(idx)
        geom_plot.update_figure({})
        ui.notify("Table origin reset to auto-detected", color="info")

    def _clear_offset_stale_caption() -> None:
        nonlocal offset_changed_since_calc
        offset_changed_since_calc = False
        _update_stale_caption()

    ctx.clear_offset_stale_caption = _clear_offset_stale_caption

    async def preview_setup() -> None:
        nonlocal last_preview_mode, live_preview_requested
        if state.rdsr_df is None:
            ui.notify("Load data first", type="warning")
            return
        last_preview_mode = "plot_setup"
        live_preview_requested = True
        if live_preview_allowed():
            await _render_preview("plot_setup")
        else:
            _update_paused_badge()

    async def preview_event() -> None:
        nonlocal last_preview_mode, live_preview_requested
        if state.rdsr_df is None:
            ui.notify("Load data first", type="warning")
            return
        last_preview_mode = "plot_event"
        live_preview_requested = True
        if live_preview_allowed():
            await _render_preview("plot_event")
        else:
            _update_paused_badge()

    async def preview_procedure() -> None:
        nonlocal last_preview_mode, live_preview_requested
        if state.rdsr_df is None:
            ui.notify("Load data first", type="warning")
            return
        last_preview_mode = "plot_procedure"
        live_preview_requested = True
        if live_preview_allowed():
            await _render_preview("plot_procedure")
        else:
            _update_paused_badge()

    def _rebuild_exam_selector() -> None:
        if not state.is_multi_exam:
            return
        exam_selector_guard["suppress"] = True
        opts = _exam_selector_options()
        exam_select.set_options(opts)
        exam_select.set_value(_exam_select_value(opts))
        exam_selector_guard["suppress"] = False

    def _on_exam_select_change(_e) -> None:
        nonlocal last_table_origin_scrub, slider_timer, table_origin_pending
        if exam_selector_guard["suppress"]:
            return
        old_index = state.active_exam_index
        if slider_timer is not None:
            slider_timer.cancel()
            slider_timer = None
        if table_origin_pending and old_index is not None:
            commit_table_origin_transform(state, old_index)
            table_origin_pending = False
        new_index = int(exam_select.value or 0)
        state.active_exam_index = new_index
        last_table_origin_scrub = False
        _update_preview_caption()
        ctx.refresh_per_exam()

    exam_select.on_value_change(_on_exam_select_change)

    def _on_composite_toggle(e) -> None:
        nonlocal composite_preview, live_preview_requested
        composite_preview = bool(e.value)
        _update_preview_caption()
        _update_paused_badge()
        if last_preview_mode:
            live_preview_requested = True
            _schedule_debounced_render()

    composite_checkbox.on_value_change(_on_composite_toggle)

    def _refresh_geometry_sliders() -> None:
        nonlocal composite_preview, last_table_origin_scrub, was_multi_exam
        nonlocal live_preview_requested, _in_render_chain
        composite_preview = composite_preview_after_exam_mode_change(
            was_multi_exam,
            state.is_multi_exam,
            composite_preview,
        )
        if was_multi_exam and not state.is_multi_exam:
            last_table_origin_scrub = False
            composite_checkbox.set_value(False)
        was_multi_exam = state.is_multi_exam
        _rebuild_exam_selector()
        _sync_table_sliders_from_meta()
        _sync_patient_sliders_from_meta()
        _update_preview_caption()
        active_idx = state.active_exam_index if state.is_multi_exam else None
        composite = _resolve_composite_for_render() if state.is_multi_exam else False
        clamped = clamp_geometry_event_index(
            state,
            int(geom_event_input.value or 0),
            active_exam_index=active_idx,
            composite=composite,
        )
        geom_event_input.set_value(clamped)
        if last_preview_mode and not _in_render_chain:
            live_preview_requested = True
            _schedule_debounced_render()

    original_refresh_per_exam = ctx.refresh_per_exam

    def _refresh_per_exam_with_sliders() -> None:
        original_refresh_per_exam()
        _refresh_geometry_sliders()

    ctx.refresh_per_exam = _refresh_per_exam_with_sliders
    _update_preview_caption()
