"""Settings-tab human phantom preview figure builder (no RDSR).

Builds a Plotly figure of the selected human mesh on table+pad for the Settings
UI. Mesh files resolve from the shipped catalog first, then the per-user library;
prefer ``{stem}_reduced_3000t`` when present in either root.
Dose calculation continues to use the full logical mesh stem.

Inputs
------
- ``PreviewSnapshot`` (or fields captured via ``capture_phantom_preview_snapshot``)
  built on the UI thread. The figure builder must not read the live GUI
  ``state`` singleton.

Outputs
-------
- ``make_phantom_preview_fig`` → Plotly figure ``dict`` or ``None`` on failure /
  non-human model.
- ``make_placeholder_dosemap_fig`` → zero-dose Results-tab map shown before any calculation.
- ``resolve_preview_mesh`` → STL stem for preview loading.

Requirements
------------
- ``Phantom``, ``position_patient_phantom_on_table``, ``create_mesh_3d_general``,
  shipped ``COLOR_*`` constants, ``safe_error_event``.
"""

from __future__ import annotations

import base64
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import plotly.graph_objects as go

from guiskindose import constants as c
from guiskindose.geom_calc import position_patient_phantom_on_table
from guiskindose.phantom_class import Phantom
from guiskindose.plotting.create_mesh3d import create_mesh_3d_general
from guiskindose.plotting.get_camera_view import get_camera_view
from guiskindose.plotting.plot_layout import default_geometry_layout
from guiskindose.privacy import safe_error_event

from .geometry_preview import effective_patient_offset_for_preview
from .settings_builder import build_settings
from .state import AppState

logger = logging.getLogger(__name__)

# Same package root Phantom uses for STL loads (gui/ → guiskindose/phantom_data).
_PHANTOM_DATA_DIR = Path(__file__).resolve().parent.parent / "phantom_data"
_PREVIEW_BG = "rgb(5,5,5)"
_SHORT_LABELS = {
    "patient": "Patient",
    "table": "Table",
    "pad": "Pad",
}
_MESH_ARRAY_KEYS = ("x", "y", "z", "i", "j", "k", "intensity")


def _expand_binary_plotly_arrays(fig_dict: dict[str, Any]) -> dict[str, Any]:
    """Replace Plotly binary ``bdata`` blobs with plain Python lists.

    ``Figure.to_dict()`` often encodes large Mesh3d arrays as ``{dtype, bdata}``.
    Expanding keeps the Settings preview dict JSON-friendly for tests and NiceGUI.
    """
    for trace in fig_dict.get("data", []):
        if not isinstance(trace, dict):
            continue
        for key in _MESH_ARRAY_KEYS:
            value = trace.get(key)
            if not isinstance(value, dict) or "bdata" not in value:
                continue
            dtype = np.dtype(value.get("dtype", "f8"))
            arr = np.frombuffer(base64.b64decode(value["bdata"]), dtype=dtype)
            trace[key] = arr.tolist()
    return fig_dict


@dataclass(frozen=True)
class PreviewSnapshot:
    """Immutable pose/scale inputs for Settings phantom preview (UI-thread capture)."""

    phantom_model: str
    human_mesh: str
    patient_orientation: str
    scale_lat: float
    scale_ap: float
    scale_lon: float
    d_lon: float
    d_ver: float
    d_lat: float
    # Custom phantom/table/pad dimensions as sorted (key, value) pairs; None keeps the defaults.
    # A tuple, not a dict, so snapshots compare by value in the placeholder cache key
    # (they hash too while the values are scalars, as every shipped dimension is).
    phantom_dimensions: tuple[tuple[str, Any], ...] | None = None

    @property
    def logical_mesh_stem(self) -> str:
        """Non-reduced mesh stem for captions and Plotly ``uirevision``."""
        return self.human_mesh


