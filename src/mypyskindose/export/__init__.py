"""Rich Report Export — audit documents (XLSX/PDF/HTML) from a dose calculation.

Public API:

* :func:`collect_export_payload` — build the writer-facing payload from a source
  bundle (:class:`ExportSource` / :class:`ExportExamSource`).
* :class:`ExportPayload` — the report structure writers consume.
* :func:`build_export_source_from_cli` — assemble an ``ExportSource`` headlessly.

Writers live under ``mypyskindose.export.writers`` and are imported lazily so the
optional ``reportlab`` dependency is only required when a PDF is produced.
"""

from __future__ import annotations

from .models import (
    RICH_EXPORT_SCHEMA_VERSION,
    ExportError,
    ExportExamSource,
    ExportPayload,
    ExportSource,
)
from .payload import collect_export_payload, resolve_calculation_result
from .cli_source import build_export_source_from_cli

__all__ = [
    "RICH_EXPORT_SCHEMA_VERSION",
    "ExportError",
    "ExportExamSource",
    "ExportPayload",
    "ExportSource",
    "collect_export_payload",
    "resolve_calculation_result",
    "build_export_source_from_cli",
]
