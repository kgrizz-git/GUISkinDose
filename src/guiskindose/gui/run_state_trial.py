"""Trial (pre-mutation) import validation for run-state documents.

Moved here from :mod:`guiskindose.gui.run_state` to hold the module size cap;
:func:`_trial_apply_settings` is byte-identical. :func:`trial_confirm_equipment`
validates a v2 equipment section against the loaded prefix — current frames,
identity, counts, geometry, and intended doc transforms — before the applier
mutates anything. Both helpers are synchronous, GUI-light, and open no
files, stores, or bundles.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from guiskindose.equipment_capture import capture_to_mapping, frame_geometry_rows, geometry_digest_v1
from guiskindose.equipment_confirmation import (
    confirm_captured_application,
    prepare_captured_candidate,
)
from guiskindose.equipment_profiles.capture_checks import (
    CODE_EQUIPMENT_GEOMETRY_MISMATCH,
    CODE_INVALID_EQUIPMENT_CAPTURE,
    CaptureError,
)
from guiskindose.gui.exam_transforms import _apply_transform_flags
from guiskindose.gui.run_state_equipment import (
    decode_equipment_section,
    translate_capture_error,
)
from guiskindose.gui.run_state_errors import RunStateError
from guiskindose.privacy import opaque_exam_label

if TYPE_CHECKING:
    from guiskindose.gui.state import AppState

__all__ = ["check_exam_count_alignment", "restore_equipment", "trial_confirm_equipment"]

_GEOMETRY_FLAG_KEYS = (
    "swap_lat_lon",
    "flip_ap1",
    "flip_ap2",
    "flip_tx",
    "flip_ty",
    "flip_tz",
)


def _trial_apply_settings(settings: dict, profiles: Any, app_state: AppState) -> None:
    """Validate the merged post-import state by building settings on a copy.

    Applies the settings slice to a shallow copy — scalar rebinding only, so
    the live session cannot be affected — then constructs the real settings
    object from it. Constructor failures (invalid plane-code map, out-of-range
    angular step, non-bool flags) become `RunStateError` here at import time
    instead of surfacing later at calculation with half-applied state behind
    them. The message keeps the underlying detail for logs/tests; the GUI
    surfaces only the fixed per-code message.
    """
    import copy

    from guiskindose.constants import (
        KEY_NORMALIZATION_DETECTOR_SIDE_LENGTH,
        KEY_NORMALIZATION_FIELD_SIZE_MODE,
        KEY_NORMALIZATION_MANUFACTURER,
        KEY_NORMALIZATION_MODELS,
    )
    from guiskindose.gui.run_state import _apply_settings_slice
    from guiskindose.gui.settings_builder import build_settings

    trial = copy.copy(app_state)
    _apply_settings_slice(settings, trial, [])
    if profiles:
        # The constructor stores the list verbatim, so required keys are
        # checked here — otherwise a keyless profile would import cleanly and
        # raise KeyError inside update_used_settings at the next file load.
        required = (
            KEY_NORMALIZATION_MANUFACTURER,
            KEY_NORMALIZATION_MODELS,
            KEY_NORMALIZATION_FIELD_SIZE_MODE,
            KEY_NORMALIZATION_DETECTOR_SIDE_LENGTH,
        )
        for index, profile in enumerate(profiles):
            missing = [key for key in required if key not in profile]
            if missing:
                raise RunStateError(
                    f"normalization_settings[{index}] missing required keys: {', '.join(missing)}",
                    code="invalid_settings",
                )
        trial.normalization_profiles = profiles
    try:
        build_settings(trial)
    except Exception:
        raise RunStateError("Imported settings failed validation.", code="invalid_settings") from None


def _intended_geometry(doc_exam: Any, meta: Any) -> tuple[dict[str, bool], Any]:
    """Document-effective geometry flags/override, mirroring the applier.

    Toggle keys present and non-null in the document win; absent keys keep
    the live meta value. ``table_origin_override`` follows key presence
    (an explicit null clears a live override). Offsets never affect geometry
    and are not carried here.
    """
    document = doc_exam if type(doc_exam) is dict else {}
    live = meta if type(meta) is dict else {}
    flags = {
        key: bool(document[key]) if document.get(key) is not None else bool(live.get(key, False))
        for key in _GEOMETRY_FLAG_KEYS
    }
    override = document["table_origin_override"] if "table_origin_override" in document else live.get(
        "table_origin_override"
    )
    return flags, override


def _live_geometry(meta: Any) -> tuple[dict[str, bool], Any]:
    """Current effective geometry flags/override of one loaded exam."""
    live = meta if type(meta) is dict else {}
    return (
        {key: bool(live.get(key, False)) for key in _GEOMETRY_FLAG_KEYS},
        live.get("table_origin_override"),
    )


def _effective_exam_intent(document: Any, exam: Any, app_state: AppState) -> dict[str, Any]:
    """Mirror the final single-exam global-to-meta coupling before mutation."""
    intent = dict(exam) if type(exam) is dict else {}
    if len(app_state.loaded_exam_meta) == 1:
        gui = document.get("gui_state") or {}
        for key in ("swap_lat_lon", "flip_ap1", "flip_ap2"):
            value = gui.get(key)
            intent[key] = getattr(app_state, key) if value is None else value
    return intent


def check_retained_geometry_intent(document: Any, version: Any, app_state: AppState) -> None:
    """Unspecified capture slots preserve authority, never bypass flag checks."""
    if version != 2:
        return
    exams = (document.get("gui_state") or {}).get("exams") or []
    for position, (exam, meta, loaded) in enumerate(
        zip(exams, app_state.loaded_exam_meta, app_state.loaded_exams, strict=False)
    ):
        capture = getattr(loaded, "equipment_capture", None)
        if capture is not None:
            intent = _effective_exam_intent(document, exam, app_state)
            _prove_doc_geometry(capture, intent, meta, position)


def _prove_doc_geometry(
    context: Any, doc_exam: Any, meta: Any, position: int
) -> None:
    """Prove intended doc transforms reproduce the confirmed geometry.

    Trial-applies the document-effective flags/override to a copy of the
    pristine base frame (the live frame is never touched) and requires the
    resulting digest to equal the capture's checksum; anything else —
    including a missing base when a change was requested — rejects the whole
    import with an opaque position. Digest-identical intents pass through.
    """
    intended_flags, intended_override = _intended_geometry(doc_exam, meta)
    live_flags, live_override = _live_geometry(meta)
    if intended_flags == live_flags and intended_override == live_override:
        return
    live = meta if type(meta) is dict else {}
    base = live.get("base_data")
    if base is None:
        raise RunStateError(
            f"Equipment capture geometry cannot be verified ({opaque_exam_label(position)}).",
            code=CODE_EQUIPMENT_GEOMETRY_MISMATCH,
        )
    try:
        trial = _apply_transform_flags(
            base,
            intended_flags["swap_lat_lon"],
            intended_flags["flip_ap1"],
            intended_flags["flip_ap2"],
            live.get("schema", ""),
            table_origin_override=intended_override,
            table_origin_detected=live.get("table_origin_detected"),
            flip_tx=intended_flags["flip_tx"],
            flip_ty=intended_flags["flip_ty"],
            flip_tz=intended_flags["flip_tz"],
        )
        digest = geometry_digest_v1(frame_geometry_rows(trial, context.event_count))
    except (CaptureError, ValueError, TypeError, AttributeError, KeyError):
        raise RunStateError(
            f"Equipment capture geometry does not match ({opaque_exam_label(position)}).",
            code=CODE_EQUIPMENT_GEOMETRY_MISMATCH,
        ) from None
    if digest != context.geometry_hash:
        raise RunStateError(
            f"Equipment capture geometry does not match ({opaque_exam_label(position)}).",
            code=CODE_EQUIPMENT_GEOMETRY_MISMATCH,
        )


def _captures_equivalent(left: Any, right: Any) -> bool:
    """Canonical mapping equality with both sides revalidated (no memory trust).

    Rebuilds each side's canonical mapping (recomputing checksums, never
    trusting stored hashes) and compares the full mappings — recipe,
    identity, geometry, and provenance. Any revalidation failure counts as
    mismatch (closed refusal downstream), never as equality. Cancellation
    propagates.
    """
    try:
        return capture_to_mapping(left) == capture_to_mapping(right)
    except Exception:
        return False


def _confirm_loaded_position(
    context: Any, doc_exam: Any, meta: Any, frame: Any, norm: Any, position: int
) -> None:
    """Confirm one loaded position: current frame plus intended doc geometry."""
    try:
        candidate = prepare_captured_candidate(context=context, norm=norm)
        confirm_captured_application(context=context, frame=frame, candidate=candidate)
    except CaptureError as exc:
        # Translator accepts closed codes only and emits fixed text plus an opaque exam number.
        raise translate_capture_error(exc, position) from None  # nosemgrep: mypyskindose-raw-exception-to-diagnostic
    except (ValueError, TypeError, AttributeError, KeyError):
        raise RunStateError(
            f"Equipment capture section is invalid ({opaque_exam_label(position)}).",
            code=CODE_INVALID_EQUIPMENT_CAPTURE,
        ) from None
    _prove_doc_geometry(context, doc_exam, meta, position)


def check_exam_count_alignment(document: Any, version: Any, doc_count: int, live_count: int) -> None:
    """Enforce the exam-count gate: more live exams than document always fails.

    Fewer live exams proceed only for a v2 document with a present equipment
    envelope (the remainder stages as pending); v1 and equipment-less imports
    keep the strict historical gate, so partial settings can never apply
    silently. Value-free counts only.
    """
    if live_count > doc_count:
        raise RunStateError(
            f"exam count mismatch: document has {doc_count} exam(s), "
            f"session has {live_count} loaded — load the same inputs in the same order/count.",
            code="exam_count_mismatch",
        )
    from guiskindose.gui.run_state import RUN_STATE_SCHEMA_VERSION

    stages_pending = (
        version == RUN_STATE_SCHEMA_VERSION and document.get("equipment") is not None
    )
    if live_count < doc_count and not stages_pending:
        raise RunStateError(
            f"exam count mismatch: document has {doc_count} exam(s), "
            f"session has {live_count} loaded — load the same inputs in the same order/count.",
            code="exam_count_mismatch",
        )


def trial_confirm_equipment(
    section: Any, *, doc_exams: Any, app_state: AppState, document: Any = None
) -> tuple[tuple[Any, ...], Any]:
    """Trial-validate a v2 equipment section against the loaded prefix.

    Decodes against the document exam count (raising translated errors),
    rejects a bound nonempty session staging any non-null capture (authority
    conflict, closed pre-mutation), then confirms every loaded position —
    current-frame identity, count, geometry, and all 15 leaves, plus the
    intended document geometry proof — before the applier mutates anything.
    Unloaded tail positions validate structurally here and stage later via
    :func:`build_pending`. Pure except for reads: frames, metas, homes, and
    settings are never written. Returns the decoded contexts plus the trial
    normalization home (for snapshot publication without rebuilding).
    The caller guarantees no more live exams than document exams (count gate).
    """
    from guiskindose.gui.settings_builder import build_settings

    if type(doc_exams) is not list:
        raise RunStateError(
            "Equipment trial needs a document exam list.",
            code=CODE_INVALID_EQUIPMENT_CAPTURE,
        )
    contexts = decode_equipment_section(section, exam_count=len(doc_exams))
    if contexts is None:
        raise RunStateError(
            "Equipment trial needs a present envelope.",
            code=CODE_INVALID_EQUIPMENT_CAPTURE,
        )
    live_metas = app_state.loaded_exam_meta
    tail = contexts[len(live_metas):]
    session = app_state.equipment_profile_session
    if session is not None and len(session.profiles) > 0 and any(entry is not None for entry in tail):
        raise RunStateError(
            "Staged equipment captures conflict with the bound live session; "
            "unbind the session and re-import the configuration.",
            code=CODE_INVALID_EQUIPMENT_CAPTURE,
        )
    norm = build_settings(app_state).normalization_settings
    live_frames = [getattr(exam, "normalized_data", None) for exam in app_state.loaded_exams]
    live_exams = app_state.loaded_exams
    # Live prefix only: trailing unloaded positions stage later (non-strict
    # zip is exact here — the applier's count gate bounds live by doc count).
    for position, (context, meta, frame, exam) in enumerate(
        zip(contexts, live_metas, live_frames, live_exams, strict=False)
    ):
        if context is None:
            continue
        intent = _effective_exam_intent(document or {}, doc_exams[position], app_state)
        _confirm_loaded_position(context, intent, meta, frame, norm, position)
        live_capture = getattr(exam, "equipment_capture", None)
        if live_capture is not None and not _captures_equivalent(context, live_capture):
            raise RunStateError(
                f"Imported equipment capture conflicts with the loaded exam "
                f"({opaque_exam_label(position)}); unload and reload, or re-import without equipment.",
                code=CODE_INVALID_EQUIPMENT_CAPTURE,
            )
    return contexts, norm


def restore_equipment(document: Any, version: Any, *, doc_exams: Any, app_state: AppState) -> None:
    """Trial-validate and stage v2 equipment (no-op for v1/absent/null).

    Present envelopes confirm the loaded prefix and stage the unloaded tail
    as pending; anything else leaves every equipment home untouched (v1 and
    absent/null imports never clear pending, captures, or sessions). Called
    pre-mutation; any breach raises before the applier writes. The pending
    assignment here is safe to order before the settings trial: a later
    failure rolls the whole import back through the caller's snapshot.
    """
    from guiskindose.gui.run_state import RUN_STATE_SCHEMA_VERSION
    from guiskindose.gui.run_state_equipment import build_pending, publish_restored_captures

    if version != RUN_STATE_SCHEMA_VERSION:
        return
    section = document.get("equipment")
    if section is None:
        return
    contexts, norm = trial_confirm_equipment(
        section, doc_exams=doc_exams, app_state=app_state, document=document
    )
    live = len(app_state.loaded_exam_meta)
    app_state.equipment_pending = build_pending(contexts[live:], doc_exams[live:])
    publish_restored_captures(contexts=contexts, app_state=app_state, norm=norm)
