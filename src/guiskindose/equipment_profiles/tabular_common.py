"""Shared, stdlib-only primitives for the flat tabular sources.

Everything here is source-kind agnostic: the CSV and TSV adapters differ only in the delimiter and the
accepted file suffix. This module owns the parts that must be identical for both, and identical to the
contract in ``dev-docs/EQUIPMENT_PROFILE_SCHEMA.md``:

- bounded decode of raw bytes (strict UTF-8, optional BOM, no unpaired surrogates);
- strict header validation (exactly the required columns, no duplicate or unknown columns, reordering allowed);
- strict row width and non-applicable-cell checks;
- scalar cell parsing that never accepts NaN/Infinity, booleans as numbers, or non-lexical booleans;
- list and alias-map cell parsing, where ``{`` means a quoted JSON object and ``|`` means a list.

Every failure is a value-free :class:`EquipmentProfileError` carrying the caller's source kind, an allowlisted
column or ``record_type`` name, and a 0-based row index. No raw cell text, unknown column name, file path, or
library error message reaches an error.
"""

from __future__ import annotations

import csv
import io
import json
import math
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from guiskindose.equipment_profiles.constants import (
    AXIS_FIELDS,
    FIELD_SIZE_MODE,
    FLAT_BLANK_DISALLOWED_COLUMNS,
    FLAT_BOOLEAN_FALSE,
    FLAT_BOOLEAN_TOKENS,
    FLAT_BOOLEAN_TRUE,
    FLAT_COLUMNS,
    FLAT_COLUMNS_BY_RECORD_TYPE,
    FLAT_FIELD_PATH_VOCABULARY,
    FLAT_LIST_SEPARATOR,
    FLAT_PROMOTION_COLUMN,
    FLAT_REQUIRED_COLUMNS_BY_RECORD_TYPE,
    MAX_LONG_TEXT,
    MAX_SHORT_TEXT,
    ROTATION_DIRECTION,
    ROTATION_LEAVES,
    SIGN_VALUES,
    SWAP_LATERAL_LONGITUDINAL,
    TRANSLATION_DIRECTION,
    TRANSLATION_OFFSET,
)
from guiskindose.equipment_profiles.errors import EquipmentProfileError, ProfileErrorCode

_UTF8_BOM = "\ufeff"

#: Columns that carry list cells.
_LIST_COLUMNS = frozenset({"models", "manufacturer_aliases", "model_aliases"})

#: Columns whose maximum length is the bounded-free-text limit.
_LONG_TEXT_COLUMNS = frozenset({"notes", "comment", "source"})

_SURROGATE_RANGES = ((0xD800, 0xDFFF),)


def decode_tabular_bytes(raw: bytes, source_kind: str) -> str:
    """Decode raw tabular bytes: strict UTF-8, optional BOM, no unpaired surrogates.

    Decoding happens exactly once, on the same byte snapshot the source hash is taken from.
    """
    if not raw:
        raise EquipmentProfileError(ProfileErrorCode.EMPTY_SOURCE, source_kind=source_kind)
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise EquipmentProfileError(
            ProfileErrorCode.UNSUPPORTED_SOURCE_ENCODING, source_kind=source_kind
        ) from None
    if text.startswith(_UTF8_BOM):
        text = text[1:]
    for index, char in enumerate(text):
        code = ord(char)
        if any(low <= code <= high for low, high in _SURROGATE_RANGES):
            raise EquipmentProfileError(
                ProfileErrorCode.UNSUPPORTED_SOURCE_ENCODING,
                source_kind=source_kind,
                row_index=index,
            )
    return text


