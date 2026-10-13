"""Dataclasses for tabular input provenance and adapter results."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import pandas as pd

if TYPE_CHECKING:
    from guiskindose.equipment_profiles.capture import CapturedCoordinates
    from guiskindose.equipment_resolution import EquipmentApplicationReceipt
    from guiskindose.settings.normalization_settings import NormalizationSettings


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
    detection_mode: str | None = None
    matched_column_count: int | None = None


@dataclass
class InputAdapterResult:
    """Normalized tabular RDSR result together with provenance and warnings."""
    normalized_data: pd.DataFrame
    raw_data: pd.DataFrame | None
    provenance: InputProvenance
    warnings: list[str] = field(default_factory=list)
    study_id: str | None = field(default=None)
    equipment_receipt: EquipmentApplicationReceipt | None = field(default=None)
    # Captured-coordinate authority minted at load on the exam's final frame
    # (post-filter, post-transform). The value is frozen; loaders set it once
    # and never clear it, so geometry edited afterwards refuses loudly at
    # calculation instead of silently falling back to baseline.
    equipment_capture: CapturedCoordinates | None = field(default=None)
    # Genuine per-exam normalization snapshot retained at load (the receipt's
    # proven leaves applied to an isolated copy — never shared last-load
    # state). Feeds private baselines for capture-less entries in mixed
    # captured calculation. Excluded from reprs; never serialized.
    normalization_snapshot: NormalizationSettings | None = field(default=None, repr=False)


@dataclass
class ParsedEventTable:
    """Parsed tabular event data together with provenance metadata."""
    parsed_data: pd.DataFrame
    provenance: InputProvenance
