"""Settings-JSON equipment-profile source requests (experimental).

Parses an explicit optional ``equipment_profiles`` settings block into one
assembled candidate session. This helper does not bind sessions itself: it never touches
settings objects, constructors, serialization, or outputs, so request paths
live transiently in the caller's config only. Exact request grammar::

    equipment_profiles = {
        "files": [{"path": str, "format"?: "json"|"csv"|"tsv"|"xlsx",
                   "sheet"?: int|string}, ...],
        "store": {"path": str, "ids"?: [str, ...]},
    }

An absent (``None``) block returns ``None`` without any I/O; an explicit
empty mapping assembles an empty session. There is deliberately no
``schema_version``: the grammar is code-versioned and unknown keys fail
closed, so a version field would promise evolution this slice does not
implement. Mappings require exact builtin types with exact-string keys
(str subclasses and hostile key equality are not JSON keys), and key
counts are gated against the allowlist before any iteration. Paths must be
non-empty exact strings with valid unicode and no NUL; relative paths
resolve against the explicit settings base directory — validated first,
without touching the filesystem — or against the working directory for
inline JSON/dict configs, and absolute paths ignore the base. Every request
shape and bound validates fully before any profile or store I/O, including
inferred formats and integer sheet ranges; the store opens only through the
read-only factory and its frozen snapshot composes with files in one
:meth:`assemble_session` call, preserving every source, conflict, and
capability gate. The frozen :class:`_ValidatedRequest` seam carries resolved
plain paths plus the optional store selection (counts-only repr);
:func:`_assemble_composed` assembles up to two validated sides once, so a
single CLI+config candidate shares this path. The seam stays internal; only
the parser is the validation boundary, not the dataclass constructor.

Failures are :class:`EquipmentProfileError` (never paths, cells, IDs,
notes, or causes), and the CLI boundary applies its existing value-free converter.

.. note::
   Headless CLI wiring validates the settings block explicitly before the
   legacy construction runs, so an invalid block fails closed instead of
   falling back to example settings. The ``ValueError``-swallowing fallback
   in ``parse_settings_to_settings_class`` is untouched and still applies
   only to non-profile settings failures.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from guiskindose.equipment_profiles import (
    EquipmentProfileSession,
    FileSource,
    ProfileStore,
    assemble_session,
)
from guiskindose.equipment_profiles.constants import (
    JSON_SOURCE_SUFFIXES,
    MAX_SOURCES,
    MAX_XLSX_SHEETS,
    SOURCE_KIND_CSV,
    SOURCE_KIND_JSON,
    SOURCE_KIND_TSV,
    SOURCE_KIND_XLSX,
    TABULAR_SUFFIX_TO_KIND,
    XLSX_SOURCE_SUFFIXES,
)
from guiskindose.equipment_profiles.errors import EquipmentProfileError, ProfileErrorCode
from guiskindose.equipment_profiles.store_schema import normalize_selection

__all__ = ["equipment_session_from_config", "split_json_block"]


class _DuplicateJsonKey(Exception):
    """Internal sentinel for duplicate JSON object keys (never escapes)."""


def _unique_object(pairs: list[tuple[Any, Any]]) -> dict[Any, Any]:
    """object_pairs_hook rejecting duplicate keys; JSON keys are always plain str."""
    seen: set[Any] = set()
    for key, _value in pairs:
        if key in seen:
            raise _DuplicateJsonKey()
        seen.add(key)
    return dict(pairs)


def split_json_block(text: str) -> tuple[Any | None, str]:
    """Split an equipment_profiles block off JSON settings text.

    Returns (block_or_None, working_text_without_block). Malformed JSON
    raises ValueError so callers preserve legacy handling; a profile-bearing
    document with duplicate keys anywhere raises closed
    ``DUPLICATE_JSON_KEY`` (never the raw parser cause, never echoed keys)
    instead of silently last-wins. Unrelated documents pass through
    byte-identical.
    """
    parsed = json.loads(text)
    if not isinstance(parsed, dict) or "equipment_profiles" not in parsed:
        return None, text
    try:
        json.loads(text, object_pairs_hook=_unique_object)
    except _DuplicateJsonKey:
        raise EquipmentProfileError(
            ProfileErrorCode.DUPLICATE_JSON_KEY, source_kind="memory", field_path=()
        ) from None
    block = parsed.pop("equipment_profiles")
    return block, json.dumps(parsed)


_BLOCK_FIELDS = ("files", "store")
_FILE_FIELDS = ("path", "format", "sheet")
_STORE_FIELDS = ("path", "ids")
_FILE_FORMATS = (SOURCE_KIND_JSON, SOURCE_KIND_CSV, SOURCE_KIND_TSV, SOURCE_KIND_XLSX)
_SUFFIX_TO_KIND: dict[str, str] = (
    dict.fromkeys(JSON_SOURCE_SUFFIXES, SOURCE_KIND_JSON)
    | dict(TABULAR_SUFFIX_TO_KIND)
    | dict.fromkeys(XLSX_SOURCE_SUFFIXES, SOURCE_KIND_XLSX)
)


@dataclass(frozen=True, repr=False)
class _ValidatedRequest:
    """Frozen pre-I/O request: resolved file sources plus optional store selection.

    Constructed only by :func:`_parse_request` after full validation, so
    later composition can trust it without revalidating. The repr carries
    counts only — never paths or IDs.
    """

    files: tuple[FileSource, ...]
    store_path: str | None
    store_ids: tuple[str, ...] | None

    def __repr__(self) -> str:
        return f"ValidatedRequest(files={len(self.files)}, store={self.store_path is not None})"


def _allowlisted(mapping: Any, allowed: tuple[str, ...], field_path: tuple[str, ...]) -> dict[str, Any]:
    """Require an exact builtin dict with exact-string keys inside the allowlist.

    Exact-type first (subclasses and hostile key equality are not JSON
    keys), then a fixed key-count gate — exceeding the allowlist guarantees
    an unknown key, so unbounded maps fail without iteration — then per-key
    membership. All before any value is read.
    """
    if type(mapping) is not dict:
        raise EquipmentProfileError(
            ProfileErrorCode.INVALID_TYPE, source_kind="memory", field_path=field_path
        )
    if len(mapping) > len(allowed):
        raise EquipmentProfileError(
            ProfileErrorCode.UNKNOWN_FIELD, source_kind="memory", field_path=field_path
        )
    for key in mapping:
        if type(key) is not str:
            raise EquipmentProfileError(
                ProfileErrorCode.INVALID_TYPE, source_kind="memory", field_path=field_path
            )
        if key not in allowed:
            raise EquipmentProfileError(
                ProfileErrorCode.UNKNOWN_FIELD, source_kind="memory", field_path=field_path
            )
    return mapping


def _checked_path(text: Any, field_path: tuple[str, ...]) -> str:
    """Require an exact non-empty NUL-free valid-unicode string path; never echoes."""
    if type(text) is not str or text == "" or "\x00" in text:
        raise EquipmentProfileError(
            ProfileErrorCode.INVALID_TYPE, source_kind="memory", field_path=field_path
        )
    try:
        text.encode("utf-8")
    except UnicodeEncodeError:
        raise EquipmentProfileError(
            ProfileErrorCode.INVALID_TYPE, source_kind="memory", field_path=field_path
        ) from None
    return text


def _validated_base(base: Any) -> Path | None:
    """Validate the explicit base directory without touching the filesystem.

    ``None`` selects working-directory resolution. Hostile hooks, bytes,
    NUL, and surrogate-carrying text fail closed with suppressed causes and
    no path echo; `KeyboardInterrupt` and `SystemExit` pass through untouched.
    """
    if base is None:
        return None
    if type(base) is str:
        text = base
    elif isinstance(base, os.PathLike):
        try:
            text = os.fspath(base)
        except Exception:
            raise EquipmentProfileError(
                ProfileErrorCode.INVALID_TYPE,
                source_kind="memory",
                field_path=("equipment_profiles",),
            ) from None
    else:
        raise EquipmentProfileError(
            ProfileErrorCode.INVALID_TYPE,
            source_kind="memory",
            field_path=("equipment_profiles",),
        )
    if type(text) is not str or "\x00" in text:
        raise EquipmentProfileError(
            ProfileErrorCode.INVALID_TYPE,
            source_kind="memory",
            field_path=("equipment_profiles",),
        )
    try:
        text.encode("utf-8")
    except UnicodeEncodeError:
        raise EquipmentProfileError(
            ProfileErrorCode.INVALID_TYPE,
            source_kind="memory",
            field_path=("equipment_profiles",),
        ) from None
    return Path(text)


def _resolve_request_path(text: str, base: Path | None) -> str:
    """Resolve validated request text against the base with pure string ops (no I/O)."""
    candidate = Path(text)
    if candidate.is_absolute() or base is None:
        return text
    return str(base / text)


def _checked_sheet(candidate: Any) -> int | str:
    """Require an exact non-negative int or non-empty exact str sheet selector."""
    if type(candidate) is int and candidate >= 0:
        return candidate
    if type(candidate) is str and candidate != "" and "\x00" not in candidate:
        try:
            candidate.encode("utf-8")
        except UnicodeEncodeError:
            pass
        else:
            return candidate
    raise EquipmentProfileError(
        ProfileErrorCode.VALUE_OUT_OF_RANGE,
        source_kind="memory",
        field_path=("equipment_profiles", "files"),
    )


def _file_source(entry: Any, base: Path | None) -> FileSource:
    """Validate one file-request mapping into a resolved ``FileSource`` (no I/O)."""
    fields = ("equipment_profiles", "files")
    mapping = _allowlisted(entry, _FILE_FIELDS, fields)
    if "path" not in mapping:
        raise EquipmentProfileError(
            ProfileErrorCode.MISSING_REQUIRED_FIELD, source_kind="memory", field_path=fields
        )
    text = _resolve_request_path(_checked_path(mapping["path"], fields), base)
    source_format: str | None = None
    if "format" in mapping:
        if type(mapping["format"]) is not str or mapping["format"] not in _FILE_FORMATS:
            raise EquipmentProfileError(
                ProfileErrorCode.INVALID_ENUM, source_kind="memory", field_path=fields
            )
        source_format = mapping["format"]
    sheet: int | str | None = None
    if "sheet" in mapping:
        sheet = _checked_sheet(mapping["sheet"])
    suffix_kind = _SUFFIX_TO_KIND.get(Path(text).suffix.lower())
    if source_format is None and suffix_kind is None:
        raise EquipmentProfileError(
            ProfileErrorCode.UNSUPPORTED_SOURCE_SUFFIX, source_kind="memory", field_path=()
        )
    effective = source_format if source_format is not None else suffix_kind
    if sheet is not None and effective != SOURCE_KIND_XLSX:
        raise EquipmentProfileError(
            ProfileErrorCode.INVALID_TYPE, source_kind="memory", field_path=fields
        )
    if type(sheet) is int and sheet >= MAX_XLSX_SHEETS:
        raise EquipmentProfileError(
            ProfileErrorCode.VALUE_OUT_OF_RANGE, source_kind="memory", field_path=fields
        )
    return FileSource(path=text, format=source_format, sheet=sheet)


def _store_selection(block: dict[str, Any]) -> tuple[str, ...] | None:
    """Validate the store ID selector; None when the store block carries none."""
    if "store" not in block:
        return None
    request = _allowlisted(block["store"], _STORE_FIELDS, ("equipment_profiles", "store"))
    if "ids" not in request:
        return None
    raw_ids = request["ids"]
    if type(raw_ids) not in (list, tuple):
        raise EquipmentProfileError(
            ProfileErrorCode.INVALID_TYPE,
            source_kind="memory",
            field_path=("equipment_profiles", "store"),
        )
    if len(raw_ids) <= MAX_SOURCES and any(type(name) is not str for name in raw_ids):
        raise EquipmentProfileError(
            ProfileErrorCode.INVALID_PROFILE_ID, source_kind="memory",
            field_path=("equipment_profiles", "store"),
        )
    return normalize_selection(raw_ids)


def _store_path(block: dict[str, Any], base: Path | None) -> str | None:
    """Validate and resolve the store path; None without a store block."""
    if "store" not in block:
        return None
    fields = ("equipment_profiles", "store")
    mapping = _allowlisted(block["store"], _STORE_FIELDS, fields)
    if "path" not in mapping:
        raise EquipmentProfileError(
            ProfileErrorCode.MISSING_REQUIRED_FIELD, source_kind="memory", field_path=fields
        )
    return _resolve_request_path(_checked_path(mapping["path"], fields), base)


def _parse_request(config: Any, base: Path | None) -> _ValidatedRequest:
    """Validate everything and freeze a no-I/O request for later assembly."""
    block = _allowlisted(config, _BLOCK_FIELDS, ("equipment_profiles",))
    raw_files: list[Any] = []
    if "files" in block:
        declared = block["files"]
        if type(declared) not in (list, tuple):
            raise EquipmentProfileError(
                ProfileErrorCode.INVALID_TYPE,
                source_kind="memory",
                field_path=("equipment_profiles", "files"),
            )
        if len(declared) > MAX_SOURCES:
            raise EquipmentProfileError(
                ProfileErrorCode.PROFILE_LIMIT_EXCEEDED,
                source_kind="memory",
                field_path=("equipment_profiles", "files"),
                count=len(declared),
            )
        for entry in declared:
            if len(raw_files) >= MAX_SOURCES:
                raise EquipmentProfileError(
                    ProfileErrorCode.PROFILE_LIMIT_EXCEEDED,
                    source_kind="memory",
                    field_path=("equipment_profiles", "files"),
                    count=len(raw_files) + 1,
                )
            raw_files.append(entry)
    selection = _store_selection(block)
    store_path = _store_path(block, base)
    sources = tuple(_file_source(entry, base) for entry in raw_files)
    if len(sources) + (1 if store_path is not None else 0) > MAX_SOURCES:
        raise EquipmentProfileError(
            ProfileErrorCode.PROFILE_LIMIT_EXCEEDED,
            source_kind="memory",
            field_path=("equipment_profiles",),
            count=len(sources) + 1,
        )
    return _ValidatedRequest(files=sources, store_path=store_path, store_ids=selection)


def _check_composed_bounds(first: _ValidatedRequest | None, second: _ValidatedRequest | None) -> None:
    """Pure combined file-plus-snapshot gate shared with the assembler.

    Runs before settings construction, mutations, and all profile/store
    I/O: the total request count across both sides must stay within
    ``MAX_SOURCES``. Closed and value-free.
    """
    files = sum(len(request.files) for request in (first, second) if request is not None)
    stores = sum(1 for request in (first, second) if request is not None and request.store_path is not None)
    if files + stores > MAX_SOURCES:
        raise EquipmentProfileError(
            ProfileErrorCode.PROFILE_LIMIT_EXCEEDED,
            source_kind="memory",
            field_path=("equipment_profiles",),
            count=files + stores,
        )


def _assemble_composed(
    first: _ValidatedRequest | None, second: _ValidatedRequest | None
) -> EquipmentProfileSession | None:
    """Assemble two validated sides once; None unless a side is present.

    Files concatenate first-side-first (order affects diagnostics only);
    snapshots open in side order with at most one per side. The combined
    bound rechecks here so direct callers get the same gate as the early
    pre-construction check. Duplicate claims across sides fail the canonical
    conflicts — never deduped or overridden.
    """
    sides = [request for request in (first, second) if request is not None]
    if not sides:
        return None
    _check_composed_bounds(first, second)
    files = [source for request in sides for source in request.files]
    snapshots = []
    for request in sides:
        if request.store_path is not None:
            with ProfileStore.open_read_only(request.store_path) as store:
                snapshots.append(store.selected_snapshot(request.store_ids))
    return assemble_session(
        files=files,
        snapshots=snapshots,
        settings_base_dir=None,
    )


def equipment_session_from_config(
    config: Any,
    settings_base_dir: str | Path | None = None,
) -> EquipmentProfileSession | None:
    """Assemble one candidate session from a settings-JSON source block.

    ``None`` returns ``None`` without touching anything. The base directory
    validates first; every request then validates fully before any profile
    or store I/O, and a failed candidate publishes nothing.
    """
    if config is None:
        return None
    base = _validated_base(settings_base_dir)
    return _assemble_composed(None, _parse_request(config, base))
