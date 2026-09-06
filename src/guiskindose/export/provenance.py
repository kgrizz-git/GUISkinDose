"""Input provenance collection (§2) — tabular and DICOM branches.

An exam carries an ``InputProvenance`` (tabular adapters) or ``None`` (DICOM
RDSR). The report-level provenance summarizes source type, schema, files, and
event counts across all exams.
"""

from __future__ import annotations

from .models import ExportExamSource, ProvenanceInfo


def _sum_discarded(exams: list[ExportExamSource]) -> dict[str, int]:
    totals: dict[str, int] = {}
    for exam in exams:
        for reason, count in exam.discarded_events.items():
            totals[reason] = totals.get(reason, 0) + int(count)
    return totals


def collect_provenance(
    exams: list[ExportExamSource],
    import_warnings: list[str],
    fallback_file_name: str | None,
    *,
    include_source_identifiers: bool = False,
) -> ProvenanceInfo:
    """Aggregate per-exam input provenance and metadata into a report-level structure."""
    processed = sum(len(e.normalized_data) for e in exams)
    discarded_events = _sum_discarded(exams)
    discarded = sum(discarded_events.values())

    source_files = []
    if include_source_identifiers:
        source_files = [e.source_file for e in exams if e.source_file] or (
            [fallback_file_name] if fallback_file_name else []
        )

    # Tabular branch when any exam carries an InputProvenance.
    prov = next((e.provenance for e in exams if e.provenance is not None), None)
    warnings = list(import_warnings)
    if prov is not None:
        for e in exams:
            if e.provenance is not None:
                warnings.extend(e.provenance.warnings)
        lat_lon_swapped = any(bool(e.transform_meta.get("lat_lon_swapped")) for e in exams)
        return ProvenanceInfo(
            source_type=prov.source_type,
            schema_name=prov.schema_name,
            source_files=source_files,
            encoding=prov.detected_encoding,
            delimiter=prov.detected_delimiter,
            header_row_index=prov.header_row_index,
            column_map=dict(prov.column_map),
            lat_lon_swapped=lat_lon_swapped,
            sheet_name=prov.sheet_name,
            metadata_confidence="tabular_inferred",
            exam_count=len(exams),
            events_loaded=processed + discarded,
            events_processed=processed,
            events_discarded=discarded,
            discarded_events=discarded_events,
            warnings=_dedupe(warnings),
        )

    # DICOM RDSR branch.
    lat_lon_swapped = any(bool(e.transform_meta.get("lat_lon_swapped")) for e in exams)
    return ProvenanceInfo(
        source_type="dicom",
        schema_name="rdsr",
        source_files=source_files,
        encoding=None,
        delimiter=None,
        header_row_index=None,
        column_map={},
        lat_lon_swapped=lat_lon_swapped,
        sheet_name=None,
        metadata_confidence="dicom_tags",
        exam_count=len(exams),
        events_loaded=processed + discarded,
        events_processed=processed,
        events_discarded=discarded,
        discarded_events=discarded_events,
        warnings=_dedupe(warnings),
    )


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out
