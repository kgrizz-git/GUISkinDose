"""Regression: below-floor kVp policy ``skip`` must keep export event lengths aligned.

``calculate_dose`` drops below-floor rows under policy ``skip``, but export used to
pass the pre-skip ``data_norm`` into ``PySkinDoseOutput``. That raised ``ValueError``
on single-exam dict/JSON export (GUI path) and silently dropped multi-exam results.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from mypyskindose import constants as c
from mypyskindose import load_settings_example_json
from mypyskindose.analyze_data import analyze_data, analyze_multiple_exams
from mypyskindose.calculate_dose.calculate_dose import _build_output_template
from mypyskindose.geom_calc import apply_below_floor_kvp_policy
from mypyskindose.input_adapters.models import InputAdapterResult, InputProvenance
from mypyskindose.phantom_class import Phantom
from mypyskindose.settings import PyskindoseSettings


def _settings_skip() -> PyskindoseSettings:
    """Build dict-output calculate_dose settings with skip policy."""
    settings = PyskindoseSettings(
        settings=load_settings_example_json(),
        output_format=c.RUN_ARGUMENTS_OUTPUT_DICT,
    )
    settings.mode = c.MODE_CALCULATE_DOSE
    settings.phantom.model = "plane"
    settings.below_floor_kvp_policy = c.BELOW_FLOOR_KVP_POLICY_SKIP
    settings.plot.notebook_mode = False
    settings.plot.plot_dosemap = False
    return settings


def _two_event_frame() -> pd.DataFrame:
    """Two-event frame: one in-floor kVp and one below the HVL floor."""
    return pd.DataFrame(
        {
            "kVp": [70.0, 10.0],
            "K_IRP": [1.0, 1.0],
            "filter_thickness_Cu": [0.0, 0.0],
            "filter_thickness_Al": [0.0, 0.0],
            "Tx": [0.0, 0.0],
            "Ty": [0.0, 0.0],
            "Tz": [0.0, 0.0],
            "FS_lat": [10.0, 10.0],
            "FS_long": [10.0, 10.0],
            "Ap1": [0.0, 0.0],
            "Ap2": [0.0, 0.0],
            "Ap3": [0.0, 0.0],
            "At1": [0.0, 0.0],
            "At2": [0.0, 0.0],
            "At3": [0.0, 0.0],
            "DSD": [120.0, 120.0],
            "DSH": [70.0, 70.0],
            "DSL": [0.0, 0.0],
            "acquisition_plane": ["Single Plane", "Single Plane"],
        }
    )


def _fake_calculate_dose(normalized_data, settings, table, pad, exam_id=None):
    """Mirror calculate_dose length behavior after below-floor policy."""
    filtered = apply_below_floor_kvp_policy(
        data_norm=normalized_data,
        policy=settings.below_floor_kvp_policy,
        manual_kvp=settings.below_floor_kvp_manual,
    )
    patient = Phantom(phantom_model="plane", phantom_dim=settings.phantom.dimension)
    n_events = len(filtered)
    n_cells = len(patient.r)
    output = _build_output_template(total_number_of_events=n_events, dose_map_size=n_cells)
    output[c.OUTPUT_KEY_HITS] = [[False] * n_cells for _ in range(n_events)]
    output[c.OUTPUT_KEY_CORRECTION_BACK_SCATTER] = [np.array([]) for _ in range(n_events)]
    output[c.OUTPUT_KEY_CORRECTION_INVERSE_SQUARE_LAW] = [0.0 for _ in range(n_events)]
    output[c.OUTPUT_KEY_CORRECTION_MEDIUM] = [1.0] * n_events
    output[c.OUTPUT_KEY_CORRECTION_TABLE] = [1.0] * n_events
    output[c.OUTPUT_KEY_CORRECTION_KERMA_METER] = [1.0] * n_events
    output[c.OUTPUT_KEY_KERMA_CORRECTED] = [1.0] * n_events
    output[c.OUTPUT_KEY_EFFECTIVE_DATA_NORM] = filtered
    return patient, output


def test_single_exam_skip_policy_passes_aligned_data_norm_to_export() -> None:
    """Dict export must receive data_norm length matching dose-loop event arrays."""
    captured: dict[str, int] = {}

    def _capture_format(analysis_result, data_norm, patient, table, pad, settings):
        captured["n_data"] = len(data_norm)
        captured["n_hits"] = len(analysis_result[c.OUTPUT_KEY_HITS])
        return {"psd": 0.0, "events": captured["n_data"]}

    with (
        patch("mypyskindose.analyze_data.calculate_dose", side_effect=_fake_calculate_dose),
        patch("mypyskindose.analyze_data.create_geometry_plot"),
        patch("mypyskindose.analyze_data.create_dose_map_plot"),
        patch(
            "mypyskindose.analyze_data.calculate_rotation_matrices",
            side_effect=lambda frame: frame,
        ),
        patch(
            "mypyskindose.analyze_data.format_analysis_result_for_export",
            side_effect=_capture_format,
        ),
    ):
        result = analyze_data(_two_event_frame(), _settings_skip())

    assert result == {"psd": 0.0, "events": 1}
    assert captured["n_data"] == 1
    assert captured["n_hits"] == 1


def test_multi_exam_skip_policy_keeps_exam_with_aligned_lengths() -> None:
    """Multi-exam must keep the exam when skip shortens the dose arrays."""
    provenance = InputProvenance(
        source_type="csv",
        schema_name="normalized",
        original_filename="skip.csv",
        header_row_index=0,
        detected_encoding="utf-8",
        detected_delimiter=",",
        sheet_name=None,
        column_map={},
        unit_conversions={},
    )
    exam = InputAdapterResult(_two_event_frame(), None, provenance, study_id="S1")
    captured: dict[str, int] = {}

    def _capture_multi(patient, table, pad, raw_output, settings, data_norm):
        captured["n_data"] = len(data_norm)
        captured["n_hits"] = len(raw_output[c.OUTPUT_KEY_HITS])
        if captured["n_data"] != captured["n_hits"]:
            raise ValueError(
                "Hits:\n\tThe hits list is not the same length as the number of normalized events"
            )
        out = MagicMock()
        out.DoseMap = raw_output[c.OUTPUT_KEY_DOSE_MAP]
        return out

    with (
        patch("mypyskindose.analyze_data.calculate_dose", side_effect=_fake_calculate_dose),
        patch("mypyskindose.analyze_data.create_geometry_plot"),
        patch("mypyskindose.analyze_data.create_dose_map_plot"),
        patch(
            "mypyskindose.analyze_data.calculate_rotation_matrices",
            side_effect=lambda frame: frame,
        ),
        patch("mypyskindose.analyze_data._multi_exam_output", side_effect=_capture_multi),
    ):
        multi = analyze_multiple_exams([exam], _settings_skip())

    assert captured["n_data"] == 1
    assert captured["n_hits"] == 1
    assert len(multi.exams) == 1
    assert multi.exams[0].event_count == 1
    assert multi.total_events == 1
    assert multi.warnings == []
