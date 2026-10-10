"""CSV equipment-profile adapter.

Reads a bounded byte snapshot once, decodes it once, streams it through the standard-library CSV reader, and
assembles the same canonical document mapping the JSON adapter produces — so a filled CSV and the equivalent
JSON have identical profile hashes while their source hashes differ. There is no third-party dependency and
no DataFrame materialization.

Ordering rules that differ from the nested form:

- Rows may appear in any order; coordinate and transmission rows may precede their ``profile`` row, so grouping
  is two-pass and the orphan check is answered only after every row has been seen.
- Rows are grouped by ``profile_id``. A group needs at least one ``profile`` row to supply identity and
  provenance; otherwise the coordinate/transmission rows are orphans and fail.
- Repeated ``profile`` rows for one ``profile_id`` may agree; disagreement is ``conflicting_profile_metadata``.
- A repeated coordinate leaf fails even when identical, mirroring a duplicate JSON object key.
- A repeated transmission key fails through the canonical cross-profile check, even when identical.

Bounds run during row accumulation, before any profile object is built: the aggregate logical-row ceiling is
checked per row, and the profile-count ceiling is checked when a new group appears.

Every rejection carries source kind ``csv`` and an allowlisted column or ``record_type`` name plus a 0-based
row index. No raw cell text, column name, file path, or library message is ever included.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from guiskindose.equipment_profiles.canonical import source_bytes_hash
from guiskindose.equipment_profiles.constants import (
    FIELD_SIZE_MODE,
    FLAT_PROMOTION_COLUMN,
    MAX_AGGREGATE_ROWS,
    MAX_PROFILES,
    MAX_SOURCE_BYTES,
    RECORD_TYPE_COORDINATE,
    RECORD_TYPE_PROFILE,
    SCHEMA_VERSION,
    SOURCE_KIND_CSV,
    SWAP_LATERAL_LONGITUDINAL,
    TABULAR_SUFFIX_TO_KIND,
    TRANSLATION_OFFSET,
)
from guiskindose.equipment_profiles.errors import EquipmentProfileError, ProfileErrorCode
from guiskindose.equipment_profiles.json_source import ParsedDocument
from guiskindose.equipment_profiles.tabular_common import (
    ParsedRow,
    alias_map_cell,
    boolean_cell,
    coordinate_leaf_path,
    decode_tabular_bytes,
    list_cell,
    number_cell,
    optional_text,
    parse_row,
    profile_id_cell,
    required_text,
    sign_cell,
    tabular_rows,
    validate_header,
)
from guiskindose.equipment_profiles.validation import validate_document

_CSV_DELIMITER = ","


class _ProfileGroup:
    """Mutable accumulator for one ``profile_id`` group, folded into an immutable profile mapping."""

    __slots__ = ("coordinate_leaves", "first_index", "metadata", "profile_id", "seen_profile_row", "transmission")

    def __init__(self, profile_id: str, first_index: int) -> None:
        self.profile_id = profile_id
        self.first_index = first_index
        self.seen_profile_row = False
        self.metadata: dict[str, Any] = {"profile_id": profile_id}
        self.coordinate_leaves: dict[str, tuple[str, Any, str]] = {}
        self.transmission: list[dict[str, Any]] = []
        self.first_index = first_index


def _read_bounded_bytes(raw: bytes, source_kind: str) -> None:
    """Apply the byte ceiling to an already-read snapshot."""
    if len(raw) > MAX_SOURCE_BYTES:
        raise EquipmentProfileError(
            ProfileErrorCode.OVERSIZED_SOURCE, source_kind=source_kind, count=MAX_SOURCE_BYTES
        )


def _bounded_read(path: Path, source_kind: str) -> bytes:
    """Read at most ``MAX_SOURCE_BYTES + 1`` bytes in one call, then apply the ceiling."""
    try:
        with path.open("rb") as handle:
            return handle.read(MAX_SOURCE_BYTES + 1)
    except (OSError, ValueError):
        raise EquipmentProfileError(ProfileErrorCode.UNREADABLE_SOURCE, source_kind=source_kind) from None


def _identity_payload(row: ParsedRow, source_kind: str) -> dict[str, Any]:
    """Build the identity/provenance half of a profile from a ``profile`` row."""
    payload: dict[str, Any] = {
        "profile_id": profile_id_cell(row, source_kind),
        "manufacturer": required_text(row, "manufacturer", source_kind),
        "models": list_cell(row, "models", source_kind),
    }
    manufacturer_aliases = list_cell(row, "manufacturer_aliases", source_kind)
    if manufacturer_aliases:
        payload["manufacturer_aliases"] = manufacturer_aliases
    model_aliases = alias_map_cell(row, "model_aliases", source_kind)
    if model_aliases:
        payload["model_aliases"] = model_aliases
    provenance: dict[str, str] = {}
    source = optional_text(row, "source", source_kind)
    notes = optional_text(row, "notes", source_kind)
    if source is not None:
        provenance["source"] = source
    if notes is not None:
        provenance["notes"] = notes
    if provenance:
        payload["provenance"] = provenance
    if boolean_cell(row, FLAT_PROMOTION_COLUMN, source_kind):
        payload["promote_coordinate_wildcard"] = True
    return payload


def _merge_profile_metadata(group: _ProfileGroup, row: ParsedRow, source_kind: str) -> None:
    """Fold one ``profile`` row into its group, rejecting contradictory repeated metadata."""
    payload = _identity_payload(row, source_kind)
    if not group.seen_profile_row:
        group.metadata.update(payload)
        group.seen_profile_row = True
        return
    if group.metadata != payload:
        raise EquipmentProfileError(
            ProfileErrorCode.CONFLICTING_PROFILE_METADATA,
            source_kind=source_kind,
            field_path=(RECORD_TYPE_PROFILE,),
            row_index=row.index,
        )


def _apply_coordinate_row(group: _ProfileGroup, row: ParsedRow, source_kind: str) -> None:
    """Fold one ``coordinate`` row into its group's coordinate block mapping."""
    field = required_text(row, "field", source_kind)
    block, leaf = coordinate_leaf_path(source_kind, row.index, field)
    if block == "detector_side_length":
        parsed: Any = number_cell(row, "value", source_kind)
    elif block == FIELD_SIZE_MODE:
        parsed = required_text(row, "value", source_kind)
    elif block == SWAP_LATERAL_LONGITUDINAL:
        parsed = boolean_cell(row, "value", source_kind)
    elif block == TRANSLATION_OFFSET:
        parsed = number_cell(row, "value", source_kind)
    else:
        parsed = sign_cell(row, "value", source_kind)
    key = f"{block}.{leaf}" if leaf else block
    if key in group.coordinate_leaves:
        raise EquipmentProfileError(
            ProfileErrorCode.DUPLICATE_JSON_KEY,
            source_kind=source_kind,
            field_path=("field",),
            row_index=row.index,
        )
    group.coordinate_leaves[key] = (key, parsed, leaf)


