"""Tests for the multi-exam pipeline (ExamResult, MultiExamResult, analyze_multiple_exams)."""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "tabular_inputs"


# ── helpers ──────────────────────────────────────────────────────────────


def _make_settings(phantom_model: str = "cylinder"):
    from mypyskindose import load_settings_example_json
    from mypyskindose.settings import PyskindoseSettings

    base = load_settings_example_json()
    base["mode"] = "calculate_dose"
    base["silence_pydicom_warnings"] = True
    base["phantom"]["model"] = phantom_model
    base["plot"]["notebook_mode"] = False
    base["plot"]["plot_dosemap"] = False
    return PyskindoseSettings(settings=base)


def _make_exam_result(dose_map: np.ndarray):
    from mypyskindose.format_export_data import ExamResult

    mock_output = MagicMock()
    mock_output.to_dict.return_value = {"psd": 1.0, "dose_map": dose_map.tolist()}

    return ExamResult(
        exam_id="exam_A",
        source_file="test.csv",
        event_count=5,
        patient_offset=[0.0, 0.0, 0.0],
        settings_snapshot={"mode": "calculate_dose"},
        output=mock_output,
        warnings=[],
    )


# ── ExamResult / MultiExamResult serialization ───────────────────────────


class TestExamResultSerialization:
    def test_exam_result_fields(self):

        dose_map = np.array([0.1, 0.2, 0.3])
        er = _make_exam_result(dose_map)
        assert er.exam_id == "exam_A"
        assert er.source_file == "test.csv"
        assert er.event_count == 5
        assert er.patient_offset == [0.0, 0.0, 0.0]


class TestMultiExamResultSerialization:
    def _make_multi(self):
        from mypyskindose.format_export_data import MultiExamResult

        dm1 = np.array([0.5, 1.0, 0.0])
        dm2 = np.array([0.3, 0.2, 0.5])
        agg = dm1 + dm2
        return MultiExamResult(
            exams=[_make_exam_result(dm1), _make_exam_result(dm2)],
            aggregate_dose_map=agg,
            aggregate_psd=float(agg.max()),
            total_events=10,
            warnings=[],
        )

    def test_to_dict_structure(self):
        mr = self._make_multi()
        d = mr.to_dict()
        assert d["schema_version"] == 2
        assert "exams" in d
        assert len(d["exams"]) == 2
        assert "aggregate_dose_map" in d
        assert "aggregate_psd" in d
        assert "total_events" in d
        assert d["total_events"] == 10
        assert "source_file" not in d["exams"][0]

    def test_identified_serialization_requires_explicit_opt_in(self):
        mr = self._make_multi()
        default_json = mr.to_json()
        identified = mr.to_dict(include_source_identifiers=True)

        assert "test.csv" not in default_json
        assert identified["exams"][0]["source_file"] == "test.csv"

    def test_aggregate_psd_is_max_of_aggregate_map(self):
        mr = self._make_multi()
        assert mr.aggregate_psd == pytest.approx(float(mr.aggregate_dose_map.max()))

    def test_to_json_round_trips(self):
        mr = self._make_multi()
        parsed = json.loads(mr.to_json())
        assert parsed["total_events"] == 10
        assert len(parsed["exams"]) == 2
        assert len(parsed["aggregate_dose_map"]) == 3

    def test_aggregate_dose_map_is_sum_of_per_exam_maps(self):
        from mypyskindose.format_export_data import MultiExamResult

        dm1 = np.array([1.0, 2.0])
        dm2 = np.array([3.0, 4.0])
        mr = MultiExamResult(
            exams=[_make_exam_result(dm1), _make_exam_result(dm2)],
            aggregate_dose_map=dm1 + dm2,
            aggregate_psd=float((dm1 + dm2).max()),
            total_events=2,
            warnings=[],
        )
        expected = dm1 + dm2
        np.testing.assert_array_equal(mr.aggregate_dose_map, expected)


# ── multi-study split via registry ───────────────────────────────────────


class TestMultiStudySplitViaRegistry:
    def test_single_study_returns_single_result(self):
        from mypyskindose.input_adapters.registry import read_and_normalize_input

        result = read_and_normalize_input(_FIXTURES / "normalized_events.csv")
        assert not isinstance(result, list)
        assert len(result.normalized_data) == 2

    def test_multi_study_returns_list(self):
        from mypyskindose.input_adapters.registry import read_and_normalize_input

        result = read_and_normalize_input(_FIXTURES / "normalized_events_multistudy.csv")
        assert isinstance(result, list)
        assert len(result) == 2

    def test_multi_study_study_ids_set(self):
        from mypyskindose.input_adapters.registry import read_and_normalize_input

        results = read_and_normalize_input(_FIXTURES / "normalized_events_multistudy.csv")
        assert isinstance(results, list)
        ids = {r.study_id for r in results}
        assert ids == {"A001", "A002"}

    def test_multi_study_each_group_has_correct_event_count(self):
        from mypyskindose.input_adapters.registry import read_and_normalize_input

        results = read_and_normalize_input(_FIXTURES / "normalized_events_multistudy.csv")
        assert isinstance(results, list)
        for r in results:
            assert len(r.normalized_data) == 1

    def test_multi_study_provenance_preserved(self):
        from mypyskindose.input_adapters.registry import read_and_normalize_input

        results = read_and_normalize_input(_FIXTURES / "normalized_events_multistudy.csv")
        assert isinstance(results, list)
        for r in results:
            assert r.provenance.schema_name == "normalized"
            assert r.provenance.original_filename == "normalized_events_multistudy.csv"

    def test_multi_study_normalized_data_has_no_study_id_column(self):
        from mypyskindose.input_adapters.registry import read_and_normalize_input

        results = read_and_normalize_input(_FIXTURES / "normalized_events_multistudy.csv")
        assert isinstance(results, list)
        for r in results:
            assert "study_id" not in r.normalized_data.columns
            assert "__study_id__" not in r.normalized_data.columns


