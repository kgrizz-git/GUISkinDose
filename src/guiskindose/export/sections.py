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

from ._exam_view import ExamView
from .models import ExportExamSource

# Settings fields surfaced in the snapshot (§4).
_SETTINGS_KEYS = (
    "mode",
    "estimate_k_tab",
    "k_tab_val",
    "inherent_filtration",
    "below_floor_kvp_policy",
    "below_floor_kvp_manual",
    "beam_miss_warn",
    "remove_invalid_rows",
    "corrections_db_path",
)


def _first_present(df: pd.DataFrame | None, column: str) -> str | None:
    if df is None or column not in df.columns:
        return None
    series = df[column].dropna()
    if series.empty:
        return None
    val = series.iloc[0]
    text = str(val).strip()
    return text or None


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
    """Extract equipment details (manufacturer, model, profile) from the exam."""
    df = exam.normalized_data
    profile = exam.transform_meta.get("normalization_profile")
    if profile is None and exam.provenance is not None:
        profile = exam.provenance.schema_name
    return {
        "manufacturer": _first_present(df, KEY_NORMALIZATION_MANUFACTURER),
        "model": _first_present(df, KEY_NORMALIZATION_MODEL_NAME),
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
    claiming envelope processing. Only detected rotational or
    positioner-motion rows qualify.
    """
    if not handling:
        return False
    rows = handling.get("rows", [])
    return any(
        isinstance(row, dict) and row.get("classification") in ("rotational", "positioner_motion")
        for row in rows
    )


def _effective_counts(handling: dict[str, Any]) -> tuple[int, int, int]:
    """(coverage_rows, static_rows, total_rows) from ledger effective handling."""
    rows = handling.get("rows", [])
    coverage = sum(1 for row in rows if isinstance(row, dict) and row.get("effective_handling") == "coverage")
    static = sum(
        1
        for row in rows
        if isinstance(row, dict)
        and row.get("classification") in ("rotational", "positioner_motion")
        and row.get("effective_handling") == "static"
    )
    return coverage, static, len(rows)


def rotational_methodology_paragraph(handling: dict[str, Any] | None) -> str | None:
    """One methodology paragraph for rotational handling, or None when absent."""
    if not has_rotational_content(handling):
        return None
    assert handling is not None
    aggregate = handling.get("aggregate", {})
    total = int(aggregate.get("total_events", 0) or 0)
    kerma = float(aggregate.get("rotational_kerma", 0.0) or 0.0)
    total_kerma = float(aggregate.get("total_kerma", 0.0) or 0.0)
    fraction = (100.0 * kerma / total_kerma) if total_kerma > 0 else 0.0
    coverage, static, _ = _effective_counts(handling)
    treatment = (
        f"{coverage} event(s) ran as conditional coverage envelopes "
        f"(estimate-grade, not a guaranteed bound)"
    )
    if static:
        treatment += f"; {static} detected event(s) ran static with warnings"
    fallback = " Static fallbacks occurred — see the ledger." if aggregate.get("any_fallback_to_static") else ""
    return (
        f"Rotational handling: {treatment} out of {total} events "
        f"({fraction:.1f}% of K_IRP in rotational envelopes). Enveloped events "
        f"are evaluated at full event kerma over candidate poses with the "
        f"cellwise maximum kept; kerma records are unchanged (multiplier 1.0)."
        f"{fallback}"
    )


def rotational_ledger_table(handling: dict[str, Any] | None) -> list[list[str]]:
    """Per-event ledger rows (header + one row per detected event)."""
    header = ["Event", "Classification", "Handling", "Endpoints (Ap1/Ap2)", "Candidates", "K_IRP"]
    if not handling:
        return [header]
    rows = [header]
    for row in handling.get("rows", []):
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
                str(row.get("kerma", "")),
            ]
        )
    return rows
