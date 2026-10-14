"""TSV equipment-profile adapter.

TSV is the same flat table as CSV, read with a tab delimiter from a bounded byte snapshot: identical header
rules, identical grouping, identical canonical document, therefore identical profile hashes. This module is
a thin delegation so the two adapters cannot drift apart.
"""

from __future__ import annotations

import os
from pathlib import Path

from guiskindose.equipment_profiles.constants import SOURCE_KIND_TSV
from guiskindose.equipment_profiles.csv_source import parse_tabular_bytes, parse_tabular_file
from guiskindose.equipment_profiles.json_source import ParsedDocument

_TSV_DELIMITER = "\t"
_TSV_SUFFIX = ".tsv"


def parse_tsv_bytes(raw: bytes) -> ParsedDocument:
    """Parse and validate a TSV profile document from raw bytes."""
    return parse_tabular_bytes(raw, delimiter=_TSV_DELIMITER, source_kind=SOURCE_KIND_TSV, suffix=_TSV_SUFFIX)


def parse_tsv_file(path: str | os.PathLike[str]) -> ParsedDocument:
    """Read, parse, and validate a TSV profile file.

    The path never appears in an error. Reads use the same bounded single read as the CSV adapter, and every
    failure carries source kind ``tsv``.
    """
    return parse_tabular_file(
        Path(path), delimiter=_TSV_DELIMITER, source_kind=SOURCE_KIND_TSV, suffix=_TSV_SUFFIX
    )
