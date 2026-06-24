"""Shared Plotly layout builders for CLI / notebook / HTML plots (refactor plan Phase 4.2).

Centralizes fonts, margins, canvas colors, and scene axis styling for geometry and
dose-map plots. Does **not** cover ``gui/figures.py`` (NiceGUI app plots).
"""

from __future__ import annotations

from typing import Any, Sequence

import plotly.graph_objects as go

from ..constants import (
    COLOR_SLIDER_BACKGROUND,
    IRRADIATION_EVENT_STEP_KEY_ARGUMENTS,
    IRRADIATION_EVENT_STEP_KEY_LABEL,
    IRRADIATION_EVENT_STEP_KEY_METHOD,
    PLOT_ASPECTMODE_PLOT_DOSEMAP,
    PLOT_ASPECTMODE_PLOT_PROCEDURE,
    PLOT_ASPECTMODE_SETUP_AND_EVENT,
    PLOT_AXIS_TITLE_X,
    PLOT_AXIS_TITLE_Y,
    PLOT_AXIS_TITLE_Z,
    PLOT_DRAGMODE,
    PLOT_FONT_FAMILY,
    PLOT_FONT_SIZE,
    PLOT_HOVERLABEL_FONT_FAMILY,
    PLOT_HOVERLABEL_FONT_SIZE,
    PLOT_PROCEDURE_AXIS_RANGE_X,
    PLOT_PROCEDURE_AXIS_RANGE_Y,
    PLOT_PROCEDURE_AXIS_RANGE_Z,
    PLOT_SLIDER_BORDER_WIDTH,
    PLOT_SLIDER_FONT_SIZE_CURRENT,
    PLOT_SLIDER_FONT_SIZE_GENERAL,
    PLOT_SLIDER_TRANSITION,
    PLOT_TITLE_FONT_FAMILY,
    PLOT_TITLE_FONT_SIZE,
    PLOT_ZERO_LINE_WIDTH,
)
from .get_camera_view import get_camera_view
from .plot_settings import (
    fetch_plot_colors,
    fetch_plot_margin,
    fetch_plot_size,
    fetch_slider_colors,
    fetch_slider_padding,
)


def _geometry_scene_axis(
    title: str,
    *,
    color_grid: str,
    color_canvas: str,
    color_zero_line: str,
    color_plot_text: str | None = None,
    axis_range: Sequence[float] | None = None,
) -> dict[str, Any]:
    """Build one 3-D scene axis dict shared by setup/event and procedure plots."""
    axis: dict[str, Any] = {
        "title": title,
        "backgroundcolor": color_canvas,
        "gridcolor": color_grid,
        "linecolor": color_grid,
        "zerolinecolor": color_zero_line,
        "zerolinewidth": PLOT_ZERO_LINE_WIDTH,
    }
    if axis_range is not None:
        axis["range"] = axis_range
        axis["color"] = color_plot_text
    return axis


def _create_event_slider_step(total_events: int, event: int) -> dict[str, Any]:
    step: dict[str, Any] = {
        IRRADIATION_EVENT_STEP_KEY_METHOD: "restyle",
        IRRADIATION_EVENT_STEP_KEY_ARGUMENTS: ["visible", [False] * total_events],
        IRRADIATION_EVENT_STEP_KEY_LABEL: event + 1,
    }
    step[IRRADIATION_EVENT_STEP_KEY_ARGUMENTS][1][event] = True
    return step


