"""MyPySkinDose — NiceGUI app (Phase 1).

Run with:
    python src/mypyskindose/main.py --mode gui
or directly:
    .venv/Scripts/python -m mypyskindose --mode gui
    .venv/Scripts/python -m mypyskindose --mode gui --native
"""

from __future__ import annotations

import io
import json
import os
import tempfile
from pathlib import Path

# Fix for Windows SSL context loading error during shutdown
# Prevents aiohttp from loading Windows certificate store which causes issues on Python 3.13
os.environ['SSL_CERT_FILE'] = ''

# Fix for colorama atexit error on Windows during shutdown
# Prevents colorama from trying to reset console colors when handle is already closed
os.environ['COLORAMA_DISABLE'] = '1'

import pandas as pd

from nicegui import app, run, ui

from .helpers import (
    build_settings,
    get_example_rdsr_files,
    get_human_mesh_names,
    load_rdsr,
    load_tabular,
    run_calculation,
)
from .state import reset_results, state
from mypyskindose.debug import dprint

GUI_VERSION = "1.1.0"

# ── helper for file dialog ────────────────────────────────────────────────
def _get_save_path(default_name: str, extension: str) -> str | None:
    """Open a native Save As dialog."""
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        # map extension to filter
        ext_map = {
            "csv": [("CSV Files", "*.csv")],
            "xlsx": [("Excel Files", "*.xlsx")],
            "txt": [("Text Files", "*.txt")],
            "json": [("JSON Files", "*.json")],
            "html": [("HTML Files", "*.html")],
            "png": [("PNG Images", "*.png")],
        }
        path = filedialog.asksaveasfilename(
            initialfile=default_name,
            defaultextension=f".{extension}",
            filetypes=ext_map.get(extension, [("All Files", "*.*")])
        )
        root.destroy()
        return path if path else None
    except Exception as e:
        dprint("GUI", f"Native dialog error: {e}")
        return None

# ── constants ──────────────────────────────────────────────────────────────
HUMAN_MESHES = get_human_mesh_names()
EXAMPLE_FILES = {p.name: p for p in get_example_rdsr_files()}
COLORSCALES = ["jet", "viridis", "plasma", "inferno", "magma", "turbo", "hot"]
PHANTOM_MODELS = ["human", "cylinder", "plane"]
ORIENTATIONS = ["head_first_supine", "feet_first_supine"]

