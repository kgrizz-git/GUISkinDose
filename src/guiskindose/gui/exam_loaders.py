"""Load RDSR and tabular exams into AppState."""

from __future__ import annotations

import copy
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pandas as pd
import pydicom

from guiskindose.equipment_capture import capture_from_receipt
from guiskindose.equipment_profiles.constants import MAX_AGGREGATE_ROWS, MAX_PROFILES
from guiskindose.equipment_resolution import bind_receipt_frame, restore_receipt_to_settings
from guiskindose.privacy import UserFacingInputError, safe_error_event
from guiskindose.rdsr_normalizer import RdsrUnitError, rdsr_normalizer
from guiskindose.rdsr_parser import rdsr_parser

if TYPE_CHECKING:
    from guiskindose.equipment_profiles.capture import CapturedCoordinates
    from guiskindose.settings.normalization_settings import NormalizationSettings

from .exam_transforms import (
    _apply_transform_flags,
    _drop_exams_for_path,
    rebuild_rdsr_df,
)
from .geometry_preview import on_exams_loaded
from .offset_handlers import reset_global_offsets_on_new_load
from .settings_builder import build_settings, refresh_normalization_warnings
from .state import AppState

logger = logging.getLogger(__name__)


def _record_load_failure(operation: str, exc: BaseException) -> None:
    """Record a value-free load failure without persisting source-data details."""
    safe_error_event(logger, operation, exc)


def _raw_extracted_view(result) -> pd.DataFrame | None:
    """Build the 'raw (un-normalized)' Data-tab view from a tabular adapter result.

    ``result.raw_data`` is the verbatim ``header=None`` file read, so it still
    carries any pre-header banner/numbering rows and uses positional integer
    column names. For the raw *view* we want the raw source *values* with the
    real column headers promoted and the pre-header junk / wholly-blank rows
    dropped — i.e. what the adapter actually extracted, minus column mapping,
    renaming, and numeric coercion. ``extract_table`` does exactly this using the
    header row the adapter already detected. Falls back to the verbatim frame if
    anything is missing (e.g. a synthetic DICOM result).
    """
    from guiskindose.input_adapters.base import extract_table

    raw = getattr(result, "raw_data", None)
    header_idx = getattr(getattr(result, "provenance", None), "header_row_index", None)
    if raw is None or header_idx is None:
        return raw
    try:
        _, extracted = extract_table(raw, int(header_idx))
        return extracted.reset_index(drop=True)
    except Exception:
        return raw


def _live_session(settings: Any) -> Any | None:
    """Bound nonempty custom-profile session, else None (empty behaves session-free)."""
    session = settings.equipment_profile_session
    if session is None or len(session.profiles) == 0:
        return None
    return session


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


def _check_session_event_total(state: AppState, new_frames: list[pd.DataFrame], *, session: Any) -> None:
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


def _load_candidate(state: AppState) -> AppState:
    """Bound live authority before copying candidate exam lists."""
    session = state.equipment_profile_session
    if session is not None and session.profiles:
        _check_session_exam_count(len(state.loaded_exams), 0, session=session)
        _check_session_exam_count(len(state.loaded_exam_meta), 0, session=session)
    work = copy.copy(state)
    work.loaded_exams = list(state.loaded_exams)
    work.loaded_exam_meta = list(state.loaded_exam_meta)
    return work


