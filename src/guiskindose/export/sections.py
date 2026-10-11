"""Per-exam report sections: settings snapshot (§4), equipment (§3),
phantom/geometry (§6), coordinate corrections (§5), and rotational
handling methodology (§7b)."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from guiskindose.constants import (
    KEY_NORMALIZATION_MANUFACTURER,
    KEY_NORMALIZATION_MODEL_NAME,
)
from guiskindose.exam_identity import clean_identity_value
from guiskindose.rotational_envelope import is_disclosed_row

from ._exam_view import ExamView
from .models import ExportExamSource

# Settings fields surfaced in the snapshot (§4).
_SETTINGS_KEYS = (
    "mode",
    "k_tab_mode",
    "k_tab_val",
    "inherent_filtration",
    "below_floor_kvp_policy",
    "below_floor_kvp_manual",
    "beam_miss_warn",
    "remove_invalid_rows",
    "corrections_db_path",
)


#: Texts that are missing-value artifacts, never reportable identity.
_NON_IDENTITY_TEXTS = frozenset({"", "nan", "nat", "none"})


def _first_present(df: pd.DataFrame | None, column: str) -> str | None:
    """First non-blank value of *column*, or ``None`` when absent.

    Missing identity is never stringified into a matchable ``"none"``/``"nan"``:
    NaN/None/blank cells are skipped, and literal ``"nan"``/``"none"``/``"nat"``
    texts (case-insensitive ``str(None)``/``str(nan)`` artifacts) are treated
    as absent. Any other value keeps its exact spelling.
    """
    if df is None or column not in df.columns:
        return None
    series = df[column].dropna()
    if series.empty:
        return None
    for val in series.tolist():
        text = str(val).strip()
        if text and text.casefold() not in _NON_IDENTITY_TEXTS:
            return text
    return None


def _first_identity_pair(df: pd.DataFrame | None) -> tuple[str | None, str | None]:
    """Maker/model from one consistent row: the first row with maker identity.

    Maker and model are never assembled from different rows — a maker from one
    row paired with a model from another would invent an identity pair the exam
    never had. The model comes from the same row as the maker (``None`` when
    that row's model is missing); only when no row carries maker identity does
    the model fall back to the frame's first present model (legacy model-only
    frames, where there is no maker to contradict).
    """
    if df is None:
        return None, None
    maker_col = KEY_NORMALIZATION_MANUFACTURER if KEY_NORMALIZATION_MANUFACTURER in df.columns else None
    model_col = KEY_NORMALIZATION_MODEL_NAME if KEY_NORMALIZATION_MODEL_NAME in df.columns else None
    if maker_col is not None:
        makers = df[maker_col].tolist()
        models = df[model_col].tolist() if model_col is not None else [None] * len(df)
        for raw_maker, raw_model in zip(makers, models, strict=True):
            maker = clean_identity_value(raw_maker)
            if maker is not None:
                return maker, clean_identity_value(raw_model)
    return None, _first_present(df, model_col) if model_col is not None else None


def serialize_settings(settings: Any) -> dict[str, Any]:
    """Flatten the effective ``PyskindoseSettings`` into a report dict (§4)."""
    phantom = settings.phantom
    offset = phantom.patient_offset
    snapshot: dict[str, Any] = {key: getattr(settings, key, None) for key in _SETTINGS_KEYS}
    snapshot["corrections_db_path"], snapshot["corrections_db_source"] = _corrections_source_descriptor(settings)
    snapshot["phantom"] = {
        "model": phantom.model,
        "human_mesh": phantom.human_mesh,
        "patient_orientation": phantom.patient_orientation,
        "scale_lat": phantom.scale_lat,
        "scale_ap": phantom.scale_ap,
        "scale_lon": phantom.scale_lon,
    }
    snapshot["patient_offset"] = {
        "d_lon": offset.d_lon,
        "d_ver": offset.d_ver,
        "d_lat": offset.d_lat,
    }
    return snapshot


def _corrections_source_descriptor(settings: Any) -> tuple[str, dict[str, str | None]]:
    """Non-identifying correction-data provenance for exports.

    Returns a ``(display, descriptor)`` pair: ``"packaged"`` /
    ``{"source": "packaged-csv", "sha256": …}`` for the default, or
    ``"explicit"`` / ``{"source": "explicit-sqlite", "sha256": …}`` for an
    explicit database (hashed by file bytes). Raw filesystem paths never enter
    the payload. Defensive: any failure yields an unknown descriptor rather
    than breaking the export on metadata.
    """
    try:
        from guiskindose.correction_data import packaged_source_hash, resolve_corrections_source

        source, db_path = resolve_corrections_source(getattr(settings, "corrections_db_path", None), emit_warnings=False)
        if source == "packaged":
            return "packaged", {"source": "packaged-csv", "sha256": packaged_source_hash()}
        digest: str | None = None
        try:
            import hashlib
            from pathlib import Path as _Path

            digest = hashlib.sha256(_Path(str(db_path)).read_bytes()).hexdigest()
        except OSError:
            digest = None
        return "explicit", {"source": "explicit-sqlite", "sha256": digest}
    except Exception:
        return "unknown", {"source": "unknown", "sha256": None}


def _default_settings_snapshot() -> dict[str, Any] | None:
    try:
        from guiskindose import load_settings_example_json
        from guiskindose.settings import PyskindoseSettings

        return serialize_settings(PyskindoseSettings(settings=load_settings_example_json(), output_format="dict"))
    except Exception:
        return None


def non_default_settings(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Return the subset of ``snapshot`` that differs from ``settings_example.json``."""
    defaults = _default_settings_snapshot()
    if defaults is None:
        return {}
    diff: dict[str, Any] = {}
    for key, value in snapshot.items():
        if isinstance(value, dict):
            sub = {k: v for k, v in value.items() if defaults.get(key, {}).get(k) != v}
            if sub:
                diff[key] = sub
        elif defaults.get(key) != value:
            diff[key] = value
    return diff


