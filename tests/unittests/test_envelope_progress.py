"""Unit tests for candidate-level (fractional) progress reporting.

A recording fake progress bar is injected in place of tqdm to assert the
per-event contract: static events advance one integer unit, envelope events
advance fractionally per candidate (throttled) and snap to the exact integer
at the event boundary, and ``pbar=None`` stays supported.
"""

from __future__ import annotations

import numpy as np
import pytest
from calculate_dose_recursion_helpers import generate_synthetic_normalized_events

from guiskindose import constants as c
from guiskindose import load_settings_example_json
from guiskindose.calculate_dose import calculate_dose as calculate_dose_module
from guiskindose.calculate_dose.calculate_dose import calculate_dose
from guiskindose.phantom_class import Phantom
from guiskindose.settings import PyskindoseSettings


class _RecordingPbar:
    """Stand-in for tqdm recording every counter assignment and update."""

    def __init__(self) -> None:
        self.__dict__["n"] = 0
        self.trace: list[float] = [0]
        self.amounts: list[float] = []
        self.refreshes = 0

    def __setattr__(self, name: str, value: object) -> None:
        if name == "n" and isinstance(value, int | float):
            self.__dict__["n"] = value
            self.trace.append(value)
        else:
            super().__setattr__(name, value)

    def update(self, n: float = 1) -> None:
        self.n += n
        self.amounts.append(n)

    def refresh(self) -> None:
        self.refreshes += 1


def _settings(**overrides) -> PyskindoseSettings:
    base = load_settings_example_json()
    base["mode"] = "calculate_dose"
    base["silence_pydicom_warnings"] = True
    base["phantom"]["model"] = "plane"
    base["plot"]["notebook_mode"] = False
    base["plot"]["plot_dosemap"] = False
    base.update(overrides)
    return PyskindoseSettings(settings=base)


def _spin_frame(n_events: int, spin_index: int):
    frame = generate_synthetic_normalized_events(n_events)
    frame.at[spin_index, "acquisition_type"] = "Rotational Acquisition"
    frame.at[spin_index, "acquisition_type_code"] = "113613"
    frame.at[spin_index, "acquisition_type_coding_scheme"] = "DCM"
    frame.at[spin_index, "acquisition_type_meaning"] = "Rotational Acquisition"
    ap1_values = frame["Ap1"].to_numpy()
    ap2_values = frame["Ap2"].to_numpy()
    frame.at[spin_index, "Ap1_end"] = float(ap1_values[spin_index]) + 60.0
    frame.at[spin_index, "Ap2_end"] = float(ap2_values[spin_index])
    return frame


def _run_with_bar_factory(frame, settings, factory):
    table = Phantom(phantom_model=c.PHANTOM_MODEL_TABLE, phantom_dim=settings.phantom.dimension)
    pad = Phantom(phantom_model=c.PHANTOM_MODEL_PAD, phantom_dim=settings.phantom.dimension)
    _, output, _ = calculate_dose(normalized_data=frame, settings=settings, table=table, pad=pad)
    assert output is not None
    return output


def _run(frame, settings, monkeypatch: pytest.MonkeyPatch, factory):
    bars: list[_RecordingPbar | None] = []

    def _factory(*args, **kwargs):
        bar = factory()
        bars.append(bar)
        return bar

    monkeypatch.setattr(calculate_dose_module, "_make_progress_bar", _factory)
    output = _run_with_bar_factory(frame.copy(), settings, factory)
    assert len(bars) == 1
    return output, bars[0]


def test_envelope_advances_fractionally_with_bounded_updates(monkeypatch: pytest.MonkeyPatch):
    settings = _settings(angular_step_deg=5.0)
    _output, bar = _run(_spin_frame(2, 1), settings, monkeypatch, _RecordingPbar)
    assert isinstance(bar, _RecordingPbar)
    # Finished-event count is exactly an integer ...
    assert bar.n == 2
    assert isinstance(bar.n, int)
    # ... reached through fractional per-candidate advances ...
    fractional = [amount for amount in bar.amounts if float(amount) != int(amount)]
    assert fractional
    assert all(amount < 1.0 for amount in fractional)
    # ... throttled to ~50 updates for the envelope event (static: 1 each).
    assert len(bar.amounts) <= 55


def test_mixed_frame_snaps_to_exact_integers_after_every_event(monkeypatch: pytest.MonkeyPatch):
    settings = _settings(angular_step_deg=5.0)
    _output, bar = _run(_spin_frame(3, 1), settings, monkeypatch, _RecordingPbar)
    assert isinstance(bar, _RecordingPbar)
    assert bar.n == 3
    assert isinstance(bar.n, int)
    # Every event boundary in the trace is an exact integer: static events via
    # update(), the envelope event via the end-of-event snap.
    integral = [value for value in bar.trace if float(value) == int(value)]
    # Collapse consecutive duplicates: the snap's remainder update can land on
    # the exact integer just before the pinning assignment repeats it.
    collapsed = [integral[0]]
    collapsed.extend(value for value in integral[1:] if value != collapsed[-1])
    assert [int(value) for value in collapsed] == [0, 1, 2, 3]
    for value in bar.trace:
        assert 0 <= float(value) <= 3


def test_progress_reporting_does_not_change_dose(monkeypatch: pytest.MonkeyPatch):
    settings = _settings(angular_step_deg=5.0)
    frame = _spin_frame(2, 1)
    with_bar, _ = _run(frame, settings, monkeypatch, _RecordingPbar)
    without_bar = _run_with_bar_factory(frame.copy(), settings, None)
    np.testing.assert_array_equal(
        with_bar[c.OUTPUT_KEY_DOSE_MAP],
        without_bar[c.OUTPUT_KEY_DOSE_MAP],
    )


def test_pbar_none_still_works(monkeypatch: pytest.MonkeyPatch):
    settings = _settings(angular_step_deg=5.0)
    output, bar = _run(_spin_frame(2, 1), settings, monkeypatch, lambda: None)
    assert bar is None
    assert output[c.OUTPUT_KEY_ROTATIONAL_HANDLING]["aggregate"]["rotational_count"] == 1