# ── analyze_multiple_exams integration ───────────────────────────────────


@pytest.fixture(autouse=True)
def _quiet_logs():
    logging.getLogger("mypyskindose").setLevel(logging.WARNING)
    yield


@pytest.fixture()
def _suppress_plots():
    # Patch on the module object, not via the "mypyskindose.analyze_data.<attr>" string.
    # The package exports a function named `analyze_data` (from .analyze_data import
    # analyze_data), which shadows the submodule of the same name on the package; whether
    # mock's string traversal resolves to the module or the function depends on import
    # order and Python version. importlib.import_module always returns the module object.
    import importlib

    analyze_data_module = importlib.import_module("mypyskindose.analyze_data")
    with (
        patch.object(analyze_data_module, "create_geometry_plot"),
        patch.object(analyze_data_module, "create_dose_map_plot"),
    ):
        yield


class TestAnalyzeMultipleExams:
    """Integration tests using real RDSR data with plot side-effects suppressed."""

    def _rdsr_exam(self, settings):
        """Load the example RDSR and wrap it in InputAdapterResult."""
        from mypyskindose import get_path_to_example_rdsr_files
        from mypyskindose.helpers.read_and_normalize_rdsr_data import read_and_normalise_rdsr_data
        from mypyskindose.input_adapters.models import InputAdapterResult, InputProvenance

        rdsr = get_path_to_example_rdsr_files() / "siemens_axiom_artis.dcm"
        data_norm = read_and_normalise_rdsr_data(rdsr_filepath=str(rdsr), settings=settings)
        prov = InputProvenance(
            source_type="dcm",
            schema_name="rdsr",
            original_filename=rdsr.name,
            header_row_index=0,
            detected_encoding="n/a",
            detected_delimiter=None,
            sheet_name=None,
            column_map={},
            unit_conversions={},
            warnings=[],
        )
        return InputAdapterResult(normalized_data=data_norm, raw_data=None, provenance=prov, warnings=[])

    @pytest.mark.usefixtures("_suppress_plots")
    def test_two_exams_return_multi_exam_result(self):
        from mypyskindose.analyze_data import analyze_multiple_exams
        from mypyskindose.format_export_data import MultiExamResult

        settings = _make_settings()
        exam = self._rdsr_exam(settings)
        result = analyze_multiple_exams([exam, exam], settings)

        assert isinstance(result, MultiExamResult)
        assert len(result.exams) == 2
        assert result.total_events == 2 * len(exam.normalized_data)

    @pytest.mark.usefixtures("_suppress_plots")
    def test_aggregate_dose_map_equals_sum_of_per_exam_maps(self):
        from mypyskindose.analyze_data import analyze_multiple_exams

        settings = _make_settings()
        exam = self._rdsr_exam(settings)
        result = analyze_multiple_exams([exam, exam], settings)

        assert len(result.exams) == 2
        dm1 = result.exams[0].output.dose_map
        dm2 = result.exams[1].output.dose_map
        np.testing.assert_array_almost_equal(result.aggregate_dose_map, dm1 + dm2)

    @pytest.mark.usefixtures("_suppress_plots")
    def test_aggregate_psd_is_max_of_aggregate_map(self):
        from mypyskindose.analyze_data import analyze_multiple_exams

        settings = _make_settings()
        exam = self._rdsr_exam(settings)
        result = analyze_multiple_exams([exam, exam], settings)

        assert result.aggregate_psd == pytest.approx(float(result.aggregate_dose_map.max()))

    @pytest.mark.usefixtures("_suppress_plots")
    def test_per_exam_offsets_are_independent(self):
        """Two exams with different offsets must produce different dose maps."""
        from mypyskindose.analyze_data import analyze_multiple_exams

        settings = _make_settings()
        exam = self._rdsr_exam(settings)
        offsets = [[0.0, 0.0, 0.0], [0.0, 0.0, -35.0]]
        result = analyze_multiple_exams([exam, exam], settings, per_exam_offsets=offsets)

        assert len(result.exams) == 2
        assert result.exams[0].patient_offset == [0.0, 0.0, 0.0]
        assert result.exams[1].patient_offset == [0.0, 0.0, -35.0]
        dm1 = result.exams[0].output.dose_map
        dm2 = result.exams[1].output.dose_map
        # Different offsets → different dose distributions (not identical arrays)
        assert not np.array_equal(dm1, dm2)

    @pytest.mark.usefixtures("_suppress_plots")
    def test_exam_result_carries_source_file(self):
        from mypyskindose.analyze_data import analyze_multiple_exams

        settings = _make_settings()
        exam = self._rdsr_exam(settings)
        result = analyze_multiple_exams([exam], settings)

        assert result.exams[0].source_file == "siemens_axiom_artis.dcm"

    @pytest.mark.usefixtures("_suppress_plots")
    def test_partial_failure_returns_succeeded_exams(self):
        """A bad exam (empty DataFrame) should not prevent other exams from completing."""
        from mypyskindose.analyze_data import analyze_multiple_exams
        from mypyskindose.input_adapters.models import InputAdapterResult, InputProvenance

        settings = _make_settings()
        good_exam = self._rdsr_exam(settings)

        import pandas as pd

        bad_prov = InputProvenance(
            source_type="csv", schema_name="normalized", original_filename="bad.csv",
            header_row_index=0, detected_encoding="utf-8", detected_delimiter=",",
            sheet_name=None, column_map={}, unit_conversions={}, warnings=[],
        )
        bad_exam = InputAdapterResult(
            normalized_data=pd.DataFrame(), raw_data=None, provenance=bad_prov, warnings=[]
        )

        result = analyze_multiple_exams([good_exam, bad_exam], settings)

        assert len(result.exams) == 1, "only the good exam should succeed"
        assert result.exams_excluded >= 1
        assert len(result.warnings) >= 1, "failure should be recorded in warnings"
        assert any("excluded from the aggregate peak skin dose" in w for w in result.warnings)

    @pytest.mark.usefixtures("_suppress_plots")
    def test_to_dict_and_to_json_roundtrip(self):
        from mypyskindose.analyze_data import analyze_multiple_exams

        settings = _make_settings()
        exam = self._rdsr_exam(settings)
        result = analyze_multiple_exams([exam], settings)

        d = result.to_dict()
        assert "exams" in d
        assert len(d["aggregate_dose_map"]) > 0

        parsed = json.loads(result.to_json())
        assert parsed["total_events"] == d["total_events"]



