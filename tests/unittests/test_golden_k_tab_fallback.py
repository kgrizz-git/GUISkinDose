"""Goldens for the k_tab fallback path (measured_with_fallback) and measured_only on unusable measured data.

Recorded 2026-10-07 and reproduced across repeated and parallel runs. Two synthetic
inputs have no usable measured data: a model absent from the table, and the shipped
all-0.0 AlluraClarity Plane B rows. With the fallback every event uses ``k_tab_val``
(0.8), so the result is bit-identical to ``estimate``. With ``measured_only`` the
events get 1.0 (no table attenuation), so the dose is exactly 1 / 0.8 = 1.25 times
larger (0.20462 / 0.16369 and 19.2269 / 15.3815).
"""

from __future__ import annotations

import numpy as np
import pytest
from calculate_dose_recursion_helpers import generate_synthetic_normalized_events

from guiskindose import constants as c
from guiskindose import load_settings_example_json
from guiskindose.calculate_dose.calculate_dose import calculate_dose
from guiskindose.phantom_class import Phantom
from guiskindose.settings import PyskindoseSettings

_INPUTS = {
    "unknown_model": ("GE Innova", "Single Plane", "single", "no_device"),
    "allura_plane_b": ("AlluraClarity", "Plane B", "B", "invalid_inherited"),
}
_GOLDEN = {
    "fallback_or_estimate": {"psd_mgy": 0.16369364352276702, "dose_sum": 15.38148096200018, "k_tab": 0.8},
    "measured_only": {"psd_mgy": 0.2046170544034588, "dose_sum": 19.22685120250022, "k_tab": 1.0},
}


def _run(input_name: str, mode: str):
    model, plane, canonical, _ = _INPUTS[input_name]
    base = load_settings_example_json()
    base.update(mode="calculate_dose", silence_pydicom_warnings=True, k_tab_mode=mode)
    base["phantom"]["model"] = "cylinder"
    base["plot"]["notebook_mode"] = False
    base["plot"]["plot_dosemap"] = False
    settings = PyskindoseSettings(settings=base)
    frame = generate_synthetic_normalized_events(3)
    frame["model"] = model
    frame["acquisition_plane"] = plane
    frame["acquisition_plane_canonical"] = canonical
    dim = settings.phantom.dimension
    table = Phantom(phantom_model=c.PHANTOM_MODEL_TABLE, phantom_dim=dim)
    pad = Phantom(phantom_model=c.PHANTOM_MODEL_PAD, phantom_dim=dim)
    _, output, _ = calculate_dose(normalized_data=frame, settings=settings, table=table, pad=pad)
    assert output is not None
    return output


@pytest.mark.parametrize("input_name", list(_INPUTS))
@pytest.mark.parametrize("mode", ["measured_with_fallback", "estimate"])
def test_fallback_and_estimate_give_the_same_golden(input_name: str, mode: str) -> None:
    output = _run(input_name, mode)
    golden = _GOLDEN["fallback_or_estimate"]
    dose_map = output[c.OUTPUT_KEY_DOSE_MAP]
    assert float(np.max(dose_map)) == pytest.approx(golden["psd_mgy"])
    assert float(np.sum(dose_map)) == pytest.approx(golden["dose_sum"])
    assert output[c.OUTPUT_KEY_CORRECTION_TABLE] == pytest.approx([golden["k_tab"]] * 3)
    expected = "fallback" if mode == "measured_with_fallback" else "estimated"
    assert set(output[c.OUTPUT_KEY_CORRECTION_TABLE_STATUSES]) == {expected}


@pytest.mark.parametrize("input_name", list(_INPUTS))
def test_measured_only_gives_unity_and_a_larger_golden_dose(input_name: str) -> None:
    output = _run(input_name, "measured_only")
    golden = _GOLDEN["measured_only"]
    dose_map = output[c.OUTPUT_KEY_DOSE_MAP]
    assert float(np.max(dose_map)) == pytest.approx(golden["psd_mgy"])
    assert float(np.sum(dose_map)) == pytest.approx(golden["dose_sum"])
    assert output[c.OUTPUT_KEY_CORRECTION_TABLE] == pytest.approx([golden["k_tab"]] * 3)
    assert set(output[c.OUTPUT_KEY_CORRECTION_TABLE_STATUSES]) == {_INPUTS[input_name][3]}
    assert golden["psd_mgy"] / _GOLDEN["fallback_or_estimate"]["psd_mgy"] == pytest.approx(1.25)
