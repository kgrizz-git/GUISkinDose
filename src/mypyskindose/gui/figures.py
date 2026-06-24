"""Plotly figure builders for the GUI (geometry preview and dose map).

These functions read from the shared ``state`` singleton and ``build_settings``;
they do not depend on any page-construction scope, so they live here rather than
inside the page function. Each returns a Plotly figure ``dict`` (or ``bytes`` for
the HTML/PNG exporters), or ``None`` on failure.
"""

from __future__ import annotations

import traceback

from mypyskindose.debug import dprint

from .geometry_preview import effective_patient_offset_for_preview, rdsr_df_for_geometry_preview
from .helpers import build_settings
from .state import state


def make_geometry_fig(
    mode: str,
    event_index: int,
    *,
    active_exam_index: int | None = None,
    composite: bool = False,
):
    """Build a Plotly Figure for geometry preview. Returns fig dict or None."""
    try:
        import plotly.graph_objects as go

        from mypyskindose import constants as c
        from mypyskindose.helpers.calculate_rotation_matrices import calculate_rotation_matrices
        from mypyskindose.phantom_class import Phantom
        from mypyskindose.plotting.create_geometry_plot import create_geometry_plot

        preview_df = rdsr_df_for_geometry_preview(
            state,
            active_exam_index=active_exam_index,
            composite=composite,
        )
        if preview_df is None or len(preview_df) == 0:
            return None

        if mode == "plot_event":
            event_index = min(max(0, event_index), len(preview_df) - 1)

        settings = build_settings(
            state,
            mode=mode,
            output_format="dict",
            patient_offset=effective_patient_offset_for_preview(state, active_exam_index),
        )
        settings.plot.plot_event_index = event_index
        settings.plot.notebook_mode = False
        settings.plot.interactivity = True

        data_norm = calculate_rotation_matrices(preview_df.copy())

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
