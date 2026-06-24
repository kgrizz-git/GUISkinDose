"""Backward-compatible wrapper — layout logic lives in ``plot_layout.default_dosemap_layout``."""

from .plot_layout import default_dosemap_layout


def create_layout_for_dose_map_plots(
    PLOT_MARGINS,
    PLOT_HEIGHT,
    PLOT_WIDTH,
    COLOR_PLOT_TEXT,
    COLOR_CANVAS,
):
    """Build dose-map layout using explicit theme values (legacy call signature)."""
    return default_dosemap_layout(
        color_plot_text=COLOR_PLOT_TEXT,
        color_canvas=COLOR_CANVAS,
        plot_height=PLOT_HEIGHT,
        plot_width=PLOT_WIDTH,
        plot_margin=PLOT_MARGINS,
    )
