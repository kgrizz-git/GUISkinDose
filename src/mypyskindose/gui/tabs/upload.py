"""Upload tab — file load, examples, import preview, and event summary.

Refactor plan Phase 3.3g. The coupling cluster: handlers call shared refreshers
wired onto ``PageContext`` so other tabs and the restore tail reach them without
closing over ``index()`` scope.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from nicegui import run, ui

from ..concurrency import operation_guard, upload_lock
from ..constants import EXAMPLE_FILES
from ..helpers import (
    clear_multi_exam_state,
    get_excel_sheets,
    load_rdsr,
    load_tabular,
    rebuild_rdsr_df,
)
from ..page_context import PageContext
from ..state import reset_results, state
from ..upload_temp_files import (
    clear_all_temp_uploads,
    register_temp_upload,
    remove_temp_upload,
)
from ..widgets.event_table import build as build_event_table
from ..widgets.import_preview import build as build_import_preview

# Reject uploads larger than this (see module docstring in the original app.py).
MAX_UPLOAD_BYTES = 64 * 1024 * 1024  # 64 MiB

_TABULAR_SUFFIXES = frozenset({".csv", ".tsv", ".xlsx", ".xlsm"})

_FORMAT_BADGE_COLORS = {
    "dicom": "purple",
    "dcm": "purple",
    "csv": "teal",
    "tsv": "teal",
    "xlsx": "green",
    "xlsm": "green",
}


def upload_exceeds_limit(num_bytes: int) -> bool:
    """True if an upload of this size must be rejected (see MAX_UPLOAD_BYTES)."""
    return num_bytes > MAX_UPLOAD_BYTES


def build(ctx: PageContext) -> None:
    with ui.tab_panel("upload"):
        with ui.column().classes("max-w-4xl mx-auto w-full gap-6"):
            ui.label("Load File").classes("text-2xl font-bold tracking-tight")

            with ui.card().classes("modern-card w-full border-red-900 bg-red-950/20").bind_visibility_from(
                state, "normalization_method", backward=lambda v: v == "Fallback"
            ):
                with ui.row().classes("items-center gap-3"):
                    ui.icon("warning", color="negative").classes("text-xl icon-outlined")
                    ui.label().bind_text_from(
                        state, "normalization_warnings", backward=lambda ws: f"NORMALIZATION ALERT: {ws[0]}" if ws else ""
                    ).classes("mono-text text-xs font-bold text-red-400")

            with ui.card().classes("modern-card w-full"):
                ui.label("Load file").classes("text-subtitle2 q-mb-xs")
                ui.label(
                    "DICOM RDSR (.dcm) or tabular event table (.csv, .tsv, .xlsx, .xlsm)"
                ).classes("text-sm text-grey-4 q-mb-sm")

                async def handle_upload(e):
                    async with upload_lock:
                        await _do_upload(e)

                async def _do_upload(e):
                    with operation_guard("uploading another file") as proceed:
                        if not proceed:
                            return
                        file_name = e.file.name
                        suffix = Path(file_name).suffix.lower() or ".dcm"
                        data = await e.file.read()
                        from mypyskindose.debug import dprint

                        dprint("GUI", f"Uploading {suffix} file ({len(data)} bytes)")
                        if upload_exceeds_limit(len(data)):
                            upload_status.set_text("Upload rejected — file too large")
                            ui.notify(
                                f"File too large ({len(data) / 1024 / 1024:.1f} MB); "
                                f"limit is {MAX_UPLOAD_BYTES // 1024 // 1024} MB.",
                                type="negative",
                                timeout=8000,
                            )
                            _uploader["el"].reset()
                            return
                        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                            tmp.write(data)
                            tmp_path = Path(tmp.name)
                        register_temp_upload(tmp_path)

                        state.input_sheet_name = 0
                        state.available_sheets = []
                        import_preview.sheet_row.set_visibility(False)

                        upload_status.set_text("PARSING...")
                        if suffix in _TABULAR_SUFFIXES:
                            state.input_source_type = suffix.lstrip(".")
                            ok, msg = await run.io_bound(load_tabular, tmp_path, state)
                        else:
                            state.input_source_type = "dicom"
                            ok, msg = await run.io_bound(load_rdsr, tmp_path, state)
                        if ok:
                            state.file_name = file_name
                            ctx.file_label.set_text(file_name.upper())
                            ctx.events_label.set_text(
                                f"{len(state.rdsr_df) if state.rdsr_df is not None else 0} EVENTS"
                            )
                            upload_status.set_text(f"OK: {msg}")
                            ui.notify(msg, color="positive")
                            n_exams = len(state.loaded_exams)
                            n_events = len(state.rdsr_df) if state.rdsr_df is not None else 0
                            ctx.file_label.set_text(
                                file_name.upper() if n_exams == 1 else f"{n_exams} FILES"
                            )
                            ctx.events_label.set_text(f"{n_events} EVENTS")
                            if state.is_multi_exam:
                                ui.notify(
                                    f"{len(state.loaded_exams)} exams loaded — each gets its own "
                                    "dose map; skin doses are summed across all exams on the "
                                    "phantom (aggregate PSD = peak of the summed map).",
                                    color="blue",
                                    multi_line=True,
                                )
                            reset_results()
                            event_table.refresh()
                            _refresh_exams_table()
                            if state.input_source_type != "dicom":
                                import_preview.refresh()
                                import_preview.set_transform_defaults()
                            if suffix in (".xlsx", ".xlsm"):
                                sheets = await run.io_bound(get_excel_sheets, tmp_path)
                                if len(sheets) > 1:
                                    state.available_sheets = sheets
                                    import_preview.sheet_select.set_options(
                                        {s: s for s in sheets}, value=sheets[0]
                                    )
                                    import_preview.sheet_row.set_visibility(True)
                        else:
                            upload_status.set_text("Could not load — see message")
                            ui.notify(msg, type="negative", timeout=10000, multi_line=True)

                        _uploader["el"].reset()

                uploader_container = ui.column().classes("w-full gap-0")
                _uploader: dict[str, ui.upload] = {}

                def _build_uploader() -> None:
                    uploader_container.clear()
                    with uploader_container:
                        _uploader["el"] = ui.upload(
                            on_upload=handle_upload,
                            label="DRAG AND DROP OR CLICK TO SELECT",
                            max_file_size=MAX_UPLOAD_BYTES,
                            multiple=True,
                        ).props(
                            'accept=".dcm,.csv,.tsv,.xlsx,.xlsm" flat bordered color=deep-purple auto-upload'
                        ).classes("w-full bg-black/40 uploader-no-list")

                _build_uploader()

                with ui.row().classes("w-full justify-end q-mt-xs"):
                    ui.button(
                        "Clear all", icon="restart_alt", on_click=lambda: clear_all_exams()
                    ).props("flat dense size=sm color=grey-5").classes("icon-outlined").tooltip(
                        "Clear all loaded exams and reset the upload area"
                    )

                exams_section_label = ui.label("Loaded files").classes("text-subtitle2 q-mt-md q-mb-xs")
                exams_section_label.set_visibility(False)
                exams_list = ui.column().classes("w-full gap-2")
                exams_list.set_visibility(False)

                def clear_all_exams() -> None:
                    clear_all_temp_uploads()
                    clear_multi_exam_state(state)
                    state.rdsr_df = None
                    state.rdsr_raw_df = None
                    state.file_name = ""
                    state.file_path = None
                    state.input_source_type = ""
                    state.available_sheets = []
                    state.input_sheet_name = 0
                    state.import_provenance = None
                    state.import_warnings = []
                    state.import_has_errors = False
                    state.swap_lat_lon = False
                    state.flip_ap1 = False
                    state.flip_ap2 = False
                    state.manufacturer = ""
                    state.model = ""
                    state.normalization_method = "Unknown"
                    state.normalization_warnings = []
                    state.table_offset_x = 0.0
                    state.table_offset_y = 0.0
                    state.table_offset_z = 0.0
                    reset_results()
                    import_preview.sheet_row.set_visibility(False)
                    ctx.file_label.set_text("No file loaded")
                    ctx.events_label.set_text("0 events")
                    ctx.psd_label.set_text("PSD: 0.00 mGy")
                    upload_status.set_text("No file loaded")
                    example_select.set_value(None)
                    _build_uploader()
                    event_table.refresh()
                    _refresh_exams_table()
                    import_preview.refresh()

                with ui.row().classes("w-full items-center gap-3 q-mt-sm"):
                    ui.label("…or try a bundled example:").classes("text-caption text-grey-5")
                    example_select = ui.select(
                        options=list(EXAMPLE_FILES.keys()),
                        label="Bundled example",
                        value=None,
                    ).classes("grow").mark("example-select")

                upload_status = ui.label("No file loaded").classes("text-caption text-grey-5 q-mt-xs")

                async def load_example():
                    name = example_select.value
                    if not name:
                        return
                    with operation_guard("loading an example") as proceed:
                        if not proceed:
                            return
                        path = EXAMPLE_FILES[name]
                        clear_all_temp_uploads()
                        clear_multi_exam_state(state)
                        state.input_source_type = "dicom"
                        state.swap_lat_lon = False
                        state.flip_ap1 = False
                        state.flip_ap2 = False
                        upload_status.set_text("PARSING...")
                        ok, msg = await run.io_bound(load_rdsr, path, state)
                        if ok:
                            state.file_name = name
                            ctx.file_label.set_text(name.upper())
                            ctx.events_label.set_text(
                                f"{len(state.rdsr_df) if state.rdsr_df is not None else 0} EVENTS"
                            )
                            upload_status.set_text(f"OK: {msg}")
                            ui.notify(msg, color="positive")
                            reset_results()
                            event_table.refresh()
                            _refresh_exams_table()
                        else:
                            upload_status.set_text("Could not load — see message")
                            ui.notify(msg, type="negative", timeout=10000, multi_line=True)

                example_select.on_value_change(lambda: load_example())

                ui.separator().classes("q-my-sm bg-zinc-800")

                with ui.row().classes("w-full items-end gap-4"):
                    schema_select = ui.select(
                        options={
                            "auto": "Auto-detect schema",
                            "normalized": "Normalized",
                            "generic_rdsr_like": "Raw RDSR-like",
                            "radimetrics": "Radimetrics CSV",
                            "dosetrack": "DoseTrack XLSX/CSV",
                        },
                        label="Input schema (tabular files only)",
                        value=state.input_schema,
                    ).bind_value(state, "input_schema").classes("grow")

                async def _on_schema_change():
                    if state.file_path is None or state.input_source_type in ("", "dicom"):
                        return
                    with operation_guard("changing the input schema") as proceed:
                        if not proceed:
                            return
                        state.input_schema = schema_select.value or "auto"
                        upload_status.set_text("RE-PARSING...")
                        ok, msg = await run.io_bound(load_tabular, state.file_path, state, True)
                        if ok:
                            upload_status.set_text(f"OK: {msg}")
                            ui.notify(msg, color="positive")
                            reset_results()
                            event_table.refresh()
                            _refresh_exams_table()
                            import_preview.refresh()
                            import_preview.set_transform_defaults()
                        else:
                            upload_status.set_text("Could not load — see message")
                            ui.notify(msg, type="negative", timeout=10000, multi_line=True)

                schema_select.on_value_change(lambda: _on_schema_change())

            import_preview = build_import_preview(ctx, upload_status)
            event_table = build_event_table()

            def _refresh_exams_table():
                exams_list.clear()
                has_exams = bool(state.loaded_exams)
                exams_section_label.set_visibility(has_exams)
                exams_list.set_visibility(has_exams)
                if has_exams:
                    with exams_list:
                        for idx, exam in enumerate(state.loaded_exams):
                            meta = (
                                state.loaded_exam_meta[idx]
                                if idx < len(state.loaded_exam_meta) else {}
                            )
                            src = (meta.get("source_type") or "?").lower()
                            schema = meta.get("schema") or getattr(
                                getattr(exam, "provenance", None), "schema_name", "—"
                            )
                            study_id = str(exam.study_id) if getattr(exam, "study_id", None) else "—"
                            warnings = meta.get("warnings") or []
                            with ui.card().classes("modern-card w-full bg-blue-950/20 q-pa-sm"):
                                with ui.row().classes("items-center w-full gap-3 no-wrap"):
                                    ui.label(f"#{idx + 1}").classes("text-caption text-grey-5 font-bold")
                                    ui.badge(
                                        src.upper(),
                                        color=_FORMAT_BADGE_COLORS.get(src, "blue"),
                                    ).classes("text-xs")
                                    ui.label(meta.get("file_name", "—")).classes(
                                        "text-caption font-mono truncate"
                                    ).style("max-width: 200px")
                                    ui.label(schema).classes("text-caption text-grey-5")
                                    ui.label(study_id).classes(
                                        "text-caption text-grey-6 font-mono truncate"
                                    ).style("max-width: 160px")
                                    ui.label(f"{len(exam.normalized_data)} ev").classes(
                                        "text-caption text-grey-4"
                                    )
                                    if warnings:
                                        ui.icon("warning", color="orange").classes(
                                            "text-sm icon-outlined"
                                        ).tooltip("; ".join(warnings[:3]))
                                    if meta.get("table_origin_override") is not None:
                                        ui.badge("ORIGIN", color="amber").classes(
                                            "text-xs"
                                        ).tooltip("Manual table-origin override active")
                                    ui.space()
                                    ui.button(
                                        icon="close",
                                        on_click=lambda e, i=idx: _remove_exam(i),
                                    ).props("flat round dense size=sm color=grey-5").classes(
                                        "icon-outlined"
                                    ).tooltip("Remove this exam")
                        if state.is_multi_exam:
                            ui.label(
                                "Edit per-exam offsets and coordinate corrections in "
                                "Settings → Per-exam corrections."
                            ).classes("text-caption text-grey-6 italic q-mt-xs")

                ctx.refresh_per_exam()

            def _remove_exam(index: int) -> None:
                if not (0 <= index < len(state.loaded_exams)):
                    return
                meta = state.loaded_exam_meta[index] if index < len(state.loaded_exam_meta) else {}
                file_path = meta.get("file_path")
                state.loaded_exams.pop(index)
                if index < len(state.loaded_exam_meta):
                    state.loaded_exam_meta.pop(index)

                if file_path is not None and all(
                    m.get("file_path") != file_path for m in state.loaded_exam_meta
                ):
                    remove_temp_upload(file_path)

                rebuild_rdsr_df(state)
                state.is_multi_exam = len(state.loaded_exams) > 1

                n = len(state.loaded_exams)
                n_events = len(state.rdsr_df) if state.rdsr_df is not None else 0
                if n == 0:
                    state.file_name = ""
                    state.file_path = None
                    ctx.file_label.set_text("No file loaded")
                    ctx.events_label.set_text("0 events")
                elif n == 1:
                    meta0 = state.loaded_exam_meta[0]
                    state.file_name = meta0.get("file_name", "")
                    state.file_path = meta0.get("file_path")
                    state.swap_lat_lon = meta0.get("swap_lat_lon", False)
                    state.flip_ap1 = meta0.get("flip_ap1", False)
                    state.flip_ap2 = meta0.get("flip_ap2", False)
                    ctx.file_label.set_text(state.file_name.upper())
                    ctx.events_label.set_text(f"{n_events} EVENTS")
                else:
                    state.file_name = f"{n} files"
                    ctx.file_label.set_text(f"{n} FILES")
                    ctx.events_label.set_text(f"{n_events} EVENTS")

                reset_results()
                ctx.psd_label.set_text("PSD: 0.00 mGy")
                event_table.refresh()
                _refresh_exams_table()
                import_preview.refresh()

            ctx.refresh_event_table = event_table.refresh
            ctx.refresh_import_preview = import_preview.refresh
            ctx.refresh_exams_table = _refresh_exams_table
