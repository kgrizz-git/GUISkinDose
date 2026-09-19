"""Mode/format matrix for analyze_data's HTML output contract.

Regression coverage for the notebook docs-build failure: plot modes return no
output by design, so html format must not raise for them — only dose modes
with genuinely missing output fail.
"""

from __future__ import annotations

import sys

import pandas as pd
import pytest

import guiskindose.analyze_data as _analyze_data_symbol  # noqa: F401  (keeps the submodule imported)
from guiskindose import constants as c
from guiskindose.analyze_data import analyze_data
from guiskindose.settings import PyskindoseSettings

# The name `guiskindose.analyze_data` resolves to the analyze_data() function
# (shadowed by the package __init__), so patch targets must come from the real
# module object below — never the dotted string path.
analyze_data_module = sys.modules["guiskindose.analyze_data"]


def _settings(mode: str) -> PyskindoseSettings:
    from guiskindose import load_settings_example_json

    settings = PyskindoseSettings(settings=load_settings_example_json())
    settings.mode = mode
    settings.output_format = "html"
    return settings


def _frame() -> pd.DataFrame:
    return pd.DataFrame({"At1": [0.0], "At2": [0.0], "At3": [0.0]})


@pytest.fixture(autouse=True)
def _no_plots(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(analyze_data_module, "create_geometry_plot", lambda **kwargs: None)
    monkeypatch.setattr(analyze_data_module, "create_dose_map_plot", lambda **kwargs: None)


@pytest.mark.parametrize("mode", [c.MODE_PLOT_SETUP, c.MODE_PLOT_EVENT, c.MODE_PLOT_PROCEDURE])
def test_plot_modes_html_return_none_without_raising(mode: str) -> None:
    assert analyze_data(normalized_data=_frame(), settings=_settings(mode)) is None


def test_dose_mode_html_missing_output_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        analyze_data_module, "calculate_dose", lambda **kwargs: (None, None, None)
    )
    with pytest.raises(RuntimeError, match=r"Expected HTML output but dose calculation returned no data."):
        analyze_data(normalized_data=_frame(), settings=_settings(c.MODE_CALCULATE_DOSE))


def test_plot_dosemap_html_missing_output_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        analyze_data_module, "calculate_dose", lambda **kwargs: (None, None, None)
    )
    with pytest.raises(RuntimeError, match=r"Expected HTML output but dose calculation returned no data."):
        analyze_data(normalized_data=_frame(), settings=_settings(c.MODE_PLOT_DOSEMAP))