def load_rdsr(file_path: Path, state: AppState) -> tuple[bool, str]:
    """Parse and normalise an RDSR file and append it to the exam list.

    Accumulating: each call adds one entry to ``state.loaded_exams`` and
    ``state.loaded_exam_meta`` rather than replacing the previous load.
    Publication is candidate-based: every step (reset, parse, normalize,
    filter, mint, appends, raw copy, rebuild, preview, display fields) runs
    on a bounded shallow candidate with fresh exam lists, and the live state
    adopts it wholesale only on full success. Existing exams, metas, frames,
    and every other home are never mutated — only rebound at adoption — so
    any failure (including rebuild/preview faults, and cancellation, which
    propagates uncaught) leaves the live state identical with no restore
    pass. Returns ``(success, message)``.
    """
    from guiskindose.input_adapters.models import InputAdapterResult, InputProvenance

    # T20: seed per-exam meta from globals before reset zeros them.
    seed_d_lon = state.d_lon
    seed_d_ver = state.d_ver
    seed_d_lat = state.d_lat
    try:
        work = _load_candidate(state)
        reset_global_offsets_on_new_load(work)
        settings = build_settings(work, mode="calculate_dose")

        # Pre-read exam ceiling: a fresh DICOM load always appends exactly
        # one exam, so 64 loaded already refuse before the file is touched.
        live = _live_session(settings)
        _check_session_exam_count(len(work.loaded_exams), 1, session=live)

        # Manually parse and normalise so we can keep the raw version
        data_raw = pydicom.dcmread(str(file_path))
        data_parsed = rdsr_parser(data_raw, silence_pydicom_warnings=settings.silence_pydicom_warnings)

        # Normalize (never modifies data_parsed). A bound session publishes one
        # genuine receipt for this exam; without a session nothing is issued.
        session_receipts: list = []
        df = rdsr_normalizer(
            data_parsed,
            settings=settings,
            equipment_receipt_out=session_receipts if live is not None else None,
        )

        if settings.remove_invalid_rows and len(df[df.kVp == 0]):
            df = df[df.kVp != 0].reset_index(drop=True)

        # Session authority is minted on the final frame (post-filter, with the
        # session's receipt rebound to it); the O(1) exam recount and the
        # bounded retained-event sum refuse before anything is published.
        _check_session_exam_count(len(work.loaded_exams), 1, session=live)
        _check_session_event_total(work, [df], session=live)
        capture, snapshot = _mint_session_capture(
            settings=settings,
            receipt=session_receipts[0] if session_receipts else None,
            frame=df,
        )

        # Build a synthetic InputAdapterResult so DICOM and tabular exams are
        # handled uniformly in the exam list and by analyze_multiple_exams().
        provenance = InputProvenance(
            source_type="dicom",
            schema_name="dicom_rdsr",
            original_filename=file_path.name,
            header_row_index=0,
            detected_encoding="N/A",
            detected_delimiter=None,
            sheet_name=None,
            column_map={},
            unit_conversions={},
        )
        result = InputAdapterResult(
            normalized_data=df,
            raw_data=data_parsed.copy(),
            provenance=provenance,
            warnings=[],
            study_id=None,
            equipment_capture=capture,
            normalization_snapshot=snapshot,
        )

        # Auto-detected table origin from manufacturer/model matching — captured
        # per exam so the Phase 2.5 override can pre-fill and reset to it.
        norm = settings.normalization_settings

        # ── Accumulate (candidate lists) ────────────────────────────────
        work.loaded_exams.append(result)
        work.loaded_exam_meta.append({
            "file_name": file_path.name,
            "file_path": file_path,
            "source_type": "dicom",
            "schema": "dicom_rdsr",
            "sheet": None,
            "provenance": provenance,
            "warnings": [],
            # Pristine copy for the per-exam transform engine (Phase 2.2/2.5).
            # DICOM has no swap/flip toggles, but the table-origin override
            # (Phase 2.5) re-bases from this base.
            "base_data": df.copy(),
            "swap_lat_lon": False,
            "flip_ap1": False,
            "flip_ap2": False,
            # Axis-direction sign flips (Phase 2.4) — not exposed for DICOM (its
            # trans_dir convention is matched at normalization); seeded False so the
            # meta schema is uniform across exam types.
            "flip_tx": False,
            "flip_ty": False,
            "flip_tz": False,
            # Auto-detected table origin (from manufacturer/model matching) that a
            # manual override would replace; None override = use auto (Phase 2.5).
            "table_origin_detected": {
                "x": float(norm.trans_offset.x),
                "y": float(norm.trans_offset.y),
                "z": float(norm.trans_offset.z),
            },
            "table_origin_override": None,
            # Per-exam patient offset (Phase 2.3): default to the pre-reset global
            # offset; editable per exam in the loaded-exam list. Only consumed in
            # multi-exam mode (analyze_multiple_exams); single-exam uses global.
            "d_lon": seed_d_lon,
            "d_ver": seed_d_ver,
            "d_lat": seed_d_lat,
            "normalization_method": norm.normalization_method,
            "input_manufacturer": norm.input_manufacturer,
            "input_model": norm.input_model,
        })

        # Rebuild concat event preview from all loaded exams
        rebuild_rdsr_df(work)
        on_exams_loaded(work)
        work.is_multi_exam = len(work.loaded_exams) > 1

        # Raw copy only once the file is accepted (last-loaded DICOM wins for
        # the raw preview); on the candidate, a rejected file never replaces it.
        work.rdsr_raw_df = data_parsed.copy()

        # Update single-file-style fields so the rest of the UI is consistent
        work.file_path = file_path
        if len(work.loaded_exams) == 1:
            work.file_name = file_path.name
        else:
            work.file_name = f"{len(work.loaded_exams)} files"

        # Extract DICOM metadata for display (last-loaded wins)
        work.manufacturer = norm.matched_manufacturer
        work.model = norm.matched_model
        work.input_manufacturer = norm.input_manufacturer
        work.input_model = norm.input_model
        work.normalization_method = norm.normalization_method
        work.table_offset_x = norm.trans_offset.x
        work.table_offset_y = norm.trans_offset.y
        work.table_offset_z = norm.trans_offset.z
        refresh_normalization_warnings(work)

        state.__dict__.update(work.__dict__)
        return True, f"Loaded {len(df)} irradiation events"
    except RdsrUnitError as exc:
        # Unit mismatch is a specific, actionable condition. Its message is built
        # from fixed labels only, so it is shown instead of the generic error.
        # The candidate is discarded, so the live state is untouched.
        _record_load_failure("DICOM_RDSR_UNIT_MISMATCH", exc)
        return False, exc.user_message()
    except UserFacingInputError as exc:
        # Missing geometry, conflicting duplicates, no events: value-free message.
        _record_load_failure("DICOM_RDSR_INPUT", exc)
        return False, exc.user_message()
    except Exception as exc:
        _record_load_failure("DICOM_RDSR_LOAD", exc)
        return False, "Could not read this DICOM RDSR file. Check the file and try again."