# ── End-to-end multi-file / multi-study integration ──────────────────────


class TestMultiExamIntegration:
    """End-to-end runs through the public main.py entry points with real example
    data and plot side-effects suppressed."""

    @pytest.mark.usefixtures("_suppress_plots")
    def test_two_rdsr_files_via_analyze_multiple_input_files(self):
        from mypyskindose import get_path_to_example_rdsr_files
        from mypyskindose.format_export_data import MultiExamResult
        from mypyskindose.main import analyze_multiple_input_files

        rdsr = get_path_to_example_rdsr_files()
        files = [
            rdsr / "siemens_axiom_artis.dcm",
            rdsr / "philips_allura_clarity_u104.dcm",
        ]
        result = analyze_multiple_input_files(files, settings=_make_settings())

        assert isinstance(result, MultiExamResult)
        assert len(result.exams) == 2
        assert {e.source_file for e in result.exams} == {
            "siemens_axiom_artis.dcm",
            "philips_allura_clarity_u104.dcm",
        }
        assert result.aggregate_psd > 0
        # Aggregate is the element-wise sum across exams.
        summed = sum(np.asarray(e.output.dose_map) for e in result.exams)
        assert np.allclose(result.aggregate_dose_map, summed)
        assert result.aggregate_psd == pytest.approx(float(np.max(summed)))

    @pytest.mark.usefixtures("_suppress_plots")
    def test_mixed_format_dicom_plus_csv(self):
        from mypyskindose import get_path_to_example_rdsr_files
        from mypyskindose.format_export_data import MultiExamResult
        from mypyskindose.main import analyze_multiple_input_files

        rdsr = get_path_to_example_rdsr_files()
        files = [
            rdsr / "siemens_axiom_artis.dcm",
            _FIXTURES / "normalized_events.csv",
        ]
        result = analyze_multiple_input_files(
            files, settings=_make_settings(), input_schema="normalized"
        )

        assert isinstance(result, MultiExamResult)
        assert len(result.exams) == 2
        sources = {e.source_file for e in result.exams}
        assert "siemens_axiom_artis.dcm" in sources
        assert "normalized_events.csv" in sources
        assert result.aggregate_psd > 0

    @pytest.mark.usefixtures("_suppress_plots")
    def test_multistudy_csv_via_analyze_input_file(self):
        from mypyskindose.format_export_data import MultiExamResult
        from mypyskindose.main import analyze_input_file

        result = analyze_input_file(
            _FIXTURES / "normalized_events_multistudy.csv",
            settings=_make_settings(),
            input_schema="normalized",
        )

        assert isinstance(result, MultiExamResult)
        # The fixture spans more than one study → auto-split into multiple exams.
        assert len(result.exams) >= 2
        assert result.total_events == sum(e.event_count for e in result.exams)
        assert result.aggregate_psd > 0
