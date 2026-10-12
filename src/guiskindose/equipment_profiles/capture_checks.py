"""Shared strict checkers and constructed-context validation for captures.

Scalar, JSON, depth, and node guards fail closed with :class:`CaptureError`
carrying stable closed-vocabulary codes; messages never echo document
values. The object validators at the bottom share every helper with mapping
parsing, so direct construction faces the same checks — including checksum
recomputation. This module imports only stdlib, constants, keys, and
canonical serialization: never profile types, so type and validation layers
stay acyclic.
"""

from __future__ import annotations

import json
import math
import re
from typing import Any

from guiskindose.equipment_profiles.constants import (
    DETECTOR_SIDE_LENGTH_MAX,
    FIELD_SIZE_MODES,
    MAX_AGGREGATE_ROWS,
    MAX_JSON_DEPTH,
    MAX_PROFILES,
    MAX_REVISION,
    MAX_SHORT_TEXT,
    MAX_SOURCE_BYTES,
    MAX_TRAVERSAL_NODES,
    OFFSET_MAX,
    OFFSET_MIN,
    PROFILE_ID_PATTERN,
    SIGN_VALUES,
    SOURCE_KINDS,
)
from guiskindose.equipment_profiles.keys import (
    normalize_manufacturer_key,
    normalize_model_key,
)
from guiskindose.equipment_profiles.resolver import LEAF_ORDER

#: Envelope versions this codec reads. Anything else fails closed.
CAPTURE_ENVELOPE_SCHEMA_VERSION = 1

#: The only capture mode this codec implements. Transmission stays rejected
#: until Phase 4 locks and implements those shapes.
CAPTURE_MODE_COORDINATES = "coordinates"

#: Versioned portable geometry checksum algorithm (contract §6). Geometry rows
#: at any boundary are additionally capped at ``CAPTURE_MAX_RECIPE_ROWS``.
GEOMETRY_ALGORITHM_V1 = "normalized-geometry-v1"

#: Schema version of the canonical geometry object the checksum covers.
GEOMETRY_SCHEMA_VERSION = 1

#: Locked column order of the geometry checksum, in retained event order.
GEOMETRY_COLUMNS_V1 = (
    "Tx",
    "Ty",
    "Tz",
    "Ap1",
    "Ap2",
    "Ap3",
    "At1",
    "At2",
    "At3",
    "kVp",
    "DSL",
    "FS_lat",
    "FS_long",
    "DSD",
    "DSI",
    "DID",
    "DSIRP",
)

#: Exact envelope keys. Anything else is malformed.
CAPTURE_ENVELOPE_KEYS = frozenset({"schema_version", "mode", "captures"})

#: Exact per-exam capture keys. Anything else is malformed.
CAPTURE_KEYS = frozenset(
    {
        "match",
        "effective_coordinates",
        "input_identity",
        "matched_identity",
        "event_count",
        "geometry_hash_algorithm",
        "geometry_hash",
        "capture_hash",
    }
)

#: Capture-count ceiling, reused from the core profile bound and checked
#: before any per-entry copy.
CAPTURE_MAX_CAPTURES = MAX_PROFILES

#: Aggregate recipe/geometry-row ceiling, reused from the core row bound.
CAPTURE_MAX_RECIPE_ROWS = MAX_AGGREGATE_ROWS

#: Raw JSON-text ceiling, reused from the core source-byte bound and checked
#: before parsing.
CAPTURE_MAX_BYTES = MAX_SOURCE_BYTES

#: A capture failed structural, type, enum, bound, equality, or checksum validation.
CODE_INVALID_EQUIPMENT_CAPTURE = "invalid_equipment_capture"

#: An envelope, geometry, or algorithm version is not supported by this codec.
CODE_UNSUPPORTED_EQUIPMENT_CAPTURE_VERSION = "unsupported_equipment_capture_version"

#: Confirmed geometry does not match the captured checksum (restore boundary).
CODE_EQUIPMENT_GEOMETRY_MISMATCH = "equipment_geometry_mismatch"


class CaptureError(ValueError):
    """A captured-coordinate document cannot be trusted.

    Carries a stable machine-readable ``code`` so a later boundary (e.g. the
    run-state reader mapping to ``RunStateError``) can translate without
    importing GUI code. Messages are fixed closed-vocabulary strings — never
    document values, keys, labels, hashes, or paths.
    """

    def __init__(self, message: str, code: str = CODE_INVALID_EQUIPMENT_CAPTURE) -> None:
        super().__init__(message)
        self.code = code


