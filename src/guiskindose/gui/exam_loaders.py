"""Load RDSR and tabular exams into AppState."""

from __future__ import annotations

import copy
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pandas as pd
import pydicom

from guiskindose.equipment_confirmation import prepare_replay_settings
from guiskindose.equipment_profiles.constants import MAX_PROFILES
from guiskindose.gui.exam_equipment import (
    _bounds_authority,
    _check_session_event_total,
    _check_session_exam_count,
    _confirm_consumed_capture,
    _drop_zero_kvp_rows,
    _live_session,
    _mint_session_captures,
    _peek_pending_entry,
    _read_tabular_results,
    _resolve_dicom_authority,
)
from guiskindose.gui.run_state_equipment import PendingEntry
from guiskindose.privacy import UserFacingInputError, safe_error_event
from guiskindose.rdsr_normalizer import RdsrUnitError, rdsr_normalizer
from guiskindose.rdsr_parser import rdsr_parser

if TYPE_CHECKING:
    from guiskindose.equipment_profiles.capture import CapturedCoordinates

from .exam_transforms import (
    _apply_transform_flags,
    _drop_exams_for_path,
    rebuild_rdsr_df,
)
from .geometry_preview import on_exams_loaded
from .offset_handlers import reset_global_offsets_on_new_load, sync_single_exam_globals_from_meta
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


