"""Per-tube partial dose maps and summaries (CF workflow Phase 4). Synthetic data only."""

from __future__ import annotations

import numpy as np
import pytest
from calculate_dose_recursion_helpers import generate_synthetic_normalized_events

from guiskindose import constants as c
from guiskindose import load_settings_example_json
from guiskindose.calculate_dose.calculate_dose import calculate_dose
from guiskindose.calculate_dose.tube_dose import add_event_dose, init_tube_outputs, summarize_tubes
from guiskindose.phantom_class import Phantom
from guiskindose.settings import PyskindoseSettings

_PLANES = {"A": "Plane A", "B": "Plane B", "single": "Single Plane", "unknown": "not a plane"}


def _settings(**km) -> PyskindoseSettings:
    base = load_settings_example_json()
    base["mode"] = "calculate_dose"
    base["silence_pydicom_warnings"] = True
    base["phantom"]["model"] = "plane"
    base["plot"]["notebook_mode"] = False
    base["plot"]["plot_dosemap"] = False
    base["kerma_meter_correction"].update(km)
    return PyskindoseSettings(settings=base)


def _frame(tubes: list[str]):
    frame = generate_synthetic_normalized_events(len(tubes))
    frame["acquisition_plane"] = [_PLANES[t] for t in tubes]
    # The code-backed canonical identity wins over the meaning text.
    frame["acquisition_plane_canonical"] = tubes
    return frame


def _run(frame, settings):
    dim = settings.phantom.dimension
    table = Phantom(phantom_model=c.PHANTOM_MODEL_TABLE, phantom_dim=dim)
    pad = Phantom(phantom_model=c.PHANTOM_MODEL_PAD, phantom_dim=dim)
    _, output, _ = calculate_dose(normalized_data=frame, settings=settings, table=table, pad=pad)
    assert output is not None
    return output


def _by_tube(output) -> dict:
    return {row["tube"]: row for row in output[c.OUTPUT_KEY_TUBE_SUMMARY]}


def test_biplane_partial_maps_sum_to_combined_map():
    out = _run(_frame(["A", "B", "A", "B"]), _settings())
    maps = out[c.OUTPUT_KEY_TUBE_DOSE_MAPS]
    assert set(maps) == {"A", "B"}
    assert np.allclose(maps["A"] + maps["B"], out[c.OUTPUT_KEY_DOSE_MAP])
    assert out[c.OUTPUT_KEY_TUBE_IDENTITY] == ["A", "B", "A", "B"]


def test_per_tube_kerma_sums_to_totals_and_headline_psd_is_combined_peak():
    out = _run(_frame(["A", "B", "A", "B"]), _settings(enable=True, explicit_label="unit", default_factor=1.0))
    rows = _by_tube(out)
    assert sum(r["kerma_reported"] for r in rows.values()) == pytest.approx(sum(out[c.OUTPUT_KEY_KERMA]))
    assert sum(r["kerma_corrected"] for r in rows.values()) == pytest.approx(sum(out[c.OUTPUT_KEY_KERMA_CORRECTED]))
    assert sum(r["events"] for r in rows.values()) == 4
    combined_peak = float(out[c.OUTPUT_KEY_DOSE_MAP].max())
    assert max(r["peak_dose"] for r in rows.values()) <= combined_peak + 1e-12
    assert combined_peak > 0


def test_applied_cf_is_per_tube_and_kerma_weighted():
    out = _run(
        _frame(["A", "B", "A"]),
        _settings(enable=True, explicit_label="unit", in_memory_table={("unit", "A"): 1.5, ("unit", "B"): 2.0}),
    )
    rows = _by_tube(out)
    assert rows["A"]["applied_cf"] == pytest.approx(1.5)
    assert rows["B"]["applied_cf"] == pytest.approx(2.0)
    assert rows["A"]["kerma_corrected"] == pytest.approx(1.5 * rows["A"]["kerma_reported"])


