import copy
import logging
from typing import Any, Dict

import numpy as np
import pandas as pd

from mypyskindose import constants as c
from mypyskindose.calculate_dose.calculate_dose import calculate_dose
from mypyskindose.format_export_data import (
    ExamResult,
    MultiExamResult,
    PySkinDoseOutput,
    format_analysis_result_for_export,
)
from mypyskindose.helpers.calculate_rotation_matrices import calculate_rotation_matrices
from mypyskindose.input_adapters.models import InputAdapterResult
from mypyskindose.phantom_class import Phantom
from mypyskindose.plotting.create_dose_map_plot import create_dose_map_plot
from mypyskindose.plotting.create_geometry_plot import create_geometry_plot
from mypyskindose.privacy import exception_class_name, opaque_exam_label, safe_error_event
from mypyskindose.settings import PyskindoseSettings, initialize_settings
from mypyskindose.debug import dprint

logger = logging.getLogger(__name__)


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
) -> Dict[str, Any] | str | PySkinDoseOutput:
    """Analyze data och settings, and runs PySkinDose in desired mode.

    Parameters
    ----------
    normalized_data : pd.DataFrame
        RDSR data, normalized for compliance with PySkinDose.
    settings : Union[str, dict, PyskindoseSettings]
        Settings class for PySkinDose

    Returns
    -------
    Dict[str, Any]
        output dictionary containing calculation specifics such as dose map, correction
        factors, etc.

    """
    settings = initialize_settings(settings)

    if settings.output_format not in c.RUN_ARGUMENTS_VALID_OUTPUT_FORMATS:
        raise ValueError(
            f"Invalid output format specified. Must be one of {'.'.join(c.RUN_ARGUMENTS_VALID_OUTPUT_FORMATS)}"
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
        mypyskindose_output: PySkinDoseOutput | dict[str, Any] | str = format_analysis_result_for_export(
            output, patient=patient, table=table, pad=pad, data_norm=export_data_norm, settings=settings
        )

        return mypyskindose_output

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
        if output is None:
            raise RuntimeError("Expected HTML output but dose calculation returned no data.")
        return output

    raise ValueError(f"Unhandled output format: {settings.output_format}")


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
    )


def _exam_result(
    exam: InputAdapterResult,
    exam_id: str,
    effective_offset: list[float],
    settings: PyskindoseSettings,
    output: PySkinDoseOutput,
    data_norm: pd.DataFrame,
    warnings: list[str],
) -> ExamResult:
    """Assemble the per-exam result dict after a successful dose calculation."""
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
    )


def _process_exam(
    exam: InputAdapterResult,
    exam_id: str,
    effective_offset: list[float],
    settings: PyskindoseSettings,
    warnings: list[str],
) -> ExamResult | None:
    """Run geometry + dose calculation for a single loaded exam."""
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
    create_dose_map_plot(patient=patient, settings=settings, dose_map=output.DoseMap)
    return _exam_result(exam, exam_id, effective_offset, settings, output, export_data_norm, warnings)


def analyze_multiple_exams(
    exams: list[InputAdapterResult],
    settings: str | dict | PyskindoseSettings,
    per_exam_offsets: list[list[float]] | None = None,
    per_exam_extra_warnings: list[list[str]] | None = None,
) -> MultiExamResult:
    """Process a list of exams on a shared phantom mesh topology.

    A fresh table and pad are created for every exam because their positioning
    uses incremental translation. Failed exams are retained as run warnings and
    do not discard successful results.
    """
    settings = initialize_settings(settings)
    downgrade_beam_warning = settings.beam_miss_warn == "per_event"
    if downgrade_beam_warning:
        logger.info("beam_miss_warn downgraded from 'per_event' to 'summary' for multi-exam run.")

    # Validate every configured offset before any exam produces output so a bad
    # later offset cannot leave a partial multi-exam result behind.
    _validate_per_exam_offsets(per_exam_offsets)

    exam_results: list[ExamResult] = []
    run_warnings: list[str] = []
    aggregate_dose_map: np.ndarray | None = None
    total_events = 0
    global_offset = _global_patient_offset(settings)

    for index, exam in enumerate(exams):
        exam_id = opaque_exam_label(index)
        warnings = _exam_warnings(exam, index, per_exam_extra_warnings)
        effective_offset = _effective_patient_offset(global_offset, per_exam_offsets, index)
        exam_settings = _settings_for_exam(settings, effective_offset, downgrade_beam_warning)
        try:
            result = _process_exam(exam, exam_id, effective_offset, exam_settings, warnings)
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
        exam_dose_map = result.output.DoseMap
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
