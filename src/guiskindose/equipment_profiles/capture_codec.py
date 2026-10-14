"""Strict capture/envelope parsing for captured-coordinate authorities.

Validates one capture mapping — or a whole envelope of per-exam captures —
into immutable :class:`CapturedCoordinates` authorities. The full effective
recipe is checked against the captured match only; changed bundles, files,
and stores are never consulted, and provenance travels as shape-checked
audit data. Shared validators (leaf/entry/notice/session checks, canonical
builders, construction validation) live in :mod:`capture_checks` so parsing
and direct construction face identical rules. Emission lives with the
application-layer producer; parsing here never touches application state.
"""

from __future__ import annotations

import hmac
from typing import Any

from guiskindose.equipment_profiles.capture import (
    CapturedCoordinates,
    CapturedIdentity,
    _check_notice,
    _check_source_semantics,
    _context_hash_hex,
    _selected_label,
)
from guiskindose.equipment_profiles.capture_checks import (
    _MATCH_LEVELS,
    _MATCH_SOURCES,
    _NOTICE_KINDS,
    _SESSION_KINDS,
    CAPTURE_ENVELOPE_KEYS,
    CAPTURE_ENVELOPE_SCHEMA_VERSION,
    CAPTURE_KEYS,
    CAPTURE_MAX_CAPTURES,
    CAPTURE_MAX_RECIPE_ROWS,
    CAPTURE_MODE_COORDINATES,
    GEOMETRY_ALGORITHM_V1,
    _canonical_key,
    _check_document_budget,
    _check_entry_parts,
    _check_leaf_parts,
    _checked_enum,
    _exact_int,
    _exact_list,
    _hash64,
    _identity_keys,
    _invalid,
    _leaf_value,
    _load_strict_json,
    _profile_id,
    _require_keys,
    _require_mapping,
    _text,
    _unsupported,
)
from guiskindose.equipment_profiles.constants import (
    MAX_AGGREGATE_ROWS,
    MAX_PROFILES,
    MAX_REVISION,
    MAX_SHORT_TEXT,
    MAX_SOURCES,
    SOURCE_KINDS,
)
from guiskindose.equipment_profiles.keys import clean_identity_text
from guiskindose.equipment_profiles.resolver import LEAF_ORDER

__all__ = [
    "capture_from_json",
    "capture_from_mapping",
    "envelope_from_json",
    "normalize_capture_body",
    "parse_envelope",
]

_MATCH_KEYS = frozenset(
    {
        "profile_id",
        "source",
        "level",
        "source_kind",
        "profile_hash",
        "revision",
        "matched_input_key",
        "affected_event_count",
        "fields",
        "notice",
        "active_set_hash",
        "session",
    }
)
_LEAF_KEYS = frozenset(
    {
        "field",
        "value",
        "source",
        "level",
        "profile_id",
        "source_kind",
        "profile_hash",
        "revision",
        "inherited",
    }
)
_NOTICE_KEYS = frozenset({"kind", "entries", "text"})
_ENTRY_KEYS = frozenset({"field", "source", "level", "profile_id", "label"})
_KEY_KEYS = frozenset({"manufacturer", "model"})
_IDENTITY_KEYS = frozenset({"manufacturer", "model"})
_SESSION_KEYS = frozenset({"total_profiles", "total_rows", "sources"})
_SOURCE_KEYS = frozenset(
    {
        "kind",
        "format",
        "source_hash",
        "profile_ids",
        "revisions",
        "profile_count",
        "logical_rows",
    }
)
_RECIPE_BLOCKS = (
    "translation_offset",
    "translation_direction",
    "rotation_direction",
    "swap_lateral_longitudinal",
    "field_size_mode",
    "detector_side_length",
)
_RECIPE_LEAVES: dict[str, tuple[str, ...]] = {
    "translation_offset": ("x", "y", "z"),
    "translation_direction": ("x", "y", "z"),
    "rotation_direction": ("Ap1", "Ap2", "Ap3", "At1", "At2", "At3"),
}

def _cleaned_text(value: Any) -> str | None:
    """Cleaned identity text, or ``None`` when absent or an artifact."""
    if value is None:
        return None
    if type(value) is not str:
        raise _invalid()
    return clean_identity_text(value)