def _build_coordinates(group: _ProfileGroup, source_kind: str) -> dict[str, Any] | None:
    """Nest the group's leaf entries into the canonical coordinate block mapping."""
    if not group.coordinate_leaves:
        return None
    coordinates: dict[str, Any] = {}
    for key, parsed, leaf in group.coordinate_leaves.values():
        if not leaf:
            coordinates[key] = parsed
            continue
        block, _, _name = key.partition(".")
        coordinates.setdefault(block, {})[_name] = parsed
    return coordinates


def _transmission_payload(row: ParsedRow, source_kind: str) -> dict[str, Any]:
    """Build one canonical transmission row from a ``transmission`` flat row."""
    payload: dict[str, Any] = {
        "device_model": required_text(row, "device_model", source_kind),
        "acquisition_plane": required_text(row, "acquisition_plane", source_kind),
        "kvp_kv": number_cell(row, "kvp_kv", source_kind),
        "filtration_added_mmcu": number_cell(row, "filtration_added_mmcu", source_kind),
        "filtration_added_mmal": number_cell(row, "filtration_added_mmal", source_kind),
        "k_patient_support": number_cell(row, "k_patient_support", source_kind),
        "evidence_status": required_text(row, "evidence_status", source_kind),
    }
    source = optional_text(row, "source", source_kind)
    if source is not None:
        payload["source"] = source
    row_date = optional_text(row, "date", source_kind)
    if row_date is not None:
        payload["date"] = row_date
    comment = optional_text(row, "comment", source_kind)
    if comment is not None:
        payload["comment"] = comment
    return payload


def _group_for(
    groups: dict[str, _ProfileGroup],
    order: list[str],
    row: ParsedRow,
    source_kind: str,
) -> _ProfileGroup:
    """Return the group for a row's ``profile_id``, creating it (and applying the profile ceiling) if new."""
    profile_id = profile_id_cell(row, source_kind)
    group = groups.get(profile_id)
    if group is not None:
        return group
    if len(groups) >= MAX_PROFILES:
        raise EquipmentProfileError(
            ProfileErrorCode.PROFILE_LIMIT_EXCEEDED,
            source_kind=source_kind,
            count=len(groups) + 1,
        )
    group = _ProfileGroup(profile_id, row.index)
    groups[profile_id] = group
    order.append(profile_id)
    return group


def _fold_row(group: _ProfileGroup, row: ParsedRow, source_kind: str) -> None:
    """Fold one validated flat row into its group by ``record_type``."""
    if row.record_type == RECORD_TYPE_PROFILE:
        _merge_profile_metadata(group, row, source_kind)
    elif row.record_type == RECORD_TYPE_COORDINATE:
        _apply_coordinate_row(group, row, source_kind)
    else:
        group.transmission.append(_transmission_payload(row, source_kind))


