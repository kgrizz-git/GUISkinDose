"""Intended-use notice shared by the GUI, exported reports, and figures.

The GUI reads the same wording from ``ui_copy.json`` (``onboarding.intended_use``
and ``results.intended_use``); a unit test keeps the two in sync. Exports import
it from here because the export package must not depend on the GUI.
"""

from __future__ import annotations

from typing import Any

INTENDED_USE_NOTICE = (
    "GUISkinDose is not FDA-cleared or otherwise certified as a medical device. It is intended for research, "
    "education, development, and institutional quality assurance, and its results are not independently validated "
    "for patient-care decisions. Qualified medical physicists and physicians are responsible for reviewing its "
    "inputs and outputs, evaluating patient skin dose, and making any clinical decisions."
)

INTENDED_USE_SHORT = (
    "Not FDA-cleared. Skin dose estimates must be reviewed by a qualified medical physicist or physician."
)


def stamp_figure(fig: Any) -> None:
    """Add the short notice to an exported Plotly figure, top-left on a backing box.

    Top-left because the dose-map layout already uses the bottom-left corner for its
    coordinate-frame note and the right side for the colorbar.
    """
    fig.add_annotation(
        text=INTENDED_USE_SHORT,
        xref="paper",
        yref="paper",
        x=0.01,
        y=0.99,
        xanchor="left",
        yanchor="top",
        showarrow=False,
        font={"size": 11, "color": "#FB923C"},
        bgcolor="rgba(15, 23, 42, 0.75)",
        borderpad=4,
    )
