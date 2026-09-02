"""Report writers (XLSX/PDF/HTML/DOCX).

Each writer exposes ``render_<fmt>_bytes(payload) -> bytes`` for in-memory
downloads and ``write_<fmt>(payload, path)`` for filesystem writes. Imported
lazily by callers so optional dependencies (e.g. ``reportlab``) are only needed
when that format is produced.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from guiskindose.safe_output import atomic_write_private

if TYPE_CHECKING:
    from ..models import ExportPayload

# User-facing formats and their file extensions.
FORMATS: dict[str, str] = {"xlsx": "xlsx", "pdf": "pdf", "html": "html", "docx": "docx"}

# Optional third-party package backing each format (None = core dependency).
# Used to turn a bare ``ModuleNotFoundError`` into an actionable message.
_FORMAT_PACKAGE: dict[str, str | None] = {
    "xlsx": "openpyxl",
    "pdf": "reportlab",
    "html": None,
    "docx": "docx",
}
# Install name (may differ from import name, e.g. ``docx`` → ``python-docx``).
_PACKAGE_INSTALL_NAME: dict[str, str] = {"docx": "python-docx"}


def _install_hint(package: str) -> str:
    """A copy-pasteable instruction for installing a missing export package."""
    install_name = _PACKAGE_INSTALL_NAME.get(package, package)
    return (
        f"Install it with 'pip install {install_name}', or reinstall the app with the "
        f"export extras: 'pip install guiskindose[export]'."
    )


def render_bytes(payload: ExportPayload, fmt: str) -> bytes:
    """Render a payload to bytes for the given format (lazy writer import).

    Raises :class:`~guiskindose.export.models.MissingExportDependencyError` with
    install instructions when the format's optional package is not installed.
    """
    fmt = fmt.lower()
    if fmt not in FORMATS:
        raise ValueError(f"Unsupported export format: {fmt!r}. Choose one of {sorted(FORMATS)}.")
    try:
        if fmt == "xlsx":
            from .xlsx import render_xlsx_bytes

            return render_xlsx_bytes(payload)
        if fmt == "pdf":
            from .pdf import render_pdf_bytes

            return render_pdf_bytes(payload)
        if fmt == "html":
            from .html import render_html_bytes

            return render_html_bytes(payload)
        # fmt == "docx"
        from .docx import render_docx_bytes

        return render_docx_bytes(payload)
    except ModuleNotFoundError as exc:
        package = _FORMAT_PACKAGE.get(fmt)
        # Only translate a genuinely-missing export backend; re-raise anything else.
        if package is not None and exc.name in {package, package.split(".")[0]}:
            from ..models import MissingExportDependencyError

            raise MissingExportDependencyError(fmt, package, _install_hint(package)) from exc
        raise


def write_report(
    payload: ExportPayload,
    path: Path,
    fmt: str,
    *,
    force: bool = False,
    allow_ignored_checkout: bool = False,
) -> None:
    """Write a payload through the atomic, Git-aware export boundary."""
    atomic_write_private(
        path,
        render_bytes(payload, fmt),
        force=force,
        allow_ignored_checkout=allow_ignored_checkout,
    )
