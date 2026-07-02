"""Build an :class:`ExportSource` from CLI execution (no GUI state).

The CLI captures the calculation result (single-exam ``output_dict`` or a
``MultiExamResult``), the normalized input DataFrame(s), provenance, and
warnings, then hands them here to assemble the export bundle.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .models import ExportExamSource, ExportSource

if TYPE_CHECKING:
    import pandas as pd

    from mypyskindose.format_export_data import MultiExamResult
    from mypyskindose.input_adapters.models import InputAdapterResult
    from mypyskindose.settings import PyskindoseSettings


def _offset_tuple(settings: Any) -> tuple[float, float, float]:
    off = settings.phantom.patient_offset
    return (float(off.d_lon), float(off.d_ver), float(off.d_lat))


def build_export_source_from_cli(
    settings: "PyskindoseSettings",
    *,
    output_dict: dict[str, Any] | None = None,
    multi_exam_result: "MultiExamResult | None" = None,
    inputs: "list[InputAdapterResult] | None" = None,
    single_normalized_data: "pd.DataFrame | None" = None,
    single_source_file: str | None = None,
    calc_warnings: list[str] | None = None,
    import_warnings: list[str] | None = None,
    file_name: str | None = None,
    report_title: str | None = None,
    colorscale: str = "jet",
) -> ExportSource:
    """Assemble an ``ExportSource`` for headless (CLI) export.

    Provide either ``output_dict`` + single-exam inputs, or ``multi_exam_result``
    + ``inputs`` (one ``InputAdapterResult`` per exam, parallel to the result's
    ``exams``).
    """
    exams: list[ExportExamSource] = []

    if multi_exam_result is not None:
        result_exams = multi_exam_result.exams
        for i, er in enumerate(result_exams):
            adapter = inputs[i] if inputs and i < len(inputs) else None
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
    elif output_dict is not None:
        adapter = inputs[0] if inputs else None
        exams.append(
            ExportExamSource(
                exam_id=(single_source_file or file_name or "exam"),
                normalized_data=(
                    single_normalized_data
                    if single_normalized_data is not None
                    else (adapter.normalized_data if adapter is not None else _empty_df())
                ),
                provenance=(adapter.provenance if adapter is not None else None),
                source_file=single_source_file or file_name,
                effective_settings=settings,
                patient_offset=_offset_tuple(settings),
                transform_meta={},
            )
        )

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
    )


def _empty_df():
    import pandas as pd

    return pd.DataFrame()
