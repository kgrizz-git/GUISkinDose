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
        assert d["schema_version"] == 1
        assert "exams" in d
        assert len(d["exams"]) == 2
        assert "aggregate_dose_map" in d
        assert "aggregate_psd" in d
        assert "total_events" in d
        assert d["total_events"] == 10

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
    with (
        patch("mypyskindose.analyze_data.create_geometry_plot"),
        patch("mypyskindose.analyze_data.create_dose_map_plot"),
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
        dm1 = result.exams[0].output.DoseMap
        dm2 = result.exams[1].output.DoseMap
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
        dm1 = result.exams[0].output.DoseMap
        dm2 = result.exams[1].output.DoseMap
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
        assert len(result.warnings) >= 1, "failure should be recorded in warnings"

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


# ── GUI per-exam patient offsets (Phase 2.3) ──────────────────────────────


class TestGuiPerExamOffsets:
    """The GUI seeds a per-exam patient offset into each loaded_exam_meta entry
    (defaulting to the global offset) and run_calculation forwards them to
    analyze_multiple_exams. These tests pin the loader/wiring contract without
    needing the NiceGUI runtime."""

    def _fresh_state(self, d_lon=0.0, d_ver=0.0, d_lat=0.0):
        from mypyskindose.gui.state import AppState

        st = AppState()
        st.d_lon, st.d_ver, st.d_lat = d_lon, d_ver, d_lat
        st.input_schema = "auto"
        st.input_source_type = "csv"
        return st

    def test_loader_seeds_offset_defaults_from_global(self):
        from mypyskindose.gui.helpers import load_tabular

        st = self._fresh_state(d_lon=3.0, d_ver=-2.0, d_lat=1.0)
        ok, _ = load_tabular(_FIXTURES / "normalized_events_multistudy.csv", st)
        assert ok
        assert st.is_multi_exam
        assert len(st.loaded_exam_meta) == 2
        for meta in st.loaded_exam_meta:
            assert meta["d_lon"] == 3.0
            assert meta["d_ver"] == -2.0
            assert meta["d_lat"] == 1.0

    def test_run_calculation_forwards_per_exam_offsets(self):
        from unittest.mock import patch

        from mypyskindose.gui.helpers import load_tabular, run_calculation

        st = self._fresh_state()
        ok, _ = load_tabular(_FIXTURES / "normalized_events_multistudy.csv", st)
        assert ok and st.is_multi_exam

        # Give each exam a distinct offset, as the per-exam spinboxes would.
        st.loaded_exam_meta[0]["d_lon"] = 5.0
        st.loaded_exam_meta[1]["d_lat"] = -4.0

        captured = {}

        def _fake_analyze(
            exams, settings, per_exam_offsets=None, per_exam_extra_warnings=None
        ):
            captured["per_exam_offsets"] = per_exam_offsets
            captured["per_exam_extra_warnings"] = per_exam_extra_warnings
            result = MagicMock()
            result.aggregate_psd = 1.0
            result.exams = [MagicMock(output=MagicMock(AirKerma=0.0)) for _ in exams]
            return result

        with patch(
            "mypyskindose.analyze_data.analyze_multiple_exams", side_effect=_fake_analyze
        ):
            ok, _ = run_calculation(st)

        assert ok
        assert captured["per_exam_offsets"] == [[5.0, 0.0, 0.0], [0.0, 0.0, -4.0]]


# ── GUI per-exam coordinate transforms (Phase 2.2) ────────────────────────


class TestGuiPerExamTransforms:
    """Per-exam swap/flip overrides operate on each exam's pristine base copy
    independently. Pins the helpers.py engine contract without the NiceGUI runtime."""

    def _state_with_two_exams(self, schema="radimetrics"):
        import pandas as pd
        from types import SimpleNamespace

        from mypyskindose.gui.state import AppState

        st = AppState()

        def _mk(tx, tz):
            df = pd.DataFrame({"Tx": [tx], "Tz": [tz], "Ap1": [10.0], "Ap2": [5.0]})
            exam = SimpleNamespace(
                normalized_data=df.copy(),
                provenance=SimpleNamespace(schema_name=schema),
                warnings=[],
            )
            meta = {
                "file_path": Path("a.csv"),
                "source_type": "csv",
                "schema": schema,
                "base_data": df.copy(),
                "swap_lat_lon": False,
                "flip_ap1": False,
                "flip_ap2": False,
            }
            return exam, meta

        e0, m0 = _mk(1.0, 2.0)
        e1, m1 = _mk(3.0, 4.0)
        st.loaded_exams = [e0, e1]
        st.loaded_exam_meta = [m0, m1]
        st.is_multi_exam = True
        return st

    def test_swap_applies_to_one_exam_only(self):
        from mypyskindose.gui.helpers import apply_exam_transforms

        st = self._state_with_two_exams()
        st.loaded_exam_meta[0]["swap_lat_lon"] = True
        apply_exam_transforms(st, 0)

        assert st.loaded_exams[0].normalized_data["Tx"].iloc[0] == 2.0
        assert st.loaded_exams[0].normalized_data["Tz"].iloc[0] == 1.0
        # Second exam is untouched.
        assert st.loaded_exams[1].normalized_data["Tx"].iloc[0] == 3.0
        assert st.loaded_exams[1].normalized_data["Tz"].iloc[0] == 4.0

    def test_swap_is_reversible_from_base(self):
        from mypyskindose.gui.helpers import apply_exam_transforms

        st = self._state_with_two_exams()
        st.loaded_exam_meta[0]["swap_lat_lon"] = True
        apply_exam_transforms(st, 0)
        # Toggle back off: re-derives from the pristine base, not the swapped frame.
        st.loaded_exam_meta[0]["swap_lat_lon"] = False
        apply_exam_transforms(st, 0)

        assert st.loaded_exams[0].normalized_data["Tx"].iloc[0] == 1.0
        assert st.loaded_exams[0].normalized_data["Tz"].iloc[0] == 2.0

    def test_flip_ap1_negates_angle(self):
        from mypyskindose.gui.helpers import apply_exam_transforms

        st = self._state_with_two_exams()
        st.loaded_exam_meta[1]["flip_ap1"] = True
        apply_exam_transforms(st, 1)

        assert st.loaded_exams[1].normalized_data["Ap1"].iloc[0] == -10.0
        assert st.loaded_exams[0].normalized_data["Ap1"].iloc[0] == 10.0

    def test_normalized_schema_skips_swap(self):
        from mypyskindose.gui.helpers import apply_exam_transforms

        st = self._state_with_two_exams(schema="normalized")
        st.loaded_exam_meta[0]["swap_lat_lon"] = True
        apply_exam_transforms(st, 0)

        # Swap is a no-op for the already-canonical normalized schema.
        assert st.loaded_exams[0].normalized_data["Tx"].iloc[0] == 1.0
        assert st.loaded_exams[0].normalized_data["Tz"].iloc[0] == 2.0

    def test_rebuilds_concatenated_preview(self):
        from mypyskindose.gui.helpers import apply_exam_transforms

        st = self._state_with_two_exams()
        st.loaded_exam_meta[0]["swap_lat_lon"] = True
        apply_exam_transforms(st, 0)

        assert st.rdsr_df is not None
        assert len(st.rdsr_df) == 2
        assert st.rdsr_df["Tx"].iloc[0] == 2.0  # exam 0 swapped
        assert st.rdsr_df["Tx"].iloc[1] == 3.0  # exam 1 unchanged

    def test_supports_transforms_gating(self):
        from mypyskindose.gui.helpers import exam_supports_transforms

        st = self._state_with_two_exams()
        assert exam_supports_transforms(st.loaded_exams[0], st.loaded_exam_meta[0])
        # DICOM and normalized exams have no per-exam toggles.
        assert not exam_supports_transforms(
            st.loaded_exams[0], {"source_type": "dicom", "schema": "dicom_rdsr"}
        )
        assert not exam_supports_transforms(
            st.loaded_exams[0], {"source_type": "csv", "schema": "normalized"}
        )

    def test_loader_stores_base_data(self):
        from mypyskindose.gui.helpers import load_tabular
        from mypyskindose.gui.state import AppState

        st = AppState()
        st.input_schema = "auto"
        ok, _ = load_tabular(_FIXTURES / "normalized_events_multistudy.csv", st)
        assert ok
        for meta in st.loaded_exam_meta:
            assert "base_data" in meta and meta["base_data"] is not None


# ── GUI per-exam table-origin override (Phase 2.5) ────────────────────────


class TestGuiTableOriginOverride:
    """Manual table-origin override re-bases Tx/Ty/Tz by (override − detected),
    applied per exam through the same engine, and is auditable via a warning."""

    def _state_one_exam(self, detected, schema="dicom_rdsr", source="dicom"):
        import pandas as pd
        from types import SimpleNamespace

        from mypyskindose.gui.state import AppState

        st = AppState()
        df = pd.DataFrame({"Tx": [10.0], "Ty": [20.0], "Tz": [30.0]})
        exam = SimpleNamespace(
            normalized_data=df.copy(),
            provenance=SimpleNamespace(schema_name=schema),
            warnings=[],
        )
        st.loaded_exams = [exam]
        st.loaded_exam_meta = [{
            "file_path": Path("a.dcm"),
            "source_type": source,
            "schema": schema,
            "base_data": df.copy(),
            "swap_lat_lon": False,
            "flip_ap1": False,
            "flip_ap2": False,
            "table_origin_detected": dict(detected),
            "table_origin_override": None,
        }]
        st.is_multi_exam = False
        return st

    def test_override_rebases_columns_by_delta(self):
        from mypyskindose.gui.helpers import apply_exam_transforms

        # detected origin (1, 2, 3); override to (4, 2, 3) → +3 on Tx only.
        st = self._state_one_exam({"x": 1.0, "y": 2.0, "z": 3.0})
        st.loaded_exam_meta[0]["table_origin_override"] = {"x": 4.0, "y": 2.0, "z": 3.0}
        apply_exam_transforms(st, 0)

        df = st.loaded_exams[0].normalized_data
        assert df["Tx"].iloc[0] == 13.0  # 10 + (4 - 1)
        assert df["Ty"].iloc[0] == 20.0  # unchanged
        assert df["Tz"].iloc[0] == 30.0  # unchanged

    def test_reset_to_none_restores_base(self):
        from mypyskindose.gui.helpers import apply_exam_transforms

        st = self._state_one_exam({"x": 1.0, "y": 2.0, "z": 3.0})
        st.loaded_exam_meta[0]["table_origin_override"] = {"x": 9.0, "y": 9.0, "z": 9.0}
        apply_exam_transforms(st, 0)
        st.loaded_exam_meta[0]["table_origin_override"] = None
        apply_exam_transforms(st, 0)

        df = st.loaded_exams[0].normalized_data
        assert df["Tx"].iloc[0] == 10.0
        assert df["Ty"].iloc[0] == 20.0
        assert df["Tz"].iloc[0] == 30.0

    def test_supports_table_origin_requires_base_with_columns(self):
        from mypyskindose.gui.helpers import exam_supports_table_origin

        st = self._state_one_exam({"x": 0.0, "y": 0.0, "z": 0.0})
        assert exam_supports_table_origin(st.loaded_exams[0], st.loaded_exam_meta[0])
        # No base_data → unsupported.
        assert not exam_supports_table_origin(st.loaded_exams[0], {"base_data": None})

    def test_override_note_only_when_active(self):
        from mypyskindose.gui.helpers import _table_origin_override_note

        meta = {
            "table_origin_detected": {"x": 1.0, "y": 0.0, "z": 0.0},
            "table_origin_override": None,
        }
        assert _table_origin_override_note(meta) == []

        meta["table_origin_override"] = {"x": 5.0, "y": 0.0, "z": 0.0}
        note = _table_origin_override_note(meta)
        assert len(note) == 1
        assert "table-origin override" in note[0].lower()

    def test_loader_seeds_override_none_and_detected(self):
        from mypyskindose.gui.helpers import load_tabular
        from mypyskindose.gui.state import AppState

        st = AppState()
        st.input_schema = "auto"
        ok, _ = load_tabular(_FIXTURES / "normalized_events_multistudy.csv", st)
        assert ok
        for meta in st.loaded_exam_meta:
            assert meta["table_origin_override"] is None
            assert meta["table_origin_detected"] == {"x": 0.0, "y": 0.0, "z": 0.0}


# ── GUI per-exam axis-direction sign flips (Phase 2.4) ────────────────────


class TestGuiAxisDirectionFlips:
    """Per-exam trans_dir sign flips (flip_tx/ty/tz) reverse a table axis about its
    auto-detected origin, default off, and compose with swap and origin override."""

    def _state_with_two_exams(self, schema="radimetrics", detected=None):
        import pandas as pd
        from types import SimpleNamespace

        from mypyskindose.gui.state import AppState

        st = AppState()

        def _mk(tx, ty, tz):
            df = pd.DataFrame(
                {"Tx": [tx], "Ty": [ty], "Tz": [tz], "Ap1": [10.0], "Ap2": [5.0]}
            )
            exam = SimpleNamespace(
                normalized_data=df.copy(),
                provenance=SimpleNamespace(schema_name=schema),
                warnings=[],
            )
            meta = {
                "file_path": Path("a.csv"),
                "source_type": "csv",
                "schema": schema,
                "base_data": df.copy(),
                "swap_lat_lon": False,
                "flip_ap1": False,
                "flip_ap2": False,
                "flip_tx": False,
                "flip_ty": False,
                "flip_tz": False,
                "table_origin_detected": dict(detected or {"x": 0.0, "y": 0.0, "z": 0.0}),
                "table_origin_override": None,
            }
            return exam, meta

        e0, m0 = _mk(1.0, 5.0, 2.0)
        e1, m1 = _mk(3.0, 7.0, 4.0)
        st.loaded_exams = [e0, e1]
        st.loaded_exam_meta = [m0, m1]
        st.is_multi_exam = True
        return st

    def test_flip_tx_negates_one_axis_one_exam(self):
        from mypyskindose.gui.helpers import apply_exam_transforms

        st = self._state_with_two_exams()
        st.loaded_exam_meta[0]["flip_tx"] = True
        apply_exam_transforms(st, 0)

        # detected origin is 0 → plain negation of Tx only.
        assert st.loaded_exams[0].normalized_data["Tx"].iloc[0] == -1.0
        assert st.loaded_exams[0].normalized_data["Ty"].iloc[0] == 5.0
        assert st.loaded_exams[0].normalized_data["Tz"].iloc[0] == 2.0
        # Second exam untouched.
        assert st.loaded_exams[1].normalized_data["Tx"].iloc[0] == 3.0

    def test_flip_is_reversible_from_base(self):
        from mypyskindose.gui.helpers import apply_exam_transforms

        st = self._state_with_two_exams()
        st.loaded_exam_meta[0]["flip_ty"] = True
        apply_exam_transforms(st, 0)
        st.loaded_exam_meta[0]["flip_ty"] = False
        apply_exam_transforms(st, 0)

        assert st.loaded_exams[0].normalized_data["Ty"].iloc[0] == 5.0

    def test_flip_pivots_about_detected_origin(self):
        from mypyskindose.gui.helpers import apply_exam_transforms

        # Non-zero detected origin (DICOM-like): col → 2·detected − col.
        st = self._state_with_two_exams(detected={"x": 10.0, "y": 0.0, "z": 0.0})
        st.loaded_exam_meta[0]["flip_tx"] = True
        apply_exam_transforms(st, 0)

        assert st.loaded_exams[0].normalized_data["Tx"].iloc[0] == 19.0  # 2*10 - 1

    def test_normalized_schema_skips_flip(self):
        from mypyskindose.gui.helpers import apply_exam_transforms

        st = self._state_with_two_exams(schema="normalized")
        st.loaded_exam_meta[0]["flip_tx"] = True
        apply_exam_transforms(st, 0)

        # No-op for the already-canonical normalized schema.
        assert st.loaded_exams[0].normalized_data["Tx"].iloc[0] == 1.0

    def test_flip_then_swap_compose(self):
        from mypyskindose.gui.helpers import apply_exam_transforms

        # flip_tx applied first (Tx → −1), then swap Tx ↔ Tz.
        st = self._state_with_two_exams()
        st.loaded_exam_meta[0]["flip_tx"] = True
        st.loaded_exam_meta[0]["swap_lat_lon"] = True
        apply_exam_transforms(st, 0)

        df = st.loaded_exams[0].normalized_data
        assert df["Tx"].iloc[0] == 2.0   # Tz value moved in
        assert df["Tz"].iloc[0] == -1.0  # flipped Tx value moved out

    def test_flip_then_origin_override_compose(self):
        from mypyskindose.gui.helpers import apply_exam_transforms

        # detected x=1, base Tx=1: flip about detected → 2*1-1 = 1; then
        # override x=4 adds (4-1)=+3 → 4.
        st = self._state_with_two_exams(detected={"x": 1.0, "y": 0.0, "z": 0.0})
        st.loaded_exam_meta[0]["flip_tx"] = True
        st.loaded_exam_meta[0]["table_origin_override"] = {"x": 4.0, "y": 0.0, "z": 0.0}
        apply_exam_transforms(st, 0)

        assert st.loaded_exams[0].normalized_data["Tx"].iloc[0] == 4.0

    def test_loader_seeds_axis_flags_off(self):
        from mypyskindose.gui.helpers import load_tabular
        from mypyskindose.gui.state import AppState

        st = AppState()
        st.input_schema = "auto"
        ok, _ = load_tabular(_FIXTURES / "normalized_events_multistudy.csv", st)
        assert ok
        for meta in st.loaded_exam_meta:
            assert meta["flip_tx"] is False
            assert meta["flip_ty"] is False
            assert meta["flip_tz"] is False


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
        summed = sum(np.asarray(e.output.DoseMap) for e in result.exams)
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
