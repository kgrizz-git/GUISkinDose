"""Captured-coordinate authority types for equipment profiles.

A validated capture is a distinct captured authority: the full effective
15-leaf recipe plus the match that produced it, input/matched identities, the
final retained count, a versioned portable geometry checksum, and a capture
checksum binding everything. It reproduces confirmed raw normalization without
reopening profile files/stores or consulting changed bundled values; original
source/profile hashes travel as audit data only and can never re-derive
omitted notes.

This module holds immutable types, version constants, and the coded error.
Every type validates fully at construction — forged in-memory copies (for
example via :func:`dataclasses.replace`) fail here, never at emit time — and
every repr shows closed-vocabulary tokens and counts only, even for the
arguments of a failed construction. Parsing, serialization, checksums, and
the application-layer producer live elsewhere; nothing here performs I/O,
reads stores or files, imports pandas/normalization/dose/GUI code, or claims
restore/calculation behavior.

Contract: ``dev-docs/EQUIPMENT_PROFILE_RUNSTATE_EXPORT_CONTRACT.md`` §§3, 6.
"""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from typing import Any

from guiskindose.equipment_profiles.canonical import canonical_json_bytes
from guiskindose.equipment_profiles.capture_checks import (
    _HEX_64_RE,
    _MATCH_LEVELS,
    _MATCH_SOURCES,
    _NOTICE_KINDS,
    _SESSION_KINDS,
    CAPTURE_ENVELOPE_KEYS,
    CAPTURE_ENVELOPE_SCHEMA_VERSION,
    CAPTURE_KEYS,
    CAPTURE_MAX_BYTES,
    CAPTURE_MAX_CAPTURES,
    CAPTURE_MAX_RECIPE_ROWS,
    CAPTURE_MODE_COORDINATES,
    CODE_EQUIPMENT_GEOMETRY_MISMATCH,
    CODE_INVALID_EQUIPMENT_CAPTURE,
    CODE_UNSUPPORTED_EQUIPMENT_CAPTURE_VERSION,
    GEOMETRY_ALGORITHM_V1,
    GEOMETRY_COLUMNS_V1,
    GEOMETRY_SCHEMA_VERSION,
    CaptureError,
    _check_document_budget,
    _check_entry_parts,
    _check_leaf_parts,
    _check_provenance_kind,
    _check_source_level,
    _checked_enum,
    _exact_int,
    _hash64,
    _identity_keys,
    _invalid,
    _profile_id,
    _text,
    _unsupported,
)
from guiskindose.equipment_profiles.constants import (
    MAX_AGGREGATE_ROWS,
    MAX_PROFILES,
    MAX_REVISION,
    MAX_SOURCES,
    SOURCE_KINDS,
)
from guiskindose.equipment_profiles.keys import clean_identity_text
from guiskindose.equipment_profiles.resolver import LEAF_ORDER

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
    "CaptureError",
    "CapturedCoordinates",
    "CapturedIdentity",
    "CapturedLeaf",
    "CapturedNoticeEntry",
    "context_body_mapping",
    "context_match_mapping",
    "context_recipe_nested",
    "context_source_mapping",
    "validate_constructed_context",
]


def _construction_error() -> CaptureError:
    """Closed-vocabulary construction failure (never echoes arguments)."""
    return CaptureError(
        "Equipment capture holds invalid construction arguments.",
        CODE_INVALID_EQUIPMENT_CAPTURE,
    )


@dataclass(frozen=True, slots=True, repr=False)
class CapturedIdentity:
    """One identity spelling pair: bounded text or ``None`` when missing."""

    manufacturer: str | None
    model: str | None

    def __post_init__(self) -> None:
        try:
            for name in ("manufacturer", "model"):
                spelling = getattr(self, name)
                if spelling is not None:
                    object.__setattr__(self, name, clean_identity_text(_text(spelling)))
        except CaptureError:
            raise
        except (TypeError, AttributeError):
            raise _construction_error() from None

    def __repr__(self) -> str:
        try:
            maker = self.manufacturer is not None
            model = self.model is not None
        except (TypeError, AttributeError):
            maker = False
            model = False
        return f"CapturedIdentity(maker={maker!r}, model={model!r})"


