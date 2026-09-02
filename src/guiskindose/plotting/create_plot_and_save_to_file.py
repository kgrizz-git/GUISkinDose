import logging

import plotly.graph_objects as go

logger = logging.getLogger(__name__)


def create_plot_and_save_to_file(mode: str, data: list[go.Mesh3d | go.Scatter3d], layout: go.Layout):
    """

    :param mode:
    :param data:
    :param layout:
    :return:
    """
    logger.debug(f"Creating {mode} plot (rendered via Figure.show)")

    fig = go.Figure(data=data, layout=layout)

    fig.show()
