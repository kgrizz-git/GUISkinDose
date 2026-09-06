"""Render a Plotly figure from assembled traces and layout."""
import logging

import plotly.graph_objects as go

logger = logging.getLogger(__name__)


def create_plot_and_save_to_file(mode: str, data: list[go.Mesh3d | go.Scatter3d], layout: go.Layout):
    """Build a Plotly figure from data and layout and render it.

    Parameters
    ----------
    mode : str
        Plot mode label used for debug logging.
    data : list[go.Mesh3d | go.Scatter3d]
        Plotly trace objects.
    layout : go.Layout
        Plotly layout configuration.

    """
    logger.debug(f"Creating {mode} plot (rendered via Figure.show)")

    fig = go.Figure(data=data, layout=layout)

    fig.show()