@dataclass(frozen=True, slots=True, repr=False)
class CapturedLeaf:
    """One validated effective leaf: dotted path, normalized value, provenance."""

    field: str
    value: Any
    source: str
    level: str
    profile_id: str
    source_kind: str
    profile_hash: str
    revision: int | None
    inherited: bool

    def __post_init__(self) -> None:
        try:
            normalized = _check_leaf_parts(
                self.field,
                self.value,
                self.source,
                self.level,
                self.profile_id,
                self.source_kind,
                self.profile_hash,
                self.revision,
                self.inherited,
            )
            object.__setattr__(self, "value", normalized)
        except CaptureError:
            raise
        except (TypeError, AttributeError, IndexError, KeyError):
            raise _construction_error() from None

    def __repr__(self) -> str:
        return (
            "CapturedLeaf("
            f"field={self.field!r}, source={self.source!r}, level={self.level!r})"
        )


@dataclass(frozen=True, slots=True, repr=False)
class CapturedNoticeEntry:
    """One validated inherited-leaf notice entry with its display label."""

    field: str
    source: str
    level: str
    profile_id: str
    label: str

    def __post_init__(self) -> None:
        try:
            _check_entry_parts(self.field, self.source, self.level, self.profile_id, self.label)
        except CaptureError:
            raise
        except (TypeError, AttributeError, IndexError, KeyError):
            raise _construction_error() from None

    def __repr__(self) -> str:
        return (
            "CapturedNoticeEntry("
            f"field={self.field!r}, source={self.source!r}, level={self.level!r})"
        )


@dataclass(frozen=True, slots=True, repr=False)
class CapturedCoordinates:
    """One validated captured-coordinate authority for a single exam.

    Built only through validated construction (parsing or the producer); the
    checksum is verified at parse time and full validity is re-asserted on
    serialization, so a forged in-memory copy fails rather than exporting.
    Provenance fields are captured history, never freshly verified source.
    This context authorizes nothing on its own — restore/calculation
    boundaries decide what to do with it.
    """

    profile_id: str
    source: str
    level: str
    source_kind: str
    profile_hash: str
    revision: int | None
    matched_input_key: tuple[str, str]
    affected_event_count: int
    fields: tuple[CapturedLeaf, ...]
    notice_kind: str
    notice_entries: tuple[CapturedNoticeEntry, ...]
    notice_text: str
    input_identity: CapturedIdentity
    matched_identity: CapturedIdentity
    event_count: int
    geometry_hash_algorithm: str
    geometry_hash: str
    capture_hash: str
    active_set_hash: str
    session_total_profiles: int
    session_total_rows: int
    session_sources: tuple[tuple[Any, ...], ...]

    def __post_init__(self) -> None:
        try:
            validate_constructed_context(self)
        except CaptureError:
            raise
        except (TypeError, AttributeError, IndexError, KeyError):
            raise _construction_error() from None

    def effective_value(self, dotted_path: str) -> Any:
        """Return the effective recipe value for one dotted leaf path."""
        try:
            for leaf in self.fields:
                if leaf.field == dotted_path:
                    return leaf.value
        except (TypeError, AttributeError):
            raise _construction_error() from None
        raise CaptureError(
            "Equipment capture is missing a coordinate field.",
            CODE_INVALID_EQUIPMENT_CAPTURE,
        )

    def __repr__(self) -> str:
        return (
            "CapturedCoordinates("
            f"source={self.source!r}, level={self.level!r}, "
            f"leaves={len(self.fields)}, entries={len(self.notice_entries)}, "
            f"notice={self.notice_kind!r}, events={self.event_count!r})"
        )


