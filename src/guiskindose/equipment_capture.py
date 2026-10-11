"""Application-layer capture production and emission.

This module lives outside the stdlib-only ``equipment_profiles`` core on
purpose: producing a persistent capture from live application state must
validate the current receipt against the current frame and settings first.
It calls the existing public bridge (:func:`receipt_to_mapping`, which runs
the full binding validation — session, identity, count, geometry checksum,
fresh re-resolution equality, and live-settings currency) and normalizes any
boundary failure to a closed :class:`CaptureError`. A stale receipt blessed
with a fresh checksum can never be produced here: changed geometry, identity,
counts, sessions, live fields, or forged notices all fail inside the bridge
before any digest is computed.

Emission (canonical mappings, JSON text, envelopes) lives here with the
producer because writers share the production boundary; parsing and
validation stay in the core codec so offline readers never touch application
state. Core codec modules must never import this module (or the bridge,
frame, or settings types behind it).
"""

from __future__ import annotations

import hashlib
import hmac
from collections.abc import Sequence
from typing import Any

from guiskindose.equipment_profiles.canonical import canonical_json_bytes
from guiskindose.equipment_profiles.capture import (
    CAPTURE_ENVELOPE_SCHEMA_VERSION,
    CAPTURE_MAX_CAPTURES,
    CAPTURE_MODE_COORDINATES,
    CODE_INVALID_EQUIPMENT_CAPTURE,
    GEOMETRY_ALGORITHM_V1,
    GEOMETRY_COLUMNS_V1,
    GEOMETRY_SCHEMA_VERSION,
    CapturedCoordinates,
    CaptureError,
    context_body_mapping,
    validate_constructed_context,
)
from guiskindose.equipment_profiles.capture_checks import _geometry_number
from guiskindose.equipment_profiles.capture_codec import (
    capture_from_mapping,
    normalize_capture_body,
)
from guiskindose.equipment_profiles.constants import MAX_AGGREGATE_ROWS
from guiskindose.equipment_profiles.keys import clean_identity_text
from guiskindose.equipment_resolution import (
    EquipmentApplicationReceipt,
    receipt_to_mapping,
)

__all__ = [
    "capture_from_receipt",
    "capture_to_json",
    "capture_to_mapping",
    "envelope_to_json",
    "envelope_to_mapping",
    "geometry_digest_v1",
]


def _closed() -> CaptureError:
    """Closed-vocabulary production failure (never echoes live state)."""
    return CaptureError(
        "Equipment capture cannot be produced from this receipt.",
        CODE_INVALID_EQUIPMENT_CAPTURE,
    )


def _malformed() -> CaptureError:
    """Closed-vocabulary emission failure (never echoes context content)."""
    return CaptureError(
        "Equipment capture context is invalid.",
        CODE_INVALID_EQUIPMENT_CAPTURE,
    )


def geometry_digest_v1(rows: Sequence[Any]) -> str:
    """Checksum retained numeric geometry with the portable v1 algorithm.

    ``rows`` holds ordered retained-event sequences of the 17 locked columns,
    capped at the aggregate-row bound. The declared length is checked before
    iterating, then an actual counter binds iteration even for lying lengths;
    every row's width is bound the same way. Values normalize to finite
    doubles (ints and ``-0.0`` merge portably); identifiers and frame indices
    never enter. The canonical object carries ``schema_version`` 1, the locked
    ``columns`` array, and ``rows``.
    """
    if isinstance(rows, (str, bytes, bytearray)) or not isinstance(rows, Sequence):
        raise _malformed()
    try:
        declared = len(rows)
    except TypeError:
        raise _malformed() from None
    if declared < 1 or declared > MAX_AGGREGATE_ROWS:
        raise _malformed()
    normalized: list[list[float]] = []
    for row in rows:
        if len(normalized) >= MAX_AGGREGATE_ROWS:
            raise _malformed()
        normalized.append(_geometry_row(row))
    if len(normalized) != declared:
        raise _malformed()
    payload = {
        "schema_version": GEOMETRY_SCHEMA_VERSION,
        "columns": list(GEOMETRY_COLUMNS_V1),
        "rows": normalized,
    }
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def _geometry_row(row: Any) -> list[float]:
    """Validate declared and actual width before hashing one geometry row."""
    if isinstance(row, (str, bytes, bytearray)) or not isinstance(row, Sequence):
        raise _malformed()
    width = len(row)
    if width != len(GEOMETRY_COLUMNS_V1):
        raise _malformed()
    values: list[float] = []
    for value in row:
        if len(values) >= width:
            raise _malformed()
        values.append(_geometry_number(value))
    if len(values) != width:
        raise _malformed()
    return values


def capture_to_mapping(context: CapturedCoordinates) -> dict[str, Any]:
    """Serialize a context back to its canonical capture mapping.

    Re-runs full validity first — not checksum-only — then refuses to emit
    when the recomputed checksum disagrees, so a forged in-memory copy fails
    here rather than exporting.
    """
    validate_constructed_context(context)
    body = context_body_mapping(context)
    normalized = normalize_capture_body(body)
    digest = hashlib.sha256(canonical_json_bytes(normalized)).hexdigest()
    if not hmac.compare_digest(digest, context.capture_hash):
        raise _malformed()
    return {**normalized, "capture_hash": digest}


def capture_to_json(context: CapturedCoordinates) -> str:
    """Serialize a context to deterministic canonical JSON text."""
    return canonical_json_bytes(capture_to_mapping(context)).decode("utf-8")