def default_procedure_sliders(
    total_events: int,
    *,
    dark_mode: bool = True,
    notebook_mode: bool = False,
) -> list[dict[str, Any]]:
    """Plotly slider config for the procedure (multi-event) geometry plot."""
    steps = [_create_event_slider_step(total_events=total_events, event=ind) for ind in range(total_events)]
    color_plot_text, color_slider_tick, color_slider_border = fetch_slider_colors(dark_mode=dark_mode)
    plot_slider_padding = fetch_slider_padding(notebook_mode=notebook_mode)
    return [
        dict(
            active=0,
            transition=PLOT_SLIDER_TRANSITION,
            bordercolor=color_slider_border,
            borderwidth=PLOT_SLIDER_BORDER_WIDTH,
            tickcolor=color_slider_tick,
            bgcolor=COLOR_SLIDER_BACKGROUND,
            currentvalue=dict(
                prefix="Active event: ",
                suffix=f" of {total_events}",
                font=dict(color=color_plot_text, size=PLOT_SLIDER_FONT_SIZE_CURRENT),
            ),
            font=dict(
                family=PLOT_FONT_FAMILY,
                color=color_plot_text,
                size=PLOT_SLIDER_FONT_SIZE_GENERAL,
            ),
            pad=plot_slider_padding,
            steps=steps,
        )
    ]


def default_geometry_layout(
    *,
    title: str,
    dark_mode: bool = True,
    notebook_mode: bool = False,
    aspectmode: str = PLOT_ASPECTMODE_SETUP_AND_EVENT,
    camera: dict[str, Any] | None = None,
) -> go.Layout:
    """Layout for single-frame setup and event geometry plots."""
    color_canvas, color_plot_text, color_grid, color_zero_line = fetch_plot_colors(dark_mode=dark_mode)
    plot_height, plot_width = fetch_plot_size(notebook_mode=notebook_mode)
    plot_margin = fetch_plot_margin(notebook_mode=notebook_mode)

    return go.Layout(
        height=plot_height,
        width=plot_width,
        margin=plot_margin,
        font=dict(family=PLOT_FONT_FAMILY, size=PLOT_FONT_SIZE, color=color_plot_text),
        title=dict(
            font=dict(
                family=PLOT_TITLE_FONT_FAMILY,
                size=PLOT_TITLE_FONT_SIZE,
                color=color_plot_text,
            ),
            text=title,
        ),
        hoverlabel=dict(
            font=dict(
                family=PLOT_HOVERLABEL_FONT_FAMILY,
                size=PLOT_HOVERLABEL_FONT_SIZE,
                color=color_plot_text,
            )
        ),
        paper_bgcolor=color_canvas,
        showlegend=False,
        dragmode=PLOT_DRAGMODE,
        scene=dict(
            aspectmode=aspectmode,
            camera=camera if camera is not None else get_camera_view(),
            xaxis=_geometry_scene_axis(
                PLOT_AXIS_TITLE_X,
                color_grid=color_grid,
                color_canvas=color_canvas,
                color_zero_line=color_zero_line,
            ),
            yaxis=_geometry_scene_axis(
                PLOT_AXIS_TITLE_Y,
                color_grid=color_grid,
                color_canvas=color_canvas,
                color_zero_line=color_zero_line,
            ),
            zaxis=_geometry_scene_axis(
                PLOT_AXIS_TITLE_Z,
                color_grid=color_grid,
                color_canvas=color_canvas,
                color_zero_line=color_zero_line,
            ),
        ),
    )


