"""Report writers (XLSX/PDF/HTML/DOCX).

Each writer exposes ``render_<fmt>_bytes(payload) -> bytes`` for in-memory
downloads and ``write_<fmt>(payload, path)`` for filesystem writes. Imported
lazily by callers so optional dependencies (e.g. ``reportlab``) are only needed
when that format is produced.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..models import ExportPayload

# User-facing formats and their file extensions (DOCX is Phase 6).
FORMATS: dict[str, str] = {"xlsx": "xlsx", "pdf": "pdf", "html": "html"}


def render_bytes(payload: "ExportPayload", fmt: str) -> bytes:
    """Render a payload to bytes for the given format (lazy writer import)."""
    fmt = fmt.lower()
    if fmt == "xlsx":
        from .xlsx import render_xlsx_bytes

        return render_xlsx_bytes(payload)
    if fmt == "pdf":
        from .pdf import render_pdf_bytes

        return render_pdf_bytes(payload)
    if fmt == "html":
        from .html import render_html_bytes

        return render_html_bytes(payload)
    raise ValueError(f"Unsupported export format: {fmt!r}. Choose one of {sorted(FORMATS)}.")


def write_report(payload: "ExportPayload", path: Path, fmt: str) -> None:
    """Write a payload to ``path`` for the given format."""
    Path(path).write_bytes(render_bytes(payload, fmt))