# ── sleek modern/material design ─────────────────────────────────────────────
# After CSS changes, regenerate dev-docs/UI_values.md:
#   python scripts/generate_ui_values.py
MODERN_CSS = r"""
:root {
    --bg-primary: #0e0e0e;
    --bg-secondary: #1d1d1d;
    --aurora-purple: #4338CA;
    --aurora-teal: #0D9488;
    --aurora-pink: #831843;
    --text-main: #F8FAFC;
    --text-muted: #94A3B8;
    --glass-bg: rgba(33, 33, 33, 0.70);
    --glass-bg-hover: rgba(33, 33, 33, 0.85);
    --glass-border: rgba(255, 255, 255, 0.15);
    --shadow-soft: 0 4px 24px rgba(0, 0, 0, 0.4);
    --shadow-hover: 0 8px 32px rgba(0, 0, 0, 0.5);
    --glow-blue: rgba(59, 130, 246, 0.3);
    --glow-purple: rgba(99, 102, 241, 0.3);
}

.text-aurora-purple { color: var(--aurora-purple) !important; }
.text-aurora-teal { color: var(--aurora-teal) !important; }
.text-aurora-pink { color: var(--aurora-pink) !important; }

body {
    background-color: var(--bg-primary) !important;
    color: var(--text-main) !important;
    font-family: 'Inter', -apple-system, sans-serif;
    background-image:
        radial-gradient(at 100% 0%, rgba(165, 141, 149, 0.17) 0%, transparent 55%),
        radial-gradient(at 0% 0%, rgba(126, 145, 194, 0.16) 0%, transparent 55%),
        radial-gradient(at 100% 100%, rgba(107, 125, 138, 0.15) 0%, transparent 60%) !important;
    background-attachment: fixed;
}

.nicegui-content { background: transparent !important; }

.q-table th {
    font-weight: 800 !important;
    color: var(--text-main) !important;
    text-transform: uppercase;
    font-size: 0.75rem;
    background: rgba(255, 255, 255, 0.05) !important;
    border-bottom: 2px solid #3d3d4d !important;
}

.q-table td {
    color: var(--text-main) !important;
    border-bottom: 1px solid rgba(255, 255, 255, 0.05) !important;
}

.modern-header {
    background-color: rgba(10, 10, 10, 0.95) !important;
    backdrop-filter: blur(24px) saturate(180%);
    border-bottom: 1px solid rgba(255, 255, 255, 0.08) !important;
    box-shadow: 0 4px 30px rgba(0,0,0,0.7) !important;
}

.q-drawer {
    background: linear-gradient(180deg, #0D0D0D 0%, #050505 100%) !important;
    background-image: radial-gradient(at 0% 100%, rgba(126, 145, 194, 0.12) 0%, transparent 65%) !important;
    border-right: 1px solid rgba(255, 255, 255, 0.08) !important;
}

.modern-card {
    border-top: 1px solid rgba(255, 255, 255, 0.15) !important;
    border-left: 1px solid rgba(255, 255, 255, 0.05) !important;
    border-right: 1px solid rgba(255, 255, 255, 0.05) !important;
    border-bottom: 1px solid rgba(255, 255, 255, 0.05) !important;
    background: var(--glass-bg) !important;
    backdrop-filter: blur(20px) saturate(150%);
    border-radius: 12px !important;
    box-shadow:
        inset 0 1px 0 rgba(255, 255, 255, 0.1),
        var(--shadow-soft),
        0 0 15px rgba(255, 255, 255, 0.05) !important;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.modern-card:hover {
    transform: translateY(-1px) !important;
    background: var(--glass-bg-hover) !important;
    box-shadow:
        inset 0 1px 0 rgba(255, 255, 255, 0.15),
        var(--shadow-hover),
        0 0 20px rgba(255, 255, 255, 0.08) !important;
}

.modern-toggle {
    border: 1px solid rgba(255, 255, 255, 0.08) !important;
    background: rgba(0, 0, 0, 0.4) !important;
    border-radius: 8px;
    overflow: hidden;
    backdrop-filter: blur(12px);
}

.modern-toggle .q-btn {
    border: 1px solid rgba(255, 255, 255, 0.05) !important;
    color: var(--text-muted) !important;
    font-weight: 600 !important;
    text-transform: uppercase;
    font-size: 0.75rem;
    padding: 0 16px !important;
    border-radius: 0 !important;
}

.modern-toggle .q-btn--active {
    background: var(--q-primary) !important;
    color: white !important;
    border-color: var(--q-primary) !important;
}

.modern-btn {
    border-radius: 8px !important;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1) !important;
    backdrop-filter: blur(12px) !important;
    background: rgba(30, 30, 30, 0.5) !important;
    border: 1px solid rgba(255, 255, 255, 0.15) !important;
}

.modern-btn:hover {
    transform: scale(1.02) !important;
    box-shadow: 0 10px 20px rgba(0, 0, 0, 0.4), 0 0 15px var(--glow-blue) !important;
    background: rgba(30, 30, 30, 0.6) !important;
}

.modern-btn-primary {
    background: linear-gradient(180deg, rgba(15, 118, 110, 0.4) 0%, rgba(13, 100, 92, 0.3) 100%) !important;
    border: 1px solid rgba(20, 184, 166, 0.4) !important;
    border-radius: 8px !important;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1) !important;
    backdrop-filter: blur(12px) !important;
}

.modern-btn-primary:hover {
    transform: scale(1.02) !important;
    background: linear-gradient(180deg, rgba(20, 184, 166, 0.5) 0%, rgba(13, 100, 92, 0.4) 100%) !important;
    box-shadow: 0 10px 20px rgba(0, 0, 0, 0.4), 0 0 20px var(--glow-blue) !important;
}

.modern-btn-secondary {
    background: linear-gradient(180deg, rgba(67, 56, 202, 0.4) 0%, rgba(55, 48, 163, 0.3) 100%) !important;
    border: 1px solid rgba(99, 102, 241, 0.4) !important;
    border-radius: 8px !important;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1) !important;
    backdrop-filter: blur(12px) !important;
}

.modern-btn-secondary:hover {
    transform: scale(1.02) !important;
    background: linear-gradient(180deg, rgba(99, 102, 241, 0.5) 0%, rgba(55, 48, 163, 0.4) 100%) !important;
    box-shadow: 0 10px 20px rgba(0, 0, 0, 0.4), 0 0 20px var(--glow-purple) !important;
}

/* Override Quasar button colors with glassmorphism */
.q-btn, .q-btn--flat, .q-btn--outline,
.q-btn.bg-deep-purple, .q-btn.text-deep-purple,
.q-btn.bg-primary, .q-btn.text-primary,
.q-btn.bg-positive, .q-btn.text-positive,
.q-btn.bg-teal, .q-btn.text-teal,
.q-btn--standard {
    background: rgba(30, 30, 30, 0.5) !important;
    backdrop-filter: blur(12px) !important;
    border: 1px solid rgba(255, 255, 255, 0.15) !important;
}

.q-btn:hover, .q-btn--flat:hover, .q-btn--outline:hover,
.q-btn.bg-deep-purple:hover, .q-btn.text-deep-purple:hover,
.q-btn.bg-primary:hover, .q-btn.text-primary:hover,
.q-btn.bg-positive:hover, .q-btn.text-positive:hover,
.q-btn.bg-teal:hover, .q-btn.text-teal:hover,
.q-btn--standard:hover {
    background: rgba(30, 30, 30, 0.6) !important;
    box-shadow: 0 10px 20px rgba(0, 0, 0, 0.4), 0 0 15px var(--glow-blue) !important;
}

/* Glassmorphism for separators and dividers */
.q-separator, .q-divider {
    background: rgba(255, 255, 255, 0.1) !important;
    box-shadow: 0 0 10px rgba(255, 255, 255, 0.05) !important;
}

/* Upload component styling */
.q-uploader, .q-uploader__header {
    background: rgba(30, 30, 30, 0.4) !important;
    backdrop-filter: blur(12px) !important;
    border: 1px solid rgba(255, 255, 255, 0.15) !important;
    border-radius: 12px !important;
    box-shadow: 0 0 15px rgba(255, 255, 255, 0.05) !important;
}

.q-uploader:hover, .q-uploader__header:hover {
    background: rgba(30, 30, 30, 0.5) !important;
    box-shadow: 0 0 20px rgba(255, 255, 255, 0.08) !important;
}

.nav-item {
    position: relative;
    padding-left: 16px;
    transition: all 0.2s ease;
    border-radius: 8px;
}

.nav-item:hover {
    background: rgba(255, 255, 255, 0.01) !important;
}

.nav-item.active {
    color: #60A5FA !important;
    background: rgba(37, 99, 235, 0.1) !important;
}

.nav-item.active::before {
    content: '';
    position: absolute;
    left: 0;
    top: 12px;
    bottom: 12px;
    width: 2px;
    background: linear-gradient(180deg, #60A5FA 0%, #3B82F6 100%);
    border-radius: 1px;
}

.q-notification--positive {
    background: #064E3B !important;
    color: #d1fae5 !important;
    border: 1px solid #059669 !important;
    border-radius: 8px !important;
    backdrop-filter: blur(12px);
}
"""


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
                    ui.label("Upload file").classes("text-subtitle2 q-mb-xs")
                    ui.label("DICOM RDSR (.dcm) or tabular event table (.csv, .tsv, .xlsx, .xlsm).").classes("text-sm text-grey-4 q-mb-sm")

                    with ui.row().classes("w-full items-end gap-4 q-mb-sm"):
                        ui.select(
                            options={"auto": "Auto-detect schema", "normalized": "Normalized", "generic_rdsr_like": "Raw RDSR-like"},
                            label="Input schema (tabular files only)",
                            value=state.input_schema,
                        ).bind_value(state, "input_schema").classes("grow")

                    upload_status = ui.label("Waiting for file...").classes("text-caption text-grey-5 q-mb-sm")

                    _TABULAR_SUFFIXES = frozenset({".csv", ".tsv", ".xlsx", ".xlsm"})

                    async def handle_upload(e):
                        dprint("GUI", f"Uploading file {e.name}")
                        suffix = Path(e.name).suffix.lower() or ".dcm"
                        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                            tmp.write(e.content.read())
                            tmp_path = Path(tmp.name)
                        upload_status.set_text("PARSING DATA STREAM...")
                        if suffix in _TABULAR_SUFFIXES:
                            state.input_source_type = suffix.lstrip(".")
                            ok, msg = await run.io_bound(load_tabular, tmp_path, state)
                        else:
                            state.input_source_type = "dicom"
                            ok, msg = await run.io_bound(load_rdsr, tmp_path, state)
                        if ok:
                            state.file_name = e.name
                            file_label.set_text(e.name.upper())
                            events_label.set_text(
                                f"{len(state.rdsr_df) if state.rdsr_df is not None else 0} EVENTS"
                            )
                            upload_status.set_text(f"SUCCESS: {msg.upper()}")
                            ui.notify(msg, color="positive")
                            reset_results()
                            _refresh_event_table()
                            if state.input_source_type != "dicom":
                                _refresh_import_preview()
                        else:
                            upload_status.set_text("STREAM ERROR")
                            ui.notify(f"Parse error: {msg[:200]}", type="negative", timeout=8000)

                    ui.upload(on_upload=handle_upload, label="DRAG AND DROP FILE").props(
                        'accept=".dcm,.csv,.tsv,.xlsx,.xlsm" flat bordered color=deep-purple'
                    ).classes("w-full bg-black/40")

                with ui.card().classes("modern-card modern-card-teal w-full"):
                    ui.label("Load example").classes("text-subtitle2 q-mb-xs")
                    
                    with ui.row().classes("w-full items-end gap-4"):
                        example_select = ui.select(
                            options=list(EXAMPLE_FILES.keys()),
                            label="Available Examples",
                            value=list(EXAMPLE_FILES.keys())[0] if EXAMPLE_FILES else None,
                        ).classes("grow")

                        async def load_example():
                            name = example_select.value
                            if not name:
                                return
                            path = EXAMPLE_FILES[name]
                            upload_status.set_text("PARSING EXAMPLE STREAM...")
                            ok, msg = await run.io_bound(load_rdsr, path, state)
                            if ok:
                                file_label.set_text(name.upper())
                                events_label.set_text(
                                    f"{len(state.rdsr_df) if state.rdsr_df is not None else 0} EVENTS"
                                )
                                upload_status.set_text(f"SUCCESS: {msg.upper()}")
                                ui.notify(msg, color="positive")
                                reset_results()
                                _refresh_event_table()
                            else:
                                ui.notify(f"Parse error: {msg[:200]}", type="negative", timeout=8000)

                        ui.button("LOAD", on_click=load_example).classes("modern-btn modern-btn-teal px-8")

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

                    # Coordinate correction options — visible for non-normalized schemas
                    with ui.card().classes("modern-card w-full bg-blue-950/20 q-pa-sm q-mb-xs").bind_visibility_from(
                        state, "import_provenance",
                        backward=lambda v: v is not None and getattr(v, "schema_name", "") != "normalized",
                    ):
                        ui.label("COORDINATE OPTIONS").classes("text-caption text-grey-4 font-bold tracking-widest q-mb-xs")
                        with ui.row().classes("items-center gap-4 flex-wrap"):
                            ui.switch("Swap lateral/longitudinal axes").bind_value(state, "swap_lat_lon").on(
                                "update:model-value", lambda: _on_swap_toggle()
                            ).tooltip(
                                "Enable for GE scanners or DoseTrack Philips exports where "
                                "TableLateralPosition and TableLongitudinalPosition are physically swapped. "
                                "Swaps Tx and Tz in the normalized output."
                            )
                            ui.label("Swaps Tx ↔ Tz after normalization").classes("text-caption text-grey-5")

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

            def _on_swap_toggle():
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

        # ══════════════════════════════════════════════════════════════════
        # TAB 2 — DATA TABLE
        # ══════════════════════════════════════════════════════════════════
        with ui.tab_panel("data"):
            with ui.column().classes("w-full gap-4"):
                with ui.column().classes("w-full gap-2 px-4"):
                    ui.label("Irradiation Event Stream").classes("text-2xl font-bold tracking-tight")
                    ui.label().bind_text_from(
                        state, "import_provenance",
                        backward=lambda v: (
                            f"Source: {state.file_name}  ·  Schema: {v.schema_name}"
                            if v is not None else f"Source: {state.file_name}"
                        ),
                    ).classes("text-caption text-grey-5").bind_visibility_from(state, "file_name", backward=bool)
                    
                    with ui.row().classes("w-full items-center gap-3 q-mb-sm"):
                        ui.label("View:").classes("text-sm opacity-60 self-center")
                        view_toggle = ui.toggle(
                            {"norm": "NORMALIZED", "raw": "RAW (UN-NORMALIZED)"},
                            value="norm"
                        ).bind_value_to(state, "view_raw", forward=lambda v: v == "raw").classes("modern-toggle")
                    
                    with ui.row().classes("w-full items-center gap-3"):
                        ui.button("EXPORT CSV", icon="description", on_click=lambda: _local_export("csv")).classes("modern-btn h-10 icon-outlined")
                        ui.button("EXPORT XLSX", icon="table_view", on_click=lambda: _local_export("xlsx")).classes("modern-btn h-10 icon-outlined")
                        ui.button("EXPORT TXT", icon="text_snippet", on_click=lambda: _local_export("txt")).classes("modern-btn h-10 icon-outlined")

                def _local_export(fmt: str):
                    df = state.rdsr_raw_df if state.view_raw else state.rdsr_df
                    if df is None:
                        ui.notify("No data to export", type="warning")
                        return
                    
                    prefix = "raw_" if state.view_raw else "normalized_"
                    default_name = f"{prefix}events_{state.file_name or 'data'}.{fmt}"
                    save_path = _get_save_path(default_name, fmt)
                    
                    # Prepare normalization metadata
                    meta_df = pd.DataFrame([{
                        "Manufacturer": state.manufacturer,
                        "Model": state.model,
                        "Normalization Method": state.normalization_method,
                        "Table Offset X [cm]": state.table_offset_x,
                        "Table Offset Y [cm]": state.table_offset_y,
                        "Table Offset Z [cm]": state.table_offset_z,
                        "Export Type": "Raw" if state.view_raw else "Normalized",
                    }])

                    if save_path:
                        try:
                            p = Path(save_path)
                            if fmt == "csv":
                                df.to_csv(p, index=True)
                            elif fmt == "txt":
                                with open(p, "w") as f:
                                    f.write("=== NORMALIZATION METADATA ===\n")
                                    f.write(meta_df.to_string() + "\n\n")
                                    f.write("=== EVENT DATA ===\n")
                                    f.write(df.to_string())
                            elif fmt == "xlsx":
                                with pd.ExcelWriter(p) as writer:
                                    df.to_excel(writer, sheet_name="Event Data", index=True)
                                    meta_df.to_excel(writer, sheet_name="Normalization Info", index=False)
                            ui.notify(f"Saved to {p.name}", color="positive")
                            return
                        except Exception as e:
                            ui.notify(f"Save failed: {e}", type="negative")

                    # Fallback to browser download
                    if fmt == "csv":
                        content = df.to_csv(index=True)
                        ui.download(content.encode(), default_name)
                    elif fmt == "txt":
                        content = "=== METADATA ===\n" + meta_df.to_string() + "\n\n" + df.to_string()
                        ui.download(content.encode(), default_name)
                    elif fmt == "xlsx":
                        output = io.BytesIO()
                        with pd.ExcelWriter(output) as writer:
                            df.to_excel(writer, sheet_name="Event Data", index=True)
                            meta_df.to_excel(writer, sheet_name="Normalization Info", index=False)
                        ui.download(output.getvalue(), default_name)
                    ui.notify(f"Downloaded {fmt.upper()}", color="positive")
                
                with ui.card().classes("modern-card w-full p-0 overflow-hidden sticky-header"):
                    raw_data_table = ui.table(
                        columns=[],
                        rows=[],
                        row_key="index",
                    ).classes("w-full h-[600px]")
                    # Allow horizontal scroll and sticky header
                    raw_data_table.props('flat bordered dense virtual-scroll')

                def _refresh_raw_table():
                    df_to_show = state.rdsr_raw_df if state.view_raw else state.rdsr_df
                    if df_to_show is None:
                        raw_data_table.columns = []
                        raw_data_table.rows = []
                        return
                    
                    df = df_to_show.reset_index()
                    # create columns from df
                    cols = [{"name": c, "label": c, "field": c, "sortable": True, "align": "left"} for c in df.columns]
                    raw_data_table.columns = cols
                    raw_data_table.rows = df.to_dict("records")
                    raw_data_table.update()

                ui.timer(2.0, _refresh_raw_table)
                view_toggle.on("update:model-value", _refresh_raw_table)

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
                    fig = await run.io_bound(_make_geometry_fig, "plot_setup", 0)
                    geom_spinner.visible = False
                    if fig:
                        geom_plot.update_figure(fig)

                async def preview_event():
                    if state.rdsr_df is None:
                        ui.notify("Load data first", type="warning")
                        return
                    geom_spinner.visible = True
                    fig = await run.io_bound(_make_geometry_fig, "plot_event", int(geom_event_input.value or 0))
                    geom_spinner.visible = False
                    if fig:
                        geom_plot.update_figure(fig)

                async def preview_procedure():
                    if state.rdsr_df is None:
                        ui.notify("Load data first", type="warning")
                        return
                    geom_spinner.visible = True
                    fig = await run.io_bound(_make_geometry_fig, "plot_procedure", 0)
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
                    run_btn_drawer.on("click", lambda: do_calculate())

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

                calc_btn.disable()
                run_btn_drawer.disable()
                calc_progress.visible = True
                calc_progress.set_value(0)
                calc_status_label.set_text("Starting...")

                def progress_cb(fraction: float, label: str):
                    calc_progress.set_value(fraction)
                    calc_status_label.set_text(label)

                ok, msg = await run.io_bound(run_calculation, state, progress_cb)

                calc_progress.set_value(1.0)
                calc_btn.enable()
                run_btn_drawer.enable()

                if ok:
                    psd_label.set_text(f"PSD: {state.psd:.2f} mGy")
                    calc_status_label.set_text(f"Done — {msg}")
                    ui.notify(f"✓ {msg}", color="positive")
                    tabs.set_value("results")
                else:
                    calc_status_label.set_text("Calculation failed")
                    ui.notify(f"Error: {msg[:300]}", type="negative", timeout=10000)

        # ══════════════════════════════════════════════════════════════════
        # TAB 6 — RESULTS
        # ══════════════════════════════════════════════════════════════════
        with ui.tab_panel("results"):
            with ui.column().classes("max-w-6xl mx-auto w-full gap-6"):
                ui.label("Results").classes("text-2xl font-bold tracking-tight")

                # metric cards
                with ui.row().classes("w-full gap-6"):
                    with ui.card().classes("modern-card grow q-pa-lg text-center"):
                        ui.label("Peak Skin Dose").classes("text-caption text-grey-6")
                        psd_metric = ui.label("—").classes("text-4xl text-aurora-purple font-bold")

                    with ui.card().classes("modern-card grow q-pa-lg text-center"):
                        ui.label("Total Air Kerma").classes("text-caption text-grey-6")
                        kerma_metric = ui.label("—").classes("text-4xl text-white font-bold")

                    with ui.card().classes("modern-card grow q-pa-lg text-center"):
                        ui.label("Events").classes("text-caption text-grey-6")
                        events_metric = ui.label("—").classes("text-4xl text-aurora-teal font-bold")

            def _refresh_metrics():
                if state.calculation_done and state.psd is not None:
                    psd_metric.set_text(f"{state.psd:.2f} mGy")
                    kerma_metric.set_text(f"{state.air_kerma:.1f} mGy")
                    events_metric.set_text(str(len(state.rdsr_df) if state.rdsr_df is not None else 0))

            ui.timer(1.0, _refresh_metrics)

            with ui.row().classes("w-full gap-6"):
                # dose map plot
                with ui.card().classes("grow modern-card p-0 overflow-hidden relative"):
                    dosemap_plot = ui.plotly({}).classes("w-full").style("height:700px")
                    dosemap_spinner = ui.spinner(size="lg", color="indigo").classes("absolute-center")
                    dosemap_spinner.visible = False

                # Controls & Correction factors
                with ui.column().classes("w-80 gap-6"):
                    with ui.card().classes("modern-card w-full"):
                        ui.label("Visual settings").classes("text-subtitle2 q-mb-sm")
                        ui.select(COLORSCALES, label="Colorscale", value=state.colorscale).bind_value(state, "colorscale").on(
                            "update:model-value", lambda: _refresh_dosemap()
                        ).classes("w-full")
                        
                        ui.button("REGENERATE PLOT", on_click=lambda: _refresh_dosemap()).classes("full-width modern-btn modern-btn-teal q-mt-md")

                    ui.label("Correction factors per event").classes("text-caption text-grey-6")
                    corr_table = ui.table(
                        columns=[
                            {"name": "event", "label": "EV", "field": "event", "align": "right"},
                            {"name": "k_isq", "label": "ISQ", "field": "k_isq", "align": "right"},
                            {"name": "k_bs", "label": "BS", "field": "k_bs", "align": "right"},
                            {"name": "k_tab", "label": "TAB", "field": "k_tab", "align": "right"},
                        ],
                        rows=[],
                        row_key="event",
                    ).classes("w-full modern-card")

            def _refresh_dosemap():
                if not state.calculation_done:
                    return
                dosemap_spinner.visible = True
                fig = _make_dosemap_fig()
                dosemap_spinner.visible = False
                if fig:
                    dosemap_plot.update_figure(fig)

            ui.timer(1.5, lambda: _refresh_dosemap() if state.calculation_done and state.dosemap_fig is None else None)

            def _refresh_corr_table():
                if not state.calculation_done or state.output is None:
                    return
                out = state.output
                corrections = out.get("corrections", {})
                k_isq_list = corrections.get("inverse_square_law", [])
                k_bs_list = corrections.get("backscatter", [])
                k_tab_list = corrections.get("table", [])

                import numpy as np
                rows = []
                n = len(k_isq_list)
                for i in range(n):
                    def _mean(lst, i):
                        try:
                            if not lst or i >= len(lst):
                                return "—"
                            v = lst[i]
                            if hasattr(v, "__len__") and len(v):
                                return round(float(np.mean(v)), 3)
                            return round(float(v), 3) if v is not None else "—"
                        except Exception:
                            return "—"

                    rows.append({
                        "event": i + 1,
                        "k_isq": _mean(k_isq_list, i),
                        "k_bs": _mean(k_bs_list, i),
                        "k_tab": _mean(k_tab_list, i),
                    })
                corr_table.rows = rows
                corr_table.update()

            ui.timer(2.0, _refresh_corr_table)

        # ══════════════════════════════════════════════════════════════════
        # TAB 7 — EXPORT
        # ══════════════════════════════════════════════════════════════════
        with ui.tab_panel("export"):
            with ui.column().classes("max-w-4xl mx-auto w-full gap-6"):
                ui.label("Export Results").classes("text-2xl font-bold tracking-tight")

                ui.label(
                    "Run a calculation first (tab 4) to enable exports."
                ).classes("text-caption text-grey-6 q-mb-md").bind_visibility_from(state, "calculation_done", backward=lambda v: not v)

                with ui.grid(columns=2).classes("w-full gap-6"):
                    with ui.card().classes("modern-card"):
                        ui.label("JSON — full results dict").classes("text-subtitle2 q-mb-sm")
                        ui.label("Full results dictionary containing all data.").classes("text-xs text-grey-5 q-mb-md")
                        ui.button("Download JSON", icon="download", on_click=lambda: download_json()).classes("full-width modern-btn icon-outlined")

                    with ui.card().classes("modern-card modern-card-teal"):
                        ui.label("Interactive HTML dose map").classes("text-subtitle2 q-mb-sm")
                        ui.label("Standalone HTML file with interactive 3D map.").classes("text-xs text-grey-5 q-mb-md")
                        ui.button("Download HTML", icon="html", on_click=lambda: download_html()).classes("full-width modern-btn icon-outlined")

                    with ui.card().classes("modern-card"):
                        ui.label("PNG dose map").classes("text-subtitle2 q-mb-sm")
                        ui.label("Static capture of the current dose map view.").classes("text-xs text-grey-5 q-mb-md")
                        ui.button("Download PNG", icon="image", on_click=lambda: download_png()).classes("full-width modern-btn icon-outlined")

                def download_json():
                    if not state.calculation_done or state.output is None:
                        ui.notify("No data to export", color="warning")
                        return
                    default_name = f"psd_results_{state.file_name or 'data'}.json"
                    save_path = _get_save_path(default_name, "json")
                    if save_path:
                        with open(save_path, "w") as f:
                            json.dump(state.output, f, indent=4)
                        ui.notify(f"Saved to {Path(save_path).name}", color="positive")
                    else:
                        content = json.dumps(state.output, indent=4)
                        ui.download(content.encode(), default_name)

                async def download_html():
                    if not state.calculation_done:
                        ui.notify("No data to export", color="warning")
                        return
                    default_name = f"dose_map_{state.file_name or 'data'}.html"
                    save_path = _get_save_path(default_name, "html")
                    content = await run.io_bound(_make_dosemap_html)
                    if not content:
                        ui.notify("Failed to generate HTML", type="negative")
                        return
                    if save_path:
                        with open(save_path, "wb") as f:
                            f.write(content)
                        ui.notify(f"Saved to {Path(save_path).name}", color="positive")
                    else:
                        ui.download(content, default_name)

                async def download_png():
                    if not state.calculation_done:
                        ui.notify("No data to export", color="warning")
                        return
                    default_name = f"dose_map_{state.file_name or 'data'}.png"
                    save_path = _get_save_path(default_name, "png")
                    content = await run.io_bound(_make_dosemap_png)
                    if not content:
                        ui.notify("Failed to generate PNG (requires kaleido)", type="negative")
                        return
                    if save_path:
                        with open(save_path, "wb") as f:
                            f.write(content)
                        ui.notify(f"Saved to {Path(save_path).name}", color="positive")
                    else:
                        ui.download(content, default_name)

    # ── Restore view if data already loaded ──
    if state.rdsr_df is not None:
        dprint("GUI", "Restoring UI state from loaded data")
        file_label.set_text(state.file_name.upper())
        events_label.set_text(f"{len(state.rdsr_df)} EVENTS")
        _refresh_event_table()
        if state.active_tab:
            tabs.set_value(state.active_tab)