def _selected_label(maker: str, model: str) -> str:
    """Rebuild the selected-source label: the model label, maker plus ``*`` for a wildcard."""
    if model == "*":
        return f"{maker} *"
    return model


def _render_notice(
    kind: str,
    selected_label: str,
    source: str,
    level: str,
    entries: tuple[Any, ...],
) -> str:
    """Render notice text from validated structure (same template as resolution)."""
    if kind == "complete":
        return (
            f"Complete match — all {len(LEAF_ORDER)} leaves from "
            f"{source} {level} `{selected_label}`."
        )
    lines = "; ".join(
        f"`{item.field}` from {item.source} {item.level} `{item.label}`" for item in entries
    )
    return f"Partial match — fields inherited from bundled/Default: {lines}."


def _check_notice(
    *,
    kind: str,
    entries: tuple[Any, ...],
    text: str,
    fields: tuple[Any, ...],
    selected_label: str,
    source: str,
    level: str,
    record: tuple[str, str, str, str, str, int | None],
) -> None:
    """Entries must equal the inherited leaves; text must re-render; roots must cohere."""
    inherited = [leaf for leaf in fields if leaf.inherited]
    if len(entries) != len(inherited):
        raise _invalid()
    for item, leaf in zip(entries, inherited, strict=True):
        if (
            item.field != leaf.field
            or item.source != leaf.source
            or item.level != leaf.level
            or item.profile_id != leaf.profile_id
        ):
            raise _invalid()
    if (kind == "complete") == bool(entries):
        raise _invalid()
    _check_leaf_roots(fields, record)
    if text != _render_notice(kind, selected_label, source, level, entries):
        raise _invalid()


def _check_leaf_roots(fields: tuple[Any, ...], record: tuple[Any, ...]) -> None:
    """Inheritance flags must agree with the selected record's full provenance."""
    if not any(not leaf.inherited for leaf in fields):
        raise _invalid()
    for leaf in fields:
        provenance = (
            leaf.profile_id, leaf.source, leaf.level, leaf.source_kind,
            leaf.profile_hash, leaf.revision,
        )
        if leaf.inherited == (provenance == record):
            raise _invalid()
        if leaf.inherited and _provenance_rank(leaf.source, leaf.level) <= _provenance_rank(record[1], record[2]):
            raise _invalid()


def _provenance_rank(source: str, level: str) -> int:
    """Coordinate-only inheritance follows the existing resolution ladder."""
    ranks = {("custom", "exact"): 0, ("bundled", "exact"): 1, ("bundled", "wildcard"): 2, ("default", "default"): 3}
    rank = ranks.get((source, level))
    if rank is None:
        raise _invalid()
    return rank


def _check_file_source(
    format_name: Any, digest: Any, revisions: tuple[tuple[str, int], ...]
) -> None:
    """File sources name an adapter format, carry a hash, and hold no revisions."""
    if type(format_name) is not str or format_name not in ("json", "csv", "tsv", "xlsx"):
        raise _invalid()
    if type(digest) is not str or _HEX_64_RE.match(digest) is None:
        raise _invalid()
    if revisions:
        raise _invalid()


def _check_memory_source(
    format_name: Any, digest: Any, revisions: tuple[tuple[str, int], ...]
) -> None:
    """Memory sources carry no format, hash, or revisions."""
    if format_name is not None or digest is not None or revisions:
        raise _invalid()


def _check_store_source(
    format_name: Any,
    digest: Any,
    profile_ids: tuple[str, ...],
    revisions: tuple[tuple[str, int], ...],
) -> None:
    """Store sources carry a set hash with revisions aligned to selected IDs."""
    if format_name is not None:
        raise _invalid()
    if type(digest) is not str or _HEX_64_RE.match(digest) is None:
        raise _invalid()
    if tuple(pair[0] for pair in revisions) != profile_ids:
        raise _invalid()