def validate_header(header: Sequence[str], source_kind: str) -> dict[str, int]:
    """Validate a strict tabular header and return the ``column -> position`` mapping.

    The header must hold exactly the 19 required columns, optionally plus
    ``promote_coordinate_wildcard``. Column order is free. Unknown and duplicate column names are rejected
    *without echoing either name*; the reported count is the column's index so the position is still
    actionable.
    """
    if not header:
        raise EquipmentProfileError(
            ProfileErrorCode.MISSING_REQUIRED_FIELD, source_kind=source_kind, field_path=("record_type",)
        )
    positions: dict[str, int] = {}
    for index, name in enumerate(header):
        if name not in FLAT_FIELD_PATH_VOCABULARY:
            raise EquipmentProfileError(
                ProfileErrorCode.UNKNOWN_FIELD, source_kind=source_kind, count=index
            )
        if name in positions:
            raise EquipmentProfileError(
                ProfileErrorCode.DUPLICATE_JSON_KEY, source_kind=source_kind, count=index
            )
        positions[name] = index
    required: set[str] = set(FLAT_COLUMNS)
    present: set[str] = set(positions)
    missing = len(required - present)
    if missing:
        raise EquipmentProfileError(
            ProfileErrorCode.MISSING_REQUIRED_FIELD, source_kind=source_kind, count=missing
        )
    if present - required - {FLAT_PROMOTION_COLUMN}:
        raise EquipmentProfileError(ProfileErrorCode.UNKNOWN_FIELD, source_kind=source_kind)
    if len(header) != len(positions):
        raise EquipmentProfileError(
            ProfileErrorCode.MALFORMED_TABULAR, source_kind=source_kind, count=len(header)
        )
    return positions


def tabular_rows(text: str, *, delimiter: str, source_kind: str) -> Iterator[list[str]]:
    """Stream rows from the decoded text using the standard-library CSV reader.

    The text is decoded once and read once; the reader is driven lazily so a hostile source cannot force a
    second full parse. Any malformed quoting is reported as ``malformed_tabular`` with the row index only.
    """
    reader = csv.reader(io.StringIO(text), delimiter=delimiter, strict=True)
    index = 0
    while True:
        try:
            row = next(reader)
        except StopIteration:
            return
        except csv.Error:
            raise EquipmentProfileError(
                ProfileErrorCode.MALFORMED_TABULAR, source_kind=source_kind, row_index=index
            ) from None
        yield row
        index += 1


def cell(row: Sequence[str], positions: Mapping[str, int], name: str) -> str:
    """Return one cell, or the empty string when the column is absent from this header."""
    position = positions.get(name)
    if position is None or position >= len(row):
        return ""
    return row[position]


@dataclass(frozen=True, slots=True)
class ParsedRow:
    """One validated flat row, checked for width, record type, and non-applicable cells."""

    record_type: str
    profile_id: str
    values: dict[str, str]
    index: int


def parse_row(
    row: Sequence[str],
    positions: Mapping[str, int],
    source_kind: str,
    *,
    source_index: int,
) -> ParsedRow:
    """Validate one flat row's width, record type, required cells, and non-applicable cells."""
    if len(row) != len(positions):
        raise EquipmentProfileError(
            ProfileErrorCode.MALFORMED_TABULAR, source_kind=source_kind, row_index=source_index
        )
    record_type = cell(row, positions, "record_type")
    if record_type not in FLAT_COLUMNS_BY_RECORD_TYPE:
        raise EquipmentProfileError(
            ProfileErrorCode.UNKNOWN_FIELD, source_kind=source_kind, row_index=source_index
        )
    applicable = FLAT_COLUMNS_BY_RECORD_TYPE[record_type]
    values = {name: cell(row, positions, name) for name in positions}
    for name, value in values.items():
        if value and name not in applicable:
            raise EquipmentProfileError(
                ProfileErrorCode.UNKNOWN_FIELD,
                source_kind=source_kind,
                field_path=(name,),
                row_index=source_index,
            )
        if not value and name in FLAT_BLANK_DISALLOWED_COLUMNS and name in applicable:
            raise EquipmentProfileError(
                ProfileErrorCode.BLANK_DISALLOWED_CELL,
                source_kind=source_kind,
                field_path=(name,),
                row_index=source_index,
            )
    for name in sorted(FLAT_REQUIRED_COLUMNS_BY_RECORD_TYPE[record_type]):
        if name in positions and not values.get(name, ""):
            raise EquipmentProfileError(
                ProfileErrorCode.BLANK_REQUIRED_CELL,
                source_kind=source_kind,
                field_path=(name,),
                row_index=source_index,
            )
    return ParsedRow(
        record_type=record_type,
        profile_id=values.get("profile_id", ""),
        values=values,
        index=source_index,
    )


