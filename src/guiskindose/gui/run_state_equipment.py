"""GUI-light run-state equipment-envelope boundary (v2 migration slice).

Decode/emit wrappers over the core capture codec (:func:`parse_envelope`)
and the application-layer emission boundary (:func:`envelope_to_mapping`)
for the run-state v2 ``equipment`` section (contract §3), plus the
fully-validated immutable pending-entry staging for unloaded positions.
No run-state document is written or applied here: this helper only validates
a section against an exam count (decode), serializes typed contexts into a
canonical envelope (emit), stages validated pending entries (build), or
derives the writer section from loaded exams — translating core
:class:`CaptureError` codes to :class:`RunStateError` with fixed value-free
messages throughout.

Diagnostic discipline (all hostile-safe, all bounded):

- Count before decode: an envelope-shaped section whose captures list
  length already mismatches the exam count rejects on count without any
  entry being parsed. Core validation stays full for aligned shapes.
- Budget first: after a parse failure the shared core budget guard re-runs
  before any localization, so node/depth failures skip the position probe
  instead of re-traversing unbounded content.
- Strict root gating: a failing entry is named only when the root is an
  exact dict with exactly the locked envelope keys (each an exact plain
  ``str``), a supported exact-int version, the coordinates mode token, and
  an exact-list captures of exactly ``exam_count`` entries. Root failures
  (version, mode, keys, budget, count) never mislabel an entry.
- No hostile key code ever runs: shape checks iterate (never look up by
  key), compare exact ``str`` against exact ``str`` only, and take values
  from iteration. Translated codes must be exact builtin ``str``; anything
  else maps to the invalid code.

Source/path/notes/station/serial values never enter diagnostics or reprs;
captured maker/model spellings are default-safe content the messages never
echo. No file, store, settings object, bundle, or live API is opened; no
NiceGUI runtime import; every wrapper is synchronous.
"""

from __future__ import annotations

import copy
import math
from dataclasses import dataclass
from typing import Any

from guiskindose.equipment_capture import envelope_to_mapping
from guiskindose.equipment_confirmation import prepare_captured_candidate
from guiskindose.equipment_profiles.capture import CapturedCoordinates, validate_constructed_context
from guiskindose.equipment_profiles.capture_checks import (
    CAPTURE_ENVELOPE_KEYS,
    CAPTURE_ENVELOPE_SCHEMA_VERSION,
    CAPTURE_MAX_CAPTURES,
    CAPTURE_MODE_COORDINATES,
    CODE_EQUIPMENT_GEOMETRY_MISMATCH,
    CODE_INVALID_EQUIPMENT_CAPTURE,
    CODE_UNSUPPORTED_EQUIPMENT_CAPTURE_VERSION,
    CaptureError,
    _check_document_budget,
)
from guiskindose.equipment_profiles.capture_codec import (
    capture_from_mapping,
    parse_envelope,
)
from guiskindose.gui.run_state_errors import RunStateError
from guiskindose.privacy import opaque_exam_label

__all__ = [
    "PendingEntry",
    "build_pending",
    "decode_equipment_section",
    "emit_equipment_section",
    "equipment_section_for_document",
    "publish_restored_captures",
    "revalidate_pending",
    "translate_capture_error",
    "validate_equipment_document",
    "warn_equipment_import",
]

_MESSAGES = {
    CODE_INVALID_EQUIPMENT_CAPTURE: "Equipment capture section is invalid.",
    CODE_UNSUPPORTED_EQUIPMENT_CAPTURE_VERSION: "Equipment capture version is not supported.",
    CODE_EQUIPMENT_GEOMETRY_MISMATCH: "Equipment capture geometry does not match.",
}

_COUNT_MESSAGE = "Equipment capture section does not match the exam count."


def _checked_exam_count(exam_count: Any) -> int:
    """Require an exact exam count in 0..64; booleans and mistypes fail closed."""
    if type(exam_count) is not int:
        raise RunStateError(_COUNT_MESSAGE, code=CODE_INVALID_EQUIPMENT_CAPTURE)
    if exam_count > CAPTURE_MAX_CAPTURES:
        raise RunStateError(
            "Too many exams for equipment capture section.",
            code=CODE_INVALID_EQUIPMENT_CAPTURE,
        )
    if exam_count < 0:
        raise RunStateError(_COUNT_MESSAGE, code=CODE_INVALID_EQUIPMENT_CAPTURE)
    return exam_count


