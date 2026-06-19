"""MyPySkinDose — NiceGUI app (Phase 1).

Run with:
    python src/mypyskindose/main.py --mode gui
or directly:
    .venv/Scripts/python -m mypyskindose --mode gui
    .venv/Scripts/python -m mypyskindose --mode gui --native
"""

from __future__ import annotations

import asyncio
import atexit
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

# Fix for Windows SSL context loading error during shutdown
# Prevents aiohttp from loading Windows certificate store which causes issues on Python 3.13
os.environ['SSL_CERT_FILE'] = ''

# Fix for colorama atexit error on Windows during shutdown
# Prevents colorama from trying to reset console colors when handle is already closed
os.environ['COLORAMA_DISABLE'] = '1'

from nicegui import Client, app, run, ui

from .helpers import (
    apply_exam_transforms,
    clear_multi_exam_state,
    exam_supports_table_origin,
    exam_supports_transforms,
    get_excel_sheets,
    load_rdsr,
    load_tabular,
    run_calculation,
)
from .styles import MODERN_CSS
from .page_context import PageContext
from .tabs import data as data_tab
from .tabs import export as export_tab
from .tabs import geometry as geometry_tab
from .tabs import results as results_tab
from .tabs import settings as settings_tab
from .state import reset_results, state
from mypyskindose.debug import configure_logging, dprint

GUI_VERSION = "1.1.0"

# ── uploaded temp-file lifecycle ──────────────────────────────────────────
# Uploads are written to NamedTemporaryFile(delete=False) so the parser (and the
# XLSX sheet picker, which re-reads the path on every sheet change) can read them.
# Without cleanup these accumulate on disk for the life of the process. We keep
# only the current upload alive: each new upload deletes the previous one, and an
# atexit sweep removes whatever remains at shutdown. Bundled example files are
# never registered here, so they are never deleted.
_uploaded_temp_files: list[Path] = []

# Serialises concurrent upload handlers. ui.upload(multiple=True) fires on_upload
# once per selected file, and NiceGUI dispatches those handlers concurrently (each
# awaits run.io_bound and yields the event loop). Without serialisation the second
# file hits the busy-guard and is rejected with a "still uploading" notice; the
# lock makes them queue and load one after another.
_upload_lock = asyncio.Lock()

# Reject uploads larger than this. RDSR DICOM files and tabular event tables are
# small (KB to single-digit MB); this cap bounds memory and /tmp disk use from a
# hostile or accidental large upload, since handle_upload reads the whole file
# into memory (e.file.read()) before spooling it to a temp file. Enforced both on
# the uploader element (max_file_size, client-side) and server-side after the
# read, in case a client bypasses the browser check.
MAX_UPLOAD_BYTES = 64 * 1024 * 1024  # 64 MiB


def _upload_exceeds_limit(num_bytes: int) -> bool:
    """True if an upload of this size must be rejected (see MAX_UPLOAD_BYTES)."""
    return num_bytes > MAX_UPLOAD_BYTES


def _register_temp_upload(path: Path) -> None:
    """Track a freshly written upload temp file (accumulating — does not delete others)."""
    _uploaded_temp_files.append(path)


def _remove_temp_upload(path: Path) -> None:
    """Delete one specific temp file and deregister it (called when user removes an exam)."""
    try:
        path.unlink(missing_ok=True)
    except OSError as exc:
        dprint("GUI", f"Could not delete temp upload {path}: {exc}")
    try:
        _uploaded_temp_files.remove(path)
    except ValueError:
        pass


def _clear_all_temp_uploads() -> None:
    """Delete and deregister all accumulated upload temp files."""
    while _uploaded_temp_files:
        old = _uploaded_temp_files.pop()
        try:
            old.unlink(missing_ok=True)
        except OSError:
            pass


@atexit.register
def _cleanup_temp_uploads() -> None:
    """Remove any remaining upload temp files at process exit."""
    for path in _uploaded_temp_files:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
    _uploaded_temp_files.clear()


# ── concurrency guard ─────────────────────────────────────────────────────
# NiceGUI runs async handlers on a single event loop, but each handler awaits
# run.io_bound(), yielding control while blocking work runs on a worker thread.
# Two handlers can therefore be in flight at once and interleave their writes to
# the shared `state` singleton. This guard makes the second operation bail out
# with a notice instead. The check-and-set has no await between the read and the
# write, so it is race-free under asyncio's cooperative scheduling.
@contextmanager
def _operation_guard(label: str) -> Iterator[bool]:
    """Yield True if the operation may proceed, False if one is already running."""
    if state.busy:
        ui.notify(
            f"Busy — please wait for the current operation to finish before {label}.",
            type="warning",
        )
        yield False
        return
    state.busy = True
    try:
        yield True
    finally:
        state.busy = False


# ── constants ──────────────────────────────────────────────────────────────
# Shared UI constants live in constants.py so per-tab modules can import them
# without a circular dependency on app.py. Only the upload tab (still inline)
# uses one here; the rest are consumed by the extracted tab modules.
from .constants import EXAMPLE_FILES  # noqa: E402 — grouped with the other imports

# MODERN_CSS lives in styles.py. After CSS changes, regenerate dev-docs/UI_values.md:
#   python scripts/generate_ui_values.py