def _rows_to_document(rows: Iterator[ParsedRow], source_kind: str) -> dict[str, Any]:
    """Group flat rows into the canonical document mapping.

    Grouping is deliberately **two-pass over in-memory row records**, because a group's ``profile`` row may
    appear after its ``coordinate`` and ``transmission`` rows: the orphan check can only be answered once every
    row has been seen. The aggregate logical-row ceiling is enforced *during* that accumulation, so the amount
    of row record materialized is bounded before any profile object is built.
    """
    groups: dict[str, _ProfileGroup] = {}
    order: list[str] = []
    for logical_rows, row in enumerate(rows, start=1):
        if logical_rows > MAX_AGGREGATE_ROWS:
            raise EquipmentProfileError(
                ProfileErrorCode.ROW_LIMIT_EXCEEDED, source_kind=source_kind, count=logical_rows
            )
        _fold_row(_group_for(groups, order, row, source_kind), row, source_kind)
    profiles: list[dict[str, Any]] = []
    for profile_id in order:
        entry = _profile_entry(groups[profile_id], source_kind)
        profiles.append(entry)
    return {"schema_version": SCHEMA_VERSION, "profiles": profiles}


def _profile_entry(group: _ProfileGroup, source_kind: str) -> dict[str, Any]:
    """Build one canonical profile mapping from its folded group, rejecting an orphan group."""
    if not group.seen_profile_row:
        raise EquipmentProfileError(
            ProfileErrorCode.MISSING_REQUIRED_FIELD,
            source_kind=source_kind,
            field_path=(RECORD_TYPE_PROFILE,),
            row_index=group.first_index,
        )
    entry: dict[str, Any] = dict(group.metadata)
    coordinates = _build_coordinates(group, source_kind)
    if coordinates:
        entry["coordinates"] = coordinates
    if group.transmission:
        entry["transmission"] = group.transmission
    return entry


def _parsed_document(document: dict[str, Any], *, source_kind: str, raw: bytes, logical_rows: int) -> ParsedDocument:
    profiles = validate_document(document, source_kind=source_kind)
    return ParsedDocument(
        profiles=profiles,
        source_kind=source_kind,
        source_hash=source_bytes_hash(raw),
        logical_rows=logical_rows,
    )


def _rows(raw: bytes, *, delimiter: str, source_kind: str, header_index: int) -> Iterator[ParsedRow]:
    text = decode_tabular_bytes(raw, source_kind)
    stream = tabular_rows(text, delimiter=delimiter, source_kind=source_kind)
    try:
        header = next(stream)
    except StopIteration:
        raise EquipmentProfileError(
            ProfileErrorCode.EMPTY_SOURCE, source_kind=source_kind, field_path=("record_type",)
        ) from None
    positions = validate_header(header, source_kind)
    for source_index, row in enumerate(stream, start=header_index):
        yield parse_row(row, positions, source_kind, source_index=source_index)


def parse_tabular_bytes(raw: bytes, *, delimiter: str, source_kind: str, suffix: str) -> ParsedDocument:
    """Parse and validate a bounded tabular document from raw bytes."""
    if suffix not in TABULAR_SUFFIX_TO_KIND:
        raise EquipmentProfileError(
            ProfileErrorCode.UNSUPPORTED_SOURCE_SUFFIX, source_kind=source_kind
        )
    _read_bounded_bytes(raw, source_kind)
    rows = _rows(raw, delimiter=delimiter, source_kind=source_kind, header_index=1)
    document = _rows_to_document(rows, source_kind)
    return _parsed_document(
        document, source_kind=source_kind, raw=raw, logical_rows=_logical_rows(document)
    )


def parse_tabular_file(path: str | os.PathLike[str], *, delimiter: str, source_kind: str, suffix: str) -> ParsedDocument:
    """Read, parse, and validate a tabular profile file.

    The path never appears in an error. The file is read with one bounded read of at most
    ``MAX_SOURCE_BYTES + 1`` bytes, so an oversized source is rejected from the read length itself.
    """
    candidate = Path(path)
    if candidate.suffix.lower() != suffix:
        raise EquipmentProfileError(
            ProfileErrorCode.UNSUPPORTED_SOURCE_SUFFIX, source_kind=source_kind
        )
    raw = _bounded_read(candidate, source_kind)
    _read_bounded_bytes(raw, source_kind)
    rows = _rows(raw, delimiter=delimiter, source_kind=source_kind, header_index=1)
    document = _rows_to_document(rows, source_kind)
    return _parsed_document(
        document, source_kind=source_kind, raw=raw, logical_rows=_logical_rows(document)
    )


def _logical_rows(document: dict[str, Any]) -> int:
    """Count logical rows for the aggregate ceiling: profiles + coordinate leaves + transmission rows."""
    total = 0
    for entry in document["profiles"]:
        total += 1
        coordinates = entry.get("coordinates")
        if isinstance(coordinates, dict):
            for block in coordinates.values():
                total += len(block) if isinstance(block, dict) else 1
        total += len(entry.get("transmission", ()))
    return total


def parse_csv_bytes(raw: bytes) -> ParsedDocument:
    """Parse and validate a CSV profile document from raw bytes."""
    return parse_tabular_bytes(raw, delimiter=_CSV_DELIMITER, source_kind=SOURCE_KIND_CSV, suffix=".csv")


def parse_csv_file(path: str | os.PathLike[str]) -> ParsedDocument:
    """Read, parse, and validate a CSV profile file."""
    return parse_tabular_file(
        path, delimiter=_CSV_DELIMITER, source_kind=SOURCE_KIND_CSV, suffix=".csv"
    )
