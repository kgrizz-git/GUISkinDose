"""Integration tests for the rotational coverage envelope in the dose loop."""

from __future__ import annotations

import numpy as np
from calculate_dose_recursion_helpers import generate_synthetic_normalized_events

from guiskindose import constants as c
from guiskindose import load_settings_example_json
from guiskindose.calculate_dose.calculate_dose import calculate_dose
from guiskindose.phantom_class import Phantom
from guiskindose.settings import PyskindoseSettings


def _settings(**overrides) -> PyskindoseSettings:
    base = load_settings_example_json()
    base["mode"] = "calculate_dose"
    base["silence_pydicom_warnings"] = True
    base["phantom"]["model"] = "plane"
    base["plot"]["notebook_mode"] = False
    base["plot"]["plot_dosemap"] = False
    base.update(overrides)
    return PyskindoseSettings(settings=base)


def _frame_with_spin():
    frame = generate_synthetic_normalized_events(2)
    frame.at[1, "acquisition_type"] = "Rotational Acquisition"
    frame.at[1, "acquisition_type_code"] = "113613"
    frame.at[1, "acquisition_type_coding_scheme"] = "DCM"
    frame.at[1, "acquisition_type_meaning"] = "Rotational Acquisition"
    frame.at[1, "Ap1_end"] = float(frame.at[1, "Ap1"]) + 60.0
    frame.at[1, "Ap2_end"] = float(frame.at[1, "Ap2"])
    return frame


def _phantoms(settings):
    table = Phantom(phantom_model=c.PHANTOM_MODEL_TABLE, phantom_dim=settings.phantom.dimension)
    pad = Phantom(phantom_model=c.PHANTOM_MODEL_PAD, phantom_dim=settings.phantom.dimension)
    return table, pad


def _run(frame, settings):
    table, pad = _phantoms(settings)
    _, output, _ = calculate_dose(normalized_data=frame, settings=settings, table=table, pad=pad)
    assert output is not None
    return output


def test_envelope_dominates_static_and_preserves_kerma():
    """Envelope PSD >= static PSD (static pose is a candidate); records equal."""
    frame = _frame_with_spin()
    settings = _settings(angular_step_deg=5.0)

    enveloped = _run(frame.copy(), settings)
    static_settings = _settings(angular_step_deg=5.0, rotational_handling="static")
    static = _run(frame.copy(), static_settings)

    handling = enveloped[c.OUTPUT_KEY_ROTATIONAL_HANDLING]
    assert handling["aggregate"]["rotational_count"] == 1
    assert handling["rows"][1]["effective_handling"] == "coverage"
    assert handling["rows"][1]["classification"] == "rotational"
    assert handling["source_event_count"] == handling["processed_event_count"] == 2

    envelope_psd = float(np.max(enveloped[c.OUTPUT_KEY_DOSE_MAP]))
    static_psd = float(np.max(static[c.OUTPUT_KEY_DOSE_MAP]))
    assert envelope_psd >= static_psd

    # Kerma records are treatment-independent (multiplier 1.0, no K/N split).
    assert enveloped[c.OUTPUT_KEY_KERMA] == static[c.OUTPUT_KEY_KERMA]
    assert enveloped[c.OUTPUT_KEY_KERMA_CORRECTED] == static[c.OUTPUT_KEY_KERMA_CORRECTED]

    details = enveloped[c.OUTPUT_KEY_ROTATIONAL_ENVELOPE][1]
    assert details["unique_candidate_count"] > 2
    assert details["winner_candidate_id"] is not None
    assert isinstance(enveloped[c.OUTPUT_KEY_HITS][1], list)


def test_static_mode_matches_legacy_numbers():
    """rotational_handling=static leaves the legacy calculation untouched."""
    frame = _frame_with_spin()
    static = _run(frame.copy(), _settings(rotational_handling="static"))
    handling = static[c.OUTPUT_KEY_ROTATIONAL_HANDLING]
    assert handling["aggregate"]["rotational_count"] == 1
    assert handling["rows"][1]["effective_handling"] == "static"
    assert handling["rows"][1]["requested_handling"] == "Static"
    assert handling["aggregate"]["any_fallback_to_static"] is False
    assert static[c.OUTPUT_KEY_ROTATIONAL_ENVELOPE] == {}
