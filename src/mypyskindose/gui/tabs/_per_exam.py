"""Per-exam corrections section (mounted under the Settings tab).

Extracted from the Upload tab (the multi-exam "per-exam corrections → Settings"
TO_DO, and the ``app.py`` decomposition): each loaded exam gets its own
patient-offset, coordinate-correction, and table-origin controls so one exam can
be edited without affecting another. The compact loaded-files summary (with the
remove button) stays on the Upload tab; only the editable controls live here.

State lives in ``state.loaded_exam_meta`` (the single source of truth, parallel to
``state.loaded_exams``). Data re-derivation is delegated to
``helpers.apply_exam_transforms``; cross-tab view refreshes go through the
``PageContext`` callbacks (``refresh_event_table`` / ``refresh_import_preview``),
which the upload tab wires before this section is built. ``ctx.refresh_per_exam``
is registered here so the upload tab can re-render these cards on load/remove.
"""

from __future__ import annotations

from nicegui import ui

from ..helpers import (
    apply_exam_transforms,
    commit_table_origin_transform,
    exam_supports_table_origin,
    exam_supports_transforms,
    stage_table_origin_axis,
)
from ..page_context import PageContext
from ..state import reset_results, state


def build_per_exam_section(ctx: PageContext) -> None:
    """Build the per-exam corrections UI and register ``ctx.refresh_per_exam``."""

    def _invalidate() -> None:
        """Mark results stale after any per-exam edit."""
        reset_results()
        ctx.psd_label.set_text("PSD: 0.00 mGy")

    def _apply_global_offset_to_all() -> None:
        """Copy the global patient offset (Phantom settings above) into every
        loaded exam's per-exam offset, overwriting any per-exam edits."""
        for meta in state.loaded_exam_meta:
            meta["d_lon"] = state.d_lon
            meta["d_ver"] = state.d_ver
            meta["d_lat"] = state.d_lat
        _invalidate()
        refresh()
        ui.notify(
            f"Applied global offset ({state.d_lon}, {state.d_ver}, "
            f"{state.d_lat} cm) to all {len(state.loaded_exam_meta)} exams.",
            color="blue",
        )

    def _on_exam_offset_change() -> None:
        """A per-exam offset spinbox changed — invalidate stale results."""
        _invalidate()
        ctx.refresh_per_exam()

    def _on_exam_transform_change(index: int, key: str, value) -> None:
        """A per-exam coordinate-correction toggle changed: store the flag,
        re-derive that exam's data from its base, and invalidate results."""
        if not (0 <= index < len(state.loaded_exam_meta)):
            return
        state.loaded_exam_meta[index][key] = bool(value)
        apply_exam_transforms(state, index)
        _invalidate()
        ctx.refresh_event_table()
        ctx.refresh_import_preview()

    def _build_table_origin_section(index: int, meta: dict) -> None:
        """Per-exam 'Advanced: table origin' override UI (Phase 2.5).

        Spinboxes pre-fill from the active override (or the auto-detected
        origin); 'Reset to auto-detected' clears the override back to None.
        """
        detected = meta.get("table_origin_detected") or {"x": 0.0, "y": 0.0, "z": 0.0}
        inputs: dict[str, ui.number] = {}
        guard = {"suppress": False}

        def _status_text() -> str:
            return (
                "Override active — using manual origin"
                if meta.get("table_origin_override") is not None
                else "Using auto-detected origin"
            )

        with ui.expansion("Advanced: table origin", icon="open_with").classes("w-full").props("dense"):
            ui.label(
                "Override the table coordinate origin (cm) for a misdetected "
                "scanner or a tabular export without convention metadata. "
                "This changes the dose map."
            ).classes("text-caption text-grey-6")
            status_label = ui.label(_status_text()).classes("text-caption text-amber-400 italic")

            def _on_change(key: str, value) -> None:
                if guard["suppress"]:
                    return
                stage_table_origin_axis(meta, key, float(value or 0.0))
                commit_table_origin_transform(state, index)
                _invalidate()
                ctx.refresh_event_table()
                ctx.refresh_import_preview()
                status_label.set_text(_status_text())

            def _on_reset() -> None:
                meta["table_origin_override"] = None
                commit_table_origin_transform(state, index)
                # Revert spinboxes without re-triggering _on_change.
                guard["suppress"] = True
                for k, inp in inputs.items():
                    inp.set_value(detected[k])
                guard["suppress"] = False
                _invalidate()
                ctx.refresh_event_table()
                ctx.refresh_import_preview()
                status_label.set_text(_status_text())

            current = meta.get("table_origin_override") or detected
            with ui.row().classes("items-center gap-2"):
                for key in ("x", "y", "z"):
                    inputs[key] = ui.number(
                        label=key,
                        value=current.get(key, 0.0),
                        step=1.0,
                        format="%.1f",
                    ).props("dense outlined").classes("w-20").on_value_change(
                        lambda e, k=key: _on_change(k, e.value)
                    )
                ui.button(
                    "Reset to auto-detected",
                    icon="restart_alt",
                    on_click=_on_reset,
                ).props("flat dense size=sm color=grey-5").classes("icon-outlined")

    def _build_exam_card(idx: int, exam, meta: dict) -> None:
        src = (meta.get("source_type") or "?").lower()
        with ui.card().classes("modern-card w-full bg-blue-950/20 q-pa-sm"):
            with ui.row().classes("items-center w-full gap-3 no-wrap"):
                ui.label(f"#{idx + 1}").classes("text-caption text-grey-5 font-bold")
                ui.label(meta.get("file_name", "—")).classes(
                    "text-caption font-mono truncate"
                ).style("max-width: 240px")
                ui.label(src.upper()).classes("text-caption text-grey-6")
                if meta.get("table_origin_override") is not None:
                    ui.badge("ORIGIN", color="amber").classes("text-xs").tooltip(
                        "Manual table-origin override active"
                    )

            # Per-exam patient offset (Phase 2.3) — bound directly to the meta dict;
            # consumed by run_calculation in multi-exam mode. Hidden for a single
            # exam (the global offset applies via analyze_data).
            if state.is_multi_exam and meta:
                with ui.row().classes("items-center gap-2 q-mt-xs"):
                    ui.label("Patient offset (cm):").classes("text-caption text-grey-5")
                    for axis, lbl in (("d_lon", "lon"), ("d_ver", "ver"), ("d_lat", "lat")):
                        meta.setdefault(axis, 0.0)
                        ui.number(
                            label=lbl,
                            value=meta[axis],
                            min=-50,
                            max=50,
                            step=1.0,
                            format="%.1f",
                        ).props("dense outlined").classes("w-20").bind_value(
                            meta, axis
                        ).on_value_change(_on_exam_offset_change)

            # Per-exam coordinate corrections (Phase 2.2) — only for non-normalized
            # tabular exams; each toggle re-derives this exam independently.
            if state.is_multi_exam and exam_supports_transforms(exam, meta):
                with ui.expansion("Coordinate corrections", icon="tune").classes("w-full").props("dense"):
                    ui.switch(
                        "Swap lateral ↔ longitudinal (Tx ↔ Tz)",
                        value=meta.get("swap_lat_lon", False),
                    ).on_value_change(
                        lambda e, i=idx: _on_exam_transform_change(i, "swap_lat_lon", e.value)
                    ).tooltip("Auto-enabled for GE exports; verify for others.")
                    ui.switch(
                        "Flip primary angle (Ap1 × −1)",
                        value=meta.get("flip_ap1", False),
                    ).on_value_change(
                        lambda e, i=idx: _on_exam_transform_change(i, "flip_ap1", e.value)
                    )
                    ui.switch(
                        "Flip secondary angle (Ap2 × −1)",
                        value=meta.get("flip_ap2", False),
                    ).on_value_change(
                        lambda e, i=idx: _on_exam_transform_change(i, "flip_ap2", e.value)
                    )
                    # Axis-direction sign flips (Phase 2.4) — reverse the direction of
                    # a table axis when this export's convention runs opposite the
                    # global/auto one.
                    ui.separator().props("dense")
                    ui.label("Axis directions (reverse table motion):").classes(
                        "text-caption text-grey-6"
                    )
                    ui.switch(
                        "Reverse longitudinal (Tx × −1)",
                        value=meta.get("flip_tx", False),
                    ).on_value_change(
                        lambda e, i=idx: _on_exam_transform_change(i, "flip_tx", e.value)
                    )
                    ui.switch(
                        "Reverse height (Ty × −1)",
                        value=meta.get("flip_ty", False),
                    ).on_value_change(
                        lambda e, i=idx: _on_exam_transform_change(i, "flip_ty", e.value)
                    )
                    ui.switch(
                        "Reverse lateral (Tz × −1)",
                        value=meta.get("flip_tz", False),
                    ).on_value_change(
                        lambda e, i=idx: _on_exam_transform_change(i, "flip_tz", e.value)
                    )

            # Manual table-origin override (Phase 2.5) — escape hatch for a
            # misdetected scanner or a tabular export with no convention metadata.
            # Shown for single- and multi-exam.
            if exam_supports_table_origin(exam, meta):
                _build_table_origin_section(idx, meta)

    def refresh() -> None:
        exams_list.clear()
        has_exams = bool(state.loaded_exams)
        empty_hint.set_visibility(not has_exams)
        exams_list.set_visibility(has_exams)
        if not has_exams:
            return
        with exams_list:
            # Per-exam patient offsets only take effect in multi-exam mode
            # (analyze_multiple_exams); a single exam uses the global offset via
            # analyze_data, so the global-copy control is hidden for one file.
            if state.is_multi_exam:
                with ui.row().classes("w-full items-center gap-3 q-mb-xs"):
                    global_offset_label = ui.label("").classes("text-caption text-grey-6")

                    def _global_offset_text() -> str:
                        return (
                            f"Global patient offset: {state.d_lon}, "
                            f"{state.d_ver}, {state.d_lat} cm"
                        )

                    global_offset_label.set_text(_global_offset_text())
                    global_offset_label.bind_text_from(
                        state, "d_lon", backward=lambda _v: _global_offset_text()
                    )
                    global_offset_label.bind_text_from(
                        state, "d_ver", backward=lambda _v: _global_offset_text()
                    )
                    global_offset_label.bind_text_from(
                        state, "d_lat", backward=lambda _v: _global_offset_text()
                    )
                    ui.space()
                    ui.button(
                        "Apply global to all",
                        icon="content_copy",
                        on_click=_apply_global_offset_to_all,
                    ).props("flat dense size=sm color=grey-5").classes("icon-outlined").tooltip(
                        "Copy the global patient offset (Phantom settings) into every "
                        "exam, overwriting per-exam edits"
                    )
            for idx, exam in enumerate(state.loaded_exams):
                meta = state.loaded_exam_meta[idx] if idx < len(state.loaded_exam_meta) else {}
                _build_exam_card(idx, exam, meta)

    with ui.expansion("Per-exam corrections", icon="rule", value=True).classes("modern-card w-full"):
        with ui.column().classes("w-full gap-3 q-pa-md"):
            ui.label(
                "Patient offsets, coordinate corrections, and table-origin overrides "
                "applied per exam. Editing one exam never affects another. Load files "
                "in the Upload tab; the loaded-files summary (and removal) lives there."
            ).classes("text-caption text-grey-6")
            empty_hint = ui.label("No exams loaded yet — load a file in the Upload tab.").classes(
                "text-caption text-grey-5 italic"
            )
            exams_list = ui.column().classes("w-full gap-2")

    ctx.refresh_per_exam = refresh
    refresh()
