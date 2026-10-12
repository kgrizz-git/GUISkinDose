"""Orchestrates dose calculation, data analysis, and output generation."""

import copy
import logging
from typing import Any

import numpy as np
import pandas as pd

from guiskindose import constants as c
from guiskindose.calculate_dose.calculate_dose import calculate_dose
from guiskindose.debug import dprint
from guiskindose.equipment_confirmation import (
    _prepare_captured_exams,
    _validate_capture_contexts,
)
from guiskindose.equipment_profiles.capture import (
    CODE_INVALID_EQUIPMENT_CAPTURE,
    CapturedCoordinates,
    CaptureError,
)
from guiskindose.format_export_data import (
    ExamResult,
    MultiExamResult,
    PySkinDoseOutput,
    format_analysis_result_for_export,
    normalize_hit_masks,
)
from guiskindose.helpers.calculate_rotation_matrices import calculate_rotation_matrices
from guiskindose.input_adapters.models import InputAdapterResult
from guiskindose.phantom_class import Phantom
from guiskindose.plotting.create_dose_map_plot import create_dose_map_plot
from guiskindose.plotting.create_geometry_plot import create_geometry_plot
from guiskindose.privacy import exception_class_name, opaque_exam_label, safe_error_event
from guiskindose.settings import PyskindoseSettings, initialize_settings

logger = logging.getLogger(__name__)
_CAPTURE_SETTINGS_ERROR = "Equipment capture cannot be applied to these settings."


def _match_mapping_for_output(
    settings: PyskindoseSettings, equipment_receipt: Any, frame: Any
) -> dict[str, Any] | None:
    """Validate a receipt's full binding and serialize it, or fail closed.

    Returns ``None`` only when no session is configured (or it is empty) and
    no receipt was supplied. A configured nonempty session with no receipt
    means the input arrived already normalized; a receipt without a session
    means forged provenance. Both fail closed.
    """
    from guiskindose.equipment_profiles.session import EquipmentProfileSession
    from guiskindose.equipment_resolution import receipt_to_mapping

    session = getattr(settings, "equipment_profile_session", None)
    if session is None:
        if equipment_receipt is not None:
            raise ValueError(
                "An equipment-profile receipt was supplied without a configured session."
            )
        return None
    if not isinstance(session, EquipmentProfileSession):
        raise ValueError(
            "equipment_profile_session must be an EquipmentProfileSession or None, "
            f"not {type(session).__name__}."
        )
    if equipment_receipt is None:
        if len(session.profiles) > 0:
            raise ValueError(
                "A custom equipment-profile session is configured but this input carries no "
                "resolved raw provenance. Load raw DICOM or raw-shaped tabular input so the "
                "session can resolve, instead of pre-normalized data."
            )
        return None
    return receipt_to_mapping(receipt=equipment_receipt, frame=frame, settings=settings)


def _apply_capture_context(
    settings: PyskindoseSettings,
    normalized_data: pd.DataFrame,
    equipment_receipt: Any,
    capture_context: Any,
) -> tuple[PyskindoseSettings, dict[str, Any]]:
    """Calculate from a captured authority on an already transformed frame.

    Rejects a simultaneous live session or receipt, clones the caller
    settings privately, prepares the captured recipe into the clone, and
    confirms frame and candidate before anything calculates. The caller's
    settings home is preserved on success and failure alike. Returns the
    working settings plus the stored validated match mapping for output.
    """
    from guiskindose.equipment_confirmation import (
        confirm_captured_application,
        prepare_captured_candidate,
    )

    if type(capture_context) is not CapturedCoordinates:
        raise CaptureError(
            "Equipment capture context must be a CapturedCoordinates or None.",
            CODE_INVALID_EQUIPMENT_CAPTURE,
        )
    if getattr(settings, "equipment_profile_session", None) is not None or equipment_receipt is not None:
        raise CaptureError(
            "A captured equipment context cannot be combined with a live session or receipt.",
            CODE_INVALID_EQUIPMENT_CAPTURE,
        )
    candidate = prepare_captured_candidate(context=capture_context, norm=settings.normalization_settings)
    try:
        work_settings = copy.deepcopy(settings)
    except Exception:
        # Untrusted boundary: the caller owns the settings graph, so any copy
        # failure (including hostile __deepcopy__ hooks) is closed, never raw.
        raise CaptureError(
            _CAPTURE_SETTINGS_ERROR,
            CODE_INVALID_EQUIPMENT_CAPTURE,
        ) from None
    _check_work_isolated(work_settings, settings)
    work_settings.normalization_settings = candidate
    _, equipment_profile_match = confirm_captured_application(
        context=capture_context, frame=normalized_data, candidate=candidate
    )
    return work_settings, equipment_profile_match