def _bounded_identity_text(text: str | None) -> None:
    """Bound optional identity spellings that survived cleaning."""
    if text is not None and (not text or len(text) > MAX_SHORT_TEXT or "\x00" in text):
        raise _invalid()


def _parse_identity_section(mapping: Any) -> dict[str, Any]:
    """Require an identity section mapping with exactly its two keys."""
    section = _require_mapping(mapping)
    _require_keys(section, _IDENTITY_KEYS)
    return section


def _parse_identity(mapping: Any) -> tuple[CapturedIdentity, tuple[str, str]]:
    """Parse an identity pair plus its canonical keys (never inferred)."""
    section = _parse_identity_section(mapping)
    maker = _cleaned_text(section["manufacturer"])
    model = _cleaned_text(section["model"])
    _bounded_identity_text(maker)
    _bounded_identity_text(model)
    return CapturedIdentity(manufacturer=maker, model=model), _identity_keys(maker, model)


def _record_tuple(match: dict[str, Any]) -> tuple[str, str, str, str, str, int | None]:
    """Record-level provenance every complete-match leaf must share."""
    return (
        match["profile_id"],
        match["source"],
        match["level"],
        match["source_kind"],
        match["profile_hash"],
        match["revision"],
    )


def _parse_matched_identity(mapping: Any) -> CapturedIdentity:
    """Parse display spellings; both are required bounded nonempty text."""
    section = _parse_identity_section(mapping)
    return CapturedIdentity(
        manufacturer=_text(section["manufacturer"]),
        model=_text(section["model"]),
    )


def _parse_optional_revision(value: Any) -> int | None:
    """Parse an optional revision: ``None`` or an exact positive int."""
    if value is None:
        return None
    return _exact_int(value, minimum=1, maximum=MAX_REVISION)


def _parse_leaf(mapping: Any, position: int) -> Any:
    """Parse one provenance leaf at its canonical position."""
    from guiskindose.equipment_profiles.capture import CapturedLeaf

    leaf = _require_mapping(mapping)
    _require_keys(leaf, _LEAF_KEYS)
    value = _check_leaf_parts(
        leaf["field"],
        leaf["value"],
        leaf["source"],
        leaf["level"],
        leaf["profile_id"],
        leaf["source_kind"],
        leaf["profile_hash"],
        leaf["revision"],
        leaf["inherited"],
        position=position,
    )
    return CapturedLeaf(
        field=LEAF_ORDER[position],
        value=value,
        source=leaf["source"],
        level=leaf["level"],
        profile_id=leaf["profile_id"],
        source_kind=leaf["source_kind"],
        profile_hash=leaf["profile_hash"],
        revision=leaf["revision"],
        inherited=leaf["inherited"],
    )


def _parse_entry(mapping: Any) -> Any:
    """Parse one notice entry; labels are validated text, never re-derived."""
    from guiskindose.equipment_profiles.capture import CapturedNoticeEntry

    entry = _require_mapping(mapping)
    _require_keys(entry, _ENTRY_KEYS)
    _check_entry_parts(
        entry["field"], entry["source"], entry["level"], entry["profile_id"], entry["label"]
    )
    return CapturedNoticeEntry(
        field=entry["field"],
        source=entry["source"],
        level=entry["level"],
        profile_id=entry["profile_id"],
        label=entry["label"],
    )


def _parse_revision_pair(value: Any) -> tuple[str, int]:
    """Parse one ``[profile_id, revision]`` pair from its exact list shape."""
    if type(value) is not list or len(value) != 2:
        raise _invalid()
    return _profile_id(value[0]), _exact_int(value[1], minimum=1, maximum=MAX_REVISION)


def _parse_id_list(value: Any) -> tuple[str, ...]:
    """Parse a bounded list of unique profile IDs."""
    raw = _exact_list(value)
    if len(raw) > CAPTURE_MAX_CAPTURES:
        raise _invalid()
    profile_ids = tuple(_profile_id(item) for item in raw)
    if len(set(profile_ids)) != len(profile_ids):
        raise _invalid()
    return profile_ids