__all__ = [
    "CAPTURE_ENVELOPE_KEYS",
    "CAPTURE_ENVELOPE_SCHEMA_VERSION",
    "CAPTURE_KEYS",
    "CAPTURE_MAX_BYTES",
    "CAPTURE_MAX_CAPTURES",
    "CAPTURE_MAX_RECIPE_ROWS",
    "CAPTURE_MODE_COORDINATES",
    "CODE_EQUIPMENT_GEOMETRY_MISMATCH",
    "CODE_INVALID_EQUIPMENT_CAPTURE",
    "CODE_UNSUPPORTED_EQUIPMENT_CAPTURE_VERSION",
    "GEOMETRY_ALGORITHM_V1",
    "GEOMETRY_COLUMNS_V1",
    "GEOMETRY_SCHEMA_VERSION",
    "_HEX_64_RE",
    "_MATCH_LEVELS",
    "_MATCH_SOURCES",
    "_NOTICE_KINDS",
    "_PROFILE_ID_RE",
    "_SESSION_KINDS",
    "CaptureError",
    "_canonical_key",
    "_check_document_budget",
    "_checked_enum",
    "_exact_bool",
    "_exact_int",
    "_exact_list",
    "_finite_number",
    "_geometry_number",
    "_hash64",
    "_identity_keys",
    "_invalid",
    "_leaf_value",
    "_load_strict_json",
    "_profile_id",
    "_require_keys",
    "_require_mapping",
    "_text",
    "_unsupported",
]

_HEX_64_RE = re.compile(r"\A[0-9a-f]{64}\Z")
_PROFILE_ID_RE = re.compile(r"\A(?:" + PROFILE_ID_PATTERN + r")\Z")
_KEY_CHARS_RE = re.compile(r"\A[0-9a-z *]*\Z")

_MATCH_SOURCES = ("custom", "bundled", "default")
_MATCH_LEVELS = ("exact", "wildcard", "default")
_NOTICE_KINDS = ("complete", "partial")
_SESSION_KINDS = ("file", "memory", "store")

#: Integers beyond this bit length are absurd for counts/revisions/versions.
_MAX_INT_BITS = 63


def _invalid() -> CaptureError:
    """Build the closed-vocabulary structural error."""
    return CaptureError(
        "Equipment capture document is invalid.",
        CODE_INVALID_EQUIPMENT_CAPTURE,
    )


def _unsupported() -> CaptureError:
    """Build the closed-vocabulary version error."""
    return CaptureError(
        "Equipment capture version is not supported.",
        CODE_UNSUPPORTED_EQUIPMENT_CAPTURE_VERSION,
    )


def _require_mapping(value: Any) -> dict[str, Any]:
    """Require an exact builtin mapping (subclasses with lying shapes fail)."""
    if type(value) is not dict:
        raise _invalid()
    return value


def _require_keys(mapping: dict[str, Any], allowed: frozenset[str]) -> None:
    """Require exactly the allowlisted keys — unknown or missing fails."""
    if len(mapping) != len(allowed) or any(type(key) is not str for key in mapping) or set(mapping) != allowed:
        raise _invalid()


def _text(value: Any, *, max_len: int = MAX_SHORT_TEXT) -> str:
    """Require bounded nonempty text with no NUL content."""
    if type(value) is not str or not value or len(value) > max_len or "\x00" in value:
        raise _invalid()
    try:
        value.encode("utf-8")
    except UnicodeError:
        raise _invalid() from None
    return value


def _profile_id(value: Any) -> str:
    """Require a well-formed profile ID."""
    text = _text(value)
    if _PROFILE_ID_RE.match(text) is None:
        raise _invalid()
    return text


def _hash64(value: Any) -> str:
    """Require a lowercase 64-hex content hash."""
    if type(value) is not str or _HEX_64_RE.match(value) is None:
        raise _invalid()
    return value


def _exact_int(value: Any, *, minimum: int, maximum: int = 2**_MAX_INT_BITS - 1) -> int:
    """Require an exact int in range; booleans and huge ints fail."""
    if type(value) is not int or not minimum <= value <= maximum:
        raise _invalid()
    if value.bit_length() > _MAX_INT_BITS:
        raise _invalid()
    return value