def get_excel_sheets(file_path: Path) -> list[str]:
    """Return the sheet names from an Excel file, or [] on error."""
    try:
        import openpyxl
        wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
        names = wb.sheetnames
        wb.close()
        return names
    except Exception:
        return []


def load_tabular(
    file_path: Path, state: AppState, replace_existing: bool = False
) -> tuple[bool, str]:
    """Load a tabular file (CSV/TSV/XLSX) and append exam(s) to the exam list.

    Accumulating: each call adds one or more entries to ``state.loaded_exams``
    and ``state.loaded_exam_meta`` rather than replacing previous loads.

    ``replace_existing`` re-parses a file already in the exam list (e.g. after a
    schema or sheet change): any exam(s) previously loaded from ``file_path`` are
    dropped before the freshly parsed one(s) are appended, so a re-parse updates
    the entry in place instead of duplicating it. The drop runs up front on the
    candidate; a failed re-parse discards the candidate, leaving the existing
    exams untouched.

    Returns ``(ok, message)``.
    """
    from guiskindose.input_adapters.registry import SchemaDetectionError

    try:
        _, msg = _parse_tabular(file_path, state, replace_existing=replace_existing)
    except SchemaDetectionError as exc:
        return _wrap_tabular_schema_detection(state, exc)
    except UserFacingInputError as exc:
        _record_load_failure("TABULAR_INPUT", exc)
        state.import_has_errors = True
        return False, exc.user_message()
    except Exception as exc:
        _record_load_failure("TABULAR_LOAD", exc)
        state.import_has_errors = True
        return False, "Could not read this file. Check the file and try again."

    return True, msg


def _parse_tabular(
    file_path: Path,
    state: AppState,
    *,
    replace_existing: bool = False,
) -> tuple[Any, str]:
    """Read a tabular file, build per-exam meta, append to ``state`` exam list.

    Returns ``(result_for_finalize, message)``. Raises ``SchemaDetectionError``
    or any adapter error to be translated by the caller. Publication is
    candidate-based, exactly like :func:`load_rdsr`: drops, appends, minting,
    and finalization (concat rebuild, provenance, display fields) all run on
    a bounded shallow candidate, and the live state adopts it wholesale only
    on full success — so parse, bounds, append, mint, and finalize failures
    (and cancellation, which propagates uncaught) all leave the live state
    identical with no restore pass.
    """
    from guiskindose.input_adapters.registry import read_and_normalize_input

    # T20: capture globals before reset; on re-parse keep current globals.
    seed_d_lon = state.d_lon
    seed_d_ver = state.d_ver
    seed_d_lat = state.d_lat
    work = _load_candidate(state)
    if not replace_existing:
        reset_global_offsets_on_new_load(work)
    settings = build_settings(work, mode="calculate_dose")
    schema = work.input_schema or "auto"
    live = _live_session(settings)
    if live is not None and not replace_existing and len(work.loaded_exams) >= MAX_PROFILES:
        # Pre-read exam ceiling: a fresh tabular load always appends at least
        # one exam, so 64 loaded already refuse before the file is touched.
        raise UserFacingInputError(
            "Too many loaded exams for custom equipment-profile authority."
        )

    raw = read_and_normalize_input(
        file_path,
        input_schema=schema,
        settings=settings,
        sheet_name=work.input_sheet_name,
    )

    preserved_flags = _collect_preserved_flags(work, file_path, replace_existing)
    if replace_existing:
        _drop_exams_for_path(work, file_path)
    # O(1) exam-count gate before any frame access; the retained-event sum
    # below runs only over the now-bounded collection with early exit.
    new_count = len(raw) if isinstance(raw, list) else 1
    _check_session_exam_count(len(work.loaded_exams), new_count, session=live)
    if live is not None:
        new_frames = (
            [exam.normalized_data for exam in raw]
            if isinstance(raw, list)
            else [raw.normalized_data]
        )
        _check_session_event_total(work, new_frames, session=live)
    start = len(work.loaded_exams)
    if isinstance(raw, list):
        out = _append_multi_study_exams(raw, work, file_path, seed_d_lon, seed_d_ver, seed_d_lat, preserved_flags)
    else:
        out = _append_single_study_exam(raw, work, file_path, seed_d_lon, seed_d_ver, seed_d_lat, preserved_flags)
    _mint_session_captures(work, settings, start)
    _finalize_tabular_state(work, file_path, out[0])
    state.__dict__.update(work.__dict__)
    return out