def default_procedure_layout(
    *,
    title: str,
    total_events: int,
    dark_mode: bool = True,
    notebook_mode: bool = False,
) -> go.Layout:
    """Layout for the interactive procedure plot (geometry + event slider)."""
    color_canvas, color_plot_text, color_grid, color_zero_line = fetch_plot_colors(dark_mode=dark_mode)
    plot_height, plot_width = fetch_plot_size(notebook_mode=notebook_mode)
    plot_margin = fetch_plot_margin(notebook_mode=notebook_mode)

    return go.Layout(
        height=plot_height,
        width=plot_width,
        margin=plot_margin,
        sliders=default_procedure_sliders(
            total_events, dark_mode=dark_mode, notebook_mode=notebook_mode
        ),
        font=dict(family=PLOT_FONT_FAMILY, size=PLOT_FONT_SIZE, color=color_plot_text),
        hoverlabel=dict(font=dict(family=PLOT_HOVERLABEL_FONT_FAMILY, size=PLOT_SLIDER_FONT_SIZE_GENERAL)),
        showlegend=False,
        dragmode=PLOT_DRAGMODE,
        title=dict(
            text=title,
            font=dict(
                family=PLOT_TITLE_FONT_FAMILY,
                size=PLOT_TITLE_FONT_SIZE,
                color=color_plot_text,
            ),
        ),
        paper_bgcolor=color_canvas,
        scene=dict(
            aspectmode=PLOT_ASPECTMODE_PLOT_PROCEDURE,
            camera=get_camera_view(),
            xaxis=_geometry_scene_axis(
                PLOT_AXIS_TITLE_X,
                color_grid=color_grid,
                color_canvas=color_canvas,
                color_zero_line=color_zero_line,
                color_plot_text=color_plot_text,
                axis_range=PLOT_PROCEDURE_AXIS_RANGE_X,
            ),
            yaxis=_geometry_scene_axis(
                PLOT_AXIS_TITLE_Y,
                color_grid=color_grid,
                color_canvas=color_canvas,
                color_zero_line=color_zero_line,
                color_plot_text=color_plot_text,
                axis_range=PLOT_PROCEDURE_AXIS_RANGE_Y,
            ),
            zaxis=_geometry_scene_axis(
                PLOT_AXIS_TITLE_Z,
                color_grid=color_grid,
                color_canvas=color_canvas,
                color_zero_line=color_zero_line,
                color_plot_text=color_plot_text,
                axis_range=PLOT_PROCEDURE_AXIS_RANGE_Z,
            ),
        ),
    )


def default_dosemap_layout(
    *,
    dark_mode: bool = True,
    notebook_mode: bool = False,
    color_plot_text: str | None = None,
    color_canvas: str | None = None,
    plot_height: int | None = None,
    plot_width: int | None = None,
    plot_margin: dict[str, int] | None = None,
) -> go.Layout:
    """Layout for the 3-D dose map plot (hidden scene axes)."""
    if color_plot_text is None or color_canvas is None:
        resolved_canvas, resolved_text, _, _ = fetch_plot_colors(dark_mode=dark_mode)
        color_canvas = color_canvas if color_canvas is not None else resolved_canvas
        color_plot_text = color_plot_text if color_plot_text is not None else resolved_text

    if plot_height is None or plot_width is None:
        resolved_height, resolved_width = fetch_plot_size(notebook_mode=notebook_mode)
        plot_height = plot_height if plot_height is not None else resolved_height
        plot_width = plot_width if plot_width is not None else resolved_width
    if plot_margin is None:
        plot_margin = fetch_plot_margin(notebook_mode=notebook_mode)

    return go.Layout(
        height=plot_height,
        width=plot_width,
        margin=plot_margin,
        font=dict(family=PLOT_FONT_FAMILY, color=color_plot_text, size=PLOT_FONT_SIZE),
        hoverlabel=dict(font=dict(family=PLOT_HOVERLABEL_FONT_FAMILY, size=PLOT_HOVERLABEL_FONT_SIZE)),
        title=dict(font=dict(family=PLOT_FONT_FAMILY, size=PLOT_FONT_SIZE, color=color_plot_text)),
        paper_bgcolor=color_canvas,
        scene=dict(
            aspectmode=PLOT_ASPECTMODE_PLOT_DOSEMAP,
            xaxis=dict(
                title="",
                backgroundcolor=color_canvas,
                showgrid=False,
                zeroline=False,
                showticklabels=False,
            ),
            yaxis=dict(
                title="",
                backgroundcolor=color_canvas,
                showgrid=False,
                zeroline=False,
                showticklabels=False,
            ),
            zaxis=dict(
                title="",
                backgroundcolor=color_canvas,
                showgrid=False,
                zeroline=False,
                showticklabels=False,
            ),
        ),
    )