def _parse_session_source(mapping: Any) -> tuple[Any, ...]:
    """Parse one session provenance source record (audit data, never verified)."""
    source = _require_mapping(mapping)
    _require_keys(source, _SOURCE_KEYS)
    kind = _checked_enum(source["kind"], _SESSION_KINDS)
    raw_revisions = _exact_list(source["revisions"])
    if len(raw_revisions) > CAPTURE_MAX_CAPTURES:
        raise _invalid()
    profile_ids = _parse_id_list(source["profile_ids"])
    revisions = tuple(_parse_revision_pair(item) for item in raw_revisions)
    profile_count = _exact_int(source["profile_count"], minimum=0, maximum=MAX_PROFILES)
    logical_rows = _exact_int(source["logical_rows"], minimum=0, maximum=MAX_AGGREGATE_ROWS)
    _check_source_semantics(
        kind,
        source["format"],
        source["source_hash"],
        profile_ids,
        revisions,
        profile_count,
        logical_rows,
    )
    return (
        kind,
        source["format"],
        source["source_hash"],
        profile_ids,
        revisions,
        profile_count,
        logical_rows,
    )


def _parse_session(mapping: Any) -> tuple[int, int, tuple[tuple[Any, ...], ...]]:
    """Parse the session summary with totals equal to the source sums."""
    session = _require_mapping(mapping)
    _require_keys(session, _SESSION_KEYS)
    raw_sources = _exact_list(session["sources"])
    if len(raw_sources) > MAX_SOURCES:
        raise _invalid()
    sources = tuple(_parse_session_source(item) for item in raw_sources)
    total_profiles = _exact_int(session["total_profiles"], minimum=0, maximum=MAX_PROFILES)
    total_rows = _exact_int(session["total_rows"], minimum=0, maximum=MAX_AGGREGATE_ROWS)
    if total_profiles != sum(item[5] for item in sources):
        raise _invalid()
    if total_rows != sum(item[6] for item in sources):
        raise _invalid()
    return total_profiles, total_rows, sources


def _parse_match(mapping: Any) -> dict[str, Any]:
    """Parse the captured match record; notice text is checked by the caller."""
    match = _require_mapping(mapping)
    _require_keys(match, _MATCH_KEYS)
    raw_fields = _exact_list(match["fields"])
    if len(raw_fields) != len(LEAF_ORDER):
        raise _invalid()
    fields = tuple(_parse_leaf(item, position) for position, item in enumerate(raw_fields))
    notice = _require_mapping(match["notice"])
    _require_keys(notice, _NOTICE_KEYS)
    kind = _checked_enum(notice["kind"], _NOTICE_KINDS)
    raw_entries = _exact_list(notice["entries"])
    if len(raw_entries) > len(LEAF_ORDER):
        raise _invalid()
    if type(notice["text"]) is not str:
        raise _invalid()
    key_section = _require_mapping(match["matched_input_key"])
    _require_keys(key_section, _KEY_KEYS)
    return {
        "profile_id": _profile_id(match["profile_id"]),
        "source": _checked_enum(match["source"], _MATCH_SOURCES),
        "level": _checked_enum(match["level"], _MATCH_LEVELS),
        "source_kind": _checked_enum(match["source_kind"], SOURCE_KINDS),
        "profile_hash": _hash64(match["profile_hash"]),
        "revision": _parse_optional_revision(match["revision"]),
        "matched_input_key": (
            _canonical_key(key_section["manufacturer"], wildcard_ok=False),
            _canonical_key(key_section["model"], wildcard_ok=True),
        ),
        "affected_event_count": _exact_int(match["affected_event_count"], minimum=0, maximum=MAX_AGGREGATE_ROWS),
        "fields": fields,
        "notice_kind": kind,
        "notice_entries": tuple(_parse_entry(item) for item in raw_entries),
        "notice_text": notice["text"],
        "active_set_hash": _hash64(match["active_set_hash"]),
        "session": _parse_session(match["session"]),
    }