def capture_phantom_preview_snapshot(app_state: AppState) -> PreviewSnapshot:
    """Capture preview inputs from GUI state on the UI thread.

    Multi-exam offsets use the active exam via
    ``effective_patient_offset_for_preview`` (same as Geometry preview).
    """
    d_lon, d_ver, d_lat = effective_patient_offset_for_preview(app_state)
    dims = app_state.phantom_dimensions
    return PreviewSnapshot(
        phantom_model=str(app_state.phantom_model),
        human_mesh=str(app_state.human_mesh),
        patient_orientation=str(app_state.patient_orientation),
        scale_lat=float(app_state.phantom_scale_lat),
        scale_ap=float(app_state.phantom_scale_ap),
        scale_lon=float(app_state.phantom_scale_lon),
        d_lon=float(d_lon),
        d_ver=float(d_ver),
        d_lat=float(d_lat),
        phantom_dimensions=tuple(sorted(dims.items())) if isinstance(dims, dict) else None,
    )


def resolve_preview_mesh(stem: str) -> str:
    """Return reduced companion stem when its STL exists; else the logical stem.

    Looks only under package ``phantom_data/``. Prefers ``_reduced_3000t`` over
    ``_reduced_1000t``. Legacy mesh aliases resolve to canonical stems first.
    """
    from guiskindose.phantom_mesh_names import prefer_reduced_preview_stem

    return prefer_reduced_preview_stem(stem, phantom_data_dir=_PHANTOM_DATA_DIR, user_library_dir=None)


def build_settings_from_snapshot(
    snapshot: PreviewSnapshot,
    *,
    mode: str = "plot_setup",
    output_format: str = "dict",
):
    """Build ``PyskindoseSettings`` from a snapshot without touching live ``state``."""
    temp = AppState(
        phantom_model=snapshot.phantom_model,
        human_mesh=snapshot.human_mesh,
        patient_orientation=snapshot.patient_orientation,
        phantom_scale_lat=snapshot.scale_lat,
        phantom_scale_ap=snapshot.scale_ap,
        phantom_scale_lon=snapshot.scale_lon,
        d_lon=snapshot.d_lon,
        d_ver=snapshot.d_ver,
        d_lat=snapshot.d_lat,
        phantom_dimensions=dict(snapshot.phantom_dimensions) if snapshot.phantom_dimensions is not None else None,
    )
    return build_settings(
        temp,
        mode=mode,
        output_format=output_format,
        patient_offset=(snapshot.d_lon, snapshot.d_ver, snapshot.d_lat),
    )


def _positioned_preview_phantoms(snapshot: PreviewSnapshot) -> tuple[Phantom, Phantom, Phantom] | None:
    """Build the preview patient, table and pad in place, or ``None`` if the patient mesh is missing.

    Human models use the reduced preview mesh. Plane and cylinder models need no mesh file.
    """
    settings = build_settings_from_snapshot(snapshot)
    human_mesh = None
    human_scale = (1.0, 1.0, 1.0)
    if snapshot.phantom_model == c.PHANTOM_MODEL_HUMAN:
        from guiskindose.phantom_mesh_names import resolve_human_mesh_stl_path

        human_mesh = resolve_preview_mesh(snapshot.logical_mesh_stem)
        try:
            mesh_path = resolve_human_mesh_stl_path(human_mesh, phantom_data_dir=_PHANTOM_DATA_DIR)
        except (ValueError, OSError):
            return None
        if not mesh_path.is_file():
            return None
        human_scale = (
            float(settings.phantom.scale_lat),
            float(settings.phantom.scale_ap),
            float(settings.phantom.scale_lon),
        )
    patient = Phantom(
        phantom_model=snapshot.phantom_model,
        phantom_dim=settings.phantom.dimension,
        human_mesh=human_mesh,
        human_scale=human_scale,
    )
    table = Phantom(phantom_model=c.PHANTOM_MODEL_TABLE, phantom_dim=settings.phantom.dimension)
    pad = Phantom(phantom_model=c.PHANTOM_MODEL_PAD, phantom_dim=settings.phantom.dimension)
    po = settings.phantom.patient_offset
    position_patient_phantom_on_table(
        patient,
        table,
        pad,
        settings.phantom.dimension.pad_thickness,
        [float(po.d_lon), float(po.d_ver), float(po.d_lat)],
        settings.phantom.patient_orientation,
    )
    return patient, table, pad


