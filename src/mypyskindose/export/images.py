"""Dose-map image rendering for exports (§10).

Pure-logic Plotly helpers that take explicit parameters and never read
``gui/state``. ``gui/figures.py`` delegates to
:func:`render_dosemap_plotly_figure` so camera presets and dimensions live here.
"""

from __future__ import annotations

from typing import Any

import numpy as np

# Camera eye presets (Plotly scene_camera.eye), oblique 3/4 views so the long
# phantom axis is visible. In the unified frame +Y is posterior (toward the
# floor for head-first supine), so the two presets face OPPOSITE Y sides — one
# frames the posterior (typical beam-entrance) surface, the other the anterior.
DORSAL = dict(x=1.5, y=1.8, z=1.4)     # posterior-facing (beam entrance side)
ANTERIOR = dict(x=1.5, y=-1.8, z=1.4)  # anterior-facing

# Two-tier resolution budget (§10): high-res cumulative vs compact per-exam.
CUMULATIVE_DIMS = dict(width=1600, height=1000, scale=1.5)
THUMBNAIL_DIMS = dict(width=800, height=600, scale=1.0)


def eye_facing(xyz: tuple[float, float, float] | None, distance: float = 2.5) -> dict[str, float]:
    """Camera eye positioned to look at a point from outside the phantom.

    Places the eye along the outward direction of ``xyz`` (from the mesh origin)
    so that surface point faces the camera. Falls back to :data:`ANTERIOR`.
    """
    if xyz is None:
        return dict(ANTERIOR)
    v = np.array(xyz, dtype=float)
    norm = float(np.linalg.norm(v))
    if not norm:
        return dict(ANTERIOR)
    u = v / norm
    return {"x": float(u[0] * distance), "y": float(u[1] * distance), "z": float(u[2] * distance)}


def dose_bbox(dose_map: np.ndarray, patient_dict: dict[str, Any], *, pad: float = 6.0):
    """Axis ranges enclosing all irradiated cells (+ padding), or ``None``.

    Used to zoom static views onto the (often small, localized) dose patch
    instead of the whole phantom.
    """
    dm = np.asarray(dose_map, dtype=float)
    if dm.size == 0 or float(dm.max()) <= 0:
        return None
    cells = patient_dict["patient_skin_cells"]
    r = np.array([cells["x"], cells["y"], cells["z"]]).T
    hot = r[dm > 0.0]
    lo = hot.min(axis=0) - pad
    hi = hot.max(axis=0) + pad
    return [(float(lo[i]), float(hi[i])) for i in range(3)]


def render_dosemap_plotly_figure(
    dose_map: np.ndarray,
    patient_dict: dict[str, Any],
    colorscale: str = "jet",
    *,
    dark: bool = True,
    ranges: list[tuple[float, float]] | None = None,
):
    """Build the dose-map Plotly ``Figure`` from explicit data (no GUI state).

    ``patient_dict`` is the inner patient dict with ``patient_skin_cells`` and
    ``triangle_vertex_indices`` (as produced by ``HumanPhantomOutput.to_dict()``).
    """
    import plotly.graph_objects as go

    from mypyskindose.plotting.plot_layout import coordinate_frame_annotation

    cells = patient_dict["patient_skin_cells"]
    r = np.array([cells["x"], cells["y"], cells["z"]]).T
    ijk = patient_dict["triangle_vertex_indices"]
    dose_map = np.asarray(dose_map, dtype=float)

    hover = [
        f"<b>lat:</b> {r[i, 2]:.2f} cm<br><b>lon:</b> {r[i, 0]:.2f} cm<br>"
        f"<b>ver:</b> {r[i, 1]:.2f} cm<br><b>dose:</b> {dose_map[i]:.2f} mGy"
        for i in range(len(r))
    ]
    cmax = float(np.max(dose_map)) if dose_map.size else 0.0
    if cmax == 0:
        cmax = 1.0

    bg = "rgb(5,5,5)" if dark else "white"
    txt = "#F8FAFC" if dark else "#0F172A"
    grid = "#262626" if dark else "#E2E8F0"

    mesh = go.Mesh3d(
        x=r[:, 0], y=r[:, 1], z=r[:, 2],
        i=ijk["i"], j=ijk["j"], k=ijk["k"],
        intensity=dose_map, intensitymode="vertex",
        colorscale=colorscale, cmin=0.0, cmax=cmax, showscale=True,
        hoverinfo="text", text=hover,
        colorbar=dict(title=dict(text="Skin dose [mGy]", font=dict(size=12))),
    )
    layout = go.Layout(
        paper_bgcolor=bg, plot_bgcolor=bg,
        font=dict(color=txt, family="Inter, sans-serif"),
        margin=dict(l=0, r=0, b=40, t=40),
        annotations=[coordinate_frame_annotation(txt)],
        scene=dict(
            aspectmode="data" if ranges is None else "cube",
            xaxis=dict(title="X - LON / PT L-R [cm]", backgroundcolor=bg, color=txt, gridcolor=grid,
                       range=(ranges[0] if ranges else None)),
            yaxis=dict(title="Y - VER / PT A-P [cm]", backgroundcolor=bg, color=txt, gridcolor=grid,
                       range=(ranges[1] if ranges else None)),
            zaxis=dict(title="Z - LAT / PT S-I [cm]", backgroundcolor=bg, color=txt, gridcolor=grid,
                       range=(ranges[2] if ranges else None)),
        ),
    )
    return go.Figure(data=[mesh], layout=layout)


def render_dosemap_png(
    dose_map: np.ndarray,
    patient_dict: dict[str, Any],
    *,
    camera_eye: dict[str, float] = DORSAL,
    width: int = 1600,
    height: int = 1000,
    scale: float = 1.5,
    colorscale: str = "jet",
    dark: bool = True,
    zoom_to_dose: bool = False,
) -> bytes | None:
    """Render a dose-map view to PNG bytes. Returns ``None`` if kaleido/plotly
    image export fails at runtime (caller omits the image + shows a notice).

    When ``zoom_to_dose`` is set, the scene is cropped to the irradiated region
    so a small localized dose patch is visible instead of the whole phantom.
    """
    try:
        ranges = dose_bbox(dose_map, patient_dict) if zoom_to_dose else None
        fig = render_dosemap_plotly_figure(dose_map, patient_dict, colorscale, dark=dark, ranges=ranges)
        fig.update_layout(scene_camera=dict(eye=camera_eye))
        return fig.to_image(format="png", width=width, height=height, scale=scale)
    except Exception:
        return None
