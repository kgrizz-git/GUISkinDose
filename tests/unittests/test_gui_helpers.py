"""Unit tests for GUI helper behavior that does not require a browser session."""

from __future__ import annotations

import importlib

import pandas as pd

from mypyskindose.gui.helpers import run_calculation
from mypyskindose.gui.state import AppState

analyze_module = importlib.import_module("mypyskindose.analyze_data")


def test_run_calculation_returns_sanitized_error(monkeypatch, capsys) -> None:
    """Calculation failures must not return raw tracebacks to the GUI."""

    def fail_calculation(*args, **kwargs):
        raise RuntimeError("patient Smith MRN123")

    monkeypatch.setattr(analyze_module, "analyze_data", fail_calculation)
    app_state = AppState(rdsr_df=pd.DataFrame({"kVp": [70]}))

    ok, message = run_calculation(app_state)
    captured = capsys.readouterr()

    assert ok is False
    assert message == "Calculation failed. See the application log for details."
    assert "Smith" not in message
    assert "MRN123" not in message
    assert "RuntimeError" in captured.err
    assert "Smith" not in captured.err
    assert "MRN123" not in captured.err
