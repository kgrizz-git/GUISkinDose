"""Shared I/O helpers for the GUI (refactor plan Phase 3.3).

Native save-dialog and tabular-provenance embedding, used by more than one tab
(export + data). They live below ``app.py`` in the import graph so per-tab
modules import them without a circular dependency on ``app`` (which imports the
tab modules). Pure / single-source-of-truth and unit-testable.
"""

from __future__ import annotations

import json

from mypyskindose.debug import dprint


# ── tabular provenance embedding in exports ───────────────────────────────
# Both the JSON payload and the HTML export embed the tabular import provenance
# so a saved result records exactly how its source table was read.
def _tabular_input_meta(file_name, provenance, swap_lat_lon, warnings) -> dict:
    """Build the tabular-input provenance dict embedded in exports.

    Downstream consumers should read the top-level ``schema_version`` on the
    export payload before parsing nested calculation fields.
    """
    return {
        "source_file": file_name,
        "schema": provenance.schema_name,
        "encoding": provenance.detected_encoding,
        "delimiter": provenance.detected_delimiter,
        "header_row_index": provenance.header_row_index,
        "column_map": provenance.column_map,
        "lat_lon_swapped": swap_lat_lon,
        "warnings": list(warnings),
    }


def _inject_html_tabular_meta(html: bytes, meta: dict) -> bytes:
    """Insert the provenance as an HTML comment immediately after <head>.

    Returns *html* unchanged if no ``<head>`` tag is present. Only the first
    ``<head>`` is annotated.
    """
    if b"<head>" not in html:
        return html
    comment = f"<head>\n<!-- mypyskindose:tabular_input {json.dumps(meta, indent=2)} -->"
    return html.replace(b"<head>", comment.encode(), 1)


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
        # Most commonly a missing Tkinter (No module named '_tkinter'); the caller
        # falls back to a browser-style download. See README.md for how to install.
        dprint("GUI", f"Native save dialog unavailable ({e}); falling back to download.")
        return None
