"""MyPySkinDose — NiceGUI app (Phase 1).

Run with:
    python src/mypyskindose/main.py --mode gui
or directly:
    .venv/Scripts/python -m mypyskindose --mode gui
    .venv/Scripts/python -m mypyskindose --mode gui --native
"""

from __future__ import annotations

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

from nicegui import app, run, ui

from .helpers import (
    get_excel_sheets,
    load_rdsr,
    load_tabular,
    run_calculation,
)
from .figures import make_geometry_fig
from .styles import MODERN_CSS
from .page_context import PageContext
from .tabs import data as data_tab
from .tabs import export as export_tab
from .tabs import results as results_tab
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


def _register_temp_upload(path: Path) -> None:
    """Track a freshly written upload temp file and delete the prior one."""
    while _uploaded_temp_files:
        old = _uploaded_temp_files.pop()
        try:
            old.unlink(missing_ok=True)
        except OSError as exc:
            dprint("GUI", f"Could not delete old temp upload {old}: {exc}")
    _uploaded_temp_files.append(path)


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
# without a circular dependency on app.py. Re-exported here for in-module use.
from .constants import (  # noqa: E402 — grouped with the other constants
    COLORSCALES,
    EXAMPLE_FILES,
    HUMAN_MESHES,
    ORIENTATIONS,
    PHANTOM_MODELS,
)

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
    
    # Import help button component
    from .components import HelpButton

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
                        with _operation_guard("uploading another file") as proceed:
                            if not proceed:
                                return
                            # NiceGUI 3.x wraps the upload in e.file (name + async read()).
                            file_name = e.file.name
                            dprint("GUI", f"Uploading file {file_name}")
                            suffix = Path(file_name).suffix.lower() or ".dcm"
                            data = await e.file.read()
                            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                                tmp.write(data)
                                tmp_path = Path(tmp.name)
                            # Track for cleanup; deletes the previous upload's temp file.
                            # Kept alive for the session so the XLSX sheet picker can re-read it.
                            _register_temp_upload(tmp_path)

                            # Reset sheet state and transform flags for every new upload
                            state.input_sheet_name = 0
                            state.available_sheets = []
                            sheet_row.set_visibility(False)
                            state.swap_lat_lon = False
                            state.flip_ap1 = False
                            state.flip_ap2 = False

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
                                reset_results()
                                _refresh_event_table()
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

                    ui.upload(on_upload=handle_upload, label="DRAG AND DROP OR CLICK TO SELECT").props(
                        'accept=".dcm,.csv,.tsv,.xlsx,.xlsm" flat bordered color=deep-purple auto-upload'
                    ).classes("w-full bg-black/40")

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
                            else:
                                upload_status.set_text("Could not load — see message")
                                ui.notify(msg, type="negative", timeout=10000, multi_line=True)

                    # Wire to the value-change (not the raw Vue event) so it fires on
                    # any selection — and is reliably simulable in the GUI flow tests.
                    example_select.on_value_change(lambda: load_example())

                    ui.separator().classes("q-my-sm bg-zinc-800")

                    with ui.row().classes("w-full items-end gap-4"):
                        ui.select(
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
                                ok, msg = await run.io_bound(load_tabular, state.file_path, state)
                                if ok:
                                    upload_status.set_text(f"SUCCESS: {msg.upper()}")
                                    reset_results()
                                    _refresh_event_table()
                                    _refresh_import_preview()
                                else:
                                    ui.notify(f"Sheet parse error: {msg[:200]}", type="negative", timeout=6000)

                        sheet_select.on("update:model-value", _on_sheet_change)
                    sheet_row.set_visibility(False)

                    # Coordinate correction options — visible for non-normalized schemas
                    with ui.card().classes("modern-card w-full bg-blue-950/20 q-pa-sm q-mb-xs").bind_visibility_from(
                        state, "import_provenance",
                        backward=lambda v: v is not None and getattr(v, "schema_name", "") != "normalized",
                    ):
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

            def _refresh_import_preview():
                prov = state.import_provenance
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

                Called once after initial file load, not on sheet re-parse, so user
                overrides are preserved across sheet changes.
                """
                if state.import_provenance is None:
                    return

                # GE equipment stores lat/lon in the opposite convention to MyPySkinDose.
                # This is a property of GE hardware, not of any specific export format.
                needs_swap = _is_ge()
                state.swap_lat_lon = needs_swap
                state.flip_ap1 = False
                state.flip_ap2 = False

                # Apply swap if needed (load_tabular loaded with swap=False)
                if needs_swap and state.rdsr_df is not None:
                    if "Tx" in state.rdsr_df.columns and "Tz" in state.rdsr_df.columns:
                        df = state.rdsr_df.copy()
                        df["Tx"], df["Tz"] = state.rdsr_df["Tz"].copy(), state.rdsr_df["Tx"].copy()
                        state.rdsr_df = df

                # Update the auto-hint label
                if needs_swap:
                    coord_auto_label.set_text("· lat/lon swap auto-enabled")
                else:
                    coord_auto_label.set_text("")

            def _on_swap_toggle() -> None:
                if state.rdsr_df is None or state.input_source_type in ("", "dicom"):
                    return
                prov = state.import_provenance
                if prov and prov.schema_name == "normalized":
                    return
                if "Tx" in state.rdsr_df.columns and "Tz" in state.rdsr_df.columns:
                    df = state.rdsr_df.copy()
                    df["Tx"], df["Tz"] = state.rdsr_df["Tz"].copy(), state.rdsr_df["Tx"].copy()
                    state.rdsr_df = df
                    reset_results()
                    _refresh_event_table()
                    _refresh_import_preview()
                    coord_auto_label.set_text("")

            def _on_flip_ap1_toggle() -> None:
                if state.rdsr_df is None or state.input_source_type in ("", "dicom"):
                    return
                if "Ap1" in state.rdsr_df.columns:
                    df = state.rdsr_df.copy()
                    df["Ap1"] = -state.rdsr_df["Ap1"]
                    state.rdsr_df = df
                    reset_results()
                    _refresh_event_table()
                    _refresh_import_preview()

            def _on_flip_ap2_toggle() -> None:
                if state.rdsr_df is None or state.input_source_type in ("", "dicom"):
                    return
                if "Ap2" in state.rdsr_df.columns:
                    df = state.rdsr_df.copy()
                    df["Ap2"] = -state.rdsr_df["Ap2"]
                    state.rdsr_df = df
                    reset_results()
                    _refresh_event_table()
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
        with ui.tab_panel("settings"):
            with ui.column().classes("max-w-4xl mx-auto w-full gap-6"):
                ui.label("Calculation Settings").classes("text-2xl font-bold tracking-tight")

                with ui.expansion("Phantom Settings", icon="person", value=True).classes("modern-card w-full"):
                    with ui.column().classes("w-full gap-4 q-pa-md"):
                        with ui.row().classes("w-full items-center justify-between"):
                            ui.label("Phantom model and positioning").classes("text-subtitle2")
                            HelpButton(
                                title="Phantom Positioning Offsets",
                                content_path="positioning_offsets.md"
                            )
                        with ui.row().classes("w-full gap-6"):
                            ui.select(PHANTOM_MODELS, label="Phantom model", value=state.phantom_model).bind_value(
                                state, "phantom_model"
                            ).on("update:model-value", reset_results).classes("grow")

                            mesh_select = ui.select(
                                HUMAN_MESHES, label="Human mesh", value=state.human_mesh
                            ).bind_value(state, "human_mesh").on("update:model-value", reset_results).classes("grow")

                        # show/hide mesh selector based on model
                        def _update_mesh_visibility():
                            mesh_select.visible = state.phantom_model == "human"

                        ui.timer(0.5, _update_mesh_visibility)

                        ui.select(ORIENTATIONS, label="Patient orientation", value=state.patient_orientation).bind_value(
                            state, "patient_orientation"
                        ).on("update:model-value", reset_results).classes("w-full")

                        ui.label("Patient offset (cm)").classes("text-caption text-grey-6 q-mt-sm")
                        with ui.row().classes("w-full gap-4"):
                            ui.number(label="Longitudinal", value=state.d_lon, step=1.0).bind_value(
                                state, "d_lon"
                            ).on("update:model-value", reset_results).classes("grow")
                            ui.number(label="Vertical", value=state.d_ver, step=1.0).bind_value(
                                state, "d_ver"
                            ).on("update:model-value", reset_results).classes("grow")
                            ui.number(label="Lateral", value=state.d_lat, step=1.0).bind_value(
                                state, "d_lat"
                            ).on("update:model-value", reset_results).classes("grow")

                with ui.expansion("Physics Settings", icon="science").classes("modern-card w-full"):
                    with ui.column().classes("w-full gap-4 q-pa-md"):
                        ui.checkbox("Use estimated table transmission (k_tab)", value=state.estimate_k_tab).bind_value(
                            state, "estimate_k_tab"
                        ).on("update:model-value", reset_results)

                        with ui.column().classes("w-full gap-1"):
                            ui.label("TRANSMISSION FACTOR (k_tab)").classes("technical-label")
                            with ui.row().classes("items-center w-full gap-4"):
                                ui.slider(min=0.0, max=1.0, step=0.01, value=state.k_tab_val).bind_value(
                                    state, "k_tab_val"
                                ).on("update:model-value", reset_results).classes("grow")
                                ui.label().bind_text_from(state, "k_tab_val", backward=lambda v: f"{v:.2f}").classes("mono-text font-bold")

                        ui.number(
                            label="Inherent filtration (mmAl)", value=state.inherent_filtration, min=0.0, step=0.1
                        ).bind_value(state, "inherent_filtration").on("update:model-value", reset_results).classes("w-full")

                        ui.checkbox("Remove invalid data (kVp = 0)", value=state.remove_invalid_rows).bind_value(
                            state, "remove_invalid_rows"
                        ).on("update:model-value", reset_results)

                with ui.expansion("Visual Settings", icon="palette").classes("modern-card w-full"):
                    with ui.column().classes("w-full gap-4 q-pa-md"):
                        ui.checkbox("Auto-render dose map on completion", value=state.plot_dosemap).bind_value(
                            state, "plot_dosemap"
                        )
                        ui.select(COLORSCALES, label="Dose map colorscale", value=state.colorscale).bind_value(
                            state, "colorscale"
                        ).classes("w-full")

        # ══════════════════════════════════════════════════════════════════
        # TAB 4 — GEOMETRY PREVIEW
        # ══════════════════════════════════════════════════════════════════
        with ui.tab_panel("geometry"):
            with ui.column().classes("max-w-6xl mx-auto w-full gap-6"):
                with ui.row().classes("w-full items-center justify-between"):
                    ui.label("Geometry Preview").classes("text-2xl font-bold tracking-tight")
                    HelpButton(
                        title="Geometry Workflow",
                        content_path="geometry_workflow.md"
                    )
                
                # controls in a row above the plot
                with ui.row().classes("w-full items-end gap-4"):
                    with ui.card().classes("modern-card w-48 p-2"):
                        ui.label("Event selection").classes("text-xs uppercase opacity-70")
                        geom_event_input = ui.number(
                            value=0, min=0, step=1
                        ).classes("w-full mono-text").props("dense flat")
                    
                    ui.button("Setup view", on_click=lambda: preview_setup()).classes("modern-btn-teal h-12 px-6")
                    ui.button("Single event", on_click=lambda: preview_event()).classes("modern-btn-teal h-12 px-6")
                    ui.button("Full procedure", on_click=lambda: preview_procedure()).classes("modern-btn-teal h-12 px-6")
                    
                    geom_spinner = ui.spinner(size="lg", color="indigo").classes("ml-4")
                    geom_spinner.visible = False

                with ui.card().classes("w-full modern-card p-0 overflow-hidden"):
                    geom_plot = ui.plotly({}).classes("w-full").style("height:700px")

                async def preview_setup():
                    if state.rdsr_df is None:
                        ui.notify("Load data first", type="warning")
                        return
                    geom_spinner.visible = True
                    fig = await run.io_bound(make_geometry_fig, "plot_setup", 0)
                    geom_spinner.visible = False
                    if fig:
                        geom_plot.update_figure(fig)

                async def preview_event():
                    if state.rdsr_df is None:
                        ui.notify("Load data first", type="warning")
                        return
                    geom_spinner.visible = True
                    fig = await run.io_bound(make_geometry_fig, "plot_event", int(geom_event_input.value or 0))
                    geom_spinner.visible = False
                    if fig:
                        geom_plot.update_figure(fig)

                async def preview_procedure():
                    if state.rdsr_df is None:
                        ui.notify("Load data first", type="warning")
                        return
                    geom_spinner.visible = True
                    fig = await run.io_bound(make_geometry_fig, "plot_procedure", 0)
                    geom_spinner.visible = False
                    if fig:
                        geom_plot.update_figure(fig)

        # ══════════════════════════════════════════════════════════════════
        # TAB 5 — CALCULATE
        # ══════════════════════════════════════════════════════════════════
        with ui.tab_panel("calculate"):
            with ui.column().classes("max-w-4xl mx-auto w-full gap-6"):
                ui.label("Run Dose Calculation").classes("text-2xl font-bold tracking-tight")

                # settings summary card
                with ui.card().classes("modern-card w-full border border-blue-100 shadow-sm"):
                    ui.label("Current settings").classes("text-xl font-bold q-mb-md")

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
                        calc_status_label.set_text(f"Done — {msg}")
                        ui.notify(f"✓ {msg}", color="positive")
                        ctx.tabs.set_value("results")
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
        if state.active_tab:
            ctx.tabs.set_value(state.active_tab)

# ── figure-building helpers (called via run.io_bound) ─────────────────────


# ── entry point ────────────────────────────────────────────────────────────

def run_gui(native: bool = False) -> None:
    """Launch the MyPySkinDose NiceGUI app."""
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

    ui.run(
        title="MyPySkinDose",
        native=native,
        window_size=window_size,
        reload=False,
        port=8765,
        show=True,
        favicon="🩻",
        reconnect_timeout=30.0,
    )


if __name__ == "__main__":
    run_gui()
