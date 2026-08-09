"""Public collector: ``collect_export_payload(source) -> ExportPayload``.

Normalizes single-exam (dict) and multi-exam (object) results into one internal
view, then assembles every report section (§1–§10). Writers consume the returned
:class:`ExportPayload` only; this module never imports GUI code.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import numpy as np
import pandas as pd

from . import images as _images
from . import metrics as _metrics
from . import sections as _sections
from ._exam_view import ExamView, view_from_dict, view_from_output
from .models import (
    APP_NAME,
    RICH_EXPORT_SCHEMA_VERSION,
    CumulativeSection,
    DosimetricMetrics,
    ExamSection,
    ExportError,
    ExportPayload,
    ExportSource,
    ImageEntry,
    ReportMeta,
    WarningsBlock,
)
from .provenance import collect_provenance


def _package_version() -> str:
    try:
        from importlib.metadata import version

        return version("mypyskindose")
    except Exception:
        return "unknown"


@dataclass
class _Resolved:
    is_multi_exam: bool
    views: list[ExamView]
    exam_ids: list[str]
    aggregate_dose_map: np.ndarray
    run_warnings: list[str]


def resolve_calculation_result(source: ExportSource) -> _Resolved:
    """Normalize the two result shapes into a uniform per-exam view list.

    Multi-exam takes precedence over ``output_dict`` when both are set.
    """
    if source.multi_exam_result is not None:
        result = source.multi_exam_result
        views = [view_from_output(er.output) for er in result.exams]
        exam_ids = [er.exam_id for er in result.exams]
        return _Resolved(
            is_multi_exam=True,
            views=views,
            exam_ids=exam_ids,
            aggregate_dose_map=np.asarray(result.aggregate_dose_map, dtype=float),
            run_warnings=list(result.warnings),
        )
    if source.output_dict is not None:
        view = view_from_dict(source.output_dict)
        exam_id = source.exams[0].exam_id if source.exams else "Exam 1"
        return _Resolved(
            is_multi_exam=False,
            views=[view],
            exam_ids=[exam_id],
            aggregate_dose_map=view.dense_dose_map,
            run_warnings=[],
        )
    raise ExportError("No calculation result: set output_dict or multi_exam_result on ExportSource.")


def _exam_source_for(source: ExportSource, index: int):
    return source.exams[index] if index < len(source.exams) else None


def _build_exam_section(view: ExamView, exam_src, exam_id: str) -> ExamSection:
    df = exam_src.normalized_data if exam_src is not None else None
    settings = exam_src.effective_settings if exam_src is not None else None
    discarded = sum(exam_src.discarded_events.values()) if exam_src is not None else 0

    snapshot = _sections.serialize_settings(settings) if settings is not None else {}
    return ExamSection(
        exam_id=exam_id,
        manufacturer=(_sections.equipment_section(exam_src)["manufacturer"] if exam_src else None),
        model=(_sections.equipment_section(exam_src)["model"] if exam_src else None),
        normalization_profile=(_sections.equipment_section(exam_src)["normalization_profile"] if exam_src else None),
        settings=snapshot,
        non_default_settings=(_sections.non_default_settings(snapshot) if snapshot else {}),
        coordinate=(_sections.coordinate_section(exam_src, settings) if exam_src and settings else {}),
        phantom=(_sections.phantom_section(view, settings) if settings is not None else {}),
        metrics=_metrics.dosimetric_metrics(view, df, events_discarded=discarded),
        corrections=_metrics.correction_stats(view),
        unit_conversions=(
            dict(getattr(exam_src.provenance, "unit_conversions", None) or {})
            if exam_src is not None and exam_src.provenance is not None
            else {}
        ),
        warnings=(list(exam_src.extra_warnings) if exam_src else []),
    )


def _cumulative_section(resolved: _Resolved, source: ExportSource) -> CumulativeSection:
    views = resolved.views
    if not resolved.is_multi_exam:
        # Single exam: cumulative mirrors the one exam.
        exam_src = _exam_source_for(source, 0)
        df = exam_src.normalized_data if exam_src else None
        discarded = sum(exam_src.discarded_events.values()) if exam_src else 0
        return CumulativeSection(
            metrics=_metrics.dosimetric_metrics(views[0], df, events_discarded=discarded),
            corrections=_metrics.correction_stats(views[0]),
        )

    dfs = [s.normalized_data for s in source.exams]
    combined_df = pd.concat(dfs, ignore_index=True) if dfs else None
    agg = resolved.aggregate_dose_map
    peak_idx = int(np.argmax(agg)) if agg.size and float(agg.max()) > 0 else None
    peak_xyz = views[0].skin_cell_xyz(peak_idx) if (peak_idx is not None and views) else None
    total_discarded = sum(sum(s.discarded_events.values()) for s in source.exams)
    dap_values = [d for d in (_metrics.total_dap_gycm2(df) for df in dfs) if d is not None]
    fluoro_values = [t for t in (_metrics.total_fluoro_time_s(df) for df in dfs) if t is not None]

    metrics = DosimetricMetrics(
        psd=(float(agg.max()) if agg.size else 0.0),
        air_kerma=_metrics.cumulative_air_kerma(views),
        dap_gycm2=(sum(dap_values) if dap_values else None),
        fluoro_time_s=(sum(fluoro_values) if fluoro_values else None),
        events_processed=sum(len(df) for df in dfs),
        events_discarded=total_discarded,
        peak_vertex_index=peak_idx,
        peak_xyz=peak_xyz,
        acquisition_breakdown=_metrics.acquisition_breakdown(combined_df),
    )
    return CumulativeSection(
        metrics=metrics,
        corrections=_metrics.cumulative_correction_stats(views),
        primary_contributing_exam=_metrics.primary_contributing_exam(views, resolved.exam_ids, agg),
    )


def _render_images(resolved: _Resolved, source: ExportSource) -> list[ImageEntry]:
    images: list[ImageEntry] = []
    views = resolved.views
    if not views:
        return images
    colorscale = source.colorscale
    patient0 = views[0].patient
    agg = resolved.aggregate_dose_map

    def add(label, view, exam_id, dose_map, patient, dims, eye, zoom):
        png = _images.render_dosemap_png(
            dose_map, patient, camera_eye=eye, colorscale=colorscale, zoom_to_dose=zoom, **dims
        )
        images.append(
            ImageEntry(
                label=label, view=view, exam_id=exam_id, png_bytes=png,
                error_message=None if png is not None else "Image unavailable (kaleido/export error)",
            )
        )

    # A whole-body context view (anatomical scale) plus a view zoomed to the
    # irradiated region — the dose patch is often small/localized and invisible
    # at whole-phantom scale. DORSAL faces the posterior (+Y), the usual beam
    # entrance for supine cases.
    if resolved.is_multi_exam:
        add("Cumulative dose map (whole body)", "context", None, agg, patient0, _images.CUMULATIVE_DIMS, _images.DORSAL, False)
        add("Cumulative dose map (irradiated region)", "dose", None, agg, patient0, _images.CUMULATIVE_DIMS, _images.DORSAL, True)
        if len(views) <= 10:
            for view, exam_id in zip(views, resolved.exam_ids, strict=True):
                add(f"Exam {exam_id} (irradiated region)", "dose", exam_id, view.dense_dose_map, view.patient,
                    _images.THUMBNAIL_DIMS, _images.DORSAL, True)
    else:
        eid = resolved.exam_ids[0]
        add("Dose map (whole body)", "context", eid, views[0].dense_dose_map, patient0, _images.CUMULATIVE_DIMS, _images.DORSAL, False)
        add("Dose map (irradiated region)", "dose", eid, views[0].dense_dose_map, patient0, _images.CUMULATIVE_DIMS, _images.DORSAL, True)
    return images


def collect_export_payload(source: ExportSource, *, with_images: bool = True) -> ExportPayload:
    """Build the writer-facing :class:`ExportPayload` from a GUI/CLI bundle."""
    resolved = resolve_calculation_result(source)

    meta = ReportMeta(
        app_name=APP_NAME,
        package_version=_package_version(),
        schema_version=RICH_EXPORT_SCHEMA_VERSION,
        generated_at=datetime.now().astimezone(),
        execution_context=source.execution_context,
        report_title=(
            source.report_title
            or f"MyPySkinDose report — {datetime.now(UTC).astimezone():%Y-%m-%d %H:%M}"
        ),
    )

    provenance = collect_provenance(
        source.exams,
        source.import_warnings,
        source.file_name,
        include_source_identifiers=source.include_source_identifiers,
    )

    exam_sections = [
        _build_exam_section(view, _exam_source_for(source, i), exam_id)
        for i, (view, exam_id) in enumerate(zip(resolved.views, resolved.exam_ids, strict=True))
    ]

    warnings = WarningsBlock(
        calc_warnings=list(source.calc_warnings),
        run_warnings=list(resolved.run_warnings),
        import_warnings=list(provenance.warnings),
        discarded_events=dict(provenance.discarded_events),
    )

    images = _render_images(resolved, source) if with_images else []

    return ExportPayload(
        meta=meta,
        provenance=provenance,
        is_multi_exam=resolved.is_multi_exam,
        exams=exam_sections,
        cumulative=_cumulative_section(resolved, source),
        warnings=warnings,
        images=images,
    )