def _collect_preserved_flags(
    state: AppState, file_path: Path, replace_existing: bool
) -> list[dict]:
    """Collect per-exam coordinate-transform flags from prior loads of file_path."""
    if not replace_existing:
        return []
    return [
        {
            "study_id": m.get("study_id"),
            "swap_lat_lon": m.get("swap_lat_lon", False),
            "flip_ap1": m.get("flip_ap1", False),
            "flip_ap2": m.get("flip_ap2", False),
            "flip_tx": m.get("flip_tx", False),
            "flip_ty": m.get("flip_ty", False),
            "flip_tz": m.get("flip_tz", False),
        }
        for m in state.loaded_exam_meta
        if m.get("file_path") == file_path
    ]


def _default_transform_flags(state: AppState) -> dict:
    return {
        "swap_lat_lon": state.swap_lat_lon,
        "flip_ap1": state.flip_ap1,
        "flip_ap2": state.flip_ap2,
        "flip_tx": False,
        "flip_ty": False,
        "flip_tz": False,
    }


def _blank_transform_flags() -> dict:
    return {
        "swap_lat_lon": False,
        "flip_ap1": False,
        "flip_ap2": False,
        "flip_tx": False,
        "flip_ty": False,
        "flip_tz": False,
    }


def _build_exam_meta_entry(
    state: AppState,
    file_path: Path,
    schema_name: str,
    base: pd.DataFrame,
    provenance,
    warnings,
    flags: dict,
    seed_d_lon: float,
    seed_d_ver: float,
    seed_d_lat: float,
    study_id: str | None = None,
) -> dict:
    """Construct a per-exam meta entry shared by single and multi-study paths."""
    return {
        "file_name": file_path.name,
        "file_path": file_path,
        "source_type": file_path.suffix.lstrip("."),
        "schema": schema_name,
        "sheet": state.input_sheet_name,
        "provenance": provenance,
        "warnings": list(warnings),
        "base_data": base,
        "study_id": study_id,
        "swap_lat_lon": flags["swap_lat_lon"],
        "flip_ap1": flags["flip_ap1"],
        "flip_ap2": flags["flip_ap2"],
        "flip_tx": flags.get("flip_tx", False),
        "flip_ty": flags.get("flip_ty", False),
        "flip_tz": flags.get("flip_tz", False),
        # Tabular exports carry no normalization trans_offset, so the
        # auto-detected origin is zero; a manual override (Phase 2.5) is
        # then an absolute table-origin shift.
        "table_origin_detected": {"x": 0.0, "y": 0.0, "z": 0.0},
        "table_origin_override": None,
        "d_lon": seed_d_lon,
        "d_ver": seed_d_ver,
        "d_lat": seed_d_lat,
        "normalization_method": "Tabular",
        "input_manufacturer": "",
        "input_model": "",
    }


