"""GUI-light run-state equipment-envelope boundary (foundation, inert).

Decode/emit wrappers over the core capture codec (:func:`parse_envelope`)
and the application-layer emission boundary (:func:`envelope_to_mapping`)
for the run-state v2 ``equipment`` section (contract §3). No run-state
document is written or applied here: this helper only validates a section
against an exam count (decode) or serializes typed contexts into a canonical
envelope (emit), translating core :class:`CaptureError` codes to
:class:`RunStateError` with fixed value-free messages. The writer,
application, and atomic rollback stay open (contract §10); the user
atomic-migration contract is unchanged and this helper exposes no partial
v2 support.

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
pandas or NiceGUI runtime import; both wrappers are synchronous.
"""

from __future__ import annotations

from typing import Any

from guiskindose.equipment_capture import envelope_to_mapping
from guiskindose.equipment_profiles.capture import CapturedCoordinates
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

__all__ = ["decode_equipment_section", "emit_equipment_section"]

_MESSAGES = {
    CODE_INVALID_EQUIPMENT_CAPTURE: "Equipment capture section is invalid.",
    CODE_UNSUPPORTED_EQUIPMENT_CAPTURE_VERSION: "Equipment capture version is not supported.",
    CODE_EQUIPMENT_GEOMETRY_MISMATCH: "Equipment capture geometry does not match.",
}

_COUNT_MESSAGE = "Equipment capture section does not match the exam count."


def _checked_exam_count(exam_count: Any) -> int:
    """Require an exact exam count in 0..64; booleans and mistypes fail closed."""
    if type(exam_count) is not int or not 0 <= exam_count <= CAPTURE_MAX_CAPTURES:
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


def _translated(exc: CaptureError, position: int | None) -> RunStateError:
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
        raise _translated(exc, _localized_position(section, count)) from None
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
        raise _translated(exc, None) from None