def equipment_section(exam: ExportExamSource) -> dict[str, str | None]:
    """Extract equipment details (manufacturer, model, profile) from the exam.

    Maker and model come from one consistent row (see
    :func:`_first_identity_pair`), never assembled across rows.
    """
    df = exam.normalized_data
    profile = exam.transform_meta.get("normalization_profile")
    if profile is None and exam.provenance is not None:
        profile = exam.provenance.schema_name
    maker, model = _first_identity_pair(df)
    return {
        "manufacturer": maker,
        "model": model,
        "normalization_profile": profile,
    }


def phantom_section(view: ExamView, settings: Any) -> dict[str, Any]:
    """Build the phantom metadata and geometry section from the 3D model view."""
    cells = view.patient.get("patient_skin_cells", {"x": [], "y": [], "z": []})
    ijk = view.patient.get("triangle_vertex_indices", {"i": []})
    vertex_count = len(cells["x"])
    dims: dict[str, float] | None = None
    if vertex_count:
        arr = np.array([cells["x"], cells["y"], cells["z"]]).T
        extents = arr.max(axis=0) - arr.min(axis=0)
        dims = {
            "lateral_x_cm": float(extents[0]),
            "vertical_y_cm": float(extents[1]),
            "longitudinal_z_cm": float(extents[2]),
        }
    return {
        "model": settings.phantom.model,
        "human_mesh": view.patient.get("human_phantom") or settings.phantom.human_mesh,
        "bounding_box_cm": dims,
        "vertex_count": vertex_count,
        "triangle_count": len(ijk["i"]),
    }


def coordinate_section(exam: ExportExamSource, settings: Any) -> dict[str, Any]:
    """Compile coordinate overrides, toggles, and offsets for the exam."""
    meta = exam.transform_meta
    offset = settings.phantom.patient_offset
    return {
        "vendor_normalization": meta.get("vendor_normalization") or (
            exam.provenance.schema_name if exam.provenance is not None else "rdsr"
        ),
        "toggles": {
            "swap_tx_tz": bool(meta.get("swap_lat_lon") or meta.get("lat_lon_swapped")),
            "flip_ap1": bool(meta.get("flip_ap1")),
            "flip_ap2": bool(meta.get("flip_ap2")),
        },
        "table_origin": {
            "detected": meta.get("table_origin_detected"),
            "override": meta.get("table_origin_override"),
            "effective": meta.get("table_origin_effective"),
        },
        "patient_offset": {
            "d_lon": offset.d_lon,
            "d_ver": offset.d_ver,
            "d_lat": offset.d_lat,
        },
    }


def has_rotational_content(handling: dict[str, Any] | None) -> bool:
    """Whether a handling ledger merits a report section.

    The dose loop always emits the ledger dict, even for all-static datasets
    — a bare non-empty dict must not trigger a "Rotational handling" section
    claiming envelope processing. See :func:`is_disclosed_row` for the
    qualifying set (shared with badges and the summary log).
    """
    if not handling:
        return False
    rows = handling.get("rows", [])
    return any(is_disclosed_row(row) for row in rows)