def required_text(row: ParsedRow, name: str, source_kind: str) -> str:
    """Return a required, bounded, non-blank text cell."""
    value = row.values.get(name, "")
    if not value:
        raise EquipmentProfileError(
            ProfileErrorCode.BLANK_REQUIRED_CELL,
            source_kind=source_kind,
            field_path=(name,),
            row_index=row.index,
        )
    return bounded_text(value, name, source_kind, row.index)


def optional_text(row: ParsedRow, name: str, source_kind: str) -> str | None:
    """Return an optional text cell, or ``None`` when blank. Null-like strings stay literal text."""
    value = row.values.get(name, "")
    if not value:
        return None
    return bounded_text(value, name, source_kind, row.index)


def bounded_text(value: str, name: str, source_kind: str, row_index: int) -> str:
    """Bound a text cell by its column's limit, rejecting unpaired surrogates."""
    for char in value:
        code = ord(char)
        if any(low <= code <= high for low, high in _SURROGATE_RANGES):
            raise EquipmentProfileError(
                ProfileErrorCode.UNSUPPORTED_SOURCE_ENCODING,
                source_kind=source_kind,
                field_path=(name,),
                row_index=row_index,
            )
    limit = MAX_LONG_TEXT if name in _LONG_TEXT_COLUMNS else MAX_SHORT_TEXT
    if len(value) > limit:
        raise EquipmentProfileError(
            ProfileErrorCode.VALUE_OUT_OF_RANGE,
            source_kind=source_kind,
            field_path=(name,),
            row_index=row_index,
            count=limit,
        )
    return value


def number_cell(row: ParsedRow, name: str, source_kind: str) -> float:
    """Parse a numeric cell. Rejects NaN/Infinity spellings, booleans, and non-numeric text."""
    raw = row.values.get(name, "")
    if not raw:
        raise EquipmentProfileError(
            ProfileErrorCode.BLANK_REQUIRED_CELL,
            source_kind=source_kind,
            field_path=(name,),
            row_index=row.index,
        )
    stripped = raw.strip()
    lowered = stripped.lower()
    if lowered in {"nan", "inf", "+inf", "-inf", "infinity", "+infinity", "-infinity"}:
        raise EquipmentProfileError(
            ProfileErrorCode.INVALID_NUMBER,
            source_kind=source_kind,
            field_path=(name,),
            row_index=row.index,
        )
    if "_" in stripped or stripped.lower() in FLAT_BOOLEAN_TOKENS:
        raise EquipmentProfileError(
            ProfileErrorCode.INVALID_NUMBER,
            source_kind=source_kind,
            field_path=(name,),
            row_index=row.index,
        )
    try:
        value = float(stripped)
    except (ValueError, OverflowError):
        raise EquipmentProfileError(
            ProfileErrorCode.INVALID_NUMBER,
            source_kind=source_kind,
            field_path=(name,),
            row_index=row.index,
        ) from None
    if not math.isfinite(value):
        raise EquipmentProfileError(
            ProfileErrorCode.INVALID_NUMBER,
            source_kind=source_kind,
            field_path=(name,),
            row_index=row.index,
        )
    return 0.0 if value == 0.0 else value


def boolean_cell(row: ParsedRow, name: str, source_kind: str) -> bool:
    """Parse a boolean cell. Only the exact lexical forms ``true`` and ``false`` are accepted."""
    raw = row.values.get(name, "")
    if not raw:
        return False
    if raw == FLAT_BOOLEAN_TRUE:
        return True
    if raw == FLAT_BOOLEAN_FALSE:
        return False
    raise EquipmentProfileError(
        ProfileErrorCode.INVALID_TYPE,
        source_kind=source_kind,
        field_path=(name,),
        row_index=row.index,
    )


def sign_cell(row: ParsedRow, name: str, source_kind: str) -> str:
    """Parse a sign cell, which must be one of the accepted literals."""
    raw = row.values.get(name, "")
    if raw not in SIGN_VALUES:
        raise EquipmentProfileError(
            ProfileErrorCode.INVALID_ENUM,
            source_kind=source_kind,
            field_path=(name,),
            row_index=row.index,
        )
    return raw