def _parse_recipe(mapping: Any) -> dict[str, Any]:
    """Parse the complete 15-leaf effective recipe in nested block shape."""
    recipe = _require_mapping(mapping)
    if set(recipe) != set(_RECIPE_BLOCKS):
        raise _invalid()
    flat: dict[str, Any] = {}
    for block, leaves in _RECIPE_LEAVES.items():
        section = recipe[block]
        if type(section) is not dict or set(section) != set(leaves):
            raise _invalid()
        for leaf in leaves:
            flat[f"{block}.{leaf}"] = _leaf_value(f"{block}.{leaf}", section[leaf])
    for scalar in (
        "swap_lateral_longitudinal",
        "field_size_mode",
        "detector_side_length",
    ):
        flat[scalar] = _leaf_value(scalar, recipe[scalar])
    return flat


def _check_recipe_equals(fields: tuple[Any, ...], recipe: dict[str, Any]) -> None:
    """The recipe must equal the match fields exactly — no inheritance left."""
    for leaf in fields:
        if leaf.field not in recipe or recipe[leaf.field] != leaf.value:
            raise _invalid()


def _normalize_fields(raw_fields: Any) -> list[dict[str, Any]]:
    """Normalize raw match field entries to canonical scalars."""
    if type(raw_fields) is not list or len(raw_fields) != len(LEAF_ORDER):
        raise _invalid()
    normalized_fields = []
    for position, item in enumerate(raw_fields):
        if type(item) is not dict:
            raise _invalid()
        field = item.get("field")
        if type(field) is not str or field != LEAF_ORDER[position] or "value" not in item:
            raise _invalid()
        entry = dict(item)
        entry["value"] = _leaf_value(field, item["value"])
        normalized_fields.append(entry)
    return normalized_fields


def _normalize_recipe_block(block: str, recipe: dict[str, Any]) -> Any:
    """Normalize one recipe block or scalar to canonical scalars."""
    if block not in recipe:
        raise _invalid()
    if block not in _RECIPE_LEAVES:
        return _leaf_value(block, recipe[block])
    section = recipe[block]
    if type(section) is not dict:
        raise _invalid()
    normalized_section = {}
    for leaf in _RECIPE_LEAVES[block]:
        if leaf not in section:
            raise _invalid()
        normalized_section[leaf] = _leaf_value(f"{block}.{leaf}", section[leaf])
    return normalized_section


def normalize_capture_body(body: Any) -> dict[str, Any]:
    """Normalize a raw capture body to its canonical scalar form.

    Integers become doubles and ``-0.0`` becomes ``+0.0`` in both the match
    fields and the recipe, so ``5`` and ``5.0`` share one checksum. Checksums
    always cover this normalized form — never the raw spellings. Structure
    beyond leaf values is not interpreted here; full validation still applies
    at parse time.
    """
    document = _require_mapping(body)
    match = document.get("match")
    recipe = document.get("effective_coordinates")
    if type(match) is not dict or type(recipe) is not dict:
        raise _invalid()
    normalized_match = dict(match)
    normalized_match["fields"] = _normalize_fields(match.get("fields"))
    normalized_recipe = {block: _normalize_recipe_block(block, recipe) for block in _RECIPE_BLOCKS}
    normalized = dict(document)
    normalized["match"] = normalized_match
    normalized["effective_coordinates"] = normalized_recipe
    for key in ("input_identity", "matched_identity"):
        identity = _require_mapping(document.get(key))
        _require_keys(identity, _IDENTITY_KEYS)
        normalized[key] = {name: _cleaned_text(value) for name, value in identity.items()}
    return normalized