def _check_work_isolated(work_settings: Any, settings: Any) -> None:
    """Require the working copy isolated from caller-owned mutable state.

    A self-returning ``__deepcopy__`` (or shared-child hooks) that rebinds the
    working copy to caller handles would let later candidate assignment — or
    downstream plot-mode dimension writes — mutate the caller. Reject before
    the candidate is assigned. Ordinary subclasses that copy cleanly pass
    unchanged. This verifies handle isolation at handoff; it cannot restrain
    a hostile hook that mutates caller state during its own copy execution.
    """
    if not isinstance(work_settings, PyskindoseSettings):
        raise CaptureError(
            _CAPTURE_SETTINGS_ERROR,
            CODE_INVALID_EQUIPMENT_CAPTURE,
        )
    try:
        shared = (
            work_settings is settings
            or work_settings.normalization_settings is settings.normalization_settings
            or work_settings.normalization_settings.trans_offset
            is settings.normalization_settings.trans_offset
            or work_settings.normalization_settings.trans_dir
            is settings.normalization_settings.trans_dir
            or work_settings.normalization_settings.rot_dir
            is settings.normalization_settings.rot_dir
            or work_settings.phantom is settings.phantom
            or work_settings.phantom.dimension is settings.phantom.dimension
        )
    except AttributeError:
        raise CaptureError(
            _CAPTURE_SETTINGS_ERROR,
            CODE_INVALID_EQUIPMENT_CAPTURE,
        ) from None
    if shared:
        raise CaptureError(
            _CAPTURE_SETTINGS_ERROR,
            CODE_INVALID_EQUIPMENT_CAPTURE,
        )


def _format_multi_exam_failure_warning(exam_id: str, exc: BaseException) -> str:
    """Build a user-facing warning when an exam raises during multi-exam calculation.

    Parameters
    ----------
    exam_id :
        Opaque exam label (for example ``Exam 2``).
    exc :
        Exception raised while processing that exam.

    Returns
    -------
    str
        Warning stating the exam was excluded from the aggregate PSD.
    """
    return (
        f"{exam_id}: calculation raised {exception_class_name(exc)} and was excluded "
        "from the aggregate peak skin dose. "
        "Review this exam's offsets, input data, and settings, then recalculate."
    )


def _format_multi_exam_no_output_warning(exam_id: str) -> str:
    """Build a user-facing warning when an exam returns no dose output.

    Parameters
    ----------
    exam_id :
        Opaque exam label (for example ``Exam 2``).

    Returns
    -------
    str
        Warning stating the exam was excluded because calculation produced no output.
    """
    return (
        f"{exam_id}: produced no dose output and was excluded from the aggregate "
        "peak skin dose (check mode setting)."
    )


