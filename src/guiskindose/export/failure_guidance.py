"""Classify export failures into actionable, edition-aware guidance.

The GUI renders these records as catalog copy (``dev-docs/ui_copy.json``); the CLI
prints :func:`install_hint_for` text. Nothing here reads or logs exception text:
the decision is based on exception type, the requested format, and read-only
environment probes. Package, format, and command values are code-owned names.
"""

from __future__ import annotations

import importlib.util
from dataclasses import dataclass
from enum import StrEnum

from guiskindose.edition import is_frozen_app

from .models import MissingExportDependencyError

# Import name of the optional backend for each export format (None = core-only).
# ``png`` uses Kaleido plus an installed Chrome/Chromium.
FORMAT_BACKENDS: dict[str, tuple[str, ...]] = {
    "png": ("kaleido",),
    "xlsx": ("openpyxl",),
    "pdf": ("reportlab",),
    "docx": ("docx",),
    "html": (),
}

# Install name when it differs from the import name.
PIP_INSTALL_NAMES: dict[str, str] = {"docx": "python-docx"}

# Provided by choreographer (installed with kaleido 1.x). Downloads Chrome for Testing.
PLOTLY_GET_CHROME_COMMAND = "plotly_get_chrome -y"

_PNG_BROWSER_ERROR = "PngBrowserUnavailableError"
_BUNDLED_BROWSER_ERROR = "BundledBrowserUnavailableError"


class ExportFailureKind(StrEnum):
    """How an export failed and what the user can do about it."""

    MISSING_PACKAGE = "missing_package"
    MISSING_BROWSER = "missing_browser"
    INCOMPLETE_INSTALL = "incomplete_install"
    PORTABLE_REPAIR = "portable_repair"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ExportFailure:
    """A classified failure. ``command`` is always a copyable, code-owned string."""

    kind: ExportFailureKind
    format: str | None = None
    import_name: str | None = None
    pip_name: str | None = None
    command: str | None = None


def pip_name(import_name: str) -> str:
    """Return the pip distribution name for an import name (``docx`` → ``python-docx``)."""
    return PIP_INSTALL_NAMES.get(import_name, import_name)


def package_install_command(import_name: str) -> str:
    """A copy-pasteable command that restores one missing package."""
    return f"pip install {pip_name(import_name)}"


def install_hint_for(import_name: str) -> str:
    """A ready-to-show sentence for CLI users.

    Built only from the code-owned package name; never includes exception text or
    paths. Frozen builds never see this through the GUI, which uses the portable
    prompt instead.
    """
    return (
        f"Install it with '{package_install_command(import_name)}'. "
        "If this copy is the portable app, re-extract the download instead of using pip."
    )


def _class_named(exc: BaseException, name: str) -> bool:
    """True when any exception class in the MRO has *name*.

    Matched by name to avoid importing the PNG/Kaleido boundary from here (that
    module imports this one for install hints).
    """
    return any(cls.__name__ == name for cls in type(exc).__mro__)


def _backend_missing(module: str) -> bool:
    """Whether *module* is absent, without importing it."""
    try:
        return importlib.util.find_spec(module) is None
    except (ImportError, ValueError):
        return True


def missing_backend(format: str | None) -> str | None:
    """Return the missing backend import name for *format*, or ``None``."""
    for module in FORMAT_BACKENDS.get((format or "").lower(), ()):
        if _backend_missing(module):
            return module
    return None


def _missing_package(format: str | None, import_name: str) -> ExportFailure:
    return ExportFailure(
        kind=ExportFailureKind.MISSING_PACKAGE,
        format=format,
        import_name=import_name,
        pip_name=pip_name(import_name),
        command=package_install_command(import_name),
    )


def probe_export_readiness(format: str | None, *, frozen: bool | None = None) -> ExportFailure | None:
    """Return guidance when a known backend for *format* is absent, else ``None``.

    Lets a caller report a missing backend before prompting for a save path.
    """
    is_frozen = is_frozen_app() if frozen is None else frozen
    backend = missing_backend(format)
    if backend is None:
        return None
    if is_frozen:
        return ExportFailure(kind=ExportFailureKind.PORTABLE_REPAIR, format=format)
    return _missing_package(format, backend)


def _import_failure(format: str | None, *, frozen: bool) -> ExportFailure:
    if frozen:
        return ExportFailure(kind=ExportFailureKind.PORTABLE_REPAIR, format=format)
    backend = missing_backend(format)
    if backend is not None:
        return _missing_package(format, backend)
    return ExportFailure(kind=ExportFailureKind.INCOMPLETE_INSTALL, format=format)


def classify_export_failure(
    exc: BaseException,
    *,
    format: str | None = None,
    frozen: bool | None = None,
) -> ExportFailure:
    """Map an export exception to guidance.

    ``frozen=None`` auto-detects with :func:`guiskindose.edition.is_frozen_app`; a
    frozen build never receives a pip command.
    """
    is_frozen = is_frozen_app() if frozen is None else frozen

    if isinstance(exc, MissingExportDependencyError):
        fmt = exc.format or format
        if is_frozen:
            return ExportFailure(kind=ExportFailureKind.PORTABLE_REPAIR, format=fmt)
        return _missing_package(fmt, exc.package)

    if isinstance(exc, ImportError):
        return _import_failure(format, frozen=is_frozen)

    if _class_named(exc, _PNG_BROWSER_ERROR):
        if is_frozen:
            return ExportFailure(kind=ExportFailureKind.PORTABLE_REPAIR, format=format or "png")
        return ExportFailure(
            kind=ExportFailureKind.MISSING_BROWSER,
            format=format or "png",
            command=PLOTLY_GET_CHROME_COMMAND,
        )

    if _class_named(exc, _BUNDLED_BROWSER_ERROR):
        return ExportFailure(kind=ExportFailureKind.PORTABLE_REPAIR, format=format or "png")

    return ExportFailure(kind=ExportFailureKind.UNKNOWN, format=format)
