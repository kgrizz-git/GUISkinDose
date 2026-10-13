"""Per-exam equipment authority for GUI loaders (session-boundary helpers).

Owns the live-session check, the exam/event ceilings, receipt rebind plus
capture minting with per-exam snapshots, and post-transform confirmation of
staged captures. All helpers are pure with respect to GUI state except for
the exam objects the caller hands them for attachment; publication stays
with the loader candidates. No file, store, or bundle is opened here —
sessions arrive already assembled and receipts arrive from the caller's own
normalizer call. Synchronous and GUI-light.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import TYPE_CHECKING, Any

from guiskindose.equipment_capture import capture_from_receipt
from guiskindose.equipment_confirmation import (
    confirm_captured_application,
    prepare_captured_candidate,
)
from guiskindose.equipment_profiles.constants import MAX_AGGREGATE_ROWS, MAX_PROFILES
from guiskindose.equipment_resolution import bind_receipt_frame, restore_receipt_to_settings
from guiskindose.gui.exam_transforms import _apply_transform_flags
from guiskindose.gui.run_state_equipment import PendingEntry, revalidate_pending
from guiskindose.gui.run_state_errors import RunStateError
from guiskindose.privacy import UserFacingInputError, opaque_exam_label

if TYPE_CHECKING:
    import pandas as pd

    from guiskindose.equipment_profiles.capture import CapturedCoordinates
    from guiskindose.gui.state import AppState
    from guiskindose.settings.normalization_settings import NormalizationSettings


def _live_session(settings: Any) -> Any | None:
    """Bound nonempty custom-profile session, else None (empty behaves session-free)."""
    session = settings.equipment_profile_session
    if session is None or len(session.profiles) == 0:
        return None
    return session


def _bounds_authority(live: Any, pending: Any, replay_capture: Any) -> Any:
    """Authority token for ceiling enforcement (None skips entirely).

    Returns the live session when bound, else the staged capture being
    replayed, else the staged pending tuple itself when entries remain —
    null slots still stage authority (flags, offsets, positions), so their
    retained rows and exam counts enforce ceilings exactly like captures.
    Anything else returns None (pure loads keep today's behavior).
    """
    if live is not None:
        return live
    if replay_capture is not None:
        return replay_capture
    return pending or None


def _check_session_exam_count(loaded_count: int, new_count: int, *, session: Any) -> None:
    """O(1) exam ceiling before any frame access (count before traversal).

    Pure loads (no session) keep today's behavior untouched.
    """
    if session is None:
        return
    if loaded_count + new_count > MAX_PROFILES:
        raise UserFacingInputError(
            "Too many loaded exams for custom equipment-profile authority."
        )


def _check_session_event_total(
    state: AppState, new_frames: list[pd.DataFrame], *, session: Any
) -> None:
    """Early-exit retained-event ceiling over every row, captured or not.

    Callers run this only after the exam-count gate bounds the collection
    (so traversal stays bounded); the sum aborts at the first breach instead
    of completing. Every retained row counts, including capture-less entries —
    a null entry is unspecified authority, never a smaller footprint.
    """
    if session is None:
        return
    retained = 0
    for frame in new_frames:
        retained += len(frame)
        if retained > MAX_AGGREGATE_ROWS:
            raise UserFacingInputError(
                "Too many retained events for custom equipment-profile authority."
            )
    for exam in state.loaded_exams:
        retained += len(exam.normalized_data)
        if retained > MAX_AGGREGATE_ROWS:
            raise UserFacingInputError(
                "Too many retained events for custom equipment-profile authority."
            )


def _mint_session_capture(
    *, settings: Any, receipt: Any, frame: Any
) -> tuple[CapturedCoordinates | None, NormalizationSettings | None]:
    """Rebind a genuine loader receipt to the final frame and mint authority.

    Returns a ``(capture, snapshot)`` pair, or ``(None, None)`` without a
    session (pure loads keep byte-identical behavior). The snapshot is the
    receipt's proven leaves applied to an isolated normalization copy — the
    exam's genuine per-exam baseline, never shared last-load state. A missing
    receipt under an active session, an empty final frame, or any bridge
    breach fails closed with a fixed message: authority is minted or the load
    is refused, never silently skipped, and forged receipts can never enter
    here (callers pass only records their own normalizer call issued).
    """
    session = _live_session(settings)
    if session is None:
        return None, None
    if receipt is None:
        raise UserFacingInputError(
            "Custom equipment profiles did not resolve this input; no authority was produced."
        )
    try:
        rebound = bind_receipt_frame(receipt, frame)
        snapshot = copy.deepcopy(settings.normalization_settings)
        restore_receipt_to_settings(rebound, snapshot)
        work = copy.deepcopy(settings)
        work.normalization_settings = snapshot
        capture = capture_from_receipt(receipt=rebound, frame=frame, settings=work)
    except UserFacingInputError:
        raise
    except Exception:
        raise UserFacingInputError(
            "Custom equipment profiles could not be applied to this input."
        ) from None
    return capture, snapshot


def _mint_session_captures(state: AppState, settings: Any, start: int) -> None:
    """Mint and attach authority for exams appended at ``start:`` (session loads).

    No session: returns immediately. Otherwise every new exam must present its
    genuine adapter receipt; each is rebound to its final transformed frame
    and minted with its per-exam snapshot retained, receipts are discarded
    (captures never ride with live receipts), and authority attaches to the
    exam results. The first breach aborts; the caller discards the whole
    candidate so publication stays atomic.
    """
    if _live_session(settings) is None:
        return
    for exam in state.loaded_exams[start:]:
        capture, snapshot = _mint_session_capture(
            settings=settings, receipt=exam.equipment_receipt, frame=exam.normalized_data
        )
        exam.equipment_capture = capture
        exam.normalization_snapshot = snapshot
        exam.equipment_receipt = None


def _confirm_consumed_capture(*, context: Any, frame: Any, norm: Any, position: int) -> Any:
    """Confirm a staged capture against the final post-transform frame.

    Runs once, here, after the entry's flags/filter shaped the frame — never
    before transforms, and never doubled with the replay loader's own
    pre-transform confirmation. A mismatch fails the load closed with a
    fixed message (opaque position); the candidate is discarded, so live
    state is untouched. Returns the isolated snapshot to retain.
    """
    try:
        snapshot = prepare_captured_candidate(context=context, norm=norm)
        confirm_captured_application(context=context, frame=frame, candidate=snapshot)
    except Exception:
        raise UserFacingInputError(
            f"Staged equipment capture does not match the loaded input ({opaque_exam_label(position)}); "
            "load the same inputs in the same order, or re-import without equipment."
        ) from None
    return snapshot

def _peek_pending_entry(state: AppState, live: Any) -> tuple[Any, Any, Any]:
    """Peek, revalidate, and conflict-check the staged head slot (pre-I/O).

    Returns ``(pending, entry, replay_capture)`` for FIFO consumption.
    Revalidation runs before any file read so forged bypass inputs fail
    here rather than mid-load; a staged capture against a bound live
    session refuses closed. Pure with respect to live state.
    """
    pending = state.equipment_pending
    entry = pending[0] if pending else None
    if entry is not None:
        try:
            entry = revalidate_pending(entry)
        except RunStateError:
            raise UserFacingInputError(
                "Staged equipment entries are invalid; re-import the configuration."
            ) from None
    replay_capture = entry.capture if entry is not None else None
    if replay_capture is not None and live is not None:
        raise UserFacingInputError(
            "Staged equipment captures conflict with the bound live session; "
            "unbind the session, then reload the file."
        )
    return pending, entry, replay_capture

def _read_tabular_results(
    *,
    file_path: Path,
    schema: str,
    work: AppState,
    settings: Any,
    replay_capture: Any,
    pending: Any,
) -> Any:
    """Read and normalize one tabular file, replaying staged captures.

    A capture slot normalizes under the staged recipe with final
    confirmation deferred to the caller (which confirms the post-transform
    frame); anything else loads with live behavior. A multi-study split
    with staged entries refuses the whole file closed. Returns the single
    result or raw list (without pending staged entries).
    """
    from guiskindose.input_adapters.registry import read_and_normalize_input

    if replay_capture is not None:
        call_settings = copy.copy(settings)
        call_settings.equipment_profile_session = None
        raw = read_and_normalize_input(
            file_path,
            input_schema=schema,
            settings=call_settings,
            sheet_name=work.input_sheet_name,
            equipment_capture_context=replay_capture,
            defer_capture_confirmation=True,
        )
    else:
        raw = read_and_normalize_input(
            file_path,
            input_schema=schema,
            settings=settings,
            sheet_name=work.input_sheet_name,
        )
    if pending and isinstance(raw, list):
        raise UserFacingInputError(
            "A multi-study file cannot consume staged equipment entries; "
            "load single-exam inputs in document order, or re-import without equipment."
        )
    return raw

def _resolve_dicom_authority(
    *,
    settings: Any,
    authority: Any,
    entry: PendingEntry | None,
    replay_capture: CapturedCoordinates | None,
    df: pd.DataFrame,
    norm: Any,
    work: AppState,
    receipt: Any,
) -> tuple[pd.DataFrame, CapturedCoordinates | None, NormalizationSettings | None, dict[str, bool], Any]:
    """Filter, transform, bound, and authorize one DICOM frame (candidate-only).

    Applies final filtering, then the pending entry's flags once (fresh
    loads keep the frame as normalized), enforces the O(1) exam recount and
    the bounded retained-event sum, then confirms the staged capture or
    mints on the rebound receipt. Pure with respect to live state: only the
    candidate ``work`` is read. Returns ``(final, capture, snapshot, flags,
    override)`` for result/meta construction.
    """
    if settings.remove_invalid_rows and len(df[df.kVp == 0]):
        df = df[df.kVp != 0].reset_index(drop=True)
    if entry is None:
        final = df
        flag_values = dict.fromkeys(PendingEntry.geometry_keys(), False)
        override_value: Any = None
    else:
        entry_flags = entry.geometry_flags()
        detected = {
            "x": float(norm.trans_offset.x),
            "y": float(norm.trans_offset.y),
            "z": float(norm.trans_offset.z),
        }
        if not any(entry_flags.values()) and entry.table_origin_override is None:
            final = df
        else:
            final = _apply_transform_flags(
                df,
                entry_flags["swap_lat_lon"],
                entry_flags["flip_ap1"],
                entry_flags["flip_ap2"],
                "dicom_rdsr",
                table_origin_override=entry.table_origin_override,
                table_origin_detected=detected,
                flip_tx=entry_flags["flip_tx"],
                flip_ty=entry_flags["flip_ty"],
                flip_tz=entry_flags["flip_tz"],
            )
        flag_values = entry_flags
        override_value = entry.table_origin_override
    # Captured authority enforces ceilings without a live session; staged
    # presence enforces them too (null slots still stage authority). The
    # caller passes the precomputed token.
    _check_session_exam_count(len(work.loaded_exams), 1, session=authority)
    _check_session_event_total(work, [final], session=authority)
    if replay_capture is not None:
        snapshot = _confirm_consumed_capture(
            context=replay_capture, frame=final, norm=norm, position=len(work.loaded_exams)
        )
        return final, replay_capture, snapshot, flag_values, override_value
    capture, snapshot = _mint_session_capture(
        settings=settings,
        receipt=receipt,
        frame=final,
    )
    return final, capture, snapshot, flag_values, override_value
