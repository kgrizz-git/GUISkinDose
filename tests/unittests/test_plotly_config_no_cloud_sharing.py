"""Figures rendered outside NiceGUI must not offer plotly's "Share chart" upload.

Standalone plotly.js 4.0 shows that button by default, so every ``fig.show`` path passes
``PLOTLY_CONFIG``, which disables it.
"""

from __future__ import annotations

import plotly.graph_objects as go

from guiskindose.plotting import create_plot_and_save_to_file as plot_module
from guiskindose.plotting.plot_settings import PLOTLY_CONFIG


def test_plotly_config_disables_cloud_sharing() -> None:
    assert PLOTLY_CONFIG["showSendToCloud"] is False


def test_cli_plot_passes_the_config(monkeypatch) -> None:
    seen: list[dict] = []
    monkeypatch.setattr(go.Figure, "show", lambda self, *a, **k: seen.append(k.get("config", {})))

    plot_module.create_plot_and_save_to_file("plot_setup", [], go.Layout())

    assert seen == [PLOTLY_CONFIG]
