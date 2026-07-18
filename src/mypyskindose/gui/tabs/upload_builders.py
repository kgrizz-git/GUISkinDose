"""Upload tab controller, view references, and layout builders.

Sibling module to ``upload.py``; owns the ``UploadTabController`` (tab-local
state and async callbacks), ``UploadViewRefs`` (UI element handles), and the
layout builder functions.  ``upload.py`` remains the thin public entry point.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from nicegui import run, ui

from ..components import HelpButton
from ..concurrency import operation_guard, require_io_result, upload_lock
from ..constants import EXAMPLE_FILES
from ..helpers import (
    adjust_active_exam_index_after_remove,
    clear_multi_exam_state,
    get_excel_sheets,
    load_rdsr,
    load_tabular,
    rebuild_rdsr_df,
    restore_globals_from_exam_meta,
)
from ..state import reset_results, state
from ..upload_temp_files import (
    clear_all_temp_uploads,
    create_temp_upload,
    remove_temp_upload,
)
from ..ui_copy import copy_text
from ..widgets.event_table import build as build_event_table
from ..widgets.import_preview import build as build_import_preview

if TYPE_CHECKING:
    from ..page_context import PageContext

MAX_UPLOAD_BYTES = 64 * 1024 * 1024

_TABULAR_SUFFIXES = frozenset({".csv", ".tsv", ".xlsx", ".xlsm"})
_LOAD_FAILURE_STATUS = "Could not load — see message"
_NO_FILE_LOADED_STATUS = "No file loaded"

_FORMAT_BADGE_COLORS = {
    "dicom": "purple",
    "dcm": "purple",
    "csv": "teal",
    "tsv": "teal",
    "xlsx": "green",
    "xlsm": "green",
}


def upload_exceeds_limit(num_bytes: int) -> bool:
    return num_bytes > MAX_UPLOAD_BYTES


class UploadTabController:
    """Tab-local state and async callbacks for the Upload tab."""

    def __init__(self, ctx: PageContext) -> None:
        self.ctx = ctx
        self.refs: UploadViewRefs = UploadViewRefs()

    async def handle_upload(self, e: Any) -> None:
        async with upload_lock:
            await self._do_upload(e)

    async def _do_upload(self, e: Any) -> None:
        with operation_guard("uploading another file") as proceed:
            if not proceed:
                return
            file_name = e.file.name
            suffix = Path(file_name).suffix.lower() or ".dcm"
            data = await e.file.read()
            from mypyskindose.debug import dprint

            dprint("GUI", f"Uploading {suffix} file ({len(data)} bytes)")
            if upload_exceeds_limit(len(data)):
                self.refs.upload_status.set_text("Upload rejected — file too large")
                ui.notify(
                    f"File too large ({len(data) / 1024 / 1024:.1f} MB); "
                    f"limit is {MAX_UPLOAD_BYTES // 1024 // 1024} MB.",
                    type="negative",
                    timeout=8000,
                )
                self.refs.uploader["el"].reset()
                return
            tmp_path = create_temp_upload(data, suffix=suffix)
            state.input_sheet_name = 0
            state.available_sheets = []
            self.refs.import_preview.sheet_row.set_visibility(False)
            self.refs.upload_status.set_text("PARSING...")
            if suffix in _TABULAR_SUFFIXES:
                state.input_source_type = suffix.lstrip(".")
                ok, msg = require_io_result(await run.io_bound(load_tabular, tmp_path, state))
            else:
                state.input_source_type = "dicom"
                ok, msg = require_io_result(await run.io_bound(load_rdsr, tmp_path, state))
            if ok:
                await self._on_load_success(file_name, suffix, tmp_path, msg)
            else:
                self.refs.upload_status.set_text(_LOAD_FAILURE_STATUS)
                ui.notify(msg, type="negative", timeout=10000, multi_line=True)
            self.refs.uploader["el"].reset()

    async def _on_load_success(self, file_name: str, suffix: str, tmp_path: Path, msg: str) -> None:
        state.file_name = file_name
        self.ctx.file_label.set_text(file_name.upper())
        self.ctx.events_label.set_text(
            f"{len(state.rdsr_df) if state.rdsr_df is not None else 0} EVENTS"
        )
        self.refs.upload_status.set_text(f"OK: {msg}")
        n_exams = len(state.loaded_exams)
        n_events = len(state.rdsr_df) if state.rdsr_df is not None else 0
        self.ctx.file_label.set_text(
            file_name.upper() if n_exams == 1 else f"{n_exams} FILES"
        )
        self.ctx.events_label.set_text(f"{n_events} EVENTS")
        if state.is_multi_exam:
            ui.notify(
                f"{len(state.loaded_exams)} exams loaded — each gets its own "
                "dose map; skin doses are summed across all exams on the "
                "phantom (aggregate PSD = peak of the summed map).",
                color="blue",
                multi_line=True,
            )
        reset_results()
        self.refs.event_table.refresh()
        self.refresh_exams_table()
        if state.input_source_type != "dicom":
            self.refs.import_preview.refresh()
            self.refs.import_preview.set_transform_defaults()
        if suffix in (".xlsx", ".xlsm"):
            sheets = require_io_result(await run.io_bound(get_excel_sheets, tmp_path))
            if len(sheets) > 1:
                state.available_sheets = sheets
                self.refs.import_preview.sheet_select.set_options(
                    {s: s for s in sheets}, value=sheets[0]
                )
                self.refs.import_preview.sheet_row.set_visibility(True)

    async def load_example(self) -> None:
        name = self.refs.example_select.value
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
            self.refs.upload_status.set_text("PARSING...")
            ok, msg = require_io_result(await run.io_bound(load_rdsr, path, state))
            if ok:
                state.file_name = name
                self.ctx.file_label.set_text(name.upper())
                self.ctx.events_label.set_text(
                    f"{len(state.rdsr_df) if state.rdsr_df is not None else 0} EVENTS"
                )
                self.refs.upload_status.set_text(f"OK: {msg}")
                ui.notify(msg, color="positive")
                reset_results()
                self.refs.event_table.refresh()
                self.refresh_exams_table()
                self.ctx.refresh_per_exam()
            else:
                self.refs.upload_status.set_text(_LOAD_FAILURE_STATUS)
                ui.notify(msg, type="negative", timeout=10000, multi_line=True)

    async def reparse_schema(self) -> None:
        if state.file_path is None or state.input_source_type in ("", "dicom"):
            return
        with operation_guard("changing the input schema") as proceed:
            if not proceed:
                return
            state.input_schema = self.refs.schema_select.value or "auto"
            self.refs.upload_status.set_text("RE-PARSING...")
            ok, msg = require_io_result(
                await run.io_bound(load_tabular, state.file_path, state, True)
            )
            if ok:
                self.refs.upload_status.set_text(f"OK: {msg}")
                ui.notify(msg, color="positive")
                reset_results()
                self.refs.event_table.refresh()
                self.refresh_exams_table()
                self.refs.import_preview.refresh()
                self.refs.import_preview.set_transform_defaults()
            else:
                self.refs.upload_status.set_text(_LOAD_FAILURE_STATUS)
                ui.notify(msg, type="negative", timeout=10000, multi_line=True)

    def clear_all_exams(self) -> None:
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
        state.d_lon = 0.0
        state.d_ver = 0.0
        state.d_lat = 0.0
        reset_results()
        self.refs.import_preview.sheet_row.set_visibility(False)
        self.ctx.file_label.set_text(_NO_FILE_LOADED_STATUS)
        self.ctx.events_label.set_text("0 events")
        self.ctx.psd_label.set_text("PSD: 0.00 mGy")
        self.refs.upload_status.set_text(_NO_FILE_LOADED_STATUS)
        self.refs.example_select.set_value(None)
        self._build_uploader()
        self.refs.event_table.refresh()
        self.refresh_exams_table()
        self.refs.import_preview.refresh()
        self.ctx.refresh_per_exam()

    def remove_exam(self, index: int) -> None:
        if not (0 <= index < len(state.loaded_exams)):
            return
        meta = state.loaded_exam_meta[index] if index < len(state.loaded_exam_meta) else {}
        file_path = meta.get("file_path")
        state.loaded_exams.pop(index)
        if index < len(state.loaded_exam_meta):
            state.loaded_exam_meta.pop(index)
        adjust_active_exam_index_after_remove(state, index)
        if file_path is not None and all(
            m.get("file_path") != file_path for m in state.loaded_exam_meta
        ):
            remove_temp_upload(file_path)
        rebuild_rdsr_df(state)
        n = len(state.loaded_exams)
        n_events = len(state.rdsr_df) if state.rdsr_df is not None else 0
        if n == 0:
            state.file_name = ""
            state.file_path = None
            self.ctx.file_label.set_text(_NO_FILE_LOADED_STATUS)
            self.ctx.events_label.set_text("0 events")
        elif n == 1:
            meta0 = state.loaded_exam_meta[0]
            state.file_name = meta0.get("file_name", "")
            state.file_path = meta0.get("file_path")
            restore_globals_from_exam_meta(state, meta0)
            self.ctx.file_label.set_text(state.file_name.upper())
            self.ctx.events_label.set_text(f"{n_events} EVENTS")
        else:
            state.file_name = f"{n} files"
            self.ctx.file_label.set_text(f"{n} FILES")
            self.ctx.events_label.set_text(f"{n_events} EVENTS")
        reset_results()
        self.ctx.psd_label.set_text("PSD: 0.00 mGy")
        self.refs.event_table.refresh()
        self.refresh_exams_table()
        self.refs.import_preview.refresh()

    def select_exam_for_geometry(self, index: int) -> None:
        if not (0 <= index < len(state.loaded_exams)):
            return
        state.active_exam_index = index
        self.ctx.refresh_per_exam()
        self.ctx.tabs.set_value("geometry")

    def refresh_exams_table(self) -> None:
        self.refs.exams_list.clear()
        has_exams = bool(state.loaded_exams)
        self.refs.exams_section_label.set_visibility(has_exams)
        self.refs.exams_list.set_visibility(has_exams)
        if has_exams:
            with self.refs.exams_list:
                for idx, exam in enumerate(state.loaded_exams):
                    self._build_exam_card(idx, exam)
                if state.is_multi_exam:
                    ui.label(
                        "Edit per-exam offsets and coordinate corrections in "
                        "Settings → Per-exam corrections."
                    ).classes("text-caption text-grey-6 italic q-mt-xs")
        self.ctx.refresh_per_exam()

    def _build_exam_card(self, idx: int, exam: Any) -> None:
        meta = (
            state.loaded_exam_meta[idx]
            if idx < len(state.loaded_exam_meta)
            else {}
        )
        src = (meta.get("source_type") or "?").lower()
        schema = meta.get("schema") or getattr(
            getattr(exam, "provenance", None), "schema_name", "—"
        )
        study_id = str(exam.study_id) if getattr(exam, "study_id", None) else "—"
        warnings = meta.get("warnings") or []
        with ui.card().classes(
            "modern-card w-full bg-blue-950/20 q-pa-sm cursor-pointer"
        ).on("click", lambda _e, i=idx: self.select_exam_for_geometry(i)):
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
                    ui.badge("ORIGIN", color="amber").classes("text-xs").tooltip(
                        copy_text("upload.exam.table_origin.tooltip")
                    )
                ui.space()
                ui.button(
                    icon="close",
                    on_click=lambda _e, i=idx: self.remove_exam(i),
                ).props("flat round dense size=sm color=grey-5 @click.stop").classes(
                    "icon-outlined"
                ).tooltip(copy_text("upload.exam.remove.tooltip"))

    def _build_uploader(self) -> None:
        self.refs.uploader_container.clear()
        with self.refs.uploader_container:
            self.refs.uploader["el"] = ui.upload(
                on_upload=self.handle_upload,
                label="DRAG AND DROP OR CLICK TO SELECT",
                max_file_size=MAX_UPLOAD_BYTES,
                multiple=True,
            ).props(
                'accept=".dcm,.csv,.tsv,.xlsx,.xlsm" flat bordered color=deep-purple auto-upload'
            ).classes("w-full bg-black/40 uploader-no-list")


@dataclass
class UploadViewRefs:
    """UI element references for the Upload tab."""

    upload_status: ui.label = None  # type: ignore[assignment]
    uploader: dict[str, ui.upload] = field(default_factory=dict)
    uploader_container: ui.column = None  # type: ignore[assignment]
    example_select: ui.select = None  # type: ignore[assignment]
    schema_select: ui.select = None  # type: ignore[assignment]
    exams_section_label: ui.label = None  # type: ignore[assignment]
    exams_list: ui.column = None  # type: ignore[assignment]
    import_preview: Any = None
    event_table: Any = None


def _build_header() -> None:
    with ui.row().classes("w-full items-center justify-between"):
        ui.label("Load File").classes("text-2xl font-bold tracking-tight")
        HelpButton(
            title="Upload and import help",
            content_path="upload_workflow.md",
            help_id="upload",
        )


def _build_normalization_warning() -> None:
    with ui.card().classes(
        "modern-card w-full border-red-900 bg-red-950/20"
    ).bind_visibility_from(
        state, "normalization_method", backward=lambda v: v == "Fallback"
    ):
        with ui.row().classes("items-center gap-3"):
            ui.icon("warning", color="negative").classes("text-xl icon-outlined")
            ui.label().bind_text_from(
                state,
                "normalization_warnings",
                backward=lambda ws: f"NORMALIZATION ALERT: {ws[0]}" if ws else "",
            ).classes("mono-text text-xs font-bold text-red-400")


def _build_upload_card(ctrl: UploadTabController) -> None:
    with ui.card().classes("modern-card w-full"):
        ui.label("Load file").classes("text-subtitle2 q-mb-xs")
        ui.label(
            "DICOM RDSR (.dcm) or tabular event table (.csv, .tsv, .xlsx, .xlsm)"
        ).classes("text-sm text-grey-4 q-mb-sm")
        ui.label(copy_text("upload.privacy_notice")).classes(
            "text-xs text-orange-5 q-mb-sm"
        )
        ctrl.refs.uploader_container = ui.column().classes("w-full gap-0")
        ctrl._build_uploader()
        with ui.row().classes("w-full justify-end q-mt-xs"):
            ui.button(
                "Clear all",
                icon="restart_alt",
                on_click=lambda: ctrl.clear_all_exams(),
            ).props("flat dense size=sm color=grey-5").classes("icon-outlined").tooltip(
                "Clear all loaded exams and reset the upload area"
            )
        ctrl.refs.exams_section_label = ui.label("Loaded files").classes(
            "text-subtitle2 q-mt-md q-mb-xs"
        )
        ctrl.refs.exams_section_label.set_visibility(False)
        ctrl.refs.exams_list = ui.column().classes("w-full gap-2")
        ctrl.refs.exams_list.set_visibility(False)
        with ui.row().classes("w-full items-center gap-3 q-mt-sm"):
            ui.label("…or try a bundled example:").classes("text-caption text-grey-5")
            ctrl.refs.example_select = ui.select(
                options=list(EXAMPLE_FILES.keys()),
                label="Bundled example",
                value=None,
            ).classes("grow").mark("example-select")
        ctrl.refs.upload_status = ui.label(_NO_FILE_LOADED_STATUS).classes(
            "text-caption text-grey-5 q-mt-xs"
        )
        ctrl.refs.example_select.on_value_change(lambda: ctrl.load_example())
        ui.separator().classes("q-my-sm bg-zinc-800")
        with ui.row().classes("w-full items-end gap-4"):
            ctrl.refs.schema_select = ui.select(
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
        ctrl.refs.schema_select.on_value_change(lambda: ctrl.reparse_schema())


def build_upload_panel(ctx: PageContext) -> None:
    """Construct and wire the complete Upload tab."""
    ctrl = UploadTabController(ctx)

    with ui.tab_panel("upload"):
        with ui.column().classes("max-w-4xl mx-auto w-full gap-6"):
            _build_header()
            _build_normalization_warning()
            _build_upload_card(ctrl)
            ctrl.refs.import_preview = build_import_preview(ctx, ctrl.refs.upload_status)
            ctrl.refs.event_table = build_event_table()

    ctx.refresh_event_table = ctrl.refs.event_table.refresh
    ctx.refresh_import_preview = ctrl.refs.import_preview.refresh
    ctx.refresh_exams_table = ctrl.refresh_exams_table


def build(ctx: PageContext) -> None:
    """Public entry point — delegates to :func:`build_upload_panel`."""
    build_upload_panel(ctx)