def test_unknown_tube_gets_its_own_partial_map():
    out = _run(_frame(["A", "unknown"]), _settings())
    assert set(out[c.OUTPUT_KEY_TUBE_DOSE_MAPS]) == {"A", "unknown"}
    assert [r["tube"] for r in out[c.OUTPUT_KEY_TUBE_SUMMARY]] == ["A", "unknown"]


def test_single_plane_allocates_no_partial_map_and_matches_combined_peak():
    out = _run(_frame(["single", "single"]), _settings())
    assert out[c.OUTPUT_KEY_TUBE_DOSE_MAPS] == {}
    (row,) = out[c.OUTPUT_KEY_TUBE_SUMMARY]
    assert row["tube"] == "single"
    assert row["peak_dose"] == pytest.approx(float(out[c.OUTPUT_KEY_DOSE_MAP].max()))
    assert row["applied_cf"] == pytest.approx(1.0)


def test_rotational_envelope_event_feeds_its_tube_map():
    frame = _frame(["A", "B"])
    frame.at[1, "acquisition_type"] = "Rotational Acquisition"
    frame.at[1, "acquisition_type_code"] = "113613"
    frame.at[1, "acquisition_type_coding_scheme"] = "DCM"
    frame.at[1, "acquisition_type_meaning"] = "Rotational Acquisition"
    frame.at[1, "Ap1_end"] = float(frame["Ap1"].to_numpy()[1]) + 60.0
    frame.at[1, "Ap2_end"] = float(frame["Ap2"].to_numpy()[1])
    out = _run(frame, _settings())
    maps = out[c.OUTPUT_KEY_TUBE_DOSE_MAPS]
    assert np.allclose(maps["A"] + maps["B"], out[c.OUTPUT_KEY_DOSE_MAP])
    assert float(maps["B"].max()) > 0


def test_tube_that_misses_the_phantom_reports_zero_peak():
    output = {
        c.OUTPUT_KEY_DOSE_MAP: np.zeros(4),
        c.OUTPUT_KEY_KERMA: [1.0, 2.0],
        c.OUTPUT_KEY_KERMA_CORRECTED: [1.0, 2.0],
        c.OUTPUT_KEY_CORRECTION_KERMA_METER: [1.0, 1.0],
    }
    init_tube_outputs(output, ["A", "B"], 4)
    add_event_dose(output, 0, np.array([0.0, 3.0, 1.0, 0.0]))  # tube A hits
    add_event_dose(output, 1, np.zeros(4))  # tube B misses
    rows = {r["tube"]: r for r in summarize_tubes(output)}
    assert rows["B"]["peak_dose"] == 0.0
    assert rows["A"]["peak_dose"] == 3.0
    assert rows["B"]["kerma_reported"] == 2.0  # kerma is still reported


def test_summary_carries_no_equipment_labels():
    out = _run(_frame(["A", "B"]), _settings(enable=True, explicit_label="Secret-Room-7"))
    assert "secret-room-7" not in repr(out[c.OUTPUT_KEY_TUBE_SUMMARY]).lower()
    assert "secret-room-7" not in repr(out[c.OUTPUT_KEY_TUBE_IDENTITY]).lower()


def test_report_table_and_gui_text_hide_lone_single_tube_and_note_non_additive_peaks():
    from guiskindose.export.sections import TUBE_NOTE, has_tube_content, tube_summary_table
    from guiskindose.gui.summary_formatters import format_tube_summary

    out = _run(_frame(["A", "B"]), _settings())
    summary = out[c.OUTPUT_KEY_TUBE_SUMMARY]
    assert has_tube_content(summary)
    table = tube_summary_table(summary)
    assert [row[0] for row in table[1:]] == ["Plane A", "Plane B"]
    text = format_tube_summary([("Exam 1", summary)])
    assert "Exam 1: Plane A" in text
    assert TUBE_NOTE in text
    single = _run(_frame(["single"]), _settings())[c.OUTPUT_KEY_TUBE_SUMMARY]
    assert not has_tube_content(single)
    assert format_tube_summary([(None, single)]) == ""
