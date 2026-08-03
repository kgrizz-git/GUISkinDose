"""Regression: below-floor kVp policy ``skip`` must keep export event lengths aligned.

``calculate_dose`` drops below-floor rows under policy ``skip``. Export packaging must
use that post-policy frame so event-array lengths stay aligned with dose-loop output.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd

from calculate_dose_recursion_helpers import generate_synthetic_normalized_events
from mypyskindose import constants as c
from mypyskindose import load_settings_example_json
from mypyskindose.analyze_data import analyze_data, analyze_multiple_exams
from mypyskindose.calculate_dose.calculate_dose import _build_output_template, calculate_dose
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
    return patient, output, filtered


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
    # Allowlisted synthetic label — digit-bearing study label assignments trip
    # scripts/check_sensitive_content.py CONTEXTUAL_PATIENT_IDENTIFIER.
    exam = InputAdapterResult(_two_event_frame(), None, provenance, study_id="test")
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


def test_calculate_dose_returns_post_skip_event_frame() -> None:
    """Real calculate_dose must return the post-policy frame as the third value."""
    settings = _settings_skip()
    norm = generate_synthetic_normalized_events(2, seed=7)
    norm.loc[1, "kVp"] = 10.0
    table = Phantom(phantom_model=c.PHANTOM_MODEL_TABLE, phantom_dim=settings.phantom.dimension)
    pad = Phantom(phantom_model=c.PHANTOM_MODEL_PAD, phantom_dim=settings.phantom.dimension)

    _, output, effective = calculate_dose(normalized_data=norm, settings=settings, table=table, pad=pad)

    assert output is not None
    assert isinstance(effective, pd.DataFrame)
    assert len(effective) == 1
    assert len(output[c.OUTPUT_KEY_HITS]) == 1
    assert "_effective_data_norm" not in output


def test_all_events_skipped_dict_export_succeeds() -> None:
    """Skip-all must export zero events instead of crashing in EventOutput."""
    frame = _two_event_frame()
    frame["kVp"] = [10.0, 10.0]
    settings = _settings_skip()

    with (
        patch("mypyskindose.analyze_data.create_geometry_plot"),
        patch("mypyskindose.analyze_data.create_dose_map_plot"),
    ):
        result = analyze_data(frame, settings)

    assert isinstance(result, dict)
    assert result["psd"] == 0.0
    assert result["events"]["number_of_events"] == 0
    assert result["air_kerma"] == 0.0


def test_multi_exam_failure_warning_is_explicit_about_exclusion() -> None:
    """Failed exams must produce clear exclusion warnings for users and exports."""
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
    good = InputAdapterResult(_two_event_frame(), None, provenance, study_id="test")
    bad = InputAdapterResult(_two_event_frame(), None, provenance, study_id="test")

    def _sometimes_fail(normalized_data, settings, table, pad, exam_id=None):
        if exam_id == "Exam 2":
            raise ValueError("Hits length mismatch")
        return _fake_calculate_dose(normalized_data, settings, table, pad, exam_id=exam_id)

    with (
        patch("mypyskindose.analyze_data.calculate_dose", side_effect=_sometimes_fail),
        patch("mypyskindose.analyze_data.create_geometry_plot"),
        patch("mypyskindose.analyze_data.create_dose_map_plot"),
        patch(
            "mypyskindose.analyze_data.calculate_rotation_matrices",
            side_effect=lambda frame: frame,
        ),
        patch(
            "mypyskindose.analyze_data._multi_exam_output",
            side_effect=lambda patient, table, pad, raw_output, settings, data_norm: MagicMock(
                DoseMap=raw_output[c.OUTPUT_KEY_DOSE_MAP]
            ),
        ),
    ):
        multi = analyze_multiple_exams([good, bad], _settings_skip())

    assert len(multi.exams) == 1
    assert multi.exams_attempted == 2
    assert multi.exams_excluded == 1
    assert any("1 of 2 exam(s) were excluded" in warning for warning in multi.warnings)
    assert any(
        warning.startswith("Exam 2:") and "excluded from the aggregate peak skin dose" in warning
        for warning in multi.warnings
    )
    assert any("ValueError" in warning for warning in multi.warnings)


def test_multi_exam_exclusion_preserves_import_warnings() -> None:
    """Excluded exams must keep import / per-exam warnings on the run list."""
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
    good = InputAdapterResult(
        _two_event_frame(),
        None,
        provenance,
        study_id="test",
        warnings=["good import note"],
    )
    bad = InputAdapterResult(
        _two_event_frame(),
        None,
        provenance,
        study_id="test",
        warnings=["bad import note"],
    )

    def _fail_second(normalized_data, settings, table, pad, exam_id=None):
        if exam_id == "Exam 2":
            raise ValueError("Hits length mismatch")
        return _fake_calculate_dose(normalized_data, settings, table, pad, exam_id=exam_id)

    with (
        patch("mypyskindose.analyze_data.calculate_dose", side_effect=_fail_second),
        patch("mypyskindose.analyze_data.create_geometry_plot"),
        patch("mypyskindose.analyze_data.create_dose_map_plot"),
        patch(
            "mypyskindose.analyze_data.calculate_rotation_matrices",
            side_effect=lambda frame: frame,
        ),
        patch(
            "mypyskindose.analyze_data._multi_exam_output",
            side_effect=lambda patient, table, pad, raw_output, settings, data_norm: MagicMock(
                DoseMap=raw_output[c.OUTPUT_KEY_DOSE_MAP]
            ),
        ),
    ):
        multi = analyze_multiple_exams(
            [good, bad],
            _settings_skip(),
            per_exam_extra_warnings=[[], ["extra offset note"]],
        )

    assert multi.exams_excluded == 1
    assert "bad import note" in multi.warnings
    assert "extra offset note" in multi.warnings
    assert any(
        warning.startswith("Exam 2:") and "excluded from the aggregate peak skin dose" in warning
        for warning in multi.warnings
    )
    # Successful exam warnings stay on ExamResult, not the run list.
    assert "good import note" not in multi.warnings
    assert "good import note" in multi.exams[0].warnings


def test_multi_exam_no_output_preserves_import_warnings() -> None:
    """No-output exclusions must keep import warnings and use the no-output message."""
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
    exam = InputAdapterResult(
        _two_event_frame(),
        None,
        provenance,
        study_id="test",
        warnings=["no-output import note"],
    )

    with (
        patch(
            "mypyskindose.analyze_data.calculate_dose",
            return_value=(None, None, None),
        ),
        patch("mypyskindose.analyze_data.create_geometry_plot"),
        patch("mypyskindose.analyze_data.create_dose_map_plot"),
        patch(
            "mypyskindose.analyze_data.calculate_rotation_matrices",
            side_effect=lambda frame: frame,
        ),
    ):
        multi = analyze_multiple_exams([exam], _settings_skip())

    assert multi.exams == []
    assert multi.exams_excluded == 1
    assert "no-output import note" in multi.warnings
    assert any(
        warning.startswith("Exam 1:") and "produced no dose output" in warning
        for warning in multi.warnings
    )