def analyze_data(
    normalized_data: pd.DataFrame,
    settings: str | dict | PyskindoseSettings,
    *,
    equipment_receipt: Any = None,
    equipment_capture_context: CapturedCoordinates | None = None,
) -> dict[str, Any] | str | PySkinDoseOutput | None:
    """Analyze data och settings, and runs PySkinDose in desired mode.

    Parameters
    ----------
    normalized_data : pd.DataFrame
        RDSR data, normalized for compliance with PySkinDose.
    settings : Union[str, dict, PyskindoseSettings]
        Settings class for PySkinDose
    equipment_receipt : Any
        Custom equipment-profile resolution record for this exam, if any.
        Raw loaders attach it when a session is bound; direct callers with a
        configured session but no record fail closed, since already-normalized
        input carries no raw provenance to apply a session to.
    equipment_capture_context : CapturedCoordinates | None
        Validated captured-coordinate authority for single-exam calculation
        without a live session. The passed frame must already be transformed
        (this path never replays raw normalization): the caller's settings
        are privately cloned, the captured recipe is prepared into the clone,
        and the frame is confirmed (identity, count, geometry, all 15 leaves)
        before any calculation, plot, or cache mutation. The stored validated
        match mapping is used for output. Never combined with a bound session
        or an equipment receipt; the context is never serialized as settings
        config and no file, store, bundle, or live resolver is contacted. The working copy is
        verified isolated (root plus normalization, phantom, and dimension homes) before the
        candidate lands, so custom clone hooks that share caller state fail closed; ordinary
        settings subclasses copy cleanly and keep working.

    Returns
    -------
    Dict[str, Any]
        output dictionary containing calculation specifics such as dose map, correction
        factors, etc. ``None`` in plot modes with ``html`` output (geometry plots
        render for side effect; only dose modes produce output). Note: ``dict`` /
        ``json`` formats raise on missing output in every mode.

    """
    settings = initialize_settings(settings)

    if settings.output_format not in c.RUN_ARGUMENTS_VALID_OUTPUT_FORMATS:
        raise ValueError(
            f"Invalid output format specified. Must be one of {'.'.join(c.RUN_ARGUMENTS_VALID_OUTPUT_FORMATS)}"
        )

    if equipment_capture_context is None:
        equipment_profile_match = _match_mapping_for_output(settings, equipment_receipt, normalized_data)
    else:
        settings, equipment_profile_match = _apply_capture_context(
            settings, normalized_data, equipment_receipt, equipment_capture_context
        )

    dprint("CALCULATION", "Creating table and pad phantoms")
    # create table, pad and patient phantoms.
    table = Phantom(phantom_model=c.PHANTOM_MODEL_TABLE, phantom_dim=settings.phantom.dimension)

    pad = Phantom(phantom_model=c.PHANTOM_MODEL_PAD, phantom_dim=settings.phantom.dimension)

    dprint("CALCULATION", "Calculating rotation matrices")
    normalized_data = calculate_rotation_matrices(normalized_data)

    dprint("RENDERING", "Creating geometry plot")
    create_geometry_plot(normalized_data=normalized_data, table=table, pad=pad, settings=settings)

    dprint("CALCULATION", "Calculating dose")
    patient, output, export_data_norm = calculate_dose(
        normalized_data=normalized_data, settings=settings, table=table, pad=pad, exam_id=None
    )

    if settings.output_format in [c.RUN_ARGUMENTS_OUTPUT_DICT, c.RUN_ARGUMENTS_OUTPUT_JSON]:
        if output is None or patient is None or export_data_norm is None:
            raise RuntimeError("Dose calculation did not produce output in calculate_dose mode.")
        dprint("PROCESSING", "Formatting analysis result for export")
        guiskindose_output: PySkinDoseOutput | dict[str, Any] | str = format_analysis_result_for_export(
            output,
            patient=patient,
            table=table,
            pad=pad,
            data_norm=export_data_norm,
            settings=settings,
            equipment_profile_match=equipment_profile_match,
        )

        return guiskindose_output

    dprint("RENDERING", "Creating dose map plot")
    dose_map = None
    if output is not None and settings.mode in (c.MODE_CALCULATE_DOSE, c.MODE_PLOT_DOSEMAP):
        dose_map = output[c.OUTPUT_KEY_DOSE_MAP]
    if patient is not None and dose_map is not None:
        create_dose_map_plot(
            patient=patient,
            settings=settings,
            dose_map=dose_map,
        )

    if settings.output_format == c.RUN_ARGUMENTS_OUTPUT_HTML:
        # Plot modes legitimately produce no output (plots render for side
        # effect); only dose modes must have data at this point.
        if output is None and settings.mode in (c.MODE_CALCULATE_DOSE, c.MODE_PLOT_DOSEMAP):
            raise RuntimeError("Expected HTML output but dose calculation returned no data.")
        return output

    raise ValueError(f"Unhandled output format: {settings.output_format}")