def _supported_version(value: Any) -> bool:
    """Exact-int supported envelope version (booleans never qualify)."""
    return type(value) is int and value == CAPTURE_ENVELOPE_SCHEMA_VERSION


def _coordinates_mode(value: Any) -> bool:
    """Exact-str coordinates mode token."""
    return type(value) is str and value == CAPTURE_MODE_COORDINATES


def _root_pair_ok(key: Any, value: Any) -> bool:
    """One envelope root pair passes the diagnostic gate."""
    if type(key) is not str or key not in CAPTURE_ENVELOPE_KEYS:
        return False
    if key == "schema_version":
        return _supported_version(value)
    if key == "mode":
        return _coordinates_mode(value)
    return True


def _envelope_captures(section: Any) -> tuple[bool, Any]:
    """Envelope-likeness for the count pre-check (hostile-safe, bounded).

    Returns ``(True, captures)`` when the section is an exact dict with at
    most three keys — all exact plain strs in the locked envelope set — and
    a ``captures`` value taken from iteration (never by key lookup) that is
    an exact list; otherwise ``(False, None)``. Version/mode are deliberately
    not required: a misaligned list rejects on count before any semantic
    decoding, whatever the root claims. At most three pairs are ever walked.
    """
    if type(section) is not dict or len(section) > len(CAPTURE_ENVELOPE_KEYS):
        return False, None
    raw: Any = None
    found = False
    for key, value in section.items():
        if type(key) is not str or key not in CAPTURE_ENVELOPE_KEYS:
            return False, None
        if key == "captures":
            raw = value
            found = True
    if not found or type(raw) is not list:
        return False, None
    return True, raw


def _aligned_captures(section: Any, count: int) -> list[Any] | None:
    """Captures list only for a fully root-gated, count-aligned envelope."""
    if type(section) is not dict or len(section) != len(CAPTURE_ENVELOPE_KEYS):
        return None
    raw: Any = None
    for key, value in section.items():
        if not _root_pair_ok(key, value):
            return None
        if key == "captures":
            raw = value
    if type(raw) is not list or len(raw) != count:
        return None
    return raw


def _localized_position(section: Any, count: int) -> int | None:
    """Name the failing opaque position only under a proven bounded root.

    The core budget guard runs first: a node/depth failure skips
    localization rather than re-traversing unbounded content. Then the
    strict root gate must hold, so root failures never mislabel an entry.
    Per-entry probing reuses the core parser — never a second validator —
    over at most 64 entries (``count`` is already bounded), each guarded by
    the parser's own budget check.
    """
    try:
        _check_document_budget(section)
    except CaptureError:
        return None
    raw = _aligned_captures(section, count)
    if raw is None:
        return None
    for index, entry in enumerate(raw):
        if entry is None:
            continue
        try:
            capture_from_mapping(entry)
        except (ValueError, TypeError, AttributeError, KeyError):
            return index
    return None


def translate_capture_error(exc: CaptureError, position: int | None) -> RunStateError:
    """Map a core capture failure to a value-free run-state error.

    The cause is suppressed (``from None`` at the raise site) and only an
    opaque exam position rides along, when the failure localizes to one.
    The code must be an exact builtin ``str`` — hostile code objects and
    unknown plain strings both map to the invalid code.
    """
    raw_code = exc.code
    code = raw_code if type(raw_code) is str and raw_code in _MESSAGES else CODE_INVALID_EQUIPMENT_CAPTURE
    message = _MESSAGES[code]
    if position is not None:
        message = f"{message} ({opaque_exam_label(position)})"
    return RunStateError(message, code=code)