def _exact_bool(value: Any) -> bool:
    """Require an exact boolean."""
    if type(value) is not bool:
        raise _invalid()
    return value


def _exact_list(value: Any) -> list[Any]:
    """Require an exact builtin list (subclasses with lying lengths fail)."""
    if type(value) is not list:
        raise _invalid()
    return value


def _finite_number(value: Any) -> float:
    """Require a finite number; normalize ints and negative zero to doubles."""
    if isinstance(value, bool):
        raise _invalid()
    if type(value) not in (int, float):
        raise _invalid()
    try:
        result = float(value)
    except OverflowError:
        raise _invalid() from None
    if not math.isfinite(result):
        raise _invalid()
    return result + 0.0


def _leaf_value(field: str, value: Any) -> Any:
    """Enforce the canonical scalar type and range for one coordinate leaf."""
    if field == "swap_lateral_longitudinal":
        return _exact_bool(value)
    if field == "field_size_mode":
        if type(value) is not str or value not in FIELD_SIZE_MODES:
            raise _invalid()
        return value
    direction = field.startswith(("translation_direction.", "rotation_direction."))
    if direction and (type(value) is not str or value not in SIGN_VALUES):
        raise _invalid()
    if direction:
        return value
    number = _finite_number(value)
    if field.startswith("translation_offset.") and not OFFSET_MIN <= number <= OFFSET_MAX:
        raise _invalid()
    if field == "detector_side_length" and not 0.0 < number <= DETECTOR_SIDE_LENGTH_MAX:
        raise _invalid()
    return number


def _canonical_key(value: Any, *, wildcard_ok: bool) -> str:
    """Require canonical key charset; the wildcard only whole as a model key."""
    if type(value) is not str or len(value) > MAX_SHORT_TEXT:
        raise _invalid()
    if _KEY_CHARS_RE.match(value) is None:
        raise _invalid()
    if "*" in value and (not wildcard_ok or value != "*"):
        raise _invalid()
    return value


def _checked_enum(value: Any, allowed: tuple[str, ...]) -> str:
    """Require an exact closed-vocabulary string."""
    if type(value) is not str or value not in allowed:
        raise _invalid()
    return value


def _geometry_number(value: Any) -> float:
    """Require a finite geometry number; normalize ints and negative zero."""
    if isinstance(value, bool) or type(value).__name__ == "bool_":
        raise _invalid()
    if isinstance(value, (int, float)):
        try:
            number = float(value)
        except OverflowError:
            raise _invalid() from None
    elif value is None or isinstance(value, (str, bytes)):
        raise _invalid()
    else:
        try:
            number = float(value)
        except (TypeError, ValueError, OverflowError):
            raise _invalid() from None
    if not math.isfinite(number):
        raise _invalid()
    return number + 0.0


def _identity_keys(maker: str | None, model: str | None) -> tuple[str, str]:
    """Canonical keys for a cleaned identity pair; missing axes are empty."""
    maker_key = normalize_manufacturer_key(maker) if maker is not None else ""
    model_key = normalize_model_key(model) if model is not None else ""
    return maker_key, model_key


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """JSON object hook: repeated keys fail instead of last-value-wins."""
    document: dict[str, Any] = {}
    for key, value in pairs:
        if key in document:
            raise _invalid()
        document[key] = value
    return document


def _reject_json_constants(value: str) -> Any:
    """JSON constant hook: NaN/Infinity literals are never accepted."""
    raise _invalid()


def _check_document_budget(document: Any) -> None:
    """Bound depth and node count of a parsed document before validation walks it.

    Iterative (never recursive): nesting deeper than the core JSON depth cap
    or more nodes than the core traversal cap fails closed. Huge payloads of
    nested irrelevant keys die here, before any hash traversal.
    """
    count = 0
    stack: list[tuple[Any, int]] = [(document, 0)]
    while stack:
        node, depth = stack.pop()
        count += 1
        if count > MAX_TRAVERSAL_NODES:
            raise _invalid()
        if type(node) not in (dict, list):
            continue
        if depth + 1 > MAX_JSON_DEPTH or len(node) > MAX_TRAVERSAL_NODES - count - len(stack):
            raise _invalid()
        children = node.values() if type(node) is dict else node
        stack.extend((value, depth + 1) for value in children)