def _check_source_semantics(
    kind: Any,
    format_name: Any,
    digest: Any,
    profile_ids: tuple[str, ...],
    revisions: tuple[tuple[str, int], ...],
    profile_count: int,
    logical_rows: int,
) -> None:
    """Require coherent per-source audit shapes and counts."""
    _checked_enum(kind, _SESSION_KINDS)
    _exact_int(profile_count, minimum=0, maximum=MAX_PROFILES)
    _exact_int(logical_rows, minimum=0, maximum=MAX_AGGREGATE_ROWS)
    if profile_count != len(profile_ids):
        raise _invalid()
    if kind == "file":
        _check_file_source(format_name, digest, revisions)
    elif kind == "memory":
        _check_memory_source(format_name, digest, revisions)
    elif kind == "store":
        _check_store_source(format_name, digest, profile_ids, revisions)
    else:
        raise _invalid()


def _typed_tuple(value: Any, member: type, *, length: int | None = None) -> tuple[Any, ...]:
    """Require an exact tuple of exact member types, optionally lengthed."""
    if type(value) is not tuple:
        raise _invalid()
    if length is not None and len(value) != length:
        raise _invalid()
    for item in value:
        if type(item) is not member:
            raise _invalid()
    return value


def _check_identity_object(identity: Any, identity_cls: type, *, allow_missing: bool) -> tuple[str, str]:
    """Validate an identity object; returns display spellings."""
    if type(identity) is not identity_cls:
        raise _invalid()
    maker = identity.manufacturer
    model = identity.model
    for spelling in (maker, model):
        if spelling is None:
            if not allow_missing:
                raise _invalid()
        else:
            _text(spelling)
    return maker or "", model or ""


def _check_revision_tuple(pair: Any) -> tuple[str, int]:
    """Validate one revision pair tuple."""
    if type(pair) is not tuple or len(pair) != 2:
        raise _invalid()
    return _profile_id(pair[0]), _exact_int(pair[1], minimum=1, maximum=MAX_REVISION)


def _check_session_tuple(source: Any) -> None:
    """Validate one session source tuple's shapes and semantics."""
    if type(source) is not tuple or len(source) != 7:
        raise _invalid()
    kind, format_name, digest, profile_ids, revisions, profile_count, logical_rows = source
    if type(profile_ids) is not tuple or len(profile_ids) > MAX_PROFILES:
        raise _invalid()
    if type(revisions) is not tuple or len(revisions) > MAX_PROFILES:
        raise _invalid()
    _typed_tuple(profile_ids, str)
    for name in profile_ids:
        _profile_id(name)
    if len(set(profile_ids)) != len(profile_ids):
        raise _invalid()
    checked = tuple(_check_revision_tuple(pair) for pair in _typed_tuple(revisions, tuple))
    _check_source_semantics(
        kind,
        format_name,
        digest,
        profile_ids,
        checked,
        profile_count,
        logical_rows,
    )


def _check_session_object(
    total_profiles: int, total_rows: int, sources: tuple[Any, ...]
) -> None:
    """Validate session totals, per-source coherence, and aggregate equality."""
    _exact_int(total_profiles, minimum=0, maximum=MAX_PROFILES)
    _exact_int(total_rows, minimum=0, maximum=MAX_AGGREGATE_ROWS)
    if len(sources) > MAX_SOURCES:
        raise _invalid()
    claimed_ids: set[str] = set()
    for source in sources:
        _check_session_tuple(source)
        if claimed_ids.intersection(source[3]):
            raise _invalid()
        claimed_ids.update(source[3])
    if total_profiles != sum(item[5] for item in sources):
        raise _invalid()
    if total_rows != sum(item[6] for item in sources):
        raise _invalid()


def context_recipe_nested(context: Any) -> dict[str, Any]:
    """Rebuild the nested recipe object from validated leaf order."""
    nested: dict[str, Any] = {
        "translation_offset": {},
        "translation_direction": {},
        "rotation_direction": {},
    }
    for leaf in context.fields:
        block, _, name = leaf.field.partition(".")
        if block in nested:
            nested[block][name] = leaf.value
        else:
            nested[leaf.field] = leaf.value
    return nested


