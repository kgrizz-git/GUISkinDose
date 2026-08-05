"""Adapter: build an :class:`ExportSource` from GUI ``AppState``.

Thin GUI-side glue so ``mypyskindose.export`` stays free of any GUI imports.
Branches on multi-exam vs single-exam per §7 of the Rich Export plan.
"""

from __future__ import annotations

import pandas as pd

from mypyskindose.export import ExportExamSource, ExportSource
from mypyskindose.privacy import opaque_exam_label

from .settings_builder import build_settings
from .state import AppState


def _single_transform_meta(state: AppState) -> dict:
    return {
        "swap_lat_lon": bool(state.swap_lat_lon),
        "lat_lon_swapped": bool(state.swap_lat_lon),
        "flip_ap1": bool(state.flip_ap1),
        "flip_ap2": bool(state.flip_ap2),
        "normalization_profile": state.normalization_method,
    }


def build_export_source_from_gui(
    state: AppState, *, include_source_identifiers: bool = False
) -> ExportSource:
    """Assemble an ``ExportSource`` from current GUI state.

    Multi-exam (``state.multi_exam_result``) takes precedence over the single
    ``state.output`` dict.
    """
    if state.multi_exam_result is not None:
        return _multi_exam_export_source(state, include_source_identifiers=include_source_identifiers)
    return _single_exam_export_source(state, include_source_identifiers=include_source_identifiers)


def _multi_exam_export_source(state: AppState, *, include_source_identifiers: bool) -> ExportSource:
    """Build a GUI export source from the current per-exam result objects."""
    assert state.multi_exam_result is not None
    result = state.multi_exam_result
    exams: list[ExportExamSource] = []
    for index, exam_result in enumerate(result.exams):
        adapter = state.loaded_exams[index] if index < len(state.loaded_exams) else None
        metadata = state.loaded_exam_meta[index] if index < len(state.loaded_exam_meta) else {}
        offset = tuple(exam_result.patient_offset)
        exams.append(
            ExportExamSource(
                exam_id=exam_result.exam_id,
                normalized_data=adapter.normalized_data if adapter is not None else pd.DataFrame(),
                provenance=adapter.provenance if adapter is not None else None,
                source_file=exam_result.source_file,
                effective_settings=build_settings(state, patient_offset=offset),  # type: ignore[arg-type]
                patient_offset=offset,  # type: ignore[arg-type]
                transform_meta=dict(metadata),
                extra_warnings=list(exam_result.warnings),
            )
        )
    return ExportSource(
        execution_context="gui",
        multi_exam_result=result,
        exams=exams,
        calc_warnings=list(state.calc_warnings),
        import_warnings=list(state.import_warnings),
        file_name=state.file_name or None,
        colorscale=state.colorscale,
        include_source_identifiers=include_source_identifiers,
    )


def _single_exam_export_source(state: AppState, *, include_source_identifiers: bool) -> ExportSource:
    """Build a GUI export source from the current single-exam result dictionary."""
    settings = build_settings(state)
    offset = (state.d_lon, state.d_ver, state.d_lat)
    exam = ExportExamSource(
        exam_id=opaque_exam_label(0),
        normalized_data=state.rdsr_df if state.rdsr_df is not None else pd.DataFrame(),
        provenance=state.import_provenance,
        source_file=state.file_name or None,
        effective_settings=settings,
        patient_offset=offset,
        transform_meta=_single_transform_meta(state),
    )
    return ExportSource(
        execution_context="gui",
        output_dict=state.output,
        exams=[exam],
        calc_warnings=list(state.calc_warnings),
        import_warnings=list(state.import_warnings),
        file_name=state.file_name or None,
        colorscale=state.colorscale,
        include_source_identifiers=include_source_identifiers,
    )