# ── page ───────────────────────────────────────────────────────────────────
@ui.page("/")
def index():
    dprint("GUI", f"Rendering index page (v{GUI_VERSION})")

    # Framework colors: Brighter Blue (#2563EB) and Brighter Green (#064E3B)
    ui.colors(primary='#2563EB', secondary='#2563EB', accent='#831843', positive='#064E3B')
    ui.add_head_html(f"<style>{MODERN_CSS}</style>")
    # Add Material Symbols Outlined font for thin-stroke icons
    ui.add_head_html('<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@24,300,0,0" />')

    ui.dark_mode(True)

    # ── header ────────────────────────────────────────────────────────────
    with ui.header().classes("items-center justify-between px-6 py-2 modern-header"):
        with ui.row().classes("items-center gap-3"):
            ui.label("MyPySkinDose").classes("text-h6 font-bold text-white")
            ui.label(f"v{GUI_VERSION}").style("color: #F8FAFC; font-weight: bold; font-size: 10px; opacity: 0.3; margin-top: 4px;")
        
        with ui.row().classes("items-center gap-6"):
            ui.button(icon="menu", on_click=lambda: left_drawer.toggle()).props("flat round color=white").classes("icon-outlined")

    # ── left drawer ───────────────────────────────────────────────────────
    with ui.left_drawer(fixed=True).classes("q-pa-md") as left_drawer:
        ui.label("Status").classes("text-caption text-grey-6 q-mb-xs")

        with ui.column().classes("gap-0 q-mb-sm"):
            file_label = ui.label("No file loaded").classes("text-caption")
            events_label = ui.label("0 events").classes("text-caption")
            psd_label = ui.label("PSD: 0.00 mGy").classes("text-h6 text-pink-5 font-bold q-mt-xs")

        ui.separator().classes("q-my-sm bg-zinc-800")
        ui.label("Navigation").classes("text-caption text-grey-6 q-mb-0")

        def go(name: str):
            tabs.set_value(name)
            state.active_tab = name
            # Update navigation button classes
            _update_nav_classes()

        def _update_nav_classes():
            """Update navigation button active states."""
            for btn, target in nav_buttons:
                if state.active_tab == target:
                    btn.classes(add="active", remove="text-grey-4")
                else:
                    btn.classes(remove="active", add="text-grey-4")

        nav_buttons = []

        def nav_btn(label, target):
            btn = ui.button(label, on_click=lambda: go(target)).props("flat align=left dense no-caps").classes("nav-item full-width text-left py-2 text-grey-4")
            nav_buttons.append((btn, target))
            return btn

        nav_btn("1 · Upload", "upload")
        nav_btn("2 · Data Table", "data")
        nav_btn("3 · Settings", "settings")
        nav_btn("4 · Geometry", "geometry")
        nav_btn("5 · Calculate", "calculate")
        nav_btn("6 · Results", "results")
        nav_btn("7 · Export", "export")

        ui.separator().classes("q-my-md bg-zinc-800")
        run_btn_drawer = ui.button("Run Calculation", icon="play_arrow").classes("full-width modern-btn icon-outlined")

    # ── main tabs ─────────────────────────────────────────────────────────
    with ui.tabs().classes("w-full").on("update:model-value", lambda e: setattr(state, "active_tab", e.args)) as tabs:
        ui.tab("upload", label="1 · Upload")
        ui.tab("data", label="2 · Data Table")
        ui.tab("settings", label="3 · Settings")
        ui.tab("geometry", label="4 · Geometry")
        ui.tab("calculate", label="5 · Calculate")
        ui.tab("results", label="6 · Results")
        ui.tab("export", label="7 · Export")

    # All cross-cutting chrome now exists; build the shared context. The two
    # refresher callables are wired after the upload tab defines them (below).
    ctx = PageContext(
        tabs=tabs,
        file_label=file_label,
        events_label=events_label,
        psd_label=psd_label,
        run_btn_drawer=run_btn_drawer,
    )

    with ui.tab_panels(tabs, value="upload").classes("w-full bg-transparent"):

        # ══════════════════════════════════════════════════════════════════
        # TAB 1 — UPLOAD
        # ══════════════════════════════════════════════════════════════════
        with ui.tab_panel("upload"):
            with ui.column().classes("max-w-4xl mx-auto w-full gap-6"):
                ui.label("Load File").classes("text-2xl font-bold tracking-tight")

                # Normalization warning banner
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

                    _TABULAR_SUFFIXES = frozenset({".csv", ".tsv", ".xlsx", ".xlsm"})

                    async def handle_upload(e):
                        # ui.upload(multiple=True) fires this once per selected file,
                        # and NiceGUI dispatches the handlers concurrently (each awaits
                        # run.io_bound and yields the loop). Serialise them through a
                        # lock so additional files queue and load one-by-one instead of
                        # tripping the busy-guard with a "still uploading" notice.
                        async with _upload_lock:
                            await _do_upload(e)

                    async def _do_upload(e):
                        with _operation_guard("uploading another file") as proceed:
                            if not proceed:
                                return
                            # NiceGUI 3.x wraps the upload in e.file (name + async read()).
                            file_name = e.file.name
                            suffix = Path(file_name).suffix.lower() or ".dcm"
                            data = await e.file.read()
                            # Log only type + size, never the name — upload filenames
                            # can carry PHI (patient name/MRN/accession).
                            dprint("GUI", f"Uploading {suffix} file ({len(data)} bytes)")
                            # Server-side size guard — the uploader's max_file_size
                            # is client-side and can be bypassed by a direct POST.
                            if _upload_exceeds_limit(len(data)):
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
                            # Track for cleanup; kept alive so the XLSX sheet picker
                            # can re-read the path. Now accumulating — does not delete
                            # the previous file (see _register_temp_upload).
                            _register_temp_upload(tmp_path)

                            # Reset sheet state for this specific upload only.
                            # Transform flags are NOT reset globally — they are
                            # per-exam (stored in loaded_exam_meta by the loaders).
                            state.input_sheet_name = 0
                            state.available_sheets = []
                            sheet_row.set_visibility(False)

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
                                # Update top-bar labels to reflect N-file count.
                                n_exams = len(state.loaded_exams)
                                n_events = len(state.rdsr_df) if state.rdsr_df is not None else 0
                                ctx.file_label.set_text(
                                    file_name.upper() if n_exams == 1
                                    else f"{n_exams} FILES"
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
                                _refresh_event_table()
                                _refresh_exams_table()
                                if state.input_source_type != "dicom":
                                    _refresh_import_preview()
                                    _set_transform_defaults()
                                # Populate sheet picker for multi-sheet Excel files
                                if suffix in (".xlsx", ".xlsm"):
                                    sheets = await run.io_bound(get_excel_sheets, tmp_path)
                                    if len(sheets) > 1:
                                        state.available_sheets = sheets
                                        sheet_select.set_options(
                                            {s: s for s in sheets}, value=sheets[0]
                                        )
                                        sheet_row.set_visibility(True)
                            else:
                                # msg is already a concise, user-facing string from
                                # the loader (not a traceback); show it in full.
                                upload_status.set_text("Could not load — see message")
                                ui.notify(msg, type="negative", timeout=10000, multi_line=True)

                            # Clear quasar's (hidden) upload queue so File objects don't
                            # accumulate across uploads. The visible loaded file is shown
                            # by the controlled card below; quasar's own file list is
                            # hidden via the .uploader-no-list CSS class, so this reset is
                            # not visible and never flashes a per-file card.
                            _uploader["el"].reset()

                    # The uploader lives in a container so it can be fully rebuilt — not
                    # just reset(). Dragging a file out of the native file-open dialog can
                    # wedge quasar in a phantom upload (0.0B/0.00%, + disabled) that
                    # reset() does NOT clear; recreating the element yields a fresh,
                    # working QUploader. _uploader holds the current instance so the
                    # upload handler and the rebuild can reach it.
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

                    # Always-visible recovery: resets the upload area (recovers a wedged
                    # uploader — e.g. a 0-byte phantom from dragging out of the native
                    # file dialog) and flushes all loaded exams.
                    with ui.row().classes("w-full justify-end q-mt-xs"):
                        ui.button(
                            "Clear all", icon="restart_alt", on_click=lambda: clear_all_exams()
                        ).props("flat dense size=sm color=grey-5").classes("icon-outlined").tooltip(
                            "Clear all loaded exams and reset the upload area"
                        )

                    # Loaded files — shown directly under the drop zone so the user
                    # can see (and remove) every accumulated exam. Visible whenever at
                    # least one exam is loaded; rebuilt by _refresh_exams_table().
                    exams_section_label = ui.label("Loaded files").classes("text-subtitle2 q-mt-md q-mb-xs")
                    exams_section_label.set_visibility(False)
                    exams_list = ui.column().classes("w-full gap-2")
                    exams_list.set_visibility(False)

                    def clear_all_exams() -> None:
                        """Clear all loaded exams, temp files, and input state."""
                        from .helpers import clear_multi_exam_state
                        _clear_all_temp_uploads()
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
                        sheet_row.set_visibility(False)
                        ctx.file_label.set_text("No file loaded")
                        ctx.events_label.set_text("0 events")
                        ctx.psd_label.set_text("PSD: 0.00 mGy")
                        upload_status.set_text("No file loaded")
                        example_select.set_value(None)
                        # Rebuild the uploader (not just reset) so a wedged/phantom
                        # upload state is fully cleared and the + button works again.
                        _build_uploader()
                        _refresh_event_table()
                        _refresh_exams_table()
                        _refresh_import_preview()

                    # Bundled examples live in the same card and auto-load on selection
                    # (no separate LOAD button) so both input paths behave identically.
                    # No preselected value, so nothing loads on page render.
                    with ui.row().classes("w-full items-center gap-3 q-mt-sm"):
                        ui.label("…or try a bundled example:").classes("text-caption text-grey-5")
                        example_select = ui.select(
                            options=list(EXAMPLE_FILES.keys()),
                            label="Bundled example",
                            value=None,
                        ).classes("grow").mark("example-select")

                    # Shared status line for both upload and example loading.
                    upload_status = ui.label("No file loaded").classes("text-caption text-grey-5 q-mt-xs")

                    async def load_example():
                        name = example_select.value
                        if not name:
                            return
                        with _operation_guard("loading an example") as proceed:
                            if not proceed:
                                return
                            path = EXAMPLE_FILES[name]
                            # Examples replace whatever is loaded (clear-then-load)
                            # rather than accumulating onto previously uploaded files.
                            _clear_all_temp_uploads()
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
                                _refresh_event_table()
                                _refresh_exams_table()
                            else:
                                upload_status.set_text("Could not load — see message")
                                ui.notify(msg, type="negative", timeout=10000, multi_line=True)

                    # Wire to the value-change (not the raw Vue event) so it fires on
                    # any selection — and is reliably simulable in the GUI flow tests.
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
                        # Re-parse the currently loaded tabular file under the newly
                        # chosen schema, so the user doesn't have to re-upload. The
                        # schema selector does not apply to DICOM RDSR loads.
                        if state.file_path is None or state.input_source_type in ("", "dicom"):
                            return
                        with _operation_guard("changing the input schema") as proceed:
                            if not proceed:
                                return
                            # Use the just-picked value directly; don't depend on the
                            # bind_value propagation order relative to this handler.
                            state.input_schema = schema_select.value or "auto"
                            upload_status.set_text("RE-PARSING...")
                            # Re-parse in place: replace the existing entry for this
                            # file rather than appending a duplicate exam.
                            ok, msg = await run.io_bound(
                                load_tabular, state.file_path, state, True
                            )
                            if ok:
                                upload_status.set_text(f"OK: {msg}")
                                ui.notify(msg, color="positive")
                                reset_results()
                                _refresh_event_table()
                                _refresh_exams_table()
                                _refresh_import_preview()
                                _set_transform_defaults()
                            else:
                                upload_status.set_text("Could not load — see message")
                                ui.notify(msg, type="negative", timeout=10000, multi_line=True)

                    schema_select.on_value_change(lambda: _on_schema_change())

                # Import preview card — visible only for tabular files
                with ui.card().classes("modern-card w-full").bind_visibility_from(
                    state, "input_source_type", backward=lambda v: v not in ("", "dicom")
                ):
                    with ui.row().classes("items-center gap-3 q-mb-xs"):
                        ui.label("Import preview").classes("text-subtitle2")
                        import_schema_badge = ui.badge("—", color="blue").classes("text-xs uppercase")

                    with ui.row().classes("w-full gap-6 q-mb-xs"):
                        import_encoding_label = ui.label("Encoding: —").classes("text-caption text-grey-5")
                        import_delimiter_label = ui.label("Delimiter: —").classes("text-caption text-grey-5")
                        import_header_label = ui.label("Header row: —").classes("text-caption text-grey-5")
                        import_sheet_label = ui.label("").classes("text-caption text-grey-5")

                    # Sheet picker — only shown for multi-sheet Excel files
                    sheet_row = ui.row().classes("w-full items-center gap-3 q-mb-xs")
                    with sheet_row:
                        ui.label("Sheet:").classes("text-caption text-grey-4")
                        sheet_select = ui.select(options={}, label="").classes("grow")

                        async def _on_sheet_change():
                            if state.file_path is None:
                                return
                            with _operation_guard("switching sheets") as proceed:
                                if not proceed:
                                    return
                                state.input_sheet_name = sheet_select.value or 0
                                # Re-parse in place: switching sheets replaces the
                                # existing entry for this file, not append a duplicate.
                                ok, msg = await run.io_bound(
                                    load_tabular, state.file_path, state, True
                                )
                                if ok:
                                    upload_status.set_text(f"SUCCESS: {msg.upper()}")
                                    reset_results()
                                    _refresh_event_table()
                                    _refresh_exams_table()
                                    _refresh_import_preview()
                                else:
                                    ui.notify(f"Sheet parse error: {msg[:200]}", type="negative", timeout=6000)

                        sheet_select.on("update:model-value", _on_sheet_change)
                    sheet_row.set_visibility(False)

                    # Coordinate correction options — visible for non-normalized
                    # schemas in single-exam mode only. In multi-exam mode each exam
                    # carries its own toggles in the loaded-exam list, so this global
                    # card is hidden (visibility managed in _refresh_import_preview).
                    coord_card = ui.card().classes("modern-card w-full bg-blue-950/20 q-pa-sm q-mb-xs")
                    coord_card.set_visibility(False)
                    with coord_card:
                        with ui.row().classes("items-center gap-3 q-mb-xs"):
                            ui.label("COORDINATE CORRECTIONS").classes("text-caption text-grey-4 font-bold tracking-widest")
                            coord_auto_label = ui.label("").classes("text-caption text-blue-400 italic")
                        ui.label(
                            "Applied after normalization. Defaults are auto-set from the detected manufacturer."
                        ).classes("text-caption text-grey-6 q-mb-sm")

                        def _coord_row(label: str, hint: str) -> None:
                            with ui.row().classes("items-center gap-3 q-mb-xs flex-wrap"):
                                ui.label(hint).classes("text-caption text-grey-5 w-48")

                        # Row 1: swap lat/lon
                        with ui.row().classes("items-center gap-3 q-mb-xs"):
                            ui.switch("Swap lateral ↔ longitudinal").bind_value(state, "swap_lat_lon").on(
                                "update:model-value", lambda: _on_swap_toggle()
                            ).tooltip(
                                "Swaps Tx ↔ Tz in the normalized output.\n"
                                "Auto-enabled for GE Radimetrics exports.\n"
                                "May also be needed for Philips DoseTrack — verify against known data."
                            )
                            ui.label("Tx ↔ Tz").classes("text-caption text-grey-5 font-mono")

                        # Row 2: flip primary angle
                        with ui.row().classes("items-center gap-3 q-mb-xs"):
                            ui.switch("Flip primary angle (Ap1)").bind_value(state, "flip_ap1").on(
                                "update:model-value", lambda: _on_flip_ap1_toggle()
                            ).tooltip(
                                "Negates Ap1 after normalization (e.g. RAO 30° → LAO 30°).\n"
                                "Use when the gantry primary rotation direction is opposite to convention."
                            )
                            ui.label("Ap1 × −1").classes("text-caption text-grey-5 font-mono")

                        # Row 3: flip secondary angle
                        with ui.row().classes("items-center gap-3 q-mb-xs"):
                            ui.switch("Flip secondary angle (Ap2)").bind_value(state, "flip_ap2").on(
                                "update:model-value", lambda: _on_flip_ap2_toggle()
                            ).tooltip(
                                "Negates Ap2 after normalization (e.g. CRA 20° → CAU 20°).\n"
                                "Use when the gantry secondary rotation direction is opposite to convention."
                            )
                            ui.label("Ap2 × −1").classes("text-caption text-grey-5 font-mono")

                        ui.separator().classes("q-my-xs")
                        ui.label(
                            "Vendor-specific normalization (rotation directions, iso-centre offsets) "
                            "is applied automatically from manufacturer settings. "
                            "Per-transform overrides are planned."
                        ).classes("text-caption text-grey-6 italic")

                    # Warnings
                    import_warnings_label = ui.label("").classes("text-caption text-orange-400 q-mb-xs")

                    # Column map table
                    ui.label("Column mapping (source → normalized)").classes("text-caption text-grey-6 q-mb-xs")
                    col_map_table = ui.table(
                        columns=[
                            {"name": "source", "label": "Source column", "field": "source", "align": "left"},
                            {"name": "mapped", "label": "Normalized variable", "field": "mapped", "align": "left"},
                        ],
                        rows=[],
                        row_key="source",
                    ).classes("w-full mono-text")
                    col_map_table.props("dense flat")

                    # Event sample
                    ui.label("First 5 events (normalized)").classes("text-caption text-grey-6 q-mt-sm q-mb-xs")
                    event_sample_table = ui.table(columns=[], rows=[], row_key="__idx").classes("w-full mono-text")
                    event_sample_table.props("dense flat virtual-scroll")

                # event summary table
                ui.label("Irradiation events").classes("text-subtitle2 q-mt-md q-mb-xs")
                event_table = ui.table(
                    columns=[
                        {"name": "idx", "label": "#", "field": "idx", "align": "right"},
                        {"name": "kVp", "label": "kVp", "field": "kVp", "align": "right"},
                        {"name": "Ap1", "label": "Ap1 (°)", "field": "Ap1", "align": "right"},
                        {"name": "Ap2", "label": "Ap2 (°)", "field": "Ap2", "align": "right"},
                        {"name": "K_IRP", "label": "K_IRP (mGy)", "field": "K_IRP", "align": "right"},
                    ],
                    rows=[],
                    row_key="idx",
                ).classes("w-full modern-card mono-text")

            def _refresh_event_table():
                if state.rdsr_df is None:
                    event_table.rows = []
                    event_table.update()
                    return
                df = state.rdsr_df
                rows = []
                for idx, (_, row) in enumerate(df.iterrows()):
                    rows.append({
                        "idx": idx + 1,
                        "kVp": round(float(row.get("kVp", 0)), 1),
                        "Ap1": round(float(row.get("Ap1", 0)), 1),
                        "Ap2": round(float(row.get("Ap2", 0)), 1),
                        "K_IRP": round(float(row.get("K_IRP", 0)), 3),
                    })
                event_table.rows = rows
                event_table.update()

            _FORMAT_BADGE_COLORS = {
                "dicom": "purple", "dcm": "purple",
                "csv": "teal", "tsv": "teal",
                "xlsx": "green", "xlsm": "green",
            }

            def _apply_global_offset_to_all() -> None:
                """Copy the global patient offset into every loaded exam's per-exam
                offset, overwriting any per-exam edits. Marks results stale."""
                for meta in state.loaded_exam_meta:
                    meta["d_lon"] = state.d_lon
                    meta["d_ver"] = state.d_ver
                    meta["d_lat"] = state.d_lat
                reset_results()
                ctx.psd_label.set_text("PSD: 0.00 mGy")
                _refresh_exams_table()
                ui.notify(
                    f"Applied global offset ({state.d_lon}, {state.d_ver}, "
                    f"{state.d_lat} cm) to all {len(state.loaded_exam_meta)} exams.",
                    color="blue",
                )

            def _on_exam_offset_change() -> None:
                """A per-exam offset spinbox changed — invalidate stale results."""
                reset_results()
                ctx.psd_label.set_text("PSD: 0.00 mGy")

            def _on_exam_transform_change(index: int, key: str, value) -> None:
                """A per-exam coordinate-correction toggle changed: store the flag,
                re-derive that exam's data from its base, and invalidate results."""
                if not (0 <= index < len(state.loaded_exam_meta)):
                    return
                state.loaded_exam_meta[index][key] = bool(value)
                apply_exam_transforms(state, index)
                reset_results()
                ctx.psd_label.set_text("PSD: 0.00 mGy")
                _refresh_event_table()
                _refresh_import_preview()

            def _build_table_origin_section(index: int, meta: dict) -> None:
                """Per-exam 'Advanced: table origin' override UI (Phase 2.5).

                Spinboxes pre-fill from the active override (or the auto-detected
                origin); 'Reset to auto-detected' clears the override back to None.
                """
                detected = meta.get("table_origin_detected") or {
                    "x": 0.0, "y": 0.0, "z": 0.0
                }
                inputs: dict[str, ui.number] = {}
                guard = {"suppress": False}

                def _status_text() -> str:
                    return (
                        "Override active — using manual origin"
                        if meta.get("table_origin_override") is not None
                        else "Using auto-detected origin"
                    )

                with ui.expansion("Advanced: table origin", icon="open_with").classes(
                    "w-full"
                ).props("dense"):
                    ui.label(
                        "Override the table coordinate origin (cm) for a misdetected "
                        "scanner or a tabular export without convention metadata. "
                        "This changes the dose map."
                    ).classes("text-caption text-grey-6")
                    status_label = ui.label(_status_text()).classes(
                        "text-caption text-amber-400 italic"
                    )

                    def _on_change(key: str, value) -> None:
                        if guard["suppress"]:
                            return
                        if meta.get("table_origin_override") is None:
                            meta["table_origin_override"] = dict(detected)
                        meta["table_origin_override"][key] = float(value or 0.0)
                        apply_exam_transforms(state, index)
                        reset_results()
                        ctx.psd_label.set_text("PSD: 0.00 mGy")
                        _refresh_event_table()
                        _refresh_import_preview()
                        status_label.set_text(_status_text())

                    def _on_reset() -> None:
                        meta["table_origin_override"] = None
                        apply_exam_transforms(state, index)
                        # Revert spinboxes without re-triggering _on_change.
                        guard["suppress"] = True
                        for k, inp in inputs.items():
                            inp.set_value(detected[k])
                        guard["suppress"] = False
                        reset_results()
                        ctx.psd_label.set_text("PSD: 0.00 mGy")
                        _refresh_event_table()
                        _refresh_import_preview()
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
                        ).props("flat dense size=sm color=grey-5").classes(
                            "icon-outlined"
                        )

            def _refresh_exams_table():
                exams_list.clear()
                has_exams = bool(state.loaded_exams)
                exams_section_label.set_visibility(has_exams)
                exams_list.set_visibility(has_exams)
                if not has_exams:
                    return
                with exams_list:
                    # Per-exam patient offsets only take effect in multi-exam mode
                    # (analyze_multiple_exams); a single exam uses the global offset
                    # via analyze_data, so the controls are hidden for one file.
                    if state.is_multi_exam:
                        with ui.row().classes("w-full items-center gap-3 q-mb-xs"):
                            ui.label(
                                f"Global patient offset: {state.d_lon}, "
                                f"{state.d_ver}, {state.d_lat} cm"
                            ).classes("text-caption text-grey-6")
                            ui.space()
                            ui.button(
                                "Apply global to all",
                                icon="content_copy",
                                on_click=_apply_global_offset_to_all,
                            ).props("flat dense size=sm color=grey-5").classes(
                                "icon-outlined"
                            ).tooltip(
                                "Copy the global patient offset (Settings tab) into "
                                "every exam, overwriting per-exam edits"
                            )
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

                            # Per-exam patient offset (Phase 2.3) — bound directly to
                            # the meta dict; consumed by run_calculation in multi-exam
                            # mode. Hidden for a single exam (global offset applies).
                            if state.is_multi_exam and meta:
                                with ui.row().classes("items-center gap-2 q-mt-xs"):
                                    ui.label("Patient offset (cm):").classes(
                                        "text-caption text-grey-5"
                                    )
                                    for axis, lbl in (
                                        ("d_lon", "lon"),
                                        ("d_ver", "ver"),
                                        ("d_lat", "lat"),
                                    ):
                                        meta.setdefault(axis, 0.0)
                                        ui.number(
                                            label=lbl,
                                            value=meta[axis],
                                            min=-50,
                                            max=50,
                                            step=1.0,
                                            format="%.1f",
                                        ).props("dense outlined").classes(
                                            "w-20"
                                        ).bind_value(meta, axis).on_value_change(
                                            _on_exam_offset_change
                                        )

                            # Per-exam coordinate corrections (Phase 2.2) — only for
                            # non-normalized tabular exams; each toggle re-derives this
                            # exam's data independently of the others.
                            if state.is_multi_exam and exam_supports_transforms(exam, meta):
                                with ui.expansion(
                                    "Coordinate corrections", icon="tune"
                                ).classes("w-full").props("dense"):
                                    ui.switch(
                                        "Swap lateral ↔ longitudinal (Tx ↔ Tz)",
                                        value=meta.get("swap_lat_lon", False),
                                    ).on_value_change(
                                        lambda e, i=idx: _on_exam_transform_change(
                                            i, "swap_lat_lon", e.value
                                        )
                                    ).tooltip(
                                        "Auto-enabled for GE exports; verify for others."
                                    )
                                    ui.switch(
                                        "Flip primary angle (Ap1 × −1)",
                                        value=meta.get("flip_ap1", False),
                                    ).on_value_change(
                                        lambda e, i=idx: _on_exam_transform_change(
                                            i, "flip_ap1", e.value
                                        )
                                    )
                                    ui.switch(
                                        "Flip secondary angle (Ap2 × −1)",
                                        value=meta.get("flip_ap2", False),
                                    ).on_value_change(
                                        lambda e, i=idx: _on_exam_transform_change(
                                            i, "flip_ap2", e.value
                                        )
                                    )

                            # Manual table-origin override (Phase 2.5) — escape hatch
                            # for a misdetected scanner or a tabular export with no
                            # convention metadata. Shown for single- and multi-exam.
                            if exam_supports_table_origin(exam, meta):
                                _build_table_origin_section(idx, meta)

            def _remove_exam(index: int) -> None:
                """Remove one accumulated exam and rebuild derived state.

                Deletes the backing temp file only when no other loaded exam still
                references it (a multi-study file produces several exams that share
                one path).
                """
                import pandas as pd

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
                    _remove_temp_upload(file_path)

                if state.loaded_exams:
                    state.rdsr_df = pd.concat(
                        [e.normalized_data for e in state.loaded_exams], ignore_index=True
                    )
                else:
                    state.rdsr_df = None
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
                    # Returning to single-exam: sync the global coordinate-correction
                    # flags to the surviving exam so the global card reflects reality.
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
                _refresh_event_table()
                _refresh_exams_table()
                _refresh_import_preview()

            def _refresh_import_preview():
                prov = state.import_provenance
                # Global coordinate-correction card: single-exam, non-normalized only.
                coord_card.set_visibility(
                    prov is not None
                    and getattr(prov, "schema_name", "") != "normalized"
                    and not state.is_multi_exam
                )
                if prov is None:
                    return
                import_schema_badge.set_text(prov.schema_name.upper().replace("_", " "))
                import_encoding_label.set_text(f"Encoding: {prov.detected_encoding or '—'}")
                delim = repr(prov.detected_delimiter) if prov.detected_delimiter else "N/A"
                import_delimiter_label.set_text(f"Delimiter: {delim}")
                import_header_label.set_text(f"Header row: {prov.header_row_index}")
                # Sheet info (Excel only)
                if state.available_sheets:
                    sheet_name = state.input_sheet_name
                    n = len(state.available_sheets)
                    import_sheet_label.set_text(f"Sheet: {sheet_name!r} ({n} available)")
                else:
                    import_sheet_label.set_text("")
                if state.import_warnings:
                    import_warnings_label.set_text("Warning: " + "; ".join(state.import_warnings[:3]))
                else:
                    import_warnings_label.set_text("")
                if prov.column_map:
                    col_map_table.rows = [{"source": k, "mapped": v} for k, v in prov.column_map.items()]
                    col_map_table.update()
                if state.rdsr_df is not None:
                    df = state.rdsr_df.head(5).reset_index(drop=True)
                    df.insert(0, "__idx", range(1, len(df) + 1))
                    event_sample_table.columns = [
                        {"name": c, "label": c, "field": c, "align": "left"} for c in df.columns
                    ]
                    event_sample_table.rows = df.fillna("—").astype(str).to_dict("records")
                    event_sample_table.update()

            _GE_MANUFACTURER_VARIANTS = frozenset({
                "ge", "ge medical systems", "ge healthcare", "general electric", "gems"
            })

            def _is_ge() -> bool:
                """Return True if the loaded data is from GE equipment."""
                # Manufacturer field is populated for direct RDSR loads
                if state.manufacturer.strip().lower() in _GE_MANUFACTURER_VARIANTS:
                    return True
                # Tabular loads (Radimetrics etc.) surface GE via import warnings
                warnings_lower = " ".join(state.import_warnings).lower()
                return "ge manufacturer detected" in warnings_lower

            def _set_transform_defaults() -> None:
                """Auto-set coordinate correction toggles based on detected manufacturer.

                Single-exam only — in multi-exam mode each exam carries its own
                defaults (set per-exam at load). Writes the GE auto-swap into the
                first exam's meta and re-derives its data through the per-exam engine
                so the single entry stays consistent if more files are added.
                """
                if state.import_provenance is None:
                    return

                # In multi-exam mode each exam owns its transforms (loaded_exam_meta);
                # the global card is hidden and these globals are unused.
                if state.is_multi_exam:
                    coord_auto_label.set_text("")
                    return

                # GE equipment stores lat/lon in the opposite convention to MyPySkinDose.
                # This is a property of GE hardware, not of any specific export format.
                needs_swap = _is_ge()
                state.swap_lat_lon = needs_swap
                state.flip_ap1 = False
                state.flip_ap2 = False

                # Push the defaults into the single exam's meta and re-derive its
                # data from the pristine base (load_tabular stored base_data).
                if state.loaded_exam_meta:
                    meta = state.loaded_exam_meta[0]
                    meta["swap_lat_lon"] = needs_swap
                    meta["flip_ap1"] = False
                    meta["flip_ap2"] = False
                    apply_exam_transforms(state, 0)

                coord_auto_label.set_text(
                    "· lat/lon swap auto-enabled" if needs_swap else ""
                )

            # The global coordinate-correction card is single-exam only (hidden in
            # multi-exam mode). Its toggles mirror the flag into the single exam's
            # meta and re-derive that exam's data through the per-exam engine, so the
            # global card and per-exam list never disagree.
            def _on_swap_toggle() -> None:
                if not state.loaded_exam_meta or state.input_source_type in ("", "dicom"):
                    return
                prov = state.import_provenance
                if prov and prov.schema_name == "normalized":
                    return
                state.loaded_exam_meta[0]["swap_lat_lon"] = state.swap_lat_lon
                apply_exam_transforms(state, 0)
                reset_results()
                _refresh_event_table()
                _refresh_exams_table()
                _refresh_import_preview()
                coord_auto_label.set_text("")

            def _on_flip_ap1_toggle() -> None:
                if not state.loaded_exam_meta or state.input_source_type in ("", "dicom"):
                    return
                state.loaded_exam_meta[0]["flip_ap1"] = state.flip_ap1
                apply_exam_transforms(state, 0)
                reset_results()
                _refresh_event_table()
                _refresh_exams_table()
                _refresh_import_preview()

            def _on_flip_ap2_toggle() -> None:
                if not state.loaded_exam_meta or state.input_source_type in ("", "dicom"):
                    return
                state.loaded_exam_meta[0]["flip_ap2"] = state.flip_ap2
                apply_exam_transforms(state, 0)
                reset_results()
                _refresh_event_table()
                _refresh_exams_table()
                _refresh_import_preview()

            # Expose the upload spine as ctx callables so out-of-module callers
            # (the restore tail, and future extracted tabs) reach them without
            # importing the closures. Upload-internal callers above stay local.
            ctx.refresh_event_table = _refresh_event_table
            ctx.refresh_import_preview = _refresh_import_preview

        # ══════════════════════════════════════════════════════════════════
        # TAB 2 — DATA TABLE
        # ══════════════════════════════════════════════════════════════════
        data_tab.build(ctx)

        # ══════════════════════════════════════════════════════════════════
        # TAB 3 — SETTINGS
        # ══════════════════════════════════════════════════════════════════
        settings_tab.build(ctx)

        # ══════════════════════════════════════════════════════════════════
        # TAB 4 — GEOMETRY PREVIEW
        # ══════════════════════════════════════════════════════════════════
        geometry_tab.build(ctx)

        # ══════════════════════════════════════════════════════════════════
        # TAB 5 — CALCULATE
        # ══════════════════════════════════════════════════════════════════
        with ui.tab_panel("calculate"):
            with ui.column().classes("max-w-4xl mx-auto w-full gap-6"):
                ui.label("Run Dose Calculation").classes("text-2xl font-bold tracking-tight")

                # settings summary card
                with ui.card().classes("modern-card w-full border border-blue-100 shadow-sm"):
                    with ui.row().classes("items-center justify-between w-full"):
                        ui.label("Current settings").classes("text-xl font-bold q-mb-md")
                        with ui.row().classes("items-center gap-2").bind_visibility_from(state, "is_multi_exam"):
                            ui.badge().bind_text_from(state, "loaded_exams", backward=lambda v: f"{len(v)} EXAMS").classes("text-xs tracking-widest font-bold")
                            ui.label("Per-exam patient offsets editable in Upload tab").classes("text-caption text-grey-5 italic")

                    with ui.grid(columns=3).classes("w-full gap-8 mono-text text-sm"):
                        # Section 1: Input Data
                        with ui.column().classes("gap-2"):
                            ui.label("INPUT DATA").classes("text-sm text-aurora-teal font-bold tracking-widest border-b border-white/10 w-full q-pb-xs")
                            
                            with ui.column().classes("gap-1"):
                                with ui.column().classes("gap-0"):
                                    ui.label("File:").classes("text-grey-5 font-normal text-[11px] uppercase tracking-tighter")
                                    ui.label().bind_text_from(state, "file_name", backward=lambda v: f"{v if v else 'None'}").classes("font-bold text-[13px] truncate w-full")
                                
                                with ui.row().classes("items-baseline gap-2"):
                                    ui.label("Events:").classes("text-grey-5 font-normal text-[11px] uppercase tracking-tighter")
                                    ui.label().bind_text_from(state, "rdsr_df", backward=lambda v: f"{len(v) if v is not None else 0}").classes("font-bold text-[13px]")
                                
                                with ui.column().classes("gap-0"):
                                    ui.label("Scanner:").classes("text-grey-5 font-normal text-[11px] uppercase tracking-tighter")
                                    ui.label().bind_text_from(state, "manufacturer", backward=lambda v: f"{v} {state.model}").classes("font-bold text-[13px]")
                                    ui.label().bind_text_from(state, "normalization_method", backward=lambda v: f"({v} Matched)").classes("text-[10px] opacity-40 italic")
                        
                        # Section 2: Phantom
                        with ui.column().classes("gap-2"):
                            ui.label("PHANTOM SETUP").classes("text-sm text-aurora-purple font-bold tracking-widest border-b border-white/10 w-full q-pb-xs")
                            
                            with ui.column().classes("gap-1"):
                                with ui.row().classes("items-baseline gap-2"):
                                    ui.label("Model:").classes("text-grey-5 font-normal text-[11px] uppercase tracking-tighter")
                                    ui.label().bind_text_from(state, "phantom_model", backward=lambda v: f"{v}").classes("font-bold text-[13px]")
                                
                                with ui.column().classes("gap-0"):
                                    ui.label("Patient Offsets:").classes("text-grey-5 font-normal text-[11px] uppercase tracking-tighter")
                                    ui.label().bind_text_from(state, "d_lon", backward=lambda v: f"{v}, {state.d_ver}, {state.d_lat} cm").classes("font-bold text-[13px]")
                                
                                with ui.column().classes("gap-0"):
                                    ui.label("Table Offsets:").classes("text-grey-5 font-normal text-[11px] uppercase tracking-tighter")
                                    ui.label().bind_text_from(state, "table_offset_x", backward=lambda v: f"{v}, {state.table_offset_y}, {state.table_offset_z} cm").classes("font-bold text-[13px]")

                        # Section 3: Physics
                        with ui.column().classes("gap-2"):
                            ui.label("PHYSICS PARAMETERS").classes("text-sm text-aurora-pink font-bold tracking-widest border-b border-white/10 w-full q-pb-xs")
                            
                            with ui.column().classes("gap-1"):
                                with ui.row().classes("items-baseline gap-2"):
                                    ui.label("k_tab:").classes("text-grey-5 font-normal text-[11px] uppercase tracking-tighter")
                                    ui.label().bind_text_from(state, "estimate_k_tab", backward=lambda v: "Estimated" if v else "Measured").classes("font-bold text-[13px]")
                                
                                with ui.row().classes("items-baseline gap-2"):
                                    ui.label("Filtration:").classes("text-grey-5 font-normal text-[11px] uppercase tracking-tighter")
                                    ui.label().bind_text_from(state, "inherent_filtration", backward=lambda v: f"{v} mmAl").classes("font-bold text-[13px]")

                with ui.column().classes("w-full items-center gap-4 q-mt-xl"):
                    calc_btn = ui.button("▶  Run Calculation", on_click=lambda: do_calculate(), icon="bolt").classes(
                        "modern-btn modern-btn-teal text-xl px-12 py-4 icon-outlined"
                    )
                    ctx.run_btn_drawer.on("click", lambda: do_calculate())

                    calc_progress = ui.linear_progress(value=0, color="indigo").classes("w-full")
                    calc_progress.visible = False
                    calc_status_label = ui.label("Waiting...").classes("text-caption text-grey-5")

            async def do_calculate():
                if state.rdsr_df is None:
                    ui.notify("Load a file first (tab 1)", color="warning")
                    return
                if state.import_has_errors:
                    ui.notify("Fix import errors before calculating (tab 1)", color="warning")
                    return

                with _operation_guard("starting a calculation") as proceed:
                    if not proceed:
                        return

                    calc_btn.disable()
                    ctx.run_btn_drawer.disable()
                    calc_progress.visible = True
                    calc_progress.set_value(0)
                    calc_status_label.set_text("Starting...")

                    def progress_cb(fraction: float, label: str):
                        calc_progress.set_value(fraction)
                        calc_status_label.set_text(label)

                    try:
                        ok, msg = await run.io_bound(run_calculation, state, progress_cb)
                    finally:
                        calc_progress.set_value(1.0)
                        calc_btn.enable()
                        ctx.run_btn_drawer.enable()

                    if ok:
                        ctx.psd_label.set_text(f"PSD: {state.psd:.2f} mGy")
                        ui.notify(f"✓ {msg}", color="positive")
                        ctx.tabs.set_value("results")
                        # Surface any calc warnings (e.g. HVL snapped for out-of-range
                        # events) — not just in the console.
                        if state.calc_warnings:
                            calc_status_label.set_text(
                                f"Done — {msg} · {len(state.calc_warnings)} warning(s), see notifications"
                            )
                            for warning in state.calc_warnings:
                                ui.notify(warning, type="warning", timeout=12000, multi_line=True)
                        else:
                            calc_status_label.set_text(f"Done — {msg}")
                    else:
                        calc_status_label.set_text("Calculation failed")
                        ui.notify(f"Error: {msg[:300]}", type="negative", timeout=10000)

        # ══════════════════════════════════════════════════════════════════
        # TAB 6 — RESULTS
        # ══════════════════════════════════════════════════════════════════
        results_tab.build(ctx)

        # ══════════════════════════════════════════════════════════════════
        # TAB 7 — EXPORT
        # ══════════════════════════════════════════════════════════════════
        export_tab.build(ctx)

    # ── Restore view if data already loaded ──
    if state.rdsr_df is not None:
        dprint("GUI", "Restoring UI state from loaded data")
        ctx.file_label.set_text(state.file_name.upper())
        ctx.events_label.set_text(f"{len(state.rdsr_df)} EVENTS")
        ctx.refresh_event_table()
        _refresh_exams_table()
        if state.active_tab:
            ctx.tabs.set_value(state.active_tab)

