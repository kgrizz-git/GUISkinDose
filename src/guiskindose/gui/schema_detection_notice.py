"""Import-preview copy for auto-detected tabular schemas (no NiceGUI imports)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from guiskindose.input_adapters.registry import _AUTO_MIN_HITS

from .ui_copy import copy_text

if TYPE_CHECKING:
    from guiskindose.input_adapters.models import InputProvenance

_TABULAR_SOURCE_TYPES = frozenset({"csv", "tsv", "xlsx", "xlsm"})


def schema_detection_notice_lines(
    provenance: InputProvenance | None,
    input_source_type: str,
) -> list[str]:
    """Return caption lines beside the import-preview schema badge, or [] when hidden."""
    if input_source_type not in _TABULAR_SOURCE_TYPES:
        return []
    if provenance is None or provenance.detection_mode != "auto":
        return []
    lines = [copy_text("upload.schema_detection.caption")]
    if provenance.matched_column_count == _AUTO_MIN_HITS:
        lines.append(copy_text("upload.schema_detection.thin_match"))
    return lines
