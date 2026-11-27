"""Classification of export failures into actionable, edition-aware guidance."""

from __future__ import annotations

import sys

import pytest

from guiskindose.export import MissingExportDependencyError
from guiskindose.export import failure_guidance as fg
from guiskindose.export.failure_guidance import (
    PLOTLY_GET_CHROME_COMMAND,
    ExportFailureKind,
    classify_export_failure,
    install_hint_for,
    missing_backend,
    probe_export_readiness,
)
from guiskindose.export.png_browser import (
    BundledBrowserUnavailableError,
    PngBrowserUnavailableError,
)


def _missing(fmt: str, package: str) -> MissingExportDependencyError:
    return MissingExportDependencyError(fmt, package, install_hint_for(package))


def test_missing_dependency_maps_to_install_command() -> None:
    failure = classify_export_failure(_missing("pdf", "reportlab"))

    assert failure.kind is ExportFailureKind.MISSING_PACKAGE
    assert failure.format == "pdf"
    assert failure.import_name == "reportlab"
    assert failure.pip_name == "reportlab"
    assert failure.command == "pip install reportlab"


def test_docx_uses_pip_name_not_import_name() -> None:
    failure = classify_export_failure(_missing("docx", "docx"))

    assert failure.pip_name == "python-docx"
    assert failure.command == "pip install python-docx"


def test_frozen_missing_dependency_is_portable_repair() -> None:
    failure = classify_export_failure(_missing("pdf", "reportlab"), frozen=True)

    assert failure.kind is ExportFailureKind.PORTABLE_REPAIR
    assert failure.command is None


def test_frozen_auto_detected_when_frozen_omitted(monkeypatch: pytest.MonkeyPatch) -> None:
    """Omitting ``frozen`` must consult is_frozen_app(), never default to pip advice."""
    monkeypatch.setattr(sys, "frozen", True, raising=False)

    failure = classify_export_failure(_missing("pdf", "reportlab"))

    assert failure.kind is ExportFailureKind.PORTABLE_REPAIR
    assert failure.command is None


def test_import_error_with_missing_backend_maps_to_package(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(fg, "missing_backend", lambda fmt: "openpyxl" if fmt == "xlsx" else None)

    failure = classify_export_failure(ModuleNotFoundError("No module named 'openpyxl'"), format="xlsx")

    assert failure.kind is ExportFailureKind.MISSING_PACKAGE
    assert failure.command == "pip install openpyxl"


def test_import_error_with_present_backend_is_incomplete_install(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(fg, "missing_backend", lambda _fmt: None)

    failure = classify_export_failure(ImportError("boom"), format="xlsx", frozen=False)

    assert failure.kind is ExportFailureKind.INCOMPLETE_INSTALL
    assert failure.command is None


def test_frozen_import_error_is_portable_repair_even_with_missing_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(fg, "missing_backend", lambda _fmt: "openpyxl")

    failure = classify_export_failure(ImportError("boom"), format="xlsx", frozen=True)

    assert failure.kind is ExportFailureKind.PORTABLE_REPAIR
    assert failure.command is None


def test_missing_browser_is_actionable_outside_frozen_builds() -> None:
    failure = classify_export_failure(PngBrowserUnavailableError())

    assert failure.kind is ExportFailureKind.MISSING_BROWSER
    assert failure.format == "png"
    assert failure.command == PLOTLY_GET_CHROME_COMMAND


def test_missing_browser_in_frozen_build_has_no_command() -> None:
    failure = classify_export_failure(PngBrowserUnavailableError(), frozen=True)

    assert failure.kind is ExportFailureKind.PORTABLE_REPAIR
    assert failure.command is None


def test_bundled_browser_error_is_portable_repair() -> None:
    failure = classify_export_failure(BundledBrowserUnavailableError())

    assert failure.kind is ExportFailureKind.PORTABLE_REPAIR
    assert failure.command is None


def test_unknown_failure_stays_generic() -> None:
    failure = classify_export_failure(RuntimeError("anything"), format="html")

    assert failure.kind is ExportFailureKind.UNKNOWN


def test_install_hint_uses_package_command_and_no_stale_extra() -> None:
    hint = install_hint_for("docx")

    assert "pip install python-docx" in hint
    assert "guiskindose[export]" not in hint


def test_probe_export_readiness_matches_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(fg, "missing_backend", lambda fmt: "openpyxl" if fmt == "xlsx" else None)

    ready = probe_export_readiness("csv", frozen=False)
    missing = probe_export_readiness("xlsx", frozen=False)
    portable = probe_export_readiness("xlsx", frozen=True)

    assert ready is None
    assert missing is not None and missing.kind is ExportFailureKind.MISSING_PACKAGE
    assert portable is not None and portable.kind is ExportFailureKind.PORTABLE_REPAIR


def test_missing_backend_probes_without_importing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(fg.importlib.util, "find_spec", lambda _name: None)

    assert missing_backend("png") == "kaleido"
    assert missing_backend("xlsx") == "openpyxl"
    assert missing_backend("pdf") == "reportlab"
    assert missing_backend("docx") == "docx"
    assert missing_backend("html") is None
    assert missing_backend(None) is None