# ── figure-building helpers (called via run.io_bound) ─────────────────────


# ── entry point ────────────────────────────────────────────────────────────

def run_gui(native: bool = False, host: str | None = None) -> None:
    """Launch the MyPySkinDose NiceGUI app.

    Binds to 127.0.0.1 (localhost only) by default. The GUI has no authentication
    and loads PHI-derived RDSR data into a single process-global, shared state, so
    it must not be exposed on the network unintentionally — and NiceGUI's browser
    mode would otherwise default to 0.0.0.0 (all interfaces). Pass an explicit
    ``host`` (e.g. ``"0.0.0.0"``) to opt into LAN serving; only do so on a trusted
    network and behind your own access controls.
    """
    # Native mode has no console; mirror logs to a file so issues are diagnosable.
    log_file = None
    if native:
        log_file = Path(tempfile.gettempdir()) / "mypyskindose-gui.log"
    configure_logging(log_file=log_file)
    dprint("GUI", f"Starting run_gui, native={native}")
    if native:
        dprint("GUI", f"Logging to {log_file}")

    if native:
        @app.on_connect
        def _handle_native_focus():
            try:
                # Set on_top to True to ensure it pops up, 
                # then maybe back to False so it doesn't block other windows forever
                # if the user prefers. But for now, let's just force it to front.
                from nicegui import app
                if app.native.main_window is not None:
                    set_on_top = getattr(app.native.main_window, "set_on_top", None)
                    if callable(set_on_top):
                        set_on_top(True)
                    # Optional: wait a bit and set to false so it's not "sticky"
                    # ui.timer(2.0, lambda: app.native.main_window.set_on_top(False), once=True)
            except Exception as exc:
                dprint("GUI", f"Native window focus failed: {exc}")

    # Suppress JavaScript timeout errors during shutdown
    import logging
    logging.getLogger('nicegui').setLevel(logging.ERROR)

    if not native:
        # Browser mode runs a standalone server that outlives the browser tab, so
        # closing the window normally leaves the process running. For a local,
        # single-user launch, treat closing the last window as "quit": when a
        # client disconnects, wait a short grace period (so a page reload, which
        # briefly drops the socket, doesn't trigger it) and shut down if no client
        # is still connected. Native mode already exits when its window closes.
        @app.on_disconnect
        def _shutdown_when_last_window_closes() -> None:
            async def _shutdown_if_idle() -> None:
                await asyncio.sleep(4.0)
                if not any(c.has_socket_connection for c in Client.instances.values()):
                    dprint("GUI", "Last browser window closed; shutting down server.")
                    app.shutdown()

            asyncio.create_task(_shutdown_if_idle())

    window_size: tuple[int, int] | None = None
    if native:
        try:
            import tkinter as tk
            _root = tk.Tk()
            _root.withdraw()
            sw, sh = _root.winfo_screenwidth(), _root.winfo_screenheight()
            _root.destroy()
            window_size = (int(sw * 0.75), int(sh * 0.75))
        except Exception as exc:
            dprint(
                "GUI",
                f"Could not detect screen size ({exc}); using default window size. "
                "Install Tkinter for screen-size detection and native Save As dialogs "
                "— see the 'native Save As dialogs (Tkinter)' note in README.md.",
            )

    # Default to localhost-only; NiceGUI browser mode would otherwise bind to
    # 0.0.0.0. LAN serving is opt-in via an explicit host (see docstring).
    bind_host = host or "127.0.0.1"
    if bind_host not in ("127.0.0.1", "localhost"):
        dprint(
            "GUI",
            f"Binding GUI to {bind_host} — exposed beyond localhost with no "
            "authentication; ensure this is a trusted network.",
        )

    try:
        ui.run(
            title="MyPySkinDose",
            native=native,
            host=bind_host,
            window_size=window_size,
            reload=False,
            port=8765,
            show=True,
            favicon="🩻",
            reconnect_timeout=30.0,
        )
    except KeyboardInterrupt:
        # Ctrl+C — exit quietly instead of dumping an asyncio CancelledError traceback.
        dprint("GUI", "Interrupted (Ctrl+C); shutting down.")


if __name__ == "__main__":
    run_gui()