def rotational_methodology_paragraph(handling: dict[str, Any] | None) -> str | None:
    """One methodology paragraph for rotational handling, or None when absent.

    Every number derives from what actually ran (ledger effective handling):
    envelope kerma sums only coverage rows, and envelope mechanics are stated
    only when at least one event ran enveloped.
    """
    if not has_rotational_content(handling):
        return None
    assert handling is not None
    rows = [row for row in handling.get("rows", []) if isinstance(row, dict)]
    detected = [row for row in rows if is_disclosed_row(row)]
    enveloped = [row for row in detected if row.get("effective_handling") == "coverage"]
    static = [row for row in detected if row.get("effective_handling") == "static"]
    envelope_kerma = sum(float(row.get("kerma") or 0.0) for row in enveloped)
    aggregate = handling.get("aggregate", {})
    total_kerma = float(aggregate.get("total_kerma", 0.0) or 0.0)
    fraction = (100.0 * envelope_kerma / total_kerma) if total_kerma > 0 else 0.0
    total = int(aggregate.get("total_events", 0) or 0)
    if enveloped:
        treatment = (
            f"{len(enveloped)} event(s) ran as conditional coverage envelopes "
            f"(estimate-grade, not a guaranteed bound)"
        )
        mechanics = (
            " Enveloped events are evaluated at full event kerma over "
            "candidate poses with the cellwise maximum kept; kerma records "
            "are unchanged (multiplier 1.0)."
        )
        degenerate = sum(
            1
            for row in enveloped
            if isinstance(row, dict) and int(row.get("unique_candidate_count", 2) or 2) <= 1
        )
        if degenerate:
            mechanics += (
                f" {degenerate} envelope(s) collapsed to a single candidate "
                f"pose (requested paths deduplicated); those equal a static "
                f"evaluation at that pose."
            )
    else:
        treatment = (
            f"{len(static)} detected event(s) ran static; no envelope was computed"
        )
        mechanics = ""
    if static and enveloped:
        treatment += f"; {len(static)} detected event(s) ran static with warnings"
    # Plan-mandated envelope elements: step, domain, direction, static
    # inclusion, fixed-geometry assumptions, endpoint concept codes.
    steps = sorted(
        {float(row["angular_step_deg"]) for row in enveloped if isinstance(row.get("angular_step_deg"), (int, float))}
    )
    domains = sorted(
        {str(row["candidate_domain"]) for row in enveloped if row.get("candidate_domain")}
    )
    directions = sorted(
        {str(row["direction_source"]) for row in enveloped if row.get("direction_source")}
    )
    statics = sum(1 for row in enveloped if row.get("include_static_pose"))
    elements = ""
    if enveloped:
        elements = (
            f" Candidate domains: {', '.join(domains) or 'n/a'}; angular step(s): "
            f"{', '.join(str(step) for step in steps) or 'n/a'}°; direction: "
            f"{', '.join(directions) or 'unknown'}; static pose included in "
            f"{statics}/{len(enveloped)} envelope(s). Start/end angles use the "
            f"DCM positioner concepts (primary 112011/end 113739, secondary "
            f"112012/end 113740); table position, field, spectrum, and "
            f"distances are held fixed unless a measured source says otherwise."
        )
    fallback = " Static fallbacks occurred — see the ledger." if aggregate.get("any_fallback_to_static") else ""
    return (
        f"Rotational handling: {treatment} out of {total} events "
        f"({fraction:.1f}% of K_IRP in rotational envelopes)."
        f"{mechanics}"
        f"{elements}"
        f"{fallback}"
    )


def _format_range(value: object) -> str:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return "—"
    low, high = value
    if low is None or high is None:
        return "—"
    return f"{low:g} to {high:g}"


def rotational_ledger_table(handling: dict[str, Any] | None) -> list[list[str]]:
    """Per-event ledger rows (header + one row per disclosed event).

    Only disclosed rows (shared predicate: detected rotational /
    positioner-motion plus contradictory declarations) render — a 49-event
    exam with one spin yields a 1-row table, not 49 rows of static noise.
    """
    header = [
        "Event",
        "Classification",
        "Handling",
        "Endpoints (Ap1/Ap2)",
        "Candidates",
        "Step°",
        "k_bs range",
        "K_IRP",
    ]
    if not handling:
        return [header]
    rows = [header]
    for row in handling.get("rows", []):
        if not is_disclosed_row(row):
            continue
        endpoints = (
            f"({row.get('ap1_start')}/{row.get('ap2_start')}) → "
            f"({row.get('ap1_end')}/{row.get('ap2_end')})"
        )
        rows.append(
            [
                str(row.get("event_index", "")),
                str(row.get("classification", "")),
                str(row.get("effective_handling", "")),
                endpoints,
                str(row.get("unique_candidate_count", "")),
                str(row.get("angular_step_deg", "")),
                _format_range(row.get("k_bs_range")),
                str(row.get("kerma", "")),
            ]
        )
    return rows