def capture_from_mapping(mapping: Any) -> CapturedCoordinates:
    """Validate one capture mapping into an immutable captured authority."""
    _check_document_budget(mapping)
    document = _require_mapping(mapping)
    _require_keys(document, CAPTURE_KEYS)
    match = _parse_match(document["match"])
    _check_recipe_equals(match["fields"], _parse_recipe(document["effective_coordinates"]))
    input_identity, input_keys = _parse_identity(document["input_identity"])
    matched_identity = _parse_matched_identity(document["matched_identity"])
    if match["matched_input_key"] != input_keys:
        raise _invalid()
    event_count = _exact_int(document["event_count"], minimum=1, maximum=MAX_AGGREGATE_ROWS)
    if event_count != match["affected_event_count"]:
        raise _invalid()
    if document["geometry_hash_algorithm"] != GEOMETRY_ALGORITHM_V1:
        raise _unsupported()
    geometry_hash = _hash64(document["geometry_hash"])
    claimed = _hash64(document["capture_hash"])
    maker_name = matched_identity.manufacturer
    model_name = matched_identity.model
    if maker_name is None or model_name is None:
        raise _invalid()
    _check_notice(
        kind=match["notice_kind"],
        entries=match["notice_entries"],
        text=match["notice_text"],
        fields=match["fields"],
        selected_label=_selected_label(maker_name, model_name),
        source=match["source"],
        level=match["level"],
        record=_record_tuple(match),
    )
    body = {key: document[key] for key in CAPTURE_KEYS if key != "capture_hash"}
    _check_document_budget(body)
    normalized = normalize_capture_body(body)
    if not hmac.compare_digest(_context_hash_hex(normalized), claimed):
        raise _invalid()
    total_profiles, total_rows, sources = match["session"]
    return CapturedCoordinates(
        profile_id=match["profile_id"],
        source=match["source"],
        level=match["level"],
        source_kind=match["source_kind"],
        profile_hash=match["profile_hash"],
        revision=match["revision"],
        matched_input_key=match["matched_input_key"],
        affected_event_count=match["affected_event_count"],
        fields=match["fields"],
        notice_kind=match["notice_kind"],
        notice_entries=match["notice_entries"],
        notice_text=match["notice_text"],
        input_identity=input_identity,
        matched_identity=matched_identity,
        event_count=event_count,
        geometry_hash_algorithm=document["geometry_hash_algorithm"],
        geometry_hash=geometry_hash,
        capture_hash=claimed,
        active_set_hash=match["active_set_hash"],
        session_total_profiles=total_profiles,
        session_total_rows=total_rows,
        session_sources=sources,
    )


def capture_from_json(text: Any) -> CapturedCoordinates:
    """Parse one JSON-text capture under the byte cap with strict constants."""
    return capture_from_mapping(_load_strict_json(text))


def _envelope_recipe_rows(entry: Any) -> int:
    """Count one envelope entry's recipe rows from raw list lengths, pre-copy."""
    if entry is None:
        return 0
    if type(entry) is not dict:
        raise _invalid()
    match = entry.get("match")
    if type(match) is not dict:
        raise _invalid()
    raw_fields = match.get("fields")
    if type(raw_fields) is not list or len(raw_fields) != len(LEAF_ORDER):
        raise _invalid()
    raw_notice = match.get("notice")
    if type(raw_notice) is not dict:
        raise _invalid()
    raw_entries = raw_notice.get("entries")
    if type(raw_entries) is not list or len(raw_entries) > len(LEAF_ORDER):
        raise _invalid()
    return 1 + len(raw_fields) + len(raw_entries)


def parse_envelope(document: Any) -> tuple[CapturedCoordinates | None, ...]:
    """Validate a capture envelope into per-exam contexts (``None`` = no capture)."""
    _check_document_budget(document)
    envelope = _require_mapping(document)
    _require_keys(envelope, CAPTURE_ENVELOPE_KEYS)
    if type(envelope["schema_version"]) is not int:
        raise _unsupported()
    if envelope["schema_version"] != CAPTURE_ENVELOPE_SCHEMA_VERSION:
        raise _unsupported()
    if type(envelope["mode"]) is not str or envelope["mode"] != CAPTURE_MODE_COORDINATES:
        raise _invalid()
    raw_captures = envelope["captures"]
    if type(raw_captures) is not list or len(raw_captures) > CAPTURE_MAX_CAPTURES:
        raise _invalid()
    total_rows = 0
    for entry in raw_captures:
        total_rows += _envelope_recipe_rows(entry)
        if total_rows > CAPTURE_MAX_RECIPE_ROWS:
            raise _invalid()
    return tuple(None if entry is None else capture_from_mapping(entry) for entry in raw_captures)


def envelope_from_json(text: Any) -> tuple[CapturedCoordinates | None, ...]:
    """Parse one JSON-text envelope under the byte cap with strict constants."""
    return parse_envelope(_load_strict_json(text))