# ── figure-building helpers (called via run.io_bound) ─────────────────────

def _make_geometry_fig(mode: str, event_index: int):
    """Build a Plotly Figure for geometry preview. Returns fig dict or None."""
    try:
        import plotly.graph_objects as go
        from mypyskindose.helpers.calculate_rotation_matrices import calculate_rotation_matrices
        from mypyskindose.phantom_class import Phantom
        from mypyskindose.plotting.create_geometry_plot import create_geometry_plot
        from mypyskindose import constants as c

        settings = build_settings(state, mode=mode, output_format="dict")
        settings.plot.plot_event_index = event_index
        settings.plot.notebook_mode = False
        settings.plot.interactivity = True

        if state.rdsr_df is None:
            return None

        data_norm = calculate_rotation_matrices(state.rdsr_df.copy())

        table = Phantom(phantom_model=c.PHANTOM_MODEL_TABLE, phantom_dim=settings.phantom.dimension)
        pad = Phantom(phantom_model=c.PHANTOM_MODEL_PAD, phantom_dim=settings.phantom.dimension)

        captured = {}
        original_show = go.Figure.show
        def _capture_show(self, *a, **kw): captured["fig"] = self
        go.Figure.show = _capture_show
        
        try:
            create_geometry_plot(normalized_data=data_norm, table=table, pad=pad, settings=settings)
        finally:
            go.Figure.show = original_show

        fig = captured.get("fig")
        if fig:
            bg = "rgb(5,5,5)"
            txt = "#F8FAFC"
            fig.update_layout(
                paper_bgcolor=bg,
                plot_bgcolor=bg,
                font=dict(color=txt, family="Inter, sans-serif"),
                scene=dict(
                    xaxis=dict(gridcolor="#262626"),
                    yaxis=dict(gridcolor="#262626"),
                    zaxis=dict(gridcolor="#262626"),
                )
            )
            return fig.to_dict()
        return None
    except Exception:
        import traceback as tb
        print(tb.format_exc())
        return None