TUBE_SECTION_TITLE = "Dose by tube"
TUBE_NOTE = (
    "Each peak is the maximum of that tube's own partial dose map. Per-tube peaks "
    "generally do not add up to the peak skin dose, which is the peak of the combined map. "
    "Applied CF is the kerma-meter correction factor used for the tube in that exam; when the "
    "tube's events used more than one factor, the range and the kerma-weighted value are shown. "
    "Equipment names are not reported."
)
_TUBE_NAMES = {"single": "Single plane", "A": "Plane A", "B": "Plane B", "unknown": "Unknown tube"}
_SOURCE_NAMES = {
    "manual": "manual",
    "file": "file",
    "default": "default",
    "mixed": "mixed",
    "off": "not applied",
}
TUBE_HEADER = [
    "Tube",
    "Events",
    "Reported kerma (mGy)",
    "Corrected kerma (mGy)",
    "Applied CF",
    "Factor source",
    "Peak dose (mGy)",
]


def has_tube_content(summary: list[dict[str, Any]] | None) -> bool:
    """Whether a per-tube summary merits a report section.

    Shown when kerma-meter correction was applied (even for one single-plane tube,
    so the factor used is always reported) or when more than one tube, or a
    non-single tube, is present. A lone uncorrected ``single`` tube repeats the
    headline numbers and is not shown. Summaries without ``cf_source`` (older
    outputs) count as uncorrected.
    """
    if not summary:
        return False
    corrected = any(row.get("cf_source", "off") != "off" for row in summary)
    return corrected or len(summary) > 1 or any(row.get("tube") != "single" for row in summary)


def tube_cf_text(row: dict[str, Any]) -> str:
    """Applied CF for a tube row: one number, or ``min-max (weighted w)`` when it varied.

    Returns ``not applied`` when correction was disabled.
    """
    if row.get("cf_source", "off") == "off":
        return "not applied"
    weighted = float(row.get("applied_cf", 1.0))
    low = float(row.get("cf_min", weighted))
    high = float(row.get("cf_max", weighted))
    if f"{low:.4g}" == f"{high:.4g}":
        return f"{weighted:.4g}"
    return f"{low:.4g}-{high:.4g} (weighted {weighted:.4g})"


def tube_source_text(row: dict[str, Any]) -> str:
    """Factor source for a tube row (manual / file / default / mixed / not applied)."""
    return _SOURCE_NAMES.get(str(row.get("cf_source", "off")), str(row.get("cf_source")))


def tube_row_cells(row: dict[str, Any]) -> list[str]:
    """Display cells of one tube row, in :data:`TUBE_HEADER` order (no equipment labels)."""
    return [
        _TUBE_NAMES.get(str(row.get("tube")), str(row.get("tube"))),
        str(row.get("events", "")),
        f"{float(row.get('kerma_reported', 0.0)):.4g}",
        f"{float(row.get('kerma_corrected', 0.0)):.4g}",
        tube_cf_text(row),
        tube_source_text(row),
        f"{float(row.get('peak_dose', 0.0)):.4g}",
    ]


def tube_report_table(blocks: list[tuple[str | None, list[dict[str, Any]] | None]]) -> list[list[str]]:
    """One table: a row per exam x tube, with a leading Exam column when exams are labelled.

    Parameters
    ----------
    blocks : list[tuple[str | None, list[dict] | None]]
        ``(exam label or None, tube summary)`` per exam. Exams whose summary does
        not merit a section (see :func:`has_tube_content`) are skipped.
    """
    shown = [(label, summary) for label, summary in blocks if has_tube_content(summary)]
    labelled = any(label is not None for label, _ in shown)
    rows = [(["Exam"] if labelled else []) + TUBE_HEADER]
    for label, summary in shown:
        for row in summary or []:
            rows.append(([label or ""] if labelled else []) + tube_row_cells(row))
    return rows


def tube_summary_table(summary: list[dict[str, Any]] | None) -> list[list[str]]:
    """Header plus one row per tube present for a single exam."""
    return tube_report_table([(None, summary)])


def tube_blocks(payload: Any) -> list[tuple[str | None, list[dict[str, Any]] | None]]:
    """``(exam label or None, summary)`` per exam of an export payload (label only for multi-exam)."""
    return [(e.exam_id if payload.is_multi_exam else None, e.tube_summary) for e in payload.exams]
