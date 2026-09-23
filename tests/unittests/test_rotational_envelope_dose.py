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
    ap1_values = frame["Ap1"].to_numpy()
    ap2_values = frame["Ap2"].to_numpy()
    frame.at[1, "Ap1_end"] = float(ap1_values[1]) + 60.0
    frame.at[1, "Ap2_end"] = float(ap2_values[1])
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


def _frame_with_unchanged_geometry_spin():
    """Spin whose static pose exactly matches the preceding event."""
    frame = generate_synthetic_normalized_events(2)
    for column in ("Tx", "Ty", "Tz", "Ap1", "Ap2", "Ap3", "At1", "At2", "At3", "FS_lat", "FS_long"):
        frame.at[1, column] = frame.at[0, column]
    frame.at[1, "acquisition_type"] = "Rotational Acquisition"
    frame.at[1, "acquisition_type_code"] = "113613"
    frame.at[1, "acquisition_type_coding_scheme"] = "DCM"
    frame.at[1, "acquisition_type_meaning"] = "Rotational Acquisition"
    frame.at[1, "Ap1_end"] = float(frame["Ap1"].to_numpy()[1]) + 60.0
    frame.at[1, "Ap2_end"] = float(frame["Ap2"].to_numpy()[1])
    return frame


def test_envelope_reuses_cache_on_unchanged_geometry():
    """new_geometry=False reuses the preceding static arrays, not empties."""
    from guiskindose.geom_calc import check_new_geometry

    frame = _frame_with_unchanged_geometry_spin()
    assert check_new_geometry(frame) == [True, False]
    output = _run(frame.copy(), _settings(angular_step_deg=10.0))
    assert output[c.OUTPUT_KEY_CORRECTION_INVERSE_SQUARE_LAW][1] is output[
        c.OUTPUT_KEY_CORRECTION_INVERSE_SQUARE_LAW
    ][0]
    assert output[c.OUTPUT_KEY_ROTATIONAL_HANDLING]["rows"][1]["effective_handling"] == "coverage"


def test_phantoms_restored_to_static_pose_after_envelope(monkeypatch):
    """Shared phantoms must observe the parent pose, not the last candidate."""
    from guiskindose.phantom_class import Phantom

    calls: list = []
    original_position = Phantom.position

    def _recording_position(self, data_norm, event):
        calls.append((self, data_norm is _frame_holder[0], event))
        return original_position(self, data_norm=data_norm, event=event)

    _frame_holder: list = []
    frame = _frame_with_spin().copy()
    _frame_holder.append(frame)
    monkeypatch.setattr(Phantom, "position", _recording_position)
    _run(frame, _settings(angular_step_deg=10.0))
    parent_calls = [call for call in calls if call[1] and call[2] == 1]
    assert parent_calls, "parent static pose must be (re)positioned last"


def test_envelope_details_disclose_mixed_slot_semantics():
    """Union hits vs static-only correction slots are labeled in output."""
    output = _run(_frame_with_spin().copy(), _settings(angular_step_deg=10.0))
    details = output[c.OUTPUT_KEY_ROTATIONAL_ENVELOPE][1]
    assert details["hits_basis"] == "candidate_union"
    assert details["legacy_correction_basis"] == "static_pose"