def context_source_mapping(source: tuple[Any, ...]) -> dict[str, Any]:
    """Expand one validated session source tuple back to its mapping shape."""
    kind, format_name, digest, profile_ids, revisions, profile_count, logical_rows = source
    return {
        "kind": kind,
        "format": format_name,
        "source_hash": digest,
        "profile_ids": list(profile_ids),
        "revisions": [list(pair) for pair in revisions],
        "profile_count": profile_count,
        "logical_rows": logical_rows,
    }


def context_match_mapping(context: Any) -> dict[str, Any]:
    """Rebuild the match mapping from a validated context."""
    return {
        "profile_id": context.profile_id,
        "source": context.source,
        "level": context.level,
        "source_kind": context.source_kind,
        "profile_hash": context.profile_hash,
        "revision": context.revision,
        "matched_input_key": {
            "manufacturer": context.matched_input_key[0],
            "model": context.matched_input_key[1],
        },
        "affected_event_count": context.affected_event_count,
        "fields": [
            {
                "field": leaf.field,
                "value": leaf.value,
                "source": leaf.source,
                "level": leaf.level,
                "profile_id": leaf.profile_id,
                "source_kind": leaf.source_kind,
                "profile_hash": leaf.profile_hash,
                "revision": leaf.revision,
                "inherited": leaf.inherited,
            }
            for leaf in context.fields
        ],
        "notice": {
            "kind": context.notice_kind,
            "entries": [
                {
                    "field": item.field,
                    "source": item.source,
                    "level": item.level,
                    "profile_id": item.profile_id,
                    "label": item.label,
                }
                for item in context.notice_entries
            ],
            "text": context.notice_text,
        },
        "active_set_hash": context.active_set_hash,
        "session": {
            "total_profiles": context.session_total_profiles,
            "total_rows": context.session_total_rows,
            "sources": [context_source_mapping(item) for item in context.session_sources],
        },
    }


def context_body_mapping(context: Any) -> dict[str, Any]:
    """Rebuild the checksum-covered body from a validated context."""
    return {
        "match": context_match_mapping(context),
        "effective_coordinates": context_recipe_nested(context),
        "input_identity": {
            "manufacturer": context.input_identity.manufacturer,
            "model": context.input_identity.model,
        },
        "matched_identity": {
            "manufacturer": context.matched_identity.manufacturer,
            "model": context.matched_identity.model,
        },
        "event_count": context.event_count,
        "geometry_hash_algorithm": context.geometry_hash_algorithm,
        "geometry_hash": context.geometry_hash,
    }


def _context_hash_hex(body: dict[str, Any]) -> str:
    """SHA-256 over the canonical bytes of a context body."""
    return hashlib.sha256(canonical_json_bytes(body)).hexdigest()


def validate_constructed_context(context: Any) -> None:
    """Validate a public context boundary with value-free shape failures."""
    try:
        _validate_constructed_context(context)
    except (TypeError, AttributeError, IndexError, KeyError):
        raise _construction_error() from None


