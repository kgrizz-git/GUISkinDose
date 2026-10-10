"""Bounded JSON and in-memory document parsing for equipment profiles.

The reader owns every non-schema failure mode that must stay value-free: an unreadable or empty file, a
source that is too large, a suffix that is not accepted, text that is not strict UTF-8, malformed JSON, and
duplicate JSON object keys. Raw exception causes are suppressed so no library text, path, or byte content
leaks into an error. A file contributes a SHA-256 of the exact bytes read, before decoding; an in-memory
document contributes none.

Bounds are applied in a deliberately cheap-first order so a hostile document cannot force exhaustive work:

1. A file is read **at most** ``MAX_SOURCE_BYTES + 1`` bytes in one bounded read, so an oversized file is
   rejected without being fully materialized and without a size-then-read race.
2. The envelope's ``profiles`` list length is checked before any traversal (``MAX_PROFILES``).
3. The depth check runs over an explicit **node budget** (``MAX_TRAVERSAL_NODES``) and a depth bound
   (``MAX_JSON_DEPTH``). A valid document holds at most ``MAX_AGGREGATE_ROWS`` logical rows, each with a
   bounded number of keys, so the budget is far above any valid document while capping work on a hostile one.
4. Each document enforces the aggregate logical-row ceiling itself, not only the multi-document combination.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from guiskindose.equipment_profiles.canonical import source_bytes_hash
from guiskindose.equipment_profiles.constants import (
    JSON_SOURCE_SUFFIXES,
    MAX_AGGREGATE_ROWS,
    MAX_JSON_DEPTH,
    MAX_PROFILES,
    MAX_SOURCE_BYTES,
    MAX_TRAVERSAL_NODES,
    SOURCE_KIND_JSON,
    SOURCE_KIND_MEMORY,
)
from guiskindose.equipment_profiles.errors import EquipmentProfileError, ProfileErrorCode
from guiskindose.equipment_profiles.models import Profile
from guiskindose.equipment_profiles.validation import validate_document

_UTF8_BOM = "\ufeff"


class _DuplicateKeyError(Exception):
    """Private signal raised by the ``object_pairs_hook``; never escapes this module."""

    __slots__ = ()


class _NonFiniteNumberError(Exception):
    """Private signal for a NaN/Infinity literal; never escapes this module."""

    __slots__ = ()


def _rejecting_pairs_hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKeyError
        result[key] = value
    return result


def _reject_constant(token: str) -> float:
    raise _NonFiniteNumberError


@dataclass(frozen=True, slots=True)
class ParsedDocument:
    """One validated document plus its source provenance.

    ``source_hash`` is ``None`` for an in-memory document, which has no source bytes.
    """

    profiles: tuple[Profile, ...]
    source_kind: str
    source_hash: str | None
    logical_rows: int


def _decode_source(raw: bytes, *, source_kind: str) -> str:
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
    return text


def _enforce_depth(value: Any, max_depth: int, *, source_kind: str, max_nodes: int) -> None:
    """Iteratively bound nesting depth and total node visits.

    Uses an explicit stack so a deep structure never depends on the interpreter recursion limit, and stops on a
    node budget so an enormous or deeply nested structure is rejected rather than walked exhaustively. Cheap
    known-count checks run before this in :func:`_parse_document`.
    """
    stack: list[tuple[Any, int]] = [(value, 1)]
    visited = 0
    while stack:
        node, depth = stack.pop()
        visited += 1
        if visited > max_nodes:
            raise EquipmentProfileError(
                ProfileErrorCode.NESTING_LIMIT_EXCEEDED, source_kind=source_kind, count=max_nodes
            )
        if depth > max_depth:
            raise EquipmentProfileError(
                ProfileErrorCode.NESTING_LIMIT_EXCEEDED, source_kind=source_kind, count=max_depth
            )
        children = node.values() if isinstance(node, Mapping) else node if isinstance(node, (list, tuple)) else ()
        for child in children:
            if visited + len(stack) >= max_nodes:
                raise EquipmentProfileError(
                    ProfileErrorCode.NESTING_LIMIT_EXCEEDED, source_kind=source_kind, count=max_nodes
                )
            stack.append((child, depth + 1))


def _loads(text: str) -> Any:
    try:
        return json.loads(text, object_pairs_hook=_rejecting_pairs_hook, parse_constant=_reject_constant)
    except _DuplicateKeyError:
        raise EquipmentProfileError(ProfileErrorCode.DUPLICATE_JSON_KEY, source_kind=SOURCE_KIND_JSON) from None
    except _NonFiniteNumberError:
        raise EquipmentProfileError(ProfileErrorCode.INVALID_NUMBER, source_kind=SOURCE_KIND_JSON) from None
    except (ValueError, TypeError, RecursionError):
        raise EquipmentProfileError(ProfileErrorCode.MALFORMED_JSON, source_kind=SOURCE_KIND_JSON) from None


def _early_envelope_checks(document: Any, source_kind: str) -> None:
    """Cheap known-count checks that run before any structure traversal."""
    if not isinstance(document, Mapping):
        raise EquipmentProfileError(ProfileErrorCode.MALFORMED_JSON, source_kind=source_kind, field_path=())
    profiles = document.get("profiles")
    if isinstance(profiles, Sequence) and not isinstance(profiles, (str, bytes)):
        if len(profiles) > MAX_PROFILES:
            raise EquipmentProfileError(
                ProfileErrorCode.PROFILE_LIMIT_EXCEEDED, source_kind=source_kind, count=len(profiles)
            )
        # Aggregate grammar totals are also known before traversal: profile count plus the children of each
        # profile object (coordinate leaves and transmission rows) is bounded by the flat table's own ceilings.
        flat_total = 0
        for entry in profiles:
            if not isinstance(entry, Mapping):
                continue
            flat_total += 1
            coordinates = entry.get("coordinates")
            if isinstance(coordinates, Mapping):
                flat_total += sum(
                    len(block) if isinstance(block, Mapping) else 1 for block in coordinates.values()
                )
            rows = entry.get("transmission")
            if isinstance(rows, Sequence) and not isinstance(rows, (str, bytes)):
                flat_total += len(rows)
        if flat_total > MAX_AGGREGATE_ROWS:
            raise EquipmentProfileError(
                ProfileErrorCode.ROW_LIMIT_EXCEEDED, source_kind=source_kind, count=flat_total
            )


def _parse_document(document: Any, *, source_kind: str) -> ParsedDocument:
    if source_kind not in (SOURCE_KIND_JSON, SOURCE_KIND_MEMORY):
        raise EquipmentProfileError(ProfileErrorCode.UNSUPPORTED_SOURCE_SUFFIX, source_kind=source_kind)
    _early_envelope_checks(document, source_kind)
    _enforce_depth(document, MAX_JSON_DEPTH, source_kind=source_kind, max_nodes=MAX_TRAVERSAL_NODES)
    profiles = validate_document(document, source_kind=source_kind)
    logical_rows = sum(profile.logical_row_count() for profile in profiles)
    if logical_rows > MAX_AGGREGATE_ROWS:
        raise EquipmentProfileError(
            ProfileErrorCode.ROW_LIMIT_EXCEEDED, source_kind=source_kind, count=logical_rows
        )
    return ParsedDocument(
        profiles=profiles,
        source_kind=source_kind,
        source_hash=None,
        logical_rows=logical_rows,
    )


def parse_json_bytes(raw: bytes) -> ParsedDocument:
    """Parse and validate a JSON document from raw bytes.

    Raises value-free errors for empty, oversized, non-UTF-8, malformed, duplicate-keyed, or
    too-deeply-nested input. The source hash covers the exact bytes, BOM included.
    """
    if not raw:
        raise EquipmentProfileError(ProfileErrorCode.EMPTY_SOURCE, source_kind=SOURCE_KIND_JSON)
    if len(raw) > MAX_SOURCE_BYTES:
        raise EquipmentProfileError(
            ProfileErrorCode.OVERSIZED_SOURCE, source_kind=SOURCE_KIND_JSON, count=MAX_SOURCE_BYTES
        )
    document = _loads(_decode_source(raw, source_kind=SOURCE_KIND_JSON))
    parsed = _parse_document(document, source_kind=SOURCE_KIND_JSON)
    return ParsedDocument(
        profiles=parsed.profiles,
        source_kind=SOURCE_KIND_JSON,
        source_hash=source_bytes_hash(raw),
        logical_rows=parsed.logical_rows,
    )


def parse_json_file(path: str | os.PathLike[str]) -> ParsedDocument:
    """Read, parse, and validate a JSON profile file.

    The path is never included in an error. The file is read with one bounded read of at most
    ``MAX_SOURCE_BYTES + 1`` bytes, so an oversized source is rejected from the read length itself rather than
    by stat-ing the file first (which would race a growing file). Unreadable files and any I/O failure collapse
    to a single value-free ``unreadable_source`` error.
    """
    candidate = Path(path)
    if candidate.suffix.lower() not in JSON_SOURCE_SUFFIXES:
        raise EquipmentProfileError(
            ProfileErrorCode.UNSUPPORTED_SOURCE_SUFFIX, source_kind=SOURCE_KIND_JSON
        )
    try:
        with candidate.open("rb") as handle:
            raw = handle.read(MAX_SOURCE_BYTES + 1)
    except (OSError, ValueError):
        raise EquipmentProfileError(ProfileErrorCode.UNREADABLE_SOURCE, source_kind=SOURCE_KIND_JSON) from None
    if len(raw) > MAX_SOURCE_BYTES:
        raise EquipmentProfileError(
            ProfileErrorCode.OVERSIZED_SOURCE, source_kind=SOURCE_KIND_JSON, count=MAX_SOURCE_BYTES
        )
    return parse_json_bytes(raw)


def parse_memory_document(document: Any) -> ParsedDocument:
    """Parse and validate an already-structured in-memory document.

    Duplicate keys cannot exist in a Python mapping, so that check does not apply here; every other rule in
    the contract still does. The returned profiles share no mutable container with ``document``.
    """
    return _parse_document(document, source_kind=SOURCE_KIND_MEMORY)