def decode_equipment_section(
    section: Any, *, exam_count: Any
) -> tuple[CapturedCoordinates | None, ...] | None:
    """Validate a run-state v2 equipment section into per-exam contexts.

    ``None`` means "unspecified" (never "clear"): the caller leaves live
    equipment state untouched. A present envelope-shaped section rejects on
    count before any entry decodes; otherwise the core validates the whole
    envelope strictly, and a malformed entry rejects the section with an
    opaque exam position and a value-free reason — but only when the
    diagnostic root gate proves the failure is entry-local. No file or store
    is opened; no application state is touched.
    """
    count = _checked_exam_count(exam_count)
    if section is None:
        return None
    found, raw = _envelope_captures(section)
    if found and len(raw) != count:
        raise RunStateError(_COUNT_MESSAGE, code=CODE_INVALID_EQUIPMENT_CAPTURE)
    try:
        parsed = parse_envelope(section)
    except CaptureError as exc:
        raise translate_capture_error(exc, _localized_position(section, count)) from None
    if len(parsed) != count:
        raise RunStateError(_COUNT_MESSAGE, code=CODE_INVALID_EQUIPMENT_CAPTURE)
    return parsed


def emit_equipment_section(captures: Any, *, exam_count: Any) -> dict[str, Any]:
    """Serialize per-exam contexts into a canonical equipment envelope.

    Accepts an exact list/tuple of ``CapturedCoordinates``-or-``None`` with
    exactly ``exam_count`` entries; every context is fully revalidated (never
    trusted from memory) before serialization, so a forged in-memory copy
    fails here rather than exporting. No file or store is opened.
    """
    count = _checked_exam_count(exam_count)
    if type(captures) not in (list, tuple):
        raise RunStateError(
            _MESSAGES[CODE_INVALID_EQUIPMENT_CAPTURE], code=CODE_INVALID_EQUIPMENT_CAPTURE
        )
    if len(captures) != count:
        raise RunStateError(_COUNT_MESSAGE, code=CODE_INVALID_EQUIPMENT_CAPTURE)
    for entry in captures:
        if entry is not None and type(entry) is not CapturedCoordinates:
            raise RunStateError(
                _MESSAGES[CODE_INVALID_EQUIPMENT_CAPTURE], code=CODE_INVALID_EQUIPMENT_CAPTURE
            )
    try:
        return envelope_to_mapping(captures)
    except CaptureError as exc:
        raise translate_capture_error(exc, None) from None


_GEOMETRY_TOGGLE_KEYS = (
    "swap_lat_lon",
    "flip_ap1",
    "flip_ap2",
    "flip_tx",
    "flip_ty",
    "flip_tz",
)


def _exact_flag(value: Any) -> bool:
    """Require an exact builtin boolean (truthy substitutes fail closed)."""
    if type(value) is not bool:
        raise RunStateError(
            "Equipment pending entry flags must be exact booleans.",
            code=CODE_INVALID_EQUIPMENT_CAPTURE,
        )
    return value


_OFFSET_MESSAGE = "Equipment pending entry offsets must be finite numbers."
_IMMUTABLE_MESSAGE = "Staged equipment overrides are immutable."


class ImmutableOverrideError(LookupError):
    """Raised when code attempts to delete from a staged override mapping."""


def _finite_offset(value: Any) -> float:
    """Require a finite non-boolean offset number."""
    if isinstance(value, bool) or type(value) not in (int, float):
        raise RunStateError(
            _OFFSET_MESSAGE,
            code=CODE_INVALID_EQUIPMENT_CAPTURE,
        )
    try:
        result = float(value)
    except (OverflowError, ValueError):
        raise RunStateError(
            _OFFSET_MESSAGE,
            code=CODE_INVALID_EQUIPMENT_CAPTURE,
        ) from None
    if not math.isfinite(result):
        raise RunStateError(
            _OFFSET_MESSAGE,
            code=CODE_INVALID_EQUIPMENT_CAPTURE,
        )
    return result


_OVERRIDE_KEYS = frozenset({"x", "y", "z"})


