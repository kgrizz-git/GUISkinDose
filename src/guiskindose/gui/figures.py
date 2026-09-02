"""Plotly figure builders for the GUI (geometry preview and dose map).

These functions read from the shared ``state`` singleton and ``build_settings``;
they do not depend on any page-construction scope, so they live here rather than
inside the page function. ``make_geometry_fig``/``make_dosemap_fig`` return a Plotly
figure ``dict`` or ``None`` on failure (an empty plot is an acceptable outcome for
Results). ``make_dosemap_html``/``make_dosemap_png`` return ``bytes`` and instead
*raise* on failure, since a silent ``None`` there is indistinguishable from NiceGUI's
cancel-on-shutdown sentinel (see ``gui/concurrency.require_io_result``).
"""

from __future__ import annotations

import logging
from typing import Any

from guiskindose.privacy import safe_error_event

from .geometry_preview import effective_patient_offset_for_preview, rdsr_df_for_geometry_preview
from .helpers import build_settings
from .state import state

logger = logging.getLogger(__name__)


def extract_exam_dose_map(exam_output: Any) -> tuple[Any, dict[str, Any]]:
    """Extract (dose_map_array, patient_dict) from a PySkinDoseOutput.

    Returns the dose-map as a zero-padded ndarray sized to the patient skin
    cells, and the patient dict suitable for ``make_dosemap_fig``.
    """
    import numpy as np

    output_dict = exam_output.to_dict()
    patient_for_fig = output_dict["patient"]
    patient_data = patient_for_fig["patient"]
    num_cells = len(patient_data["patient_skin_cells"]["x"])
    dose_map = np.zeros(num_cells)
    for idx, dose in output_dict["dose_map"]:
        dose_map[int(idx)] = dose
    return dose_map, patient_for_fig


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

        from guiskindose import constants as c
        from guiskindose.helpers.calculate_rotation_matrices import calculate_rotation_matrices
        from guiskindose.phantom_class import Phantom
        from guiskindose.plotting.create_geometry_plot import create_geometry_plot

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
                font={"color": txt, "family": "Inter, sans-serif"},
                scene={
                    "xaxis": {"gridcolor": "#262626"},
                    "yaxis": {"gridcolor": "#262626"},
                    "zaxis": {"gridcolor": "#262626"},
                },
            )
            return fig.to_dict()
        return None
    except Exception as exc:
        safe_error_event(logger, "geometry_figure_render", exc, level=logging.DEBUG)
        return None


def make_dosemap_fig(explicit_dose_map=None, explicit_patient=None):
    """Build the dose map Plotly figure.

    If explicit_dose_map and explicit_patient are provided, uses those (e.g. for aggregate map).
    Otherwise reads from current state.output. Delegates the figure construction to the
    GUI-free ``export.images`` helper so camera/label logic lives in one place.
    """
    try:
        import numpy as np

        from guiskindose.export.images import render_dosemap_plotly_figure

        if explicit_dose_map is not None and explicit_patient is not None:
            patient_data = explicit_patient["patient"]
            dose_map = explicit_dose_map
        else:
            if state.output is None:
                return None
            out = state.output
            patient_data = out["patient"]["patient"]

            # The length of r is the number of skin cells
            num_cells = len(patient_data["patient_skin_cells"]["x"])
            dose_map = np.zeros(num_cells)
            for idx, dose in out["dose_map"]:
                dose_map[int(idx)] = dose

        fig = render_dosemap_plotly_figure(dose_map, patient_data, state.colorscale, dark=True)
        state.dosemap_fig = fig
        return fig.to_dict()
    except Exception as exc:
        safe_error_event(logger, "dosemap_figure_render", exc, level=logging.DEBUG)
        return None


def make_dosemap_html(explicit_dose_map=None, explicit_patient=None) -> bytes:
    """Render the dose map as a standalone interactive HTML document.

    Raises on failure (instead of returning ``None``) so callers — notably the
    export handlers in ``gui/tabs/export.py`` — can distinguish a real render
    failure from NiceGUI's ``run.io_bound`` cancel-on-shutdown ``None`` sentinel
    (see ``require_io_result``). The failure is logged via ``safe_error_event``
    before re-raising so no exception text/PHI reaches the caller or the log.
    """
    try:
        fig_dict = make_dosemap_fig(explicit_dose_map=explicit_dose_map, explicit_patient=explicit_patient)
        if fig_dict is None:
            raise RuntimeError("Dose map figure could not be built")
        import plotly.graph_objects as go

        fig = go.Figure(fig_dict)
        return fig.to_html(full_html=True).encode()
    except Exception as exc:
        safe_error_event(logger, "dosemap_html_render", exc)
        raise


def make_dosemap_png(explicit_dose_map=None, explicit_patient=None) -> bytes:
    """Render the dose map as a static PNG (requires kaleido).

    Raises on failure (instead of returning ``None``) — mirrors
    ``make_dosemap_html``; see that docstring for the cancel-vs-failure rationale.
    """
    try:
        fig_dict = make_dosemap_fig(explicit_dose_map=explicit_dose_map, explicit_patient=explicit_patient)
        if fig_dict is None:
            raise RuntimeError("Dose map figure could not be built")
        import plotly.graph_objects as go

        fig = go.Figure(fig_dict)
        fig.update_layout(scene_camera={"eye": {"x": -2.5, "y": 1.5, "z": 0}})
        return fig.to_image(format="png")
    except Exception as exc:
        safe_error_event(logger, "dosemap_png_render", exc)
        raise