def list_cell(row: ParsedRow, name: str, source_kind: str) -> list[str]:
    """Split a flat list cell on ``|``. Only list cells use the separator."""
    raw = row.values.get(name, "")
    if not raw:
        return []
    return raw.split(FLAT_LIST_SEPARATOR)


def alias_map_cell(row: ParsedRow, name: str, source_kind: str) -> Any:
    """Parse a ``model_aliases`` cell into either a list (``|`` form) or a JSON object (map form).

    A cell whose first non-space character is ``{`` must be a properly quoted JSON object; anything else is
    the ``|``-separated shorthand list. Pipes never appear inside a JSON map cell.
    """
    raw = row.values.get(name, "")
    if not raw:
        return []
    if raw.lstrip().startswith("{"):
        try:
            return json.loads(raw, object_pairs_hook=_rejecting_pairs_hook)
        except _DuplicateKeyError:
            raise EquipmentProfileError(
                ProfileErrorCode.DUPLICATE_JSON_KEY,
                source_kind=source_kind,
                field_path=(name,),
                row_index=row.index,
            ) from None
        except (ValueError, TypeError, RecursionError):
            raise EquipmentProfileError(
                ProfileErrorCode.MALFORMED_TABULAR,
                source_kind=source_kind,
                field_path=(name,),
                row_index=row.index,
            ) from None
    return raw.split(FLAT_LIST_SEPARATOR)


class _DuplicateKeyError(Exception):
    """Private signal raised by the ``object_pairs_hook``; never escapes this module."""

    __slots__ = ()


def _rejecting_pairs_hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKeyError
        result[key] = value
    return result


def coordinate_leaf_path(source_kind: str, row_index: int, field: str) -> tuple[str, str]:
    """Split a dotted coordinate leaf path into ``(block_name, leaf_name)``.

    Rejects unknown blocks and leaves without echoing the offending cell text.
    """
    if "." not in field:
        if field in {SWAP_LATERAL_LONGITUDINAL, FIELD_SIZE_MODE, "detector_side_length"}:
            return field, ""
        raise EquipmentProfileError(
            ProfileErrorCode.UNKNOWN_FIELD,
            source_kind=source_kind,
            field_path=("field",),
            row_index=row_index,
        )
    block, _, leaf = field.partition(".")
    if block == TRANSLATION_OFFSET and leaf in AXIS_FIELDS:
        return block, leaf
    if block == TRANSLATION_DIRECTION and leaf in AXIS_FIELDS:
        return block, leaf
    if block == ROTATION_DIRECTION and leaf in dict(ROTATION_LEAVES).values():
        return block, leaf
    raise EquipmentProfileError(
        ProfileErrorCode.UNKNOWN_FIELD,
        source_kind=source_kind,
        field_path=("field",),
        row_index=row_index,
    )


def sign_leaf(source_kind: str, row_index: int, field: str) -> bool:
    """True when a dotted leaf path names a sign leaf (a direction or rotation leaf)."""
    block, leaf = coordinate_leaf_path(source_kind, row_index, field)
    return block in {TRANSLATION_DIRECTION, ROTATION_DIRECTION} and leaf != ""


def numeric_leaf(source_kind: str, row_index: int, field: str) -> bool:
    """True when a dotted leaf path names a numeric leaf."""
    block, _leaf = coordinate_leaf_path(source_kind, row_index, field)
    return block == TRANSLATION_OFFSET


def scalar_leaf(source_kind: str, row_index: int, field: str) -> str:
    """Return the block-level scalar leaf name for a non-dotted field, validating it."""
    block, leaf = coordinate_leaf_path(source_kind, row_index, field)
    if leaf:
        raise EquipmentProfileError(
            ProfileErrorCode.UNKNOWN_FIELD,
            source_kind=source_kind,
            field_path=("field",),
            row_index=row_index,
        )
    return block


def profile_id_cell(row: ParsedRow, source_kind: str) -> str:
    """Return a bounded ``profile_id`` cell."""
    return required_text(row, "profile_id", source_kind)
