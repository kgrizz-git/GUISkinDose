"""Plotly figure builders for the GUI (geometry preview and dose map).

These functions read from the shared ``state`` singleton and ``build_settings``;
they do not depend on any page-construction scope, so they live here rather than
inside the page function. Each returns a Plotly figure ``dict`` (or ``bytes`` for
the HTML/PNG exporters), or ``None`` on failure.
"""

from __future__ import annotations

import traceback

from mypyskindose.debug import dprint

from .helpers import build_settings
from .state import state


def make_geometry_fig(mode: str, event_index: int):
    """Build a Plotly Figure for geometry preview. Returns fig dict or None."""
    try:
        import plotly.graph_objects as go

        from mypyskindose import constants as c
        from mypyskindose.helpers.calculate_rotation_matrices import calculate_rotation_matrices
        from mypyskindose.phantom_class import Phantom
        from mypyskindose.plotting.create_geometry_plot import create_geometry_plot

        settings = build_settings(state, mode=mode, output_format="dict")
        settings.plot.plot_event_index = event_index
        settings.plot.notebook_mode = False
        settings.plot.interactivity = True

        if state.rdsr_df is None:
            return None

        data_norm = calculate_rotation_matrices(state.rdsr_df.copy())

        table = Phantom(phantom_model=c.PHANTOM_MODEL_TABLE, phantom_dim=settings.phantom.dimension)
        pad = Phantom(phantom_model=c.PHANTOM_MODEL_PAD, phantom_dim=settings.phantom.dimension)

        captured = {}
        original_show = go.Figure.show

        def _capture_show(self, *a, **kw):
            captured["fig"] = self

        go.Figure.show = _capture_show

        try:
            create_geometry_plot(normalized_data=data_norm, table=table, pad=pad, settings=settings)
        finally:
            go.Figure.show = original_show

        fig = captured.get("fig")
        if fig:
            bg = "rgb(5,5,5)"
            txt = "#F8FAFC"
            fig.update_layout(
                paper_bgcolor=bg,
                plot_bgcolor=bg,
                font=dict(color=txt, family="Inter, sans-serif"),
                scene=dict(
                    xaxis=dict(gridcolor="#262626"),
                    yaxis=dict(gridcolor="#262626"),
                    zaxis=dict(gridcolor="#262626"),
                ),
            )
            return fig.to_dict()
        return None
    except Exception:
        dprint("RENDERING", traceback.format_exc())
        return None


def make_dosemap_fig():
    """Build the dose map Plotly figure from current state.output."""
    try:
        import numpy as np
        import plotly.graph_objects as go

        if state.output is None:
            return None

        out = state.output
        patient_data = out["patient"]["patient"]
        r = np.array([
            patient_data["patient_skin_cells"]["x"],
            patient_data["patient_skin_cells"]["y"],
            patient_data["patient_skin_cells"]["z"],
        ]).T
        ijk_data = patient_data["triangle_vertex_indices"]
        dose_map = np.zeros(len(r))
        for idx, dose in out["dose_map"]:
            dose_map[int(idx)] = dose

        hover = [
            f"<b>lat:</b> {r[i,2]:.2f} cm<br><b>lon:</b> {r[i,0]:.2f} cm<br>"
            f"<b>ver:</b> {r[i,1]:.2f} cm<br><b>dose:</b> {dose_map[i]:.2f} mGy"
            for i in range(len(r))
        ]

        cmax = float(np.max(dose_map))
        if cmax == 0:
            cmax = 1.0

        mesh = go.Mesh3d(
            x=r[:, 0], y=r[:, 1], z=r[:, 2],
            i=ijk_data["i"], j=ijk_data["j"], k=ijk_data["k"],
            intensity=dose_map,
            intensitymode="vertex",
            colorscale=state.colorscale,
            cmin=0.0,
            cmax=cmax,
            showscale=True,
            hoverinfo="text",
            text=hover,
            colorbar=dict(title=dict(text="Skin dose [mGy]", font=dict(size=12))),
        )

        bg = "rgb(5,5,5)"  # Deep Black
        txt = "#F8FAFC"

        layout = go.Layout(
            paper_bgcolor=bg,
            plot_bgcolor=bg,
            font=dict(color=txt, family="Inter, sans-serif"),
            margin=dict(l=0, r=0, b=40, t=40),
            scene=dict(
                aspectmode="data",
                xaxis=dict(title="X - LON [cm]", backgroundcolor=bg, color=txt, gridcolor="#262626"),
                yaxis=dict(title="Y - VER [cm]", backgroundcolor=bg, color=txt, gridcolor="#262626"),
                zaxis=dict(title="Z - LAT [cm]", backgroundcolor=bg, color=txt, gridcolor="#262626"),
            ),
        )
        fig = go.Figure(data=[mesh], layout=layout)
        state.dosemap_fig = fig
        return fig.to_dict()
    except Exception:
        dprint("RENDERING", traceback.format_exc())
        return None


def make_dosemap_html() -> bytes | None:
    """Render the dose map as a standalone interactive HTML document."""
    try:
        fig_dict = make_dosemap_fig()
        if fig_dict is None:
            return None
        import plotly.graph_objects as go

        fig = go.Figure(fig_dict)
        return fig.to_html(full_html=True).encode()
    except Exception:
        return None


def make_dosemap_png() -> bytes | None:
    """Render the dose map as a static PNG (requires kaleido)."""
    try:
        fig_dict = make_dosemap_fig()
        if fig_dict is None:
            return None
        import plotly.graph_objects as go

        fig = go.Figure(fig_dict)
        fig.update_layout(scene_camera=dict(eye=dict(x=-2.5, y=1.5, z=0)))
        return fig.to_image(format="png")
    except Exception:
        return None