def _validate_session_records(exams: list[InputAdapterResult], settings: PyskindoseSettings) -> None:
    """Validate every exam's receipt binding before any exam calculates.

    Already-normalized exams carry no raw identity to apply a session to;
    pretending otherwise would silently misreport. Fails before any exam
    calculates, mirroring offset validation. Live-settings currency is
    validated per exam at result assembly, after each exam restores its own
    receipt — the shared settings object may still hold another exam here.
    """
    from guiskindose.equipment_profiles.session import EquipmentProfileSession
    from guiskindose.equipment_resolution import validate_receipt_binding

    session = getattr(settings, "equipment_profile_session", None)
    if session is None:
        if any(exam.equipment_receipt is not None for exam in exams):
            raise ValueError("Equipment-profile receipts require a configured session.")
        return
    if not isinstance(session, EquipmentProfileSession):
        raise ValueError(
            "equipment_profile_session must be an EquipmentProfileSession or None, "
            f"not {type(session).__name__}."
        )
    if len(session.profiles) == 0:
        return
    for index, exam in enumerate(exams):
        try:
            validate_receipt_binding(
                receipt=exam.equipment_receipt, frame=exam.normalized_data, settings=settings
            )
        except ValueError as exc:
            raise ValueError(f"{opaque_exam_label(index)}: {exc}") from None


def _global_patient_offset(settings: PyskindoseSettings) -> list[float]:
    """Return the global patient offset as [lon, ver, lat] in cm."""
    return [
        float(settings.phantom.patient_offset.d_lon),
        float(settings.phantom.patient_offset.d_ver),
        float(settings.phantom.patient_offset.d_lat),
    ]


def _require_valid_patient_offset(offset: object, exam_index: int) -> list[float]:
    """Require exactly three finite numeric centimeter values for one exam offset."""
    if not isinstance(offset, (list, tuple)) or len(offset) != 3:
        raise ValueError(
            f"Per-exam offset for exam {exam_index} must contain exactly 3 finite numeric values, "
            f"got {offset!r}"
        )
    if not all(
        isinstance(value, (int, float)) and not isinstance(value, bool) and np.isfinite(value)
        for value in offset
    ):
        raise ValueError(
            f"Per-exam offset for exam {exam_index} must contain exactly 3 finite numeric values, "
            f"got {offset!r}"
        )
    return [float(value) for value in offset]


def _validate_per_exam_offsets(per_exam_offsets: list[list[float]] | None) -> None:
    """Reject invalid per-exam offsets before any exam produces output."""
    if not per_exam_offsets:
        return
    for exam_index, offset in enumerate(per_exam_offsets):
        _require_valid_patient_offset(offset, exam_index)


def _effective_patient_offset(
    global_offset: list[float], per_exam_offsets: list[list[float]] | None, exam_index: int
) -> list[float]:
    """Pick the per-exam patient offset when present, else the global offset."""
    if per_exam_offsets and exam_index < len(per_exam_offsets):
        return _require_valid_patient_offset(per_exam_offsets[exam_index], exam_index)
    return global_offset


