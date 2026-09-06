"""Dataclasses for tabular input provenance and adapter results."""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd


@dataclass
class InputProvenance:
    """Typed audit trail for a tabular input load."""

    source_type: str               # "csv" | "tsv" | "xlsx"
    schema_name: str               # "normalized" | "generic_rdsr_like" | ...
    original_filename: str
    header_row_index: int
    detected_encoding: str
    detected_delimiter: str | None  # None for xlsx
    sheet_name: str | int | None    # None for non-Excel
    column_map: dict[str, str]      # source col → normalized var
    unit_conversions: dict[str, str]  # normalized var → "source_unit → target_unit"
    warnings: list[str] = field(default_factory=list)


@dataclass
class InputAdapterResult:
    """Normalized tabular RDSR result together with provenance and warnings."""
    normalized_data: pd.DataFrame
    raw_data: pd.DataFrame | None
    provenance: InputProvenance
    warnings: list[str] = field(default_factory=list)
    study_id: str | None = field(default=None)


@dataclass
class ParsedEventTable:
    """Parsed tabular event data together with provenance metadata."""
    parsed_data: pd.DataFrame
    provenance: InputProvenance
