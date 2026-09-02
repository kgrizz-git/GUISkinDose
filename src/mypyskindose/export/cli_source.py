"""Build an :class:`ExportSource` from CLI execution (no GUI state).

The CLI captures the calculation result (single-exam ``output_dict`` or a
``MultiExamResult``), the normalized input DataFrame(s), provenance, and
warnings, then hands them here to assemble the export bundle.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from mypyskindose.privacy import opaque_exam_label, resolve_loaded_exam_index

from .models import ExportExamSource, ExportSource

if TYPE_CHECKING:
    import pandas as pd

    from mypyskindose.format_export_data import MultiExamResult
    from mypyskindose.input_adapters.models import InputAdapterResult
    from mypyskindose.settings import PyskindoseSettings


def _offset_tuple(settings: Any) -> tuple[float, float, float]:
    off = settings.phantom.patient_offset
    return (float(off.d_lon), float(off.d_ver), float(off.d_lat))


def _empty_df():
    import pandas as pd

    return pd.DataFrame()


def _exam_source_from_multi_result(
    settings: PyskindoseSettings,
    multi_exam_result: MultiExamResult,
    inputs: list[InputAdapterResult] | None,
) -> list[ExportExamSource]:
    """Build per-exam export sources from a multi-exam calculation result.

    ``inputs`` is the full pre-calculation list (including exams later excluded
    from ``multi_exam_result.exams``). Match each result row by opaque ``Exam N``
    label rather than by enumeration index so excluded exams do not shift later
    rows onto the wrong normalized frame / provenance.
    """
    exams: list[ExportExamSource] = []
    n_inputs = len(inputs) if inputs else 0
    for result_index, er in enumerate(multi_exam_result.exams):
        loaded_index = resolve_loaded_exam_index(
            er.exam_id, result_index=result_index, n_loaded=n_inputs
        )
        adapter = (
            inputs[loaded_index]
            if inputs is not None and loaded_index is not None
            else None
        )
        exams.append(
            ExportExamSource(
                exam_id=er.exam_id,
                normalized_data=(adapter.normalized_data if adapter is not None else _empty_df()),
                provenance=(adapter.provenance if adapter is not None else None),
                source_file=er.source_file,
                effective_settings=settings,
                patient_offset=tuple(er.patient_offset),  # type: ignore[arg-type]
                transform_meta={},
                extra_warnings=list(er.warnings),
            )
        )
    return exams


def _exam_source_from_single(
    settings: PyskindoseSettings,
    *,
    inputs: list[InputAdapterResult] | None,
    single_normalized_data: pd.DataFrame | None,
    single_source_file: str | None,
    file_name: str | None,
) -> list[ExportExamSource]:
    """Build the single-exam export source list for CLI export."""
    adapter = inputs[0] if inputs else None
    normalized = single_normalized_data
    if normalized is None:
        normalized = adapter.normalized_data if adapter is not None else _empty_df()
    return [
        ExportExamSource(
            exam_id=opaque_exam_label(0),
            normalized_data=normalized,
            provenance=(adapter.provenance if adapter is not None else None),
            source_file=single_source_file or file_name,
            effective_settings=settings,
            patient_offset=_offset_tuple(settings),
            transform_meta={},
        )
    ]


def build_export_source_from_cli(
    settings: PyskindoseSettings,
    *,
    output_dict: dict[str, Any] | None = None,
    multi_exam_result: MultiExamResult | None = None,
    inputs: list[InputAdapterResult] | None = None,
    single_normalized_data: pd.DataFrame | None = None,
    single_source_file: str | None = None,
    calc_warnings: list[str] | None = None,
    import_warnings: list[str] | None = None,
    file_name: str | None = None,
    report_title: str | None = None,
    colorscale: str = "jet",
    include_source_identifiers: bool = False,
) -> ExportSource:
    """Assemble an ``ExportSource`` for headless (CLI) export.

    Provide either ``output_dict`` + single-exam inputs, or ``multi_exam_result``
    + ``inputs`` (the full pre-calculation input list, including any exams later
    excluded from ``multi_exam_result.exams``; rows are matched by opaque
    ``Exam N`` labels).
    """
    if multi_exam_result is not None:
        exams = _exam_source_from_multi_result(settings, multi_exam_result, inputs)
    elif output_dict is not None:
        exams = _exam_source_from_single(
            settings,
            inputs=inputs,
            single_normalized_data=single_normalized_data,
            single_source_file=single_source_file,
            file_name=file_name,
        )
    else:
        exams = []

    return ExportSource(
        execution_context="cli",
        output_dict=output_dict,
        multi_exam_result=multi_exam_result,
        exams=exams,
        calc_warnings=list(calc_warnings or []),
        import_warnings=list(import_warnings or []),
        file_name=file_name,
        colorscale=colorscale,
        report_title=report_title,
        include_source_identifiers=include_source_identifiers,
    )