def make_placeholder_dosemap_fig(snapshot: PreviewSnapshot, colorscale: str = "jet") -> dict | None:
    """Build a zero-dose map of the selected phantom for the Results tab before any calculation.

    Uses the same renderer as the real dose map, so the empty state looks like the result it
    stands in for. Returns ``None`` when the phantom cannot be built.
    """
    try:
        from guiskindose.export.images import render_dosemap_plotly_figure

        phantoms = _positioned_preview_phantoms(snapshot)
        if phantoms is None:
            return None
        patient = phantoms[0]
        r = np.asarray(patient.r)
        ijk = np.asarray(patient.ijk)
        patient_dict = {
            "patient_skin_cells": {"x": r[:, 0], "y": r[:, 1], "z": r[:, 2]},
            "triangle_vertex_indices": {"i": ijk[:, 0], "j": ijk[:, 1], "k": ijk[:, 2]},
        }
        fig = render_dosemap_plotly_figure(np.zeros(len(r)), patient_dict, colorscale, dark=True)
        # A 0-1 colour bar would read as real dose values, so the placeholder hides it. The
        # "no dose yet" note is a caption under the plot: a figure title collides with the
        # intended-use stamp the renderer draws in the top margin.
        fig.update_traces(showscale=False)
        return _expand_binary_plotly_arrays(fig.to_dict())
    except Exception as exc:
        safe_error_event(logger, "placeholder_dosemap_figure_render", exc, level=logging.DEBUG)
        return None


def make_phantom_preview_fig(snapshot: PreviewSnapshot) -> dict | None:
    """Build a Plotly figure dict for the Settings human-mesh preview.

    Returns ``None`` for non-human models, missing meshes, or unexpected errors.
    Does not read the global GUI ``state`` singleton.
    """
    try:
        if snapshot.phantom_model != c.PHANTOM_MODEL_HUMAN:
            return None

        logical_stem = snapshot.logical_mesh_stem
        phantoms = _positioned_preview_phantoms(snapshot)
        if phantoms is None:
            return None
        patient, table, pad = phantoms

        patient_text = [_SHORT_LABELS["patient"]] * len(patient.r)
        table_text = [_SHORT_LABELS["table"]] * len(table.r)
        pad_text = [_SHORT_LABELS["pad"]] * len(pad.r)

        patient_mesh = create_mesh_3d_general(
            obj=patient,
            color=c.COLOR_PATIENT,
            mesh_text=patient_text,
            lighting={"diffuse": c.PLOT_LIGHTNING_DIFFUSE, "ambient": c.PLOT_LIGHTNING_AMBIENT},
        )
        table_mesh = create_mesh_3d_general(obj=table, color=c.COLOR_TABLE, mesh_text=table_text)
        pad_mesh = create_mesh_3d_general(
            obj=pad,
            color=c.COLOR_PAD,
            mesh_text=pad_text,
            mesh_name=c.MESH_NAME_PAD,
        )

        layout = default_geometry_layout(
            title="Phantom preview",
            dark_mode=True,
            notebook_mode=True,
            camera=get_camera_view(),
        )
        fig = go.Figure(data=[patient_mesh, table_mesh, pad_mesh], layout=layout)
        fig.update_layout(
            paper_bgcolor=_PREVIEW_BG,
            plot_bgcolor=_PREVIEW_BG,
            uirevision=logical_stem,
            height=360,
            width=None,
            margin={"l": 0, "r": 0, "t": 40, "b": 0},
        )
        # Compact Settings panel: drop fixed width from default layout.
        fig.layout.width = None
        return _expand_binary_plotly_arrays(fig.to_dict())
    except Exception as exc:
        safe_error_event(logger, "phantom_preview_figure_render", exc, level=logging.DEBUG)
        return None