def _skip_json_string(text: str, start: int) -> int:
    """Skip a quoted token without interpreting escapes; JSON decoder validates it."""
    index = start + 1
    while index < len(text):
        if text[index] == "\\":
            index += 2
        elif text[index] == '"':
            return index + 1
        else:
            index += 1
    raise _invalid()


def _preflight_json(text: str) -> None:
    """Reject excessive container depth/tokens before allocating a JSON tree."""
    depth = 0
    nodes = 0
    index = 0
    while index < len(text):
        character = text[index]
        if character == '"':
            nodes += 1
            index = _skip_json_string(text, index)
        elif character in "[{":
            nodes += 1
            depth += 1
            index += 1
        elif character in "]}":
            depth -= 1
            index += 1
        elif character in "-0123456789tfn":
            nodes += 1
            index += 1
            while index < len(text) and text[index] not in " \t\r\n,]}:":
                index += 1
        else:
            index += 1
        if depth > MAX_JSON_DEPTH or nodes > MAX_TRAVERSAL_NODES:
            raise _invalid()


def _load_strict_json(text: Any) -> Any:
    """Parse JSON text with byte, depth, node, duplicate, and constant guards.

    The character-length pre-check rejects oversized input without encoding;
    only then is the exact UTF-8 size measured (lone surrogates fail closed
    here, never as an escaping ``UnicodeEncodeError``). Recursion failures
    during parsing and budget failures after it are closed errors.
    """
    if type(text) is not str:
        raise _invalid()
    if len(text) > CAPTURE_MAX_BYTES:
        raise _invalid()
    try:
        if len(text.encode("utf-8")) > CAPTURE_MAX_BYTES:
            raise _invalid()
    except UnicodeError:
        raise _invalid() from None
    _preflight_json(text)
    try:
        document = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_json_constants,
        )
    except (ValueError, RecursionError):
        raise _invalid() from None
    try:
        if len(text.encode("utf-8")) > CAPTURE_MAX_BYTES:
            raise _invalid()
    except UnicodeError:
        raise _invalid() from None
    _check_document_budget(document)
    return document


def _check_leaf_parts(
    field: Any,
    value: Any,
    source: Any,
    level: Any,
    profile_id: Any,
    source_kind: Any,
    profile_hash: Any,
    revision: Any,
    inherited: Any,
    *,
    position: int | None = None,
) -> Any:
    """Validate one leaf's parts; returns the normalized value."""
    if type(field) is not str:
        raise _invalid()
    if position is None:
        if field not in LEAF_ORDER:
            raise _invalid()
    elif field != LEAF_ORDER[position]:
        raise _invalid()
    checked_source = _checked_enum(source, _MATCH_SOURCES)
    checked_level = _checked_enum(level, _MATCH_LEVELS)
    _check_source_level(checked_source, checked_level)
    _profile_id(profile_id)
    _checked_enum(source_kind, SOURCE_KINDS)
    _check_provenance_kind(checked_source, source_kind, revision)
    _hash64(profile_hash)
    if revision is not None:
        _exact_int(revision, minimum=1, maximum=MAX_REVISION)
    if type(inherited) is not bool:
        raise _invalid()
    return _leaf_value(field, value)


def _check_entry_parts(
    field: Any, source: Any, level: Any, profile_id: Any, label: Any
) -> None:
    """Validate one notice entry's parts."""
    if type(field) is not str or field not in LEAF_ORDER:
        raise _invalid()
    checked_source = _checked_enum(source, _MATCH_SOURCES)
    checked_level = _checked_enum(level, _MATCH_LEVELS)
    _check_source_level(checked_source, checked_level)
    _profile_id(profile_id)
    _text(label)


def _check_provenance_kind(source: str, kind: str, revision: Any) -> None:
    """Store revisions belong only to custom store sources; bundled data is JSON."""
    if (kind == "store") != (revision is not None):
        raise _invalid()
    if source != "custom" and kind != "json":
        raise _invalid()


def _check_source_level(source: str, level: str) -> None:
    """Require a coherent source/level combination."""
    coherent = (
        (source == "custom" and level == "exact")
        or (source == "bundled" and level in ("exact", "wildcard"))
        or (source == "default" and level == "default")
    )
    if not coherent:
        raise _invalid()


