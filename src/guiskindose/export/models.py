"""Data models for the Rich Report Export feature.

Two families live here:

* **Input bundles** (``ExportSource`` / ``ExportExamSource``) — populated by the
  GUI or CLI adapters and handed to :func:`collect_export_payload`.
* **Payload** (``ExportPayload`` and its nested sections) — the writer-facing,
  report-layout structure produced by the collector. Writers consume
  ``ExportPayload`` only and never touch GUI state or raw calculation dicts.

The payload is intentionally *separate* from ``PySkinDoseOutput.to_dict()`` so
report-layout data never bloats the public JSON/dict export schema. See
``dev-docs/plans/RICH_EXPORT_PLAN.md``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:  # avoid importing heavy deps at module import time
    import pandas as pd

    from guiskindose.format_export_data import MultiExamResult
    from guiskindose.input_adapters.models import InputProvenance
    from guiskindose.settings import PyskindoseSettings

# Rich-export payload schema version. Separate from ``EXPORT_SCHEMA_VERSION``
# (the JSON/dict export schema) — increment when ``ExportPayload`` changes
# incompatibly.
RICH_EXPORT_SCHEMA_VERSION = 1

APP_NAME = "GUISkinDose"


class ExportError(Exception):
    """Raised when an export payload cannot be built (e.g. no calculation)."""


class MissingExportDependencyError(ExportError):
    """Raised when a report format needs an optional package that isn't installed.

    Carries the human-facing ``format`` label, the missing ``package`` name, and a
    ready-to-show ``install_hint`` so callers (GUI toast/dialog, CLI) can present
    actionable instructions instead of a bare ``ModuleNotFoundError``.
    """

    def __init__(self, fmt: str, package: str, install_hint: str) -> None:
        self.format = fmt
        self.package = package
        self.install_hint = install_hint
        super().__init__(
            f"{fmt.upper()} export needs the '{package}' package, which isn't installed. "
            f"{install_hint}"
        )


# ── Input bundles (GUI/CLI → collector) ──────────────────────────────────────


@dataclass
class ExportExamSource:
    """One exam's inputs for export, populated by GUI or CLI adapters."""

    exam_id: str
    normalized_data: pd.DataFrame
    provenance: InputProvenance | None
    source_file: str | None
    effective_settings: PyskindoseSettings
    patient_offset: tuple[float, float, float]
    transform_meta: dict[str, Any] = field(default_factory=dict)
    extra_warnings: list[str] = field(default_factory=list)
    # Structured discarded-event counts (reason code → count). ``ExamResult`` is
    # multi-exam only, so single-exam paths carry the counts here instead.
    discarded_events: dict[str, int] = field(default_factory=dict)


@dataclass
class ExportSource:
    """Top-level export bundle. Exactly one of ``output_dict`` /
    ``multi_exam_result`` must be set (single-exam vs multi-exam)."""

    execution_context: Literal["gui", "cli"]
    output_dict: dict[str, Any] | None = None
    multi_exam_result: MultiExamResult | None = None
    exams: list[ExportExamSource] = field(default_factory=list)
    calc_warnings: list[str] = field(default_factory=list)
    import_warnings: list[str] = field(default_factory=list)
    file_name: str | None = None
    colorscale: str = "jet"
    report_title: str | None = None
    load_timestamp: datetime | None = None
    include_source_identifiers: bool = False


# ── Payload (collector → writers) ─────────────────────────────────────────────


@dataclass
class ReportMeta:
    """Metadata about the report generation process (§1)."""

    app_name: str
    package_version: str
    schema_version: int
    generated_at: datetime
    execution_context: str
    report_title: str


@dataclass
class ProvenanceInfo:
    """Report-level input provenance (§2). ``source_type`` is ``"dicom"`` for
    RDSR input, else the tabular type (``csv`` / ``tsv`` / ``xlsx``)."""

    source_type: str
    schema_name: str
    source_files: list[str]
    encoding: str | None
    delimiter: str | None
    header_row_index: int | None
    column_map: dict[str, str]
    lat_lon_swapped: bool
    sheet_name: str | int | None
    metadata_confidence: str
    exam_count: int
    events_loaded: int
    events_processed: int
    events_discarded: int
    discarded_events: dict[str, int]
    warnings: list[str] = field(default_factory=list)