def _load_candidate(state: AppState) -> AppState:
    """Bound live authority before copying candidate exam lists."""
    session = state.equipment_profile_session
    pending = state.equipment_pending
    if (session is not None and session.profiles) or pending:
        _check_session_exam_count(len(state.loaded_exams), 0, session=session or pending)
        _check_session_exam_count(len(state.loaded_exam_meta), 0, session=session or pending)
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
        live = _live_session(settings)

        # Staged pending entry for this load (FIFO head, if any). A capture
        # slot replays the recipe instead of resolving live; a null slot
        # loads with live behavior but seeds the document's flags.
        pending, entry, replay_capture = _peek_pending_entry(state, live)

        # Pre-read exam ceiling: a fresh DICOM load always appends exactly
        # one exam, so 64 loaded already refuse before the file is touched.
        # The token covers live sessions, staged captures, and staged
        # presence alike — null slots still stage authority.
        _check_session_exam_count(
            len(work.loaded_exams), 1, session=_bounds_authority(live, pending, replay_capture)
        )

        # Manually parse and normalise so we can keep the raw version
        data_raw = pydicom.dcmread(str(file_path))
        data_parsed = rdsr_parser(data_raw, silence_pydicom_warnings=settings.silence_pydicom_warnings)

        # Normalize (never modifies data_parsed). Replay runs the staged
        # captured recipe with no live resolution and publishes no receipt;
        # a bound session publishes one genuine receipt for this exam, and
        # without either nothing is issued.
        session_receipts: list = []
        if replay_capture is not None:
            replay_base = copy.copy(settings)
            replay_base.equipment_profile_session = None
            replay_settings = prepare_replay_settings(context=replay_capture, settings=replay_base)
            df = rdsr_normalizer(
                data_parsed,
                settings=replay_settings,
                equipment_receipt_out=None,
                equipment_capture_context=replay_capture,
            )
            norm = replay_settings.normalization_settings
        else:
            df = rdsr_normalizer(
                data_parsed,
                settings=settings,
                equipment_receipt_out=session_receipts if live is not None else None,
            )
            norm = settings.normalization_settings

        df = _drop_zero_kvp_rows(df, settings)

        # Filter, transform, bound, and authorize on the candidate frame.
        final, capture, snapshot, flag_values, override_value = _resolve_dicom_authority(
            settings=settings,
            authority=_bounds_authority(live, pending, replay_capture),
            entry=entry,
            replay_capture=replay_capture,
            df=df,
            norm=norm,
            work=work,
            receipt=session_receipts[0] if session_receipts else None,
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
            normalized_data=final,
            raw_data=data_parsed.copy(),
            provenance=provenance,
            warnings=[],
            study_id=None,
            equipment_capture=capture,
            normalization_snapshot=snapshot,
        )

        # Auto-detected table origin from manufacturer/model matching — captured
        # per exam so the Phase 2.5 override can pre-fill and reset to it.
        # (``norm`` above already points at the replay settings for replayed
        # loads, so detected labels match the recipe that normalized them.)

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
            "swap_lat_lon": flag_values["swap_lat_lon"],
            "flip_ap1": flag_values["flip_ap1"],
            "flip_ap2": flag_values["flip_ap2"],
            # Axis-direction sign flips (Phase 2.4) — not exposed for DICOM (its
            # trans_dir convention is matched at normalization); seeded False so the
            # meta schema is uniform across exam types.
            "flip_tx": flag_values["flip_tx"],
            "flip_ty": flag_values["flip_ty"],
            "flip_tz": flag_values["flip_tz"],
            # Auto-detected table origin (from manufacturer/model matching) that a
            # manual override would replace; None override = use auto (Phase 2.5).
            "table_origin_detected": {
                "x": float(norm.trans_offset.x),
                "y": float(norm.trans_offset.y),
                "z": float(norm.trans_offset.z),
            },
            "table_origin_override": override_value,
            # Per-exam patient offset (Phase 2.3): staged document offsets for
            # pending consumption, else the pre-reset globals; editable per
            # exam in the loaded-exam list. Single-exam calculation reads
            # globals, so adoption syncs meta back via
            # sync_single_exam_globals_from_meta when len==1.
            "d_lon": entry.d_lon if entry is not None else seed_d_lon,
            "d_ver": entry.d_ver if entry is not None else seed_d_ver,
            "d_lat": entry.d_lat if entry is not None else seed_d_lat,
            "normalization_method": norm.normalization_method,
            "input_manufacturer": norm.input_manufacturer,
            "input_model": norm.input_model,
        })

        # Rebuild concat event preview from all loaded exams
        rebuild_rdsr_df(work)
        on_exams_loaded(work)
        work.is_multi_exam = len(work.loaded_exams) > 1
        if entry is not None and not work.is_multi_exam:
            sync_single_exam_globals_from_meta(work)

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
        if pending:
            state.equipment_pending = pending[1:] or None
        return True, f"Loaded {len(final)} irradiation events"
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
    pending, entry, replay_capture = _peek_pending_entry(state, live)
    if (
        not replace_existing
        and len(work.loaded_exams) >= MAX_PROFILES
        and _bounds_authority(live, pending, replay_capture) is not None
    ):
        # Pre-read exam ceiling: a fresh tabular load always appends at least
        # one exam, so 64 loaded already refuse before the file is touched.
        # The token covers live sessions, staged captures, and staged
        # presence alike — null slots still stage authority.
        raise UserFacingInputError(
            "Too many loaded exams for custom equipment-profile authority."
        )

    # Staged pending entry for this load (FIFO head, if any). Re-parsing
    # while entries are staged would silently lose their slots: refuse
    # before the drop runs. A capture slot replays the recipe instead of
    # resolving live; a null slot loads with live behavior but seeds the
    # document's flags.
    pending, entry, replay_capture = _peek_pending_entry(state, live)
    if replace_existing and pending:
        raise UserFacingInputError(
            "Cannot re-parse inputs while run-configuration equipment is staged; "
            "load the staged exams first, or re-import without equipment."
        )

    raw = _read_tabular_results(
        file_path=file_path,
        schema=schema,
        work=work,
        settings=settings,
        replay_capture=replay_capture,
        pending=pending,
    )

    preserved_flags = _collect_preserved_flags(work, file_path, replace_existing)
    if replace_existing:
        _drop_exams_for_path(work, file_path)
    # O(1) exam-count gate before any frame access; the retained-event sum
    # below runs only over the now-bounded collection with early exit.
    # Captured authority enforces ceilings without a live session.
    new_count = len(raw) if isinstance(raw, list) else 1
    authority = _bounds_authority(live, pending, replay_capture)
    _check_session_exam_count(len(work.loaded_exams), new_count, session=authority)
    if authority is not None:
        new_frames = (
            [exam.normalized_data for exam in raw]
            if isinstance(raw, list)
            else [raw.normalized_data]
        )
        _check_session_event_total(work, new_frames, session=authority)
    start = len(work.loaded_exams)
    out = _append_and_authorize_tabular(
        raw=raw,
        work=work,
        file_path=file_path,
        seeds=(seed_d_lon, seed_d_ver, seed_d_lat),
        preserved_flags=preserved_flags,
        settings=settings,
        entry=entry,
        replay_capture=replay_capture,
        start=start,
    )
    _finalize_tabular_state(work, file_path, out[0])
    if entry is not None and not work.is_multi_exam:
        sync_single_exam_globals_from_meta(work)
    state.__dict__.update(work.__dict__)
    if pending:
        state.equipment_pending = pending[1:] or None
    return out


