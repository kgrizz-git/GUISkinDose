"""Shared I/O helpers for the GUI (refactor plan Phase 3.3).

Native save-dialog and tabular-provenance embedding, used by more than one tab
(export + data). They live below ``app.py`` in the import graph so per-tab
modules import them without a circular dependency on ``app`` (which imports the
tab modules). Pure / single-source-of-truth and unit-testable.
"""

from __future__ import annotations

import json
from typing import cast

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
def _is_native_mode() -> bool:
    """Return True when the GUI is running under pywebview (--native flag)."""
    try:
        from nicegui import app as _app
        return _app.native.main_window is not None
    except Exception:
        return False


def _get_save_path(default_name: str, extension: str) -> str | None:
    """Open a native Save As dialog when running in --native (pywebview) mode.

    Uses the pywebview ``create_file_dialog`` API, which is safe to call from
    background threads (pywebview dispatches it to the main thread internally).
    Returns ``None`` in browser mode so callers fall back to ``ui.download()``.
    """
    try:
        from nicegui import app as _app
        main_window = _app.native.main_window
        if main_window is None:
            # Browser mode: let the browser handle the save dialog via ui.download().
            return None
    except Exception:
        return None

    # Native mode: use pywebview's built-in save dialog.
    ext_filter_map = {
        "csv": ("CSV Files (*.csv)",),
        "xlsx": ("Excel Files (*.xlsx)",),
        "txt": ("Text Files (*.txt)",),
        "json": ("JSON Files (*.json)",),
        "html": ("HTML Files (*.html)",),
        "png": ("PNG Images (*.png)",),
    }
    try:
        import webview
        # Stubs type SAVE_DIALOG as module_property and create_file_dialog as a
        # coroutine; pywebview's actual runtime API is synchronous — cast to match.
        result = cast(
            "tuple[str, ...] | None",
            main_window.create_file_dialog(
                cast(int, webview.SAVE_DIALOG),
                save_filename=default_name,
                file_types=ext_filter_map.get(extension, ("All Files (*.*)",)),
            ),
        )
        # pywebview returns a string path for SAVE_DIALOG, or None when cancelled.
        if not result:
            return None
        return result[0] if isinstance(result, (list, tuple)) else result
    except Exception as e:
        dprint("GUI", f"pywebview save dialog failed ({e}); falling back to download.")
        return None