def _settings_for_exam(
    settings: PyskindoseSettings, effective_offset: list[float], downgrade_beam_warning: bool
) -> PyskindoseSettings:
    """Clone settings with an exam-specific patient offset (and optional beam-warning tweak)."""
    global_offset = _global_patient_offset(settings)
    if effective_offset == global_offset and not downgrade_beam_warning:
        return settings

    exam_settings = copy.deepcopy(settings)
    if effective_offset != global_offset:
        patient_offset = exam_settings.phantom.patient_offset
        patient_offset.d_lon, patient_offset.d_ver, patient_offset.d_lat = effective_offset
    if downgrade_beam_warning:
        exam_settings.beam_miss_warn = "summary"
    return exam_settings


def _exam_warnings(
    exam: InputAdapterResult, exam_index: int, per_exam_extra_warnings: list[list[str]] | None
) -> list[str]:
    """Collect import warnings plus any per-exam extra warnings for one exam."""
    warnings = list(exam.warnings)
    if per_exam_extra_warnings and exam_index < len(per_exam_extra_warnings):
        warnings.extend(per_exam_extra_warnings[exam_index])
    return warnings


def _fresh_table_and_pad(settings: PyskindoseSettings) -> tuple[Phantom, Phantom]:
    """Create per-exam geometry to avoid compounding incremental translations."""
    dimension = settings.phantom.dimension
    table = Phantom(phantom_model=c.PHANTOM_MODEL_TABLE, phantom_dim=dimension)
    pad = Phantom(phantom_model=c.PHANTOM_MODEL_PAD, phantom_dim=dimension)
    return table, pad


def _add_missed_event_warnings(exam_warnings: list[str], exam_id: str, raw_output: dict, event_count: int) -> None:
    """Append warnings for irradiation events that missed the phantom."""
    missed = raw_output.get("missed_event_indices", [])
    if not missed:
        return

    exam_warnings.append(f"{exam_id}: {len(missed)} of {event_count} event(s) missed the patient phantom.")
    if len(missed) == event_count > 0:
        exam_warnings.append(
            f"{exam_id}: all {event_count} event(s) missed the patient phantom — dose map for this exam is all zeros; "
            "check patient offsets and vendor coordinate frame."
        )


def _multi_exam_output(
    patient: Phantom, table: Phantom, pad: Phantom, raw_output: dict, settings: PyskindoseSettings, data_norm: pd.DataFrame
) -> PySkinDoseOutput:
    """Build a PySkinDoseOutput for one exam inside a multi-exam run."""
    return PySkinDoseOutput(
        patient=patient,
        table=table,
        pad=pad,
        dose_map=raw_output[c.OUTPUT_KEY_DOSE_MAP],
        hits=[event if isinstance(event, list) else event.tolist() for event in raw_output[c.OUTPUT_KEY_HITS]],
        backscatter_correction=[
            event if isinstance(event, list) else event.tolist()
            for event in raw_output[c.OUTPUT_KEY_CORRECTION_BACK_SCATTER]
        ],
        inverse_square_law_correction=[
            event if isinstance(event, (list, float)) else ([] if event is None else event.tolist())
            for event in raw_output[c.OUTPUT_KEY_CORRECTION_INVERSE_SQUARE_LAW]
        ],  # type: ignore[arg-type]
        medium_correction=raw_output[c.OUTPUT_KEY_CORRECTION_MEDIUM],
        table_correction=raw_output[c.OUTPUT_KEY_CORRECTION_TABLE],
        settings=settings,
        data_norm=data_norm,
        kerma_meter_correction=raw_output.get(c.OUTPUT_KEY_CORRECTION_KERMA_METER),
        kerma_corrected=raw_output.get(c.OUTPUT_KEY_KERMA_CORRECTED),
        k_tab_statuses=raw_output.get(c.OUTPUT_KEY_CORRECTION_TABLE_STATUSES),
        rotational_handling=raw_output.get(c.OUTPUT_KEY_ROTATIONAL_HANDLING),
        rotational_envelope=raw_output.get(c.OUTPUT_KEY_ROTATIONAL_ENVELOPE),
        tube_summary=raw_output.get(c.OUTPUT_KEY_TUBE_SUMMARY),
        hits_union=normalize_hit_masks(raw_output.get(c.OUTPUT_KEY_HITS_UNION)),
    )