@dataclass
class CorrectionStat:
    """Summary of one correction factor across an exam (or cumulative)."""

    key: str  # k_bs | k_isq | k_med | k_tab
    minimum: float | None
    maximum: float | None
    mean: float | None
    dose_weighted_mean: float | None


@dataclass
class AcquisitionBreakdown:
    """Event count and dosimetric summary for a specific acquisition type (§7)."""

    mode: str  # fluoroscopy | acquisition | other
    raw_labels: list[str]
    event_count: int
    air_kerma: float
    dap_gycm2: float | None


@dataclass
class DosimetricMetrics:
    """Core dosimetric metrics and acquisition breakdown for an exam or procedure (§7)."""

    psd: float | None
    air_kerma: float | None
    dap_gycm2: float | None
    fluoro_time_s: float | None
    events_processed: int
    events_discarded: int
    peak_vertex_index: int | None
    peak_xyz: tuple[float, float, float] | None
    acquisition_breakdown: list[AcquisitionBreakdown] = field(default_factory=list)


@dataclass
class PrimaryContributingExam:
    """For cumulative PSD under differing per-exam offsets (§7)."""

    exam_id: str
    dose_fraction: float  # 0–1 fraction of PSD delivered to the peak vertex
    peak_xyz_baseline: tuple[float, float, float] | None
    peak_xyz_primary_frame: tuple[float, float, float] | None


@dataclass
class ExamSection:
    """Everything reported per exam (§3–§8)."""

    exam_id: str
    # Equipment (§3)
    manufacturer: str | None
    model: str | None
    normalization_profile: str | None
    # Settings snapshot (§4) — serialized effective settings + non-default flags
    settings: dict[str, Any]
    non_default_settings: dict[str, Any]
    # Coordinate corrections (§5)
    coordinate: dict[str, Any]
    # Phantom & geometry (§6)
    phantom: dict[str, Any]
    # Dosimetric (§7) and corrections (§8)
    metrics: DosimetricMetrics
    corrections: list[CorrectionStat]
    # Unit parsing / conversions applied by the input adapter (§3) —
    # {internal field: "source unit → internal (from 'header')"}. Empty for
    # DICOM RDSR (units read+asserted, not converted) and normalized inputs.
    unit_conversions: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


@dataclass
class WarningsBlock:
    """Executive alert content (§9)."""

    calc_warnings: list[str] = field(default_factory=list)
    run_warnings: list[str] = field(default_factory=list)
    import_warnings: list[str] = field(default_factory=list)
    discarded_events: dict[str, int] = field(default_factory=dict)

    def is_empty(self) -> bool:
        """Return True if there are no warnings or discarded events."""
        return not (
            self.calc_warnings
            or self.run_warnings
            or self.import_warnings
            or self.discarded_events
        )


@dataclass
class ImageEntry:
    """One rendered (or failed) dose-map image (§10)."""

    label: str
    view: str
    exam_id: str | None
    png_bytes: bytes | None
    error_message: str | None = None


@dataclass
class CumulativeSection:
    """Cumulative results across all exams (§7–§8)."""

    metrics: DosimetricMetrics
    corrections: list[CorrectionStat]
    primary_contributing_exam: PrimaryContributingExam | None = None


@dataclass
class ExportPayload:
    """Writer-facing report structure. Writers consume this only."""

    meta: ReportMeta
    provenance: ProvenanceInfo
    is_multi_exam: bool
    exams: list[ExamSection]
    cumulative: CumulativeSection
    warnings: WarningsBlock
    images: list[ImageEntry] = field(default_factory=list)
    coordinate_convention: str = (
        "Head-first supine (HFS): +X lateral (patient left), +Y anterior→posterior "
        "(down toward floor), +Z cranial. Plot labels: X - LON / PT L-R, "
        "Y - VER / PT A-P, Z - LAT / PT S-I. See VENDOR_COORDINATE_SYSTEMS.md."
    )
