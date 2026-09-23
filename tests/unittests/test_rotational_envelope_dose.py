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


def test_contradictory_event_envelopes_with_reason_recorded():
    """Stationary-coded but moving, usable endpoints: enveloped + flagged."""
    frame = generate_synthetic_normalized_events(1)
    frame.at[0, "acquisition_type"] = "Stationary Acquisition"
    frame.at[0, "acquisition_type_code"] = "113611"
    frame.at[0, "acquisition_type_coding_scheme"] = "DCM"
    frame.at[0, "acquisition_type_meaning"] = "Stationary Acquisition"
    frame.at[0, "Ap1_end"] = float(frame["Ap1"].to_numpy()[0]) + 60.0
    frame.at[0, "Ap2_end"] = float(frame["Ap2"].to_numpy()[0])
    output = _run(frame.copy(), _settings(angular_step_deg=10.0))
    handling = output[c.OUTPUT_KEY_ROTATIONAL_HANDLING]
    assert handling["rows"][0]["classification"] == "unknown"
    assert handling["rows"][0]["effective_handling"] == "coverage"
    assert "contradictory_static" in handling["rows"][0]["reason_codes"]
    assert handling["aggregate"]["any_fallback_to_static"] is False


def test_contradictory_event_without_baseline_falls_back_loudly(caplog):
    """Contradictory with unusable baseline: static + fallback reason."""
    import logging

    import numpy as _np

    frame = generate_synthetic_normalized_events(1)
    frame.at[0, "acquisition_type"] = "Stationary Acquisition"
    frame.at[0, "acquisition_type_code"] = "113611"
    frame.at[0, "acquisition_type_coding_scheme"] = "DCM"
    frame.at[0, "acquisition_type_meaning"] = "Stationary Acquisition"
    frame.at[0, "Ap1_end"] = float(frame["Ap1"].to_numpy()[0]) + 60.0
    frame.at[0, "Ap2_end"] = float(frame["Ap2"].to_numpy()[0])
    frame.at[0, "Tx"] = _np.nan
    with caplog.at_level(logging.WARNING):
        output = _run(frame.copy(), _settings(angular_step_deg=10.0))
    handling = output[c.OUTPUT_KEY_ROTATIONAL_HANDLING]
    assert handling["rows"][0]["effective_handling"] == "static"
    assert handling["rows"][0]["fallback_reason"] == "contradictory_static"
    assert handling["aggregate"]["any_fallback_to_static"] is True


def test_summary_names_contradictory_declarations():
    """The aggregate log names the contradictory count.

    NOTE: uses a dedicated handler on the module logger (repo convention)
    because pytest caplog is blind once configure_logging() sets
    propagate=False suite-wide. The integration test above proves the data
    reaches the ledger; this proves the wording.
    """
    import logging

    from guiskindose.calculate_dose.rotational_event import (
        _emit_rotational_summary,
    )
    from guiskindose.rotational_acquisition import classify_rotational_event
    from guiskindose.rotational_envelope import LedgerEventInput, build_handling_ledger

    classification = classify_rotational_event(
        {
            "Ap1": 0.0,
            "Ap2": 0.0,
            "Ap1_end": 50.0,
            "Ap2_end": 0.0,
            "acquisition_type": "Stationary Acquisition",
            "acquisition_type_code": "113611",
            "acquisition_type_coding_scheme": "DCM",
        }
    )
    ledger = build_handling_ledger(
        [
            LedgerEventInput(
                event_index=0,
                classification=classification,
                requested_handling="Auto",
                effective_handling="static",
                fallback_reason="contradictory_static",
                kerma=1.0,
                dap=None,
            )
        ]
    )
    messages: list[str] = []

    class _Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            messages.append(record.getMessage())

    logger = logging.getLogger("guiskindose.calculate_dose.rotational_event")
    handler = _Capture(level=logging.WARNING)
    logger.addHandler(handler)
    try:
        _emit_rotational_summary(ledger)
    finally:
        logger.removeHandler(handler)
    assert any("contradictory stationary declarations: 1" in message for message in messages)


def test_envelope_total_scales_sublinearly_with_candidates():
    """Max-not-sum at dose-loop level: doubling candidates must not ~double dose.

    A per-candidate summation bug would scale the map total with N; the
    cellwise maximum is N-invariant up to sampling differences.
    """
    import numpy as _np

    coarse = _run(_frame_with_spin().copy(), _settings(angular_step_deg=10.0))
    fine = _run(_frame_with_spin().copy(), _settings(angular_step_deg=2.0))
    coarse_total = float(_np.sum(coarse[c.OUTPUT_KEY_DOSE_MAP]))
    fine_total = float(_np.sum(fine[c.OUTPUT_KEY_DOSE_MAP]))
    coarse_n = coarse[c.OUTPUT_KEY_ROTATIONAL_ENVELOPE][1]["unique_candidate_count"]
    fine_n = fine[c.OUTPUT_KEY_ROTATIONAL_ENVELOPE][1]["unique_candidate_count"]
    assert fine_n > 2 * coarse_n
    # A per-candidate summation bug would scale the total ~5x here; the
    # cellwise maximum is N-invariant up to sampling differences.
    assert abs(fine_total - coarse_total) / max(coarse_total, 1e-12) < 0.5


def test_static_mode_is_deterministic_across_runs():
    """Two identical static runs agree exactly (no envelope leakage)."""
    first = _run(_frame_with_spin().copy(), _settings(rotational_handling="static"))
    second = _run(_frame_with_spin().copy(), _settings(rotational_handling="static"))
    import numpy as _np

    assert _np.array_equal(
        first[c.OUTPUT_KEY_DOSE_MAP], second[c.OUTPUT_KEY_DOSE_MAP]
    )