def _exam_result(
    exam: InputAdapterResult,
    exam_id: str,
    effective_offset: list[float],
    settings: PyskindoseSettings,
    output: PySkinDoseOutput,
    data_norm: pd.DataFrame,
    warnings: list[str],
    equipment_profile_match: dict[str, Any] | None = None,
) -> ExamResult:
    """Assemble the per-exam result dict after a successful dose calculation."""
    if equipment_profile_match is None:
        equipment_profile_match = _match_mapping_for_output(settings, exam.equipment_receipt, exam.normalized_data)
    return ExamResult(
        exam_id=exam_id,
        source_file=exam.provenance.original_filename,
        event_count=len(data_norm),
        patient_offset=effective_offset,
        settings_snapshot={
            "mode": settings.mode,
            "phantom": {
                "model": settings.phantom.model,
                "patient_offset": {
                    "d_lon": settings.phantom.patient_offset.d_lon,
                    "d_ver": settings.phantom.patient_offset.d_ver,
                    "d_lat": settings.phantom.patient_offset.d_lat,
                },
                "patient_orientation": settings.phantom.patient_orientation,
            },
        },
        output=output,
        warnings=warnings,
        equipment_profile_match=equipment_profile_match,
    )


def _process_exam(
    exam: InputAdapterResult,
    exam_id: str,
    effective_offset: list[float],
    settings: PyskindoseSettings,
    warnings: list[str],
    equipment_profile_match: dict[str, Any] | None = None,
) -> ExamResult | None:
    """Run geometry + dose calculation for a single loaded exam.

    A stored captured match bypasses live receipt handling; ``None`` keeps
    the established live path (receipt restore plus mapping validation).
    Captured mode never carries live receipts, so the restore branch stays
    dormant there by construction.
    """
    if exam.equipment_receipt is not None:
        from guiskindose.equipment_resolution import restore_receipt_to_settings

        # The shared settings object still holds whichever exam loaded last:
        # restore this exam's proven values before anything reads them.
        restore_receipt_to_settings(exam.equipment_receipt, settings.normalization_settings)
    data_norm = calculate_rotation_matrices(exam.normalized_data)
    table, pad = _fresh_table_and_pad(settings)
    dprint("RENDERING", f"{exam_id}: creating geometry plot")
    create_geometry_plot(normalized_data=data_norm, table=table, pad=pad, settings=settings)

    dprint("CALCULATION", f"{exam_id}: calculating dose")
    patient, raw_output, export_data_norm = calculate_dose(
        normalized_data=data_norm, settings=settings, table=table, pad=pad, exam_id=exam_id
    )
    if raw_output is None or patient is None or export_data_norm is None:
        # Caller appends the exclusion warning to run_warnings and also
        # preserves any import / per-exam warnings collected so far.
        return None

    _add_missed_event_warnings(warnings, exam_id, raw_output, len(export_data_norm))
    output = _multi_exam_output(patient, table, pad, raw_output, settings, export_data_norm)
    dprint("RENDERING", f"{exam_id}: creating dose map plot")
    create_dose_map_plot(patient=patient, settings=settings, dose_map=output.dose_map)
    return _exam_result(
        exam, exam_id, effective_offset, settings, output, export_data_norm, warnings,
        equipment_profile_match=equipment_profile_match,
    )


