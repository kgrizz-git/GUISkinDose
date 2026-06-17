import copy
import logging
from typing import Any, Dict, Union

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
from mypyskindose.settings import PyskindoseSettings, initialize_settings
from mypyskindose.debug import dprint

logger = logging.getLogger(__name__)


def analyze_data(
    normalized_data: pd.DataFrame,
    settings: Union[str, dict, PyskindoseSettings],
) -> Union[Dict[str, Any], str, PySkinDoseOutput]:
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
    patient, output = calculate_dose(normalized_data=normalized_data, settings=settings, table=table, pad=pad)

    if settings.output_format in [c.RUN_ARGUMENTS_OUTPUT_DICT, c.RUN_ARGUMENTS_OUTPUT_JSON]:
        if output is None or patient is None:
            raise RuntimeError("Dose calculation did not produce output in calculate_dose mode.")
        dprint("PROCESSING", "Formatting analysis result for export")
        mypyskindose_output: Union[PySkinDoseOutput, dict[str, Any], str] = format_analysis_result_for_export(
            output, patient=patient, table=table, pad=pad, data_norm=normalized_data, settings=settings
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


def analyze_multiple_exams(
    exams: list[InputAdapterResult],
    settings: Union[str, dict, PyskindoseSettings],
    per_exam_offsets: list[list[float]] | None = None,
) -> MultiExamResult:
    """Process a list of exams on a shared phantom mesh topology.

    Each exam creates fresh Phantom instances (to avoid position-state
    compounding from repeated calls to position_patient_phantom_on_table).
    The mesh topology is identical across instances, so dose_map[i] refers to
    the same anatomical vertex in every exam; element-wise summation gives the
    cumulative skin dose across all exams.

    Parameters
    ----------
    exams:
        One InputAdapterResult per exam. Use study_id for labelling when
        splitting a single multi-study file.
    settings:
        Global settings. output_format is ignored; MultiExamResult is always
        returned. The caller serializes it via to_dict() / to_json().
    per_exam_offsets:
        Optional per-exam patient offsets [[d_lon, d_ver, d_lat], ...].
        If shorter than exams or None, remaining exams use the global offset.
    """
    settings = initialize_settings(settings)

    exam_results: list[ExamResult] = []
    run_warnings: list[str] = []
    aggregate_dose_map: np.ndarray | None = None
    total_events = 0

    for i, exam in enumerate(exams):
        exam_warnings: list[str] = list(exam.warnings)

        # Determine effective patient offset for this exam.
        global_offset = [
            float(settings.phantom.patient_offset.d_lon),
            float(settings.phantom.patient_offset.d_ver),
            float(settings.phantom.patient_offset.d_lat),
        ]
        if per_exam_offsets and i < len(per_exam_offsets):
            effective_offset = [float(v) for v in per_exam_offsets[i]]
        else:
            effective_offset = global_offset

        # Build per-exam settings (deepcopy only when offset differs).
        if effective_offset != global_offset:
            exam_settings = copy.deepcopy(settings)
            exam_settings.phantom.patient_offset.d_lon = effective_offset[0]
            exam_settings.phantom.patient_offset.d_ver = effective_offset[1]
            exam_settings.phantom.patient_offset.d_lat = effective_offset[2]
        else:
            exam_settings = settings

        try:
            data_norm = calculate_rotation_matrices(exam.normalized_data)

            # Fresh phantoms per exam: position_patient_phantom_on_table uses
            # incremental translate() calls, so reusing a Phantom instance across
            # exams with different offsets would compound translations.
            table = Phantom(phantom_model=c.PHANTOM_MODEL_TABLE, phantom_dim=exam_settings.phantom.dimension)
            pad = Phantom(phantom_model=c.PHANTOM_MODEL_PAD, phantom_dim=exam_settings.phantom.dimension)

            dprint("RENDERING", f"Exam {i}: creating geometry plot")
            create_geometry_plot(normalized_data=data_norm, table=table, pad=pad, settings=exam_settings)

            dprint("CALCULATION", f"Exam {i}: calculating dose")
            patient, raw_output = calculate_dose(
                normalized_data=data_norm, settings=exam_settings, table=table, pad=pad
            )

            if raw_output is None or patient is None:
                msg = f"Exam {i} ({exam.provenance.original_filename!r}): no output (check mode setting)."
                exam_warnings.append(msg)
                run_warnings.append(msg)
                continue

            exam_dose_map: np.ndarray = raw_output[c.OUTPUT_KEY_DOSE_MAP]

            psd_output = PySkinDoseOutput(
                patient=patient,
                table=table,
                pad=pad,
                dose_map=exam_dose_map,
                hits=[
                    ev if isinstance(ev, list) else ev.tolist()
                    for ev in raw_output[c.OUTPUT_KEY_HITS]
                ],
                backscatter_correction=[
                    ev if isinstance(ev, list) else ev.tolist()
                    for ev in raw_output[c.OUTPUT_KEY_CORRECTION_BACK_SCATTER]
                ],
                inverse_square_law_correction=[
                    ev if isinstance(ev, (list, float)) else ([] if ev is None else ev.tolist())
                    for ev in raw_output[c.OUTPUT_KEY_CORRECTION_INVERSE_SQUARE_LAW]
                ],  # type: ignore[arg-type]
                medium_correction=raw_output[c.OUTPUT_KEY_CORRECTION_MEDIUM],
                table_correction=raw_output[c.OUTPUT_KEY_CORRECTION_TABLE],
                settings=exam_settings,
                data_norm=data_norm,
            )

            if aggregate_dose_map is None:
                aggregate_dose_map = exam_dose_map.copy()
            else:
                aggregate_dose_map = aggregate_dose_map + exam_dose_map

            total_events += len(data_norm)

            dprint("RENDERING", f"Exam {i}: creating dose map plot")
            create_dose_map_plot(patient=patient, settings=exam_settings, dose_map=exam_dose_map)

            exam_results.append(
                ExamResult(
                    exam_id=exam.study_id or exam.provenance.original_filename,
                    source_file=exam.provenance.original_filename,
                    event_count=len(data_norm),
                    patient_offset=effective_offset,
                    settings_snapshot={
                        "mode": exam_settings.mode,
                        "phantom": {
                            "model": exam_settings.phantom.model,
                            "patient_offset": {
                                "d_lon": exam_settings.phantom.patient_offset.d_lon,
                                "d_ver": exam_settings.phantom.patient_offset.d_ver,
                                "d_lat": exam_settings.phantom.patient_offset.d_lat,
                            },
                            "patient_orientation": exam_settings.phantom.patient_orientation,
                        },
                    },
                    output=psd_output,
                    warnings=exam_warnings,
                )
            )

        except Exception as exc:
            msg = f"Exam {i} ({exam.provenance.original_filename!r}) failed: {exc}"
            logger.warning(msg)
            run_warnings.append(msg)

    if aggregate_dose_map is None:
        aggregate_dose_map = np.array([])

    return MultiExamResult(
        exams=exam_results,
        aggregate_dose_map=aggregate_dose_map,
        aggregate_psd=float(aggregate_dose_map.max()) if aggregate_dose_map.size > 0 else 0.0,
        total_events=total_events,
        warnings=run_warnings,
    )