def _append_multi_study_exams(
    raw_exams: list,
    state: AppState,
    file_path: Path,
    seed_d_lon: float,
    seed_d_ver: float,
    seed_d_lat: float,
    preserved_flags: list[dict],
) -> tuple[Any, str]:
    """Append every exam from a multi-study tabular file and rebuild concat preview."""
    new_exams = raw_exams
    preserved_map = {f["study_id"]: f for f in preserved_flags if f.get("study_id") is not None}
    idless_flags = [f for f in preserved_flags if f.get("study_id") is None]
    idless_exam_count = sum(exam.study_id is None for exam in new_exams)
    preserved_without_study_id = iter(idless_flags) if len(idless_flags) == idless_exam_count else iter(())
    for _j, exam in enumerate(new_exams):
        schema_name = exam.provenance.schema_name
        base = exam.normalized_data.copy()
        flags = _blank_transform_flags()
        if exam.study_id is not None and exam.study_id in preserved_map:
            flags = preserved_map[exam.study_id]
        elif exam.study_id is None:
            flags = next(preserved_without_study_id, flags)
        exam.normalized_data = _apply_transform_flags(
            base, flags["swap_lat_lon"], flags["flip_ap1"],
            flags["flip_ap2"], schema_name,
            flip_tx=flags.get("flip_tx", False),
            flip_ty=flags.get("flip_ty", False),
            flip_tz=flags.get("flip_tz", False),
        )
        state.loaded_exams.append(exam)
        state.loaded_exam_meta.append(
            _build_exam_meta_entry(
                state, file_path, schema_name, base, exam.provenance, exam.warnings,
                flags, seed_d_lon, seed_d_ver, seed_d_lat, exam.study_id,
            )
        )
    result_for_finalize = raw_exams[0]  # use first exam's provenance for UI hints
    total_events = sum(len(e.normalized_data) for e in new_exams)
    msg = f"Loaded {len(new_exams)} exams, {total_events} total events"
    return result_for_finalize, msg


def _append_single_study_exam(
    result,
    state: AppState,
    file_path: Path,
    seed_d_lon: float,
    seed_d_ver: float,
    seed_d_lat: float,
    preserved_flags: list[dict],
) -> tuple[Any, str]:
    """Append a single-exam tabular file and rebuild concat preview."""
    base = result.normalized_data.copy()
    flags = preserved_flags[0] if (preserved_flags) else _default_transform_flags(state)
    result.normalized_data = _apply_transform_flags(
        base, flags["swap_lat_lon"], flags["flip_ap1"],
        flags["flip_ap2"], result.provenance.schema_name,
        flip_tx=flags.get("flip_tx", False),
        flip_ty=flags.get("flip_ty", False),
        flip_tz=flags.get("flip_tz", False),
    )
    state.loaded_exams.append(result)
    state.loaded_exam_meta.append(
        _build_exam_meta_entry(
            state, file_path, result.provenance.schema_name, base, result.provenance, result.warnings,
            flags, seed_d_lon, seed_d_ver, seed_d_lat, result.study_id,
        )
    )
    msg = f"Loaded {len(result.normalized_data)} events ({result.provenance.schema_name})"
    return result, msg


def _finalize_tabular_state(state: AppState, file_path: Path, result) -> None:
    """Apply shared post-load state: concat preview, file naming, provenance, offsets."""
    rebuild_rdsr_df(state)
    on_exams_loaded(state)
    state.is_multi_exam = len(state.loaded_exams) > 1

    # Per-file state used by the import preview and schema re-parse path.
    # The raw *view* shows the extracted source values (real headers, no
    # pre-header banner/blank rows), not the verbatim header=None dump.
    state.rdsr_raw_df = _raw_extracted_view(result)
    state.file_path = file_path
    if len(state.loaded_exams) == 1:
        state.file_name = file_path.name
    else:
        state.file_name = f"{len(state.loaded_exams)} files"
    state.import_provenance = result.provenance
    state.import_warnings = list(result.warnings)
    state.import_has_errors = False

    state.manufacturer = ""
    state.model = ""
    state.input_manufacturer = ""
    state.input_model = ""
    state.normalization_method = "Tabular"
    state.table_offset_x = 0.0
    state.table_offset_y = 0.0
    state.table_offset_z = 0.0
    refresh_normalization_warnings(state)


def _wrap_tabular_schema_detection(state: AppState, exc: BaseException) -> tuple[bool, str]:
    """Translate a SchemaDetectionError into the user-facing retry hint."""
    _record_load_failure("TABULAR_SCHEMA_DETECTION", exc)
    state.import_has_errors = True
    return False, (
        "Couldn't auto-detect this file's format. Auto-detect needs one source's "
        "own column and at least two columns it recognizes, and it stops when two "
        "sources both fit. Open the “Input schema” selector below and choose the "
        "matching format (e.g. Radimetrics CSV, DoseTrack, Raw RDSR-like, or "
        "Normalized), then upload the file again."
    )