def envelope_to_mapping(
    captures: Sequence[CapturedCoordinates | None],
) -> dict[str, Any]:
    """Serialize per-exam contexts into a canonical envelope mapping."""
    if type(captures) not in (list, tuple):
        raise _malformed()
    if len(captures) > CAPTURE_MAX_CAPTURES:
        raise _malformed()
    entries: list[dict[str, Any] | None] = []
    for entry in captures:
        if entry is None:
            entries.append(None)
        elif type(entry) is CapturedCoordinates:
            entries.append(capture_to_mapping(entry))
        else:
            raise _malformed()
    return {
        "schema_version": CAPTURE_ENVELOPE_SCHEMA_VERSION,
        "mode": CAPTURE_MODE_COORDINATES,
        "captures": entries,
    }


def envelope_to_json(captures: Sequence[CapturedCoordinates | None]) -> str:
    """Serialize per-exam contexts to deterministic canonical JSON text."""
    return canonical_json_bytes(envelope_to_mapping(captures)).decode("utf-8")


def _frame_rows(frame: Any, event_count: int) -> list[list[Any]]:
    """Extract ordered geometry rows after declared-count checks.

    The declared length is verified against the validated count and capped
    before any column is read; the zipped rows are then verified back against
    the declared count so short/long columns fail instead of truncating.
    """
    try:
        columns = frame.columns
        missing = [name for name in GEOMETRY_COLUMNS_V1 if name not in columns]
    except (AttributeError, TypeError):
        raise _closed() from None
    if missing:
        raise _closed()
    try:
        declared = len(frame)
    except TypeError:
        raise _closed() from None
    if declared != event_count or declared < 1 or declared > MAX_AGGREGATE_ROWS:
        raise _closed()
    try:
        column_values = [_bounded_column(frame[name], declared) for name in GEOMETRY_COLUMNS_V1]
    except (AttributeError, TypeError, ValueError, KeyError):
        raise _closed() from None
    try:
        rows = [list(values) for values in zip(*column_values, strict=True)]
    except (TypeError, ValueError):
        raise _closed() from None
    if len(rows) != declared:
        raise _closed()
    return rows


def _bounded_column(column: Any, expected: int) -> list[Any]:
    """Stop column iteration at the retained count before materialization."""
    values: list[Any] = []
    for value in column:
        if len(values) >= expected:
            raise _closed()
        values.append(value)
    if len(values) != expected:
        raise _closed()
    return values


def _spelling(value: Any, *, allow_missing: bool) -> str | None:
    """Receipt spelling text: ``""`` means missing only where allowed."""
    if type(value) is not str:
        raise _closed()
    if not value:
        if allow_missing:
            return None
        raise _closed()
    return clean_identity_text(value) if allow_missing else value


def _recipe_nested(fields: Any) -> dict[str, Any]:
    """Rebuild the nested recipe object from validated mapping fields."""
    try:
        nested: dict[str, Any] = {
            "translation_offset": {},
            "translation_direction": {},
            "rotation_direction": {},
        }
        for item in fields:
            block, _, name = item["field"].partition(".")
            if block in nested:
                nested[block][name] = item["value"]
            else:
                nested[item["field"]] = item["value"]
    except (AttributeError, TypeError, KeyError):
        raise _closed() from None
    return nested


def capture_from_receipt(*, receipt: Any, frame: Any, settings: Any) -> CapturedCoordinates:
    """Produce a validated capture from a current API receipt and frame.

    The bridge re-validates the receipt against this exact frame and settings
    (binding, geometry, fresh resolution, live currency); only then are the
    frame rows digested and the capture assembled through the strict parser.
    No profile file or store is opened; bundled data may be re-resolved by the
    bridge during this production call, but nothing is persisted from it —
    the capture carries the validated recipe, not live references.
    """
    if not isinstance(receipt, EquipmentApplicationReceipt):
        raise _closed()
    if type(receipt.event_count) is not int or not 1 <= receipt.event_count <= MAX_AGGREGATE_ROWS:
        raise _closed()
    try:
        mapping = receipt_to_mapping(receipt=receipt, frame=frame, settings=settings)
    except (ValueError, TypeError, AttributeError):
        raise _closed() from None
    try:
        event_count = receipt.event_count
        input_maker = receipt.input_maker
        input_model = receipt.input_model
        matched_maker = receipt.matched_maker
        matched_model = receipt.matched_model
        match_fields = mapping["fields"]
        affected = mapping["affected_event_count"]
    except (AttributeError, TypeError, KeyError):
        raise _closed() from None
    if type(event_count) is not int or event_count < 1:
        raise _closed()
    if affected != event_count:
        raise _closed()
    digest = geometry_digest_v1(_frame_rows(frame, event_count))
    body = {
        "match": mapping,
        "effective_coordinates": _recipe_nested(match_fields),
        "input_identity": {
            "manufacturer": _spelling(input_maker, allow_missing=True),
            "model": _spelling(input_model, allow_missing=True),
        },
        "matched_identity": {
            "manufacturer": _spelling(matched_maker, allow_missing=False),
            "model": _spelling(matched_model, allow_missing=False),
        },
        "event_count": event_count,
        "geometry_hash_algorithm": GEOMETRY_ALGORITHM_V1,
        "geometry_hash": digest,
    }
    normalized = normalize_capture_body(body)
    normalized["capture_hash"] = hashlib.sha256(canonical_json_bytes(normalized)).hexdigest()
    return capture_from_mapping(normalized)