class _FrozenOverride(dict):
    """Immutable override mapping: writes fail closed, reads stay dict-like.

    Behaves like a plain read-only mapping (``[]``, ``.get``, ``in``,
    iteration) so transform consumers need no changes, but every mutator
    (``__setitem__``, ``pop``, ``clear``, ``update``, ``setdefault``) raises
    ``TypeError``; ``__delitem__`` raises :class:`ImmutableOverrideError` —
    staged authority cannot be
    rewritten through a retained reference. ``|=`` declines in-place
    (``NotImplemented``) so it falls back to ``|``, which rebinds the name to
    a new plain dict and leaves this mapping untouched, as ``+=`` on a tuple. Deep-copies (and copies) into
    an equal frozen copy, so snapshots and rollback keep working.
    """

    def __setitem__(self, key: Any, value: Any) -> None:
        raise TypeError(_IMMUTABLE_MESSAGE)

    def __delitem__(self, key: Any) -> None:
        raise ImmutableOverrideError(_IMMUTABLE_MESSAGE)

    def __ior__(self, other: Any) -> Any:
        return NotImplemented

    def pop(self, *args: Any) -> Any:
        raise TypeError(_IMMUTABLE_MESSAGE)

    def popitem(self) -> Any:
        raise TypeError(_IMMUTABLE_MESSAGE)

    def clear(self) -> None:
        raise TypeError(_IMMUTABLE_MESSAGE)

    def update(self, *args: Any, **kwargs: Any) -> None:
        raise TypeError(_IMMUTABLE_MESSAGE)

    def setdefault(self, *args: Any) -> Any:
        raise TypeError(_IMMUTABLE_MESSAGE)

    def __copy__(self) -> _FrozenOverride:
        return _FrozenOverride(dict(self))

    def __deepcopy__(self, memo: dict[int, Any]) -> _FrozenOverride:
        return _FrozenOverride({key: copy.deepcopy(value, memo) for key, value in self.items()})


def _checked_override(value: Any) -> _FrozenOverride | None:
    """Require an absent override or an exact-str allowlisted mapping.

    Every key must be an exact plain ``str`` in ``{x, y, z}`` (unknown keys
    fail closed; iteration compares exact strs only, so hostile keys never
    equate); present axes must be finite non-boolean numbers. Returns an
    immutable copy (never the caller's dict), or ``None`` for absent/empty.
    """
    if value is None:
        return None
    if type(value) not in (dict, _FrozenOverride):
        raise RunStateError(
            "Equipment pending entry overrides must be mappings.",
            code=CODE_INVALID_EQUIPMENT_CAPTURE,
        )
    cleaned: dict[str, float] = {}
    for key, item in value.items():
        if type(key) is not str or key not in _OVERRIDE_KEYS:
            raise RunStateError(
                "Equipment pending entry overrides use only x, y, and z.",
                code=CODE_INVALID_EQUIPMENT_CAPTURE,
            )
        cleaned[key] = _finite_offset(item)
    if not cleaned:
        return None
    return _FrozenOverride(cleaned)


@dataclass(frozen=True)
class PendingEntry:
    """Validated immutable staging for one not-yet-loaded document position.

    Carries the decoded capture (or ``None`` for an unspecified slot) plus
    the document's geometry flags, patient offsets, and table-origin
    override for that position, so a later raw load can reproduce the
    documented load faithfully. Construction runs full validation —
    including complete capture revalidation, never a type check alone — so
    forged bypass inputs fail here rather than at a later boundary. The
    stored override is an immutable copy, never a caller-owned dict.
    """

    capture: CapturedCoordinates | None
    swap_lat_lon: bool
    flip_ap1: bool
    flip_ap2: bool
    flip_tx: bool
    flip_ty: bool
    flip_tz: bool
    d_lon: float
    d_ver: float
    d_lat: float
    table_origin_override: dict[str, float] | None

    def __post_init__(self) -> None:
        """Enforce exact shapes and full capture validity (frozen: validate only)."""
        if self.capture is not None:
            try:
                validate_constructed_context(self.capture)
            except Exception:
                raise RunStateError(
                    "Equipment pending entry captures must be captured authorities.",
                    code=CODE_INVALID_EQUIPMENT_CAPTURE,
                ) from None
        for key in _GEOMETRY_TOGGLE_KEYS:
            _exact_flag(getattr(self, key))
        for key in ("d_lon", "d_ver", "d_lat"):
            _finite_offset(getattr(self, key))
        object.__setattr__(self, "table_origin_override", _checked_override(self.table_origin_override))

    def __repr__(self) -> str:
        """Count/token-only repr: presence and shape, never values."""
        capture = "none"
        if self.capture is not None:
            capture = f"{self.capture.event_count} events"
        override = "none" if self.table_origin_override is None else "set"
        enabled = sum(1 for key in _GEOMETRY_TOGGLE_KEYS if getattr(self, key))
        return f"PendingEntry(capture={capture}, toggles={enabled}, override={override})"

    @staticmethod
    def geometry_keys() -> tuple[str, ...]:
        """Toggle field names carried for load-time transforms."""
        return _GEOMETRY_TOGGLE_KEYS

    def geometry_flags(self) -> dict[str, bool]:
        """Toggle values as a plain mapping for the transform step."""
        return {key: getattr(self, key) for key in _GEOMETRY_TOGGLE_KEYS}


