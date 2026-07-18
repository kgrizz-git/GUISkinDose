"""Shared I/O helpers for the GUI (refactor plan Phase 3.3).

Native save-dialog and tabular-provenance embedding, used by more than one tab
(export + data). They live below ``app.py`` in the import graph so per-tab
modules import them without a circular dependency on ``app`` (which imports the
tab modules). Pure / single-source-of-truth and unit-testable.
"""

from __future__ import annotations

import json
import logging

from mypyskindose.privacy import safe_error_event

logger = logging.getLogger(__name__)


# ── tabular provenance embedding in exports ───────────────────────────────
# Both the JSON payload and the HTML export embed the tabular import provenance
# so a saved result records exactly how its source table was read.
def _tabular_input_meta(
    file_name,
    provenance,
    swap_lat_lon,
    warnings,
    *,
    include_source_identifiers: bool = False,
) -> dict:
    """Build the tabular-input provenance dict embedded in exports.

    Downstream consumers should read the top-level ``schema_version`` on the
    export payload before parsing nested calculation fields.
    """
    result = {
        "schema": provenance.schema_name,
        "encoding": provenance.detected_encoding,
        "delimiter": provenance.detected_delimiter,
        "header_row_index": provenance.header_row_index,
        "column_map": provenance.column_map,
        "lat_lon_swapped": swap_lat_lon,
        "warnings": list(warnings),
    }
    if include_source_identifiers:
        result["source_file"] = file_name
    return result


def _inject_html_tabular_meta(html: bytes, meta: dict) -> bytes:
    """Insert the provenance as an HTML comment immediately after <head>.

    Returns *html* unchanged if no ``<head>`` tag is present. Only the first
    ``<head>`` is annotated. The JSON is base64-encoded to prevent untrusted
    headers, warnings, or filenames containing --> from terminating the comment
    or injecting markup.
    """
    import base64

    if b"<head>" not in html:
        return html
    json_bytes = json.dumps(meta, indent=2).encode("utf-8")
    encoded = base64.b64encode(json_bytes).decode("ascii")
    comment = f"<head>\n<!-- mypyskindose:tabular_input {encoded} -->"
    return html.replace(b"<head>", comment.encode(), 1)


# ── helper for file dialog ────────────────────────────────────────────────
def _is_native_mode() -> bool:
    """Return True when the GUI is running under pywebview (--native flag)."""
    try:
        from nicegui import app as _app
        return _app.native.main_window is not None
    except Exception:
        return False


async def _get_save_path(default_name: str, extension: str) -> str | None:
    """Open a native "Save As" dialog when running in --native (pywebview) mode.

    NiceGUI wraps pywebview's window in a ``WindowProxy`` whose
    ``create_file_dialog`` is a **coroutine** — it marshals the call to the GUI
    thread over an internal queue and awaits the result. It must be awaited (the
    old synchronous call returned an un-awaited coroutine, which blew up when a
    caller did ``Path(save_path)``). Returns ``None`` in browser mode so callers
    fall back to ``ui.download()``, and ``None`` when the user cancels the dialog.
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
        "pdf": ("PDF Files (*.pdf)",),
        "docx": ("Word Documents (*.docx)",),
    }
    try:
        import webview  # pyright: ignore[reportMissingImports]  # optional gui-native dep (pywebview)
        # FileDialog.SAVE (pywebview >=5); fall back to the deprecated SAVE_DIALOG
        # constant on older releases.
        save_dialog = webview.FileDialog.SAVE if hasattr(webview, "FileDialog") else webview.SAVE_DIALOG
        result = await main_window.create_file_dialog(
            int(save_dialog),
            save_filename=default_name,
            file_types=ext_filter_map.get(extension, ("All Files (*.*)",)),
        )
        # pywebview returns a tuple/list of paths, or None when cancelled.
        if not result:
            return None
        return result[0] if isinstance(result, (list, tuple)) else result
    except Exception as exc:
        safe_error_event(logger, "native_save_dialog", exc, level=logging.DEBUG)
        return None