def _append_and_authorize_tabular(
    *,
    raw: Any,
    work: AppState,
    file_path: Path,
    seeds: tuple[float, float, float],
    preserved_flags: list[dict],
    settings: Any,
    entry: PendingEntry | None,
    replay_capture: CapturedCoordinates | None,
    start: int,
) -> tuple[Any, str]:
    """Append one file's exams and resolve authority on the candidate.

    A staged entry seeds document offsets/flags (single-exam files only —
    the caller refuses multi-study splits with pending staged); replay
    confirms the staged capture against the final frame, live loads mint
    with receipts rebound. Pure with respect to live state: only the
    candidate ``work`` is written. Returns ``(result, message)``.
    """
    seed_d_lon, seed_d_ver, seed_d_lat = seeds
    if isinstance(raw, list):
        out = _append_multi_study_exams(raw, work, file_path, seed_d_lon, seed_d_ver, seed_d_lat, preserved_flags)
    elif entry is None:
        out = _append_single_study_exam(raw, work, file_path, seed_d_lon, seed_d_ver, seed_d_lat, preserved_flags)
    else:
        out = _append_single_study_exam(
            raw, work, file_path, entry.d_lon, entry.d_ver, entry.d_lat, preserved_flags, consumed=entry
        )
    if replay_capture is None:
        _mint_session_captures(work, settings, start)
        return out
    exam = out[0]
    if exam.equipment_receipt is not None:
        raise UserFacingInputError(
            "Staged equipment replay published a live receipt; refusing mixed authority."
        )
    snapshot = _confirm_consumed_capture(
        context=replay_capture,
        frame=exam.normalized_data,
        norm=settings.normalization_settings,
        position=start,
    )
    exam.equipment_capture = replay_capture
    exam.normalization_snapshot = snapshot
    exam.equipment_receipt = None
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
    *,
    table_origin_override: Any = None,
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
        "table_origin_override": table_origin_override,
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
    *,
    consumed: PendingEntry | None = None,
) -> tuple[Any, str]:
    """Append a single-exam tabular file and rebuild concat preview.

    A staged pending entry overrides the transform flags and table-origin
    override for this load (document authority replaces live seeding);
    otherwise preserved prior flags or live defaults apply as before.
    """
    base = result.normalized_data.copy()
    if consumed is not None:
        flags = consumed.geometry_flags()
    else:
        flags = preserved_flags[0] if (preserved_flags) else _default_transform_flags(state)
    result.normalized_data = _apply_transform_flags(
        base, flags["swap_lat_lon"], flags["flip_ap1"],
        flags["flip_ap2"], result.provenance.schema_name,
        table_origin_override=consumed.table_origin_override if consumed is not None else None,
        flip_tx=flags.get("flip_tx", False),
        flip_ty=flags.get("flip_ty", False),
        flip_tz=flags.get("flip_tz", False),
    )
    state.loaded_exams.append(result)
    state.loaded_exam_meta.append(
        _build_exam_meta_entry(
            state, file_path, result.provenance.schema_name, base, result.provenance, result.warnings,
            flags, seed_d_lon, seed_d_ver, seed_d_lat, result.study_id,
            table_origin_override=consumed.table_origin_override if consumed is not None else None,
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
