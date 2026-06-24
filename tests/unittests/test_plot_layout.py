"""Tests for shared Plotly layout helpers (refactor plan Phase 4.2)."""

from __future__ import annotations

import plotly.graph_objects as go

from mypyskindose.constants import (
    COLOR_CANVAS_DARK,
    COLOR_CANVAS_LIGHT,
    COLOR_PLOT_TEXT_DARK,
    PLOT_ASPECTMODE_PLOT_DOSEMAP,
    PLOT_ASPECTMODE_PLOT_PROCEDURE,
    PLOT_ASPECTMODE_SETUP_AND_EVENT,
    PLOT_FONT_FAMILY,
    PLOT_MARGIN,
)
from mypyskindose.plotting.create_layout_for_dose_map_plots import (
    create_layout_for_dose_map_plots,
)
from mypyskindose.plotting.plot_layout import (
    default_dosemap_layout,
    default_geometry_layout,
    default_procedure_layout,
)


def test_default_geometry_layout_is_plotly_layout_with_shared_font():
    layout = default_geometry_layout(title="Setup", dark_mode=True, notebook_mode=False)
    assert isinstance(layout, go.Layout)
    layout_dict = layout.to_plotly_json()
    assert layout_dict["font"]["family"] == PLOT_FONT_FAMILY
    assert layout_dict["scene"]["aspectmode"] == PLOT_ASPECTMODE_SETUP_AND_EVENT
    assert layout.paper_bgcolor == COLOR_CANVAS_DARK


def test_default_geometry_layout_light_mode_canvas_differs():
    dark = default_geometry_layout(title="Dark", dark_mode=True)
    light = default_geometry_layout(title="Light", dark_mode=False)
    assert dark.paper_bgcolor == COLOR_CANVAS_DARK
    assert light.paper_bgcolor == COLOR_CANVAS_LIGHT
    assert dark.paper_bgcolor != light.paper_bgcolor


def test_default_procedure_layout_includes_slider_and_procedure_aspect():
    layout = default_procedure_layout(
        title="Procedure",
        total_events=3,
        dark_mode=True,
        notebook_mode=False,
    )
    assert isinstance(layout, go.Layout)
    layout_dict = layout.to_plotly_json()
    assert layout_dict["scene"]["aspectmode"] == PLOT_ASPECTMODE_PLOT_PROCEDURE
    assert layout_dict["sliders"] is not None
    assert len(layout_dict["sliders"]) == 1
    assert len(layout_dict["sliders"][0]["steps"]) == 3


def test_default_dosemap_layout_hides_scene_ticks():
    layout = default_dosemap_layout(
        dark_mode=True,
        notebook_mode=False,
        plot_margin=PLOT_MARGIN,
    )
    assert isinstance(layout, go.Layout)
    layout_dict = layout.to_plotly_json()
    assert layout_dict["scene"]["aspectmode"] == PLOT_ASPECTMODE_PLOT_DOSEMAP
    assert layout_dict["scene"]["xaxis"]["showticklabels"] is False
    assert layout_dict["scene"]["yaxis"]["showgrid"] is False
    assert layout_dict["scene"]["zaxis"]["zeroline"] is False


def test_create_layout_for_dose_map_plots_preserves_explicit_dimensions():
    """Legacy wrapper must forward caller-supplied size, margin, and colors."""
    custom_margin = dict(l=11, r=22, b=33, t=44)
    custom_height = 720
    custom_width = 1280

    layout = create_layout_for_dose_map_plots(
        PLOT_MARGINS=custom_margin,
        PLOT_HEIGHT=custom_height,
        PLOT_WIDTH=custom_width,
        COLOR_PLOT_TEXT=COLOR_PLOT_TEXT_DARK,
        COLOR_CANVAS=COLOR_CANVAS_DARK,
    )

    assert isinstance(layout, go.Layout)
    assert layout.height == custom_height
    assert layout.width == custom_width
    assert layout.paper_bgcolor == COLOR_CANVAS_DARK
    layout_dict = layout.to_plotly_json()
    margin_dict = layout_dict["margin"]
    assert margin_dict["l"] == custom_margin["l"]
    assert margin_dict["r"] == custom_margin["r"]
    assert margin_dict["b"] == custom_margin["b"]
    assert margin_dict["t"] == custom_margin["t"]
    assert layout_dict["font"]["color"] == COLOR_PLOT_TEXT_DARK