def _make_dosemap_fig():
    """Build the dose map Plotly figure from current state.output."""
    try:
        import numpy as np
        import plotly.graph_objects as go

        if state.output is None:
            return None

        out = state.output
        patient_data = out["patient"]["patient"]
        r = np.array([
            patient_data["patient_skin_cells"]["x"],
            patient_data["patient_skin_cells"]["y"],
            patient_data["patient_skin_cells"]["z"],
        ]).T
        ijk_data = patient_data["triangle_vertex_indices"]
        dose_map = np.zeros(len(r))
        for idx, dose in out["dose_map"]:
            dose_map[int(idx)] = dose

        hover = [
            f"<b>lat:</b> {r[i,2]:.2f} cm<br><b>lon:</b> {r[i,0]:.2f} cm<br>"
            f"<b>ver:</b> {r[i,1]:.2f} cm<br><b>dose:</b> {dose_map[i]:.2f} mGy"
            for i in range(len(r))
        ]

        cmax = float(np.max(dose_map))
        if cmax == 0:
            cmax = 1.0

        mesh = go.Mesh3d(
            x=r[:, 0], y=r[:, 1], z=r[:, 2],
            i=ijk_data["i"], j=ijk_data["j"], k=ijk_data["k"],
            intensity=dose_map,
            intensitymode="vertex",
            colorscale=state.colorscale,
            cmin=0.0,
            cmax=cmax,
            showscale=True,
            hoverinfo="text",
            text=hover,
            colorbar=dict(title=dict(text="Skin dose [mGy]", font=dict(size=12))),
        )

        bg = "rgb(5,5,5)"  # Deep Black
        txt = "#F8FAFC"

        layout = go.Layout(
            paper_bgcolor=bg,
            plot_bgcolor=bg,
            font=dict(color=txt, family="Inter, sans-serif"),
            margin=dict(l=0, r=0, b=40, t=40),
            scene=dict(
                aspectmode="data",
                xaxis=dict(title="X - LON [cm]", backgroundcolor=bg, color=txt, gridcolor="#262626"),
                yaxis=dict(title="Y - VER [cm]", backgroundcolor=bg, color=txt, gridcolor="#262626"),
                zaxis=dict(title="Z - LAT [cm]", backgroundcolor=bg, color=txt, gridcolor="#262626"),
            ),
        )
        fig = go.Figure(data=[mesh], layout=layout)
        state.dosemap_fig = fig
        return fig.to_dict()
    except Exception:
        import traceback as tb
        print(tb.format_exc())
        return None


def _make_dosemap_html() -> bytes | None:
    try:
        fig_dict = _make_dosemap_fig()
        if fig_dict is None:
            return None
        import plotly.graph_objects as go
        fig = go.Figure(fig_dict)
        return fig.to_html(full_html=True).encode()
    except Exception:
        return None


def _make_dosemap_png() -> bytes | None:
    try:
        fig_dict = _make_dosemap_fig()
        if fig_dict is None:
            return None
        import plotly.graph_objects as go
        fig = go.Figure(fig_dict)
        fig.update_layout(scene_camera=dict(eye=dict(x=-2.5, y=1.5, z=0)))
        return fig.to_image(format="png")
    except Exception:
        return None


# ── entry point ────────────────────────────────────────────────────────────

def run_gui(native: bool = False) -> None:
    """Launch the MyPySkinDose NiceGUI app."""
    dprint("GUI", f"Starting run_gui, native={native}")
    
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

    ui.run(
        title="MyPySkinDose",
        native=native,
        reload=False,
        port=8765,
        show=True,
        favicon="🩻",
        reconnect_timeout=30.0,
    )


if __name__ == "__main__":
    run_gui()
