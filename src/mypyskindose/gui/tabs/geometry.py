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
from ..geometry_preview import preview_event_count
from ..helpers import (
    commit_table_origin_transform,
    effective_table_origin,
    exam_supports_table_origin,
    on_global_patient_offset_change,
    on_global_patient_offset_scrub,
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


def build(ctx: PageContext) -> None:
    slider_timer = None
    last_preview_mode: str | None = None
    live_preview_requested = False
    offset_changed_since_calc = False
    table_origin_pending = False
    composite_preview = False
    last_table_origin_scrub = False
    was_multi_exam = state.is_multi_exam
    exam_selector_guard = {"suppress": False}  # same pattern as table_guard below
    patient_guard = {"suppress": False}

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

                exam_select = ui.select(
                    options=_exam_selector_options(),
                    value=state.active_exam_index if state.active_exam_index is not None else 0,
                    label="Editing exam",
                ).classes("w-full")

            offset_controls = ui.column().classes("w-full gap-4")
            offset_controls.bind_visibility_from(
                state,
                "rdsr_df",
                backward=lambda v: v is not None and not state.is_multi_exam,
            )

            with offset_controls:
                with ui.card().classes("modern-card w-full q-pa-md"):
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
                    with ui.row().classes("w-full gap-4 items-center"):
                        for axis, lbl, attr in (
                            ("lon", "Longitudinal", "d_lon"),
                            ("ver", "Vertical", "d_ver"),
                            ("lat", "Lateral", "d_lat"),
                        ):
                            with ui.column().classes("grow gap-1"):
                                ui.label(lbl).classes("text-caption text-grey-6")
                                slider = ui.slider(
                                    min=-PATIENT_OFFSET_SLIDER_RANGE_CM,
                                    max=PATIENT_OFFSET_SLIDER_RANGE_CM,
                                    step=0.5,
                                    value=getattr(state, attr),
                                ).classes("w-full")
                                slider.bind_value(state, attr)
                                val_label = ui.label().classes("text-caption mono-text")
                                val_label.bind_text_from(
                                    state, attr, backward=lambda v, a=attr: f"{getattr(state, a):.1f} cm"
                                )
                                patient_sliders[attr] = slider

                    ui.button(
                        "Reset patient offset to 0",
                        icon="restart_alt",
                        on_click=lambda: _reset_patient_offset(),
                    ).props("flat dense color=grey-5").classes("icon-outlined q-mt-sm")

                table_origin_card = ui.card().classes("modern-card w-full q-pa-md")
                table_origin_card.bind_visibility_from(
                    state,
                    "loaded_exams",
                    backward=lambda exams: (
                        len(exams) == 1
                        and bool(state.loaded_exam_meta)
                        and exam_supports_table_origin(
                            exams[0],
                            state.loaded_exam_meta[0],
                        )
                    ),
                )

                with table_origin_card:
                    ui.label("Table origin override (cm)").classes("text-subtitle2")
                    override_caption = ui.label("Override active").classes(
                        "text-caption text-amber-6 italic"
                    )
                    override_caption.bind_visibility_from(
                        state,
                        "loaded_exam_meta",
                        backward=lambda _m: (
                            bool(state.loaded_exam_meta)
                            and state.loaded_exam_meta[0].get("table_origin_override") is not None
                        ),
                    )

                    table_sliders: dict[str, ui.slider] = {}
                    table_guard = {"suppress": False}  # see exam_selector_guard above

                    def _active_exam_index() -> int:
                        if state.is_multi_exam and state.active_exam_index is not None:
                            return state.active_exam_index
                        return 0

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
                        origin = effective_table_origin(meta)
                        table_guard["suppress"] = True
                        for key, slider in table_sliders.items():
                            slider.set_value(origin[key])
                        table_guard["suppress"] = False

                    def _sync_patient_sliders_from_meta(active_index: int | None = None) -> None:
                        if state.is_multi_exam:
                            return
                        idx = active_index if active_index is not None else _active_exam_index()
                        if idx >= len(state.loaded_exam_meta):
                            return
                        patient_guard["suppress"] = True
                        for attr, slider in patient_sliders.items():
                            slider.set_value(getattr(state, attr))
                        patient_guard["suppress"] = False

                    with ui.row().classes("w-full gap-4 items-center"):
                        for key in ("x", "y", "z"):
                            with ui.column().classes("grow gap-1"):
                                ui.label(key.upper()).classes("text-caption text-grey-6")
                                detected = (
                                    state.loaded_exam_meta[0].get("table_origin_detected")
                                    if state.loaded_exam_meta
                                    else {"x": 0.0, "y": 0.0, "z": 0.0}
                                ) or {"x": 0.0, "y": 0.0, "z": 0.0}
                                lo = min(
                                    TABLE_ORIGIN_SLIDER_MIN,
                                    float(detected.get(key, 0.0)) - 50,
                                )
                                hi = max(
                                    TABLE_ORIGIN_SLIDER_MAX,
                                    float(detected.get(key, 0.0)) + 50,
                                )
                                initial = (
                                    effective_table_origin(state.loaded_exam_meta[0])[key]
                                    if state.loaded_exam_meta
                                    else 0.0
                                )
                                slider = ui.slider(
                                    min=lo,
                                    max=hi,
                                    step=0.5,
                                    value=initial,
                                ).classes("w-full")

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
        if last_table_origin_scrub:
            return True
        return composite_preview

    def live_preview_allowed() -> bool:
        if state.busy:
            return False
        if last_preview_mode == "plot_procedure":
            if state.is_multi_exam and _resolve_composite_for_render():
                active_idx = state.active_exam_index
                if preview_event_count(state, active_exam_index=active_idx, composite=True) > 30:
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

    async def _do_debounced_render() -> None:
        nonlocal slider_timer, table_origin_pending, live_preview_requested, last_table_origin_scrub
        slider_timer = None
        if table_origin_pending:
            commit_table_origin_transform(state, _active_exam_index())
            table_origin_pending = False
            last_table_origin_scrub = False
            reset_results()
        ctx.refresh_per_exam()
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

    def _on_patient_slider_change() -> None:
        nonlocal offset_changed_since_calc, last_table_origin_scrub
        last_table_origin_scrub = False
        on_global_patient_offset_scrub(ctx)
        offset_changed_since_calc = True
        _update_stale_caption()
        _schedule_debounced_render()

    for slider in patient_sliders.values():
        slider.on_value_change(lambda _e: _on_patient_slider_change())

    def _reset_patient_offset() -> None:
        state.d_lon = 0.0
        state.d_ver = 0.0
        state.d_lat = 0.0
        on_global_patient_offset_change(ctx)
        geom_plot.update_figure({})
        ui.notify("Patient offset reset to 0", color="info")

    def _reset_table_origin() -> None:
        nonlocal table_origin_pending, offset_changed_since_calc
        if not state.loaded_exam_meta:
            return
        meta = state.loaded_exam_meta[0]
        meta["table_origin_override"] = None
        commit_table_origin_transform(state, 0)
        reset_results()
        ctx.refresh_per_exam()
        table_origin_pending = False
        offset_changed_since_calc = True
        _update_stale_caption()
        _sync_table_sliders_from_meta()
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
        exam_select.set_options(_exam_selector_options())
        idx = state.active_exam_index if state.active_exam_index is not None else 0
        exam_select.set_value(idx)
        exam_selector_guard["suppress"] = False

    def _on_exam_select_change(_e) -> None:
        nonlocal last_table_origin_scrub, slider_timer, live_preview_requested, table_origin_pending
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
        _sync_table_sliders_from_meta(new_index)
        _sync_patient_sliders_from_meta(new_index)
        if last_preview_mode:
            live_preview_requested = True
            _schedule_debounced_render()

    exam_select.on_value_change(_on_exam_select_change)

    def _refresh_geometry_sliders() -> None:
        nonlocal composite_preview, last_table_origin_scrub, was_multi_exam
        if was_multi_exam and not state.is_multi_exam:
            composite_preview = False
            last_table_origin_scrub = False
        was_multi_exam = state.is_multi_exam
        _rebuild_exam_selector()
        _sync_table_sliders_from_meta()
        _sync_patient_sliders_from_meta()

    original_refresh_per_exam = ctx.refresh_per_exam

    def _refresh_per_exam_with_sliders() -> None:
        original_refresh_per_exam()
        _refresh_geometry_sliders()

    ctx.refresh_per_exam = _refresh_per_exam_with_sliders
