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

``build_per_exam_section`` stays a thin layout/registration shell; the card and
control builders below are module-level helpers taking explicit ``ctx``/``meta``
arguments (no closure over the tab body) to keep each function's cognitive
complexity low.
"""

from __future__ import annotations

from nicegui import ui

from ..helpers import (
    apply_exam_transforms,
    bump_per_exam_offsets_version,
    commit_table_origin_transform,
    detected_table_origin,
    effective_table_origin,
    exam_supports_table_origin,
    exam_supports_transforms,
    stage_table_origin_axis,
)
from ..page_context import PageContext
from ..state import reset_results, state
from ..ui_copy import copy_text

_MUTED_CAPTION_CLASSES = "text-caption text-grey-6"


def _invalidate(ctx: PageContext) -> None:
    """Mark results stale after any per-exam edit."""
    reset_results()
    ctx.psd_label.set_text("PSD: 0.00 mGy")


def _apply_global_offset_to_all(ctx: PageContext) -> None:
    """Copy the global patient offset (Phantom settings above) into every loaded
    exam's per-exam offset, overwriting any per-exam edits."""
    for meta in state.loaded_exam_meta:
        meta["d_lon"] = state.d_lon
        meta["d_ver"] = state.d_ver
        meta["d_lat"] = state.d_lat
    bump_per_exam_offsets_version(state)
    _invalidate(ctx)
    ctx.refresh_per_exam()
    ui.notify(
        f"Applied global offset ({state.d_lon}, {state.d_ver}, "
        f"{state.d_lat} cm) to all {len(state.loaded_exam_meta)} exams.",
        color="blue",
    )


def _on_exam_offset_change(ctx: PageContext) -> None:
    """A per-exam offset spinbox changed — invalidate stale results."""
    bump_per_exam_offsets_version(state)
    _invalidate(ctx)
    ctx.refresh_per_exam()


def _on_exam_transform_change(ctx: PageContext, index: int, key: str, value) -> None:
    """A per-exam coordinate-correction toggle changed: store the flag, re-derive
    that exam's data from its base, and invalidate results."""
    if not (0 <= index < len(state.loaded_exam_meta)):
        return
    state.loaded_exam_meta[index][key] = bool(value)
    apply_exam_transforms(state, index)
    _invalidate(ctx)
    ctx.refresh_event_table()
    ctx.refresh_import_preview()
    ctx.refresh_per_exam()
    ctx.refresh_geometry_tab()


def _build_table_origin_section(ctx: PageContext, index: int, meta: dict) -> None:
    """Per-exam 'Advanced: table origin' override UI (Phase 2.5).

    Spinboxes pre-fill from the active override (or the auto-detected origin);
    'Reset to auto-detected' clears the override back to None.
    """
    detected = detected_table_origin(meta)
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
        ).classes(_MUTED_CAPTION_CLASSES)
        status_label = ui.label(_status_text()).classes("text-caption text-amber-400 italic")

        def _on_change(key: str, value) -> None:
            if guard["suppress"]:
                return
            stage_table_origin_axis(meta, key, float(value or 0.0))
            commit_table_origin_transform(state, index)
            _invalidate(ctx)
            ctx.refresh_event_table()
            ctx.refresh_import_preview()
            status_label.set_text(_status_text())
            ctx.refresh_geometry_tab()

        def _on_reset() -> None:
            meta["table_origin_override"] = None
            commit_table_origin_transform(state, index)
            # Revert spinboxes without re-triggering _on_change.
            guard["suppress"] = True
            for k, inp in inputs.items():
                inp.set_value(detected[k])
            guard["suppress"] = False
            _invalidate(ctx)
            ctx.refresh_event_table()
            ctx.refresh_import_preview()
            status_label.set_text(_status_text())
            ctx.refresh_geometry_tab()

        current = effective_table_origin(meta)
        with ui.row().classes("items-center gap-2"):
            for key in ("x", "y", "z"):
                axis_label = {
                    "x": "Table origin X (DICOM LON, PT L-R)",
                    "y": "Table origin Y (DICOM VER, PT A-P)",
                    "z": "Table origin Z (DICOM LAT, PT S-I)",
                }[key]
                inputs[key] = ui.number(
                    label=axis_label,
                    value=current.get(key, 0.0),
                    step=1.0,
                    format="%.1f",
                ).props("dense outlined").classes("w-64").on_value_change(
                    lambda e, k=key: _on_change(k, e.value)
                )
            ui.button(
                "Reset to auto-detected",
                icon="restart_alt",
                on_click=_on_reset,
            ).props("flat dense size=sm color=grey-5").classes("icon-outlined")


def _build_patient_offset_row(ctx: PageContext, meta: dict) -> None:
    """Per-exam patient offset (Phase 2.3) — bound directly to the meta dict;
    consumed by run_calculation in multi-exam mode."""
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
            ).props("dense outlined").classes("w-20").bind_value(meta, axis).on_value_change(
                lambda: _on_exam_offset_change(ctx)
            )