def _validate_constructed_context(context: Any) -> None:
    """Fully validate a constructed context: types, scalars, coherence, checksum.

    Shared by immutable construction and serialization, so forged in-memory
    copies face every check — including checksum recomputation, which catches
    checksummed-but-malformed hand-built objects. The profile types import
    lazily here (once, cached) to keep the type and validation layers
    acyclic. Raises closed errors only.
    """
    if type(context) is not CapturedCoordinates:
        raise _invalid()
    for name in (
        "profile_id",
        "source",
        "level",
        "source_kind",
        "profile_hash",
        "notice_kind",
        "notice_text",
        "geometry_hash_algorithm",
        "geometry_hash",
        "capture_hash",
        "active_set_hash",
    ):
        if type(getattr(context, name, None)) is not str:
            raise _invalid()
    fields = _typed_tuple(context.fields, CapturedLeaf, length=15)
    for position, leaf in enumerate(fields):
        _check_leaf_parts(
            leaf.field,
            leaf.value,
            leaf.source,
            leaf.level,
            leaf.profile_id,
            leaf.source_kind,
            leaf.profile_hash,
            leaf.revision,
            leaf.inherited,
            position=position,
        )
    if type(context.notice_entries) is not tuple or len(context.notice_entries) > 15:
        raise _invalid()
    entries = _typed_tuple(context.notice_entries, CapturedNoticeEntry)
    for item in entries:
        _check_entry_parts(item.field, item.source, item.level, item.profile_id, item.label)
    _check_identity_object(context.input_identity, CapturedIdentity, allow_missing=True)
    maker_name, model_name = _check_identity_object(
        context.matched_identity, CapturedIdentity, allow_missing=False
    )
    _check_session_object(
        context.session_total_profiles,
        context.session_total_rows,
        _typed_tuple(context.session_sources, tuple),
    )
    _check_key_and_counts(context)
    _check_custom_source(context)
    _check_constructed_notice(context, maker_name, model_name, fields, entries)
    body = context_body_mapping(context)
    _check_document_budget(body)
    if not hmac.compare_digest(_context_hash_hex(body), context.capture_hash):
        raise _invalid()


def _check_custom_source(context: CapturedCoordinates) -> None:
    """A custom match must agree with its captured session source and revision."""
    if context.source != "custom":
        return
    for source in context.session_sources:
        kind, format_name, _, profile_ids, revisions, _, _ = source
        if context.profile_id not in profile_ids:
            continue
        expected_kind = format_name if kind == "file" else kind
        expected_revision = dict(revisions).get(context.profile_id)
        if context.source_kind != expected_kind or context.revision != expected_revision:
            raise _invalid()
        return
    raise _invalid()


def _check_key_and_counts(context: CapturedCoordinates) -> None:
    """Matched-key, count, revision, and hash-shape coherence."""
    if type(context.matched_input_key) is not tuple or len(context.matched_input_key) != 2:
        raise _invalid()
    if context.matched_input_key != _identity_keys(
        context.input_identity.manufacturer, context.input_identity.model
    ):
        raise _invalid()
    _exact_int(context.event_count, minimum=1, maximum=MAX_AGGREGATE_ROWS)
    _exact_int(context.affected_event_count, minimum=0, maximum=MAX_AGGREGATE_ROWS)
    if context.event_count != context.affected_event_count:
        raise _invalid()
    if context.revision is not None:
        _exact_int(context.revision, minimum=1, maximum=MAX_REVISION)
    if context.geometry_hash_algorithm != GEOMETRY_ALGORITHM_V1:
        raise _unsupported()
    _hash64(context.geometry_hash)
    _hash64(context.capture_hash)
    _hash64(context.active_set_hash)
    _hash64(context.profile_hash)
    _profile_id(context.profile_id)
    _checked_enum(context.source, _MATCH_SOURCES)
    _checked_enum(context.level, _MATCH_LEVELS)
    _check_source_level(context.source, context.level)
    _checked_enum(context.source_kind, SOURCE_KINDS)
    _check_provenance_kind(context.source, context.source_kind, context.revision)
    _checked_enum(context.notice_kind, _NOTICE_KINDS)


def _check_constructed_notice(
    context: CapturedCoordinates,
    maker_name: str,
    model_name: str,
    fields: tuple[Any, ...],
    entries: tuple[Any, ...],
) -> None:
    """Notice text and root coherence for a constructed context."""
    _check_notice(
        kind=context.notice_kind,
        entries=entries,
        text=context.notice_text,
        fields=fields,
        selected_label=_selected_label(maker_name, model_name),
        source=context.source,
        level=context.level,
        record=(
            context.profile_id,
            context.source,
            context.level,
            context.source_kind,
            context.profile_hash,
            context.revision,
        ),
    )
