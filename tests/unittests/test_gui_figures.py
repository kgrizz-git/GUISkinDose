"""Tests for GUI Plotly figure builders."""

from __future__ import annotations

import pytest

pytest.importorskip("nicegui")

from mypyskindose.plotting.plot_layout import COORDINATE_FRAME_NOTE


def test_make_dosemap_fig_includes_coordinate_frame_annotation():
    from mypyskindose.gui.figures import make_dosemap_fig

    patient = {
        "patient": {
            "patient_skin_cells": {
                "x": [0.0, 1.0, 0.0],
                "y": [0.0, 0.0, 1.0],
                "z": [0.0, 0.0, 0.0],
            },
            "triangle_vertex_indices": {"i": [0], "j": [1], "k": [2]},
        }
    }

    fig = make_dosemap_fig(explicit_dose_map=[1.0, 2.0, 3.0], explicit_patient=patient)

    assert fig is not None
    assert COORDINATE_FRAME_NOTE in fig["layout"]["annotations"][0]["text"]