def _build_coordinate_corrections(ctx: PageContext, idx: int, meta: dict) -> None:
    """Per-exam coordinate corrections (Phase 2.2) — only for non-normalized
    tabular exams; each toggle re-derives this exam independently."""
    with ui.expansion("Coordinate corrections", icon="tune").classes("w-full").props("dense"):
        ui.switch(
            "Swap lateral ↔ longitudinal (Tx ↔ Tz)",
            value=meta.get("swap_lat_lon", False),
        ).on_value_change(
            lambda e, i=idx: _on_exam_transform_change(ctx, i, "swap_lat_lon", e.value)
        ).tooltip(copy_text("per_exam.tx_tz_swap.tooltip"))
        ui.switch(
            "Flip primary angle (Ap1 × −1)",
            value=meta.get("flip_ap1", False),
        ).on_value_change(
            lambda e, i=idx: _on_exam_transform_change(ctx, i, "flip_ap1", e.value)
        )
        ui.switch(
            "Flip secondary angle (Ap2 × −1)",
            value=meta.get("flip_ap2", False),
        ).on_value_change(
            lambda e, i=idx: _on_exam_transform_change(ctx, i, "flip_ap2", e.value)
        )
        # Axis-direction sign flips (Phase 2.4) — reverse the direction of a table
        # axis when this export's convention runs opposite the global/auto one.
        ui.separator().props("dense")
        ui.label("Axis directions (reverse table motion):").classes(_MUTED_CAPTION_CLASSES)
        ui.switch(
            "Reverse longitudinal (Tx × −1)",
            value=meta.get("flip_tx", False),
        ).on_value_change(
            lambda e, i=idx: _on_exam_transform_change(ctx, i, "flip_tx", e.value)
        )
        ui.switch(
            "Reverse height (Ty × −1)",
            value=meta.get("flip_ty", False),
        ).on_value_change(
            lambda e, i=idx: _on_exam_transform_change(ctx, i, "flip_ty", e.value)
        )
        ui.switch(
            "Reverse lateral (Tz × −1)",
            value=meta.get("flip_tz", False),
        ).on_value_change(
            lambda e, i=idx: _on_exam_transform_change(ctx, i, "flip_tz", e.value)
        )


def _build_exam_card_header(idx: int, meta: dict) -> None:
    src = (meta.get("source_type") or "?").lower()
    with ui.row().classes("items-center w-full gap-3 no-wrap"):
        ui.label(f"#{idx + 1}").classes("text-caption text-grey-5 font-bold")
        ui.label(meta.get("file_name", "—")).classes("text-caption font-mono truncate").style("max-width: 240px")
        ui.label(src.upper()).classes(_MUTED_CAPTION_CLASSES)
        if meta.get("table_origin_override") is not None:
            ui.badge("ORIGIN", color="amber").classes("text-xs").tooltip(
                copy_text("upload.exam.table_origin.tooltip")
            )


def _build_exam_card(ctx: PageContext, idx: int, exam, meta: dict) -> None:
    card_classes = "modern-card w-full bg-blue-950/20 q-pa-sm"
    if state.is_multi_exam and state.active_exam_index == idx:
        card_classes += " border-2 border-amber-6"
    with ui.card().classes(card_classes):
        _build_exam_card_header(idx, meta)
        # Per-exam patient offsets are hidden for a single exam (the global offset
        # applies via analyze_data).
        if state.is_multi_exam and meta:
            _build_patient_offset_row(ctx, meta)
        if state.is_multi_exam and exam_supports_transforms(exam, meta):
            _build_coordinate_corrections(ctx, idx, meta)
        # Manual table-origin override (Phase 2.5) — escape hatch for a misdetected
        # scanner or a tabular export with no convention metadata. Shown for
        # single- and multi-exam.
        if exam_supports_table_origin(exam, meta):
            _build_table_origin_section(ctx, idx, meta)


def _build_global_offset_row(ctx: PageContext) -> None:
    """Multi-exam 'Apply global to all' control (patient offsets only take effect
    in multi-exam mode via analyze_multiple_exams)."""
    with ui.row().classes("w-full items-center gap-3 q-mb-xs"):
        global_offset_label = ui.label("").classes(_MUTED_CAPTION_CLASSES)

        def _global_offset_text() -> str:
            return f"Global patient offset: {state.d_lon}, {state.d_ver}, {state.d_lat} cm"

        global_offset_label.set_text(_global_offset_text())
        for axis in ("d_lon", "d_ver", "d_lat"):
            global_offset_label.bind_text_from(state, axis, backward=lambda _v: _global_offset_text())
        ui.space()
        ui.button(
            "Apply global to all",
            icon="content_copy",
            on_click=lambda: _apply_global_offset_to_all(ctx),
        ).props("flat dense size=sm color=grey-5").classes("icon-outlined").tooltip(
            "Copy the global patient offset (Phantom settings) into every "
            "exam, overwriting per-exam edits"
        )


def _refresh_per_exam(ctx: PageContext, empty_hint: ui.label, exams_list: ui.column) -> None:
    exams_list.clear()
    has_exams = bool(state.loaded_exams)
    empty_hint.set_visibility(not has_exams)
    exams_list.set_visibility(has_exams)
    if not has_exams:
        return
    with exams_list:
        if state.is_multi_exam:
            _build_global_offset_row(ctx)
        for idx, exam in enumerate(state.loaded_exams):
            meta = state.loaded_exam_meta[idx] if idx < len(state.loaded_exam_meta) else {}
            _build_exam_card(ctx, idx, exam, meta)


def build_per_exam_section(ctx: PageContext) -> None:
    """Build the per-exam corrections UI and register ``ctx.refresh_per_exam``."""
    with ui.expansion("Per-exam corrections", icon="rule", value=True).classes("modern-card w-full"):
        with ui.column().classes("w-full gap-3 q-pa-md"):
            ui.label(
                "Patient offsets, coordinate corrections, and table-origin overrides "
                "applied per exam. Editing one exam never affects another. Load files "
                "in the Upload tab; the loaded-files summary (and removal) lives there."
            ).classes(_MUTED_CAPTION_CLASSES)
            empty_hint = ui.label("No exams loaded yet — load a file in the Upload tab.").classes(
                "text-caption text-grey-5 italic"
            )
            exams_list = ui.column().classes("w-full gap-2")

    def refresh() -> None:
        _refresh_per_exam(ctx, empty_hint, exams_list)

    ctx.refresh_per_exam = refresh
    refresh()