def analyze_multiple_exams(
    exams: list[InputAdapterResult],
    settings: str | dict | PyskindoseSettings,
    per_exam_offsets: list[list[float]] | None = None,
    per_exam_extra_warnings: list[list[str]] | None = None,
    *,
    equipment_capture_contexts: list[CapturedCoordinates | None] | tuple[CapturedCoordinates | None, ...] | None = None,
) -> MultiExamResult:
    """Process a list of exams on a shared phantom mesh topology.

    A fresh table and pad are created for every exam because their positioning
    uses incremental translation. Failed exams are retained as run warnings and
    do not discard successful results.

    ``equipment_capture_contexts`` optionally carries one validated captured
    authority per exam position as an exact builtin list or tuple
    (``None`` entries stay unspecified baseline, never fake provenance).
    With captures, any configured live session or per-exam live receipt fails
    closed, and every provided capture is validated against its own frame —
    with isolated private settings — before any exam produces output, so a
    bad later capture leaves no partial result. Each captured exam calculates
    on its own prepared work settings, so normalization from one exam is
    never borrowed by another.
    """
    settings = initialize_settings(settings)
    downgrade_beam_warning = settings.beam_miss_warn == "per_event"
    if downgrade_beam_warning:
        logger.info("beam_miss_warn downgraded from 'per_event' to 'summary' for multi-exam run.")

    # Validate every configured offset before any exam produces output so a bad
    # later offset cannot leave a partial multi-exam result behind.
    _validate_per_exam_offsets(per_exam_offsets)

    captured: list[tuple[PyskindoseSettings, dict[str, Any] | None, list[float]]] | None = None
    if equipment_capture_contexts is not None:
        # Captured mode first: shape, session/receipt rejection, and every
        # capture validated before the live session path below can misread
        # the mixed authority as a live failure with a different error.
        aligned = _validate_capture_contexts(exams, equipment_capture_contexts)
        captured = _prepare_captured_exams(exams, aligned, settings, per_exam_offsets, downgrade_beam_warning)

    # Same atomicity for custom sessions: every exam must carry its resolved
    # raw provenance before anything calculates, so a late failure cannot
    # leave a partial result behind.
    _validate_session_records(exams, settings)

    exam_results: list[ExamResult] = []
    run_warnings: list[str] = []
    aggregate_dose_map: np.ndarray | None = None
    total_events = 0
    global_offset = _global_patient_offset(settings)

    for index, exam in enumerate(exams):
        exam_id = opaque_exam_label(index)
        warnings = _exam_warnings(exam, index, per_exam_extra_warnings)
        if captured is None:
            effective_offset = _effective_patient_offset(global_offset, per_exam_offsets, index)
            exam_work = _settings_for_exam(settings, effective_offset, downgrade_beam_warning)
            stored_match = None
        else:
            exam_work, stored_match, effective_offset = captured[index]
        try:
            result = _process_exam(
                exam, exam_id, effective_offset, exam_work, warnings,
                equipment_profile_match=stored_match,
            )
        except Exception as exc:
            safe_error_event(logger, "multi_exam_analysis", exc, level=logging.WARNING)
            # Excluded exams never become ExamResult rows, so import / per-exam
            # warnings must be copied onto the run warning list here.
            run_warnings.extend(warnings)
            run_warnings.append(_format_multi_exam_failure_warning(exam_id, exc))
            continue

        if result is None:
            run_warnings.extend(warnings)
            run_warnings.append(_format_multi_exam_no_output_warning(exam_id))
            continue

        exam_results.append(result)
        exam_dose_map = result.output.dose_map
        aggregate_dose_map = exam_dose_map.copy() if aggregate_dose_map is None else aggregate_dose_map + exam_dose_map
        total_events += result.event_count

    exams_attempted = len(exams)
    exams_excluded = exams_attempted - len(exam_results)
    if exams_excluded > 0:
        run_warnings.insert(
            0,
            (
                f"{exams_excluded} of {exams_attempted} exam(s) were excluded from the "
                "aggregate peak skin dose. Per-exam details follow."
            ),
        )

    aggregate_dose_map = np.array([]) if aggregate_dose_map is None else aggregate_dose_map
    return MultiExamResult(
        exams=exam_results,
        aggregate_dose_map=aggregate_dose_map,
        aggregate_psd=float(aggregate_dose_map.max()) if aggregate_dose_map.size else 0.0,
        total_events=total_events,
        warnings=run_warnings,
        exams_attempted=exams_attempted,
        exams_excluded=exams_excluded,
    )