def revalidate_pending(entry: Any) -> PendingEntry:
    """Rebuild a staged entry through full construction validation.

    Loaders call this on the peeked head slot before any file I/O, so forged
    or mutated bypass inputs (including a tampered capture) fail closed
    before reads rather than mid-load. Returns the validated rebuild.
    """
    if type(entry) is not PendingEntry:
        raise RunStateError(
            "Staged equipment entries must be pending authorities.",
            code=CODE_INVALID_EQUIPMENT_CAPTURE,
        )
    return PendingEntry(
        capture=entry.capture,
        swap_lat_lon=entry.swap_lat_lon,
        flip_ap1=entry.flip_ap1,
        flip_ap2=entry.flip_ap2,
        flip_tx=entry.flip_tx,
        flip_ty=entry.flip_ty,
        flip_tz=entry.flip_tz,
        d_lon=entry.d_lon,
        d_ver=entry.d_ver,
        d_lat=entry.d_lat,
        table_origin_override=entry.table_origin_override,
    )


def _pending_entry(capture: Any, doc_exam: Any) -> PendingEntry:
    """Build one validated entry from a decoded capture and its document exam."""
    exam = doc_exam if type(doc_exam) is dict else {}
    flags = {key: _exact_flag(exam[key]) if key in exam else False for key in _GEOMETRY_TOGGLE_KEYS}
    return PendingEntry(
        capture=capture,
        swap_lat_lon=flags["swap_lat_lon"],
        flip_ap1=flags["flip_ap1"],
        flip_ap2=flags["flip_ap2"],
        flip_tx=flags["flip_tx"],
        flip_ty=flags["flip_ty"],
        flip_tz=flags["flip_tz"],
        d_lon=_finite_offset(exam["d_lon"]) if "d_lon" in exam else 0.0,
        d_ver=_finite_offset(exam["d_ver"]) if "d_ver" in exam else 0.0,
        d_lat=_finite_offset(exam["d_lat"]) if "d_lat" in exam else 0.0,
        table_origin_override=_checked_override(exam.get("table_origin_override")),
    )


def build_pending(contexts: Any, doc_exams: Any) -> tuple[PendingEntry, ...] | None:
    """Wrap decoded contexts positionally with document flags (staging helper).

    Takes already-decoded contexts (never re-decodes: validation and trial
    own decoding) plus the parallel document exams. ``None`` contexts mean
    unspecified (never staged). Length mismatch or a non-list exam home
    fails closed; an empty pair stages nothing (``None``). Callers pass only
    unloaded tail slices, so loaded positions never face entry validation.
    No application state is touched.
    """
    if contexts is None:
        return None
    if type(doc_exams) is not list:
        raise RunStateError(
            "Equipment pending entries need a document exam list.",
            code=CODE_INVALID_EQUIPMENT_CAPTURE,
        )
    if type(contexts) not in (list, tuple) or len(contexts) != len(doc_exams):
        raise RunStateError(
            "Equipment pending entries must align with document exams.",
            code=CODE_INVALID_EQUIPMENT_CAPTURE,
        )
    if len(contexts) > CAPTURE_MAX_CAPTURES or len(doc_exams) > CAPTURE_MAX_CAPTURES:
        raise RunStateError(
            "Too many equipment entries for one document.",
            code=CODE_INVALID_EQUIPMENT_CAPTURE,
        )
    staged = tuple(
        _pending_entry(capture, doc_exam) for capture, doc_exam in zip(contexts, doc_exams, strict=True)
    )
    if not staged:
        return None
    return staged


