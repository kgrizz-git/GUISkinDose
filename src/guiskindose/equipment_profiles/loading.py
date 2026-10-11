"""Load-level assembly for equipment-profile documents.

This module enforces the load-level bounds (profile count and aggregate logical rows) and runs the
across-source duplicate/conflict validation, then hands back an immutable :class:`ProfileSet`. Nothing here
activates a profile: the initial capability gate is a separate, later step.

Each adapter already enforces its own ceilings, so re-checking across the union only guards the combined set.
"""

from __future__ import annotations

from collections.abc import Sequence

from guiskindose.equipment_profiles.conflicts import validate_profile_set
from guiskindose.equipment_profiles.constants import MAX_AGGREGATE_ROWS, MAX_PROFILES
from guiskindose.equipment_profiles.csv_source import parse_csv_bytes, parse_csv_file
from guiskindose.equipment_profiles.errors import EquipmentProfileError, ProfileErrorCode
from guiskindose.equipment_profiles.json_source import (
    ParsedDocument,
    parse_json_bytes,
    parse_json_file,
    parse_memory_document,
)
from guiskindose.equipment_profiles.models import Profile, ProfileSet
from guiskindose.equipment_profiles.tsv_source import parse_tsv_bytes, parse_tsv_file
from guiskindose.equipment_profiles.xlsx_source import parse_xlsx_bytes, parse_xlsx_file

__all__ = [
    "ParsedDocument",
    "Profile",
    "ProfileSet",
    "combine_documents",
    "parse_csv_bytes",
    "parse_csv_file",
    "parse_json_bytes",
    "parse_json_file",
    "parse_memory_document",
    "parse_tsv_bytes",
    "parse_tsv_file",
    "parse_xlsx_bytes",
    "parse_xlsx_file",
]


def combine_documents(documents: Sequence[ParsedDocument]) -> ProfileSet:
    """Combine parsed documents into one immutable, conflict-checked profile set.

    Raises value-free errors; input order affects only deterministic diagnostics.
    """
    profiles: list[Profile] = []
    logical_rows = 0
    source_kinds: list[str] = []
    for document in documents:
        profiles.extend(document.profiles)
        logical_rows += document.logical_rows
        if document.source_kind not in source_kinds:
            source_kinds.append(document.source_kind)
    lead = source_kinds[0] if source_kinds else "json"
    if len(profiles) > MAX_PROFILES:
        raise EquipmentProfileError(
            ProfileErrorCode.PROFILE_LIMIT_EXCEEDED, source_kind=lead, count=len(profiles)
        )
    if logical_rows > MAX_AGGREGATE_ROWS:
        raise EquipmentProfileError(
            ProfileErrorCode.ROW_LIMIT_EXCEEDED, source_kind=lead, count=logical_rows
        )
    validate_profile_set(tuple(profiles), source_kind=lead)
    return ProfileSet(profiles=tuple(profiles), logical_rows=logical_rows, source_kinds=tuple(source_kinds))
