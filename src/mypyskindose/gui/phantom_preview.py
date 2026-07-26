"""Settings-tab human phantom preview figure builder (no RDSR).

Builds a Plotly figure of the selected human mesh on table+pad for the Settings
UI. Prefer ``{stem}_reduced_3000t`` when present under package ``phantom_data/``.
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

from mypyskindose import constants as c
from mypyskindose.geom_calc import position_patient_phantom_on_table
from mypyskindose.phantom_class import Phantom
from mypyskindose.plotting.create_mesh3d import create_mesh_3d_general
from mypyskindose.plotting.get_camera_view import get_camera_view
from mypyskindose.plotting.plot_layout import default_geometry_layout
from mypyskindose.privacy import safe_error_event

from .geometry_preview import effective_patient_offset_for_preview
from .settings_builder import build_settings
from .state import AppState

logger = logging.getLogger(__name__)

# Same package root Phantom uses for STL loads (gui/ → mypyskindose/phantom_data).
_PHANTOM_DATA_DIR = Path(__file__).resolve().parent.parent / "phantom_data"
_PREVIEW_BG = "rgb(5,5,5)"
_SHORT_LABELS = {
    "patient": "Patient",
    "table": "Table",
    "pad": "Pad",
}
_MESH_ARRAY_KEYS = ("x", "y", "z", "i", "j", "k")


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
    )


def resolve_preview_mesh(stem: str) -> str:
    """Return reduced companion stem when its STL exists; else the logical stem.

    Looks only under package ``phantom_data/``. Prefers ``_reduced_3000t`` over
    ``_reduced_1000t``. Legacy mesh aliases resolve to canonical stems first.
    """
    from mypyskindose.phantom_mesh_names import prefer_reduced_preview_stem

    return prefer_reduced_preview_stem(stem, phantom_data_dir=_PHANTOM_DATA_DIR)


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
    )
    return build_settings(
        temp,
        mode=mode,
        output_format=output_format,
        patient_offset=(snapshot.d_lon, snapshot.d_ver, snapshot.d_lat),
    )


def make_phantom_preview_fig(snapshot: PreviewSnapshot) -> dict | None:
    """Build a Plotly figure dict for the Settings human-mesh preview.

    Returns ``None`` for non-human models, missing meshes, or unexpected errors.
    Does not read the global GUI ``state`` singleton.
    """
    try:
        if snapshot.phantom_model != c.PHANTOM_MODEL_HUMAN:
            return None

        settings = build_settings_from_snapshot(snapshot)
        logical_stem = snapshot.logical_mesh_stem
        preview_mesh = resolve_preview_mesh(logical_stem)
        mesh_path = _PHANTOM_DATA_DIR / f"{preview_mesh}.stl"
        if not mesh_path.is_file():
            return None

        patient = Phantom(
            phantom_model=c.PHANTOM_MODEL_HUMAN,
            phantom_dim=settings.phantom.dimension,
            human_mesh=preview_mesh,
            human_scale=(
                float(settings.phantom.scale_lat),
                float(settings.phantom.scale_ap),
                float(settings.phantom.scale_lon),
            ),
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