def equipment_section_for_document(exams: Any) -> dict[str, Any] | None:
    """Derive the writer equipment section from loaded exams, or ``None``.

    Collects each exam's minted capture positionally (foreign exam objects
    without the home read as unspecified — the writer never crashes export);
    with no authority anywhere the section is ``None`` (explicit null in the
    v2 document, never an absent key). Emission revalidates every context.
    """
    if type(exams) is not list:
        raise RunStateError(
            "Equipment emission needs a loaded exam list.",
            code=CODE_INVALID_EQUIPMENT_CAPTURE,
        )
    contexts = [getattr(exam, "equipment_capture", None) for exam in exams]
    if not any(context is not None for context in contexts):
        return None
    if len(exams) > CAPTURE_MAX_CAPTURES:
        raise RunStateError(
            "Too many loaded exams for equipment emission.",
            code=CODE_INVALID_EQUIPMENT_CAPTURE,
        )
    return emit_equipment_section(contexts, exam_count=len(contexts))


def publish_restored_captures(*, contexts: Any, app_state: Any, norm: Any) -> bool:
    """Attach matching captures to authority-less loaded exams (mutation phase).

    For each loaded position with a non-null context and no live authority,
    replaces the exam object with a shallow copy carrying the validated
    capture plus a fresh isolated snapshot (prepared from the passed norm
    home). Live authority is never overwritten; null entries change nothing;
    unloaded tail positions are not published here (they stage as pending).
    Bumps ``input_revision`` when anything publishes so id-keyed preview
    caches cannot collide on recycled object identities. The caller's
    snapshot covers partial publication (list-level restore returns the
    original exam objects). Returns True when at least one exam published.
    """
    published = False
    for position, (context, exam) in enumerate(zip(contexts, app_state.loaded_exams, strict=False)):
        if context is None:
            continue
        if getattr(exam, "equipment_capture", None) is not None:
            continue
        candidate = prepare_captured_candidate(context=context, norm=norm)
        edition = copy.copy(exam)
        edition.equipment_capture = context
        edition.normalization_snapshot = candidate
        app_state.loaded_exams[position] = edition
        published = True
    if published:
        app_state.input_revision += 1
    return published


def validate_equipment_document(document: Any, *, v2: bool, exam_count: int) -> None:
    """Decode a present v2 section against the document count (validate gate).

    No-op unless a v2 document carries a present (non-null) section; absent
    and null sections are unspecified and skip silently, and v1 documents
    keep today's reader untouched. Raises translated errors without touching
    application state.
    """
    if not v2:
        return
    section = document.get("equipment")
    if section is None:
        return
    decode_equipment_section(section, exam_count=exam_count)


def warn_equipment_import(document: Any, version: Any, app_state: Any, warnings: list) -> None:
    """Record v1 equipment retention notices (never errors, never mutation).

    A v1 document carrying a reserved ``equipment`` section keeps the
    historical unknown-field reader (forward tolerance) with a fixed
    warning; the section is never applied. A v1 document arriving while live
    equipment authority exists (bound session, staged pending, or minted
    captures) warns that the document predates capture and the live state
    is retained, never verified, never wiped. Fixed texts only.
    """
    if version != 1:
        return
    if document.get("equipment") is not None:
        warnings.append(
            "This run configuration carries an equipment section from a newer version; "
            "equipment state was left untouched."
        )
    if (
        app_state.equipment_profile_session is not None
        or app_state.equipment_pending is not None
        or any(getattr(exam, "equipment_capture", None) is not None for exam in app_state.loaded_exams)
    ):
        warnings.append(
            "This run configuration predates equipment capture; live equipment "
            "state was retained, never verified, never wiped."
        )
