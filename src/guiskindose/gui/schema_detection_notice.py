"""Import-preview copy for auto-detected tabular schemas (no NiceGUI imports)."""

from __future__ import annotations

from guiskindose.input_adapters.registry import _AUTO_MIN_HITS

from .ui_copy import copy_text

_TABULAR_SOURCE_TYPES = frozenset({"csv", "tsv", "xlsx", "xlsm"})


def schema_detection_notice_lines(
    provenance: object | None,
    input_source_type: str,
) -> list[str]:
    """Return caption lines beside the import-preview schema badge, or [] when hidden.

    A provenance object that omits ``detection_mode`` or ``matched_column_count`` is
    treated as not auto-detected, so a partial stand-in cannot crash the preview refresh.
    """
    if input_source_type not in _TABULAR_SOURCE_TYPES:
        return []
    if provenance is None or getattr(provenance, "detection_mode", None) != "auto":
        return []
    lines = [copy_text("upload.schema_detection.caption")]
    if getattr(provenance, "matched_column_count", None) == _AUTO_MIN_HITS:
        lines.append(copy_text("upload.schema_detection.thin_match"))
    return lines
