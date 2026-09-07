"""Per-exam report sections: settings snapshot (§4), equipment (§3),
phantom/geometry (§6), and coordinate corrections (§5)."""

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
