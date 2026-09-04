"""GUI-facing multi-exam tests (per-exam offsets, transforms, table-origin, axis flips).

Split out of tests/unittests/test_multi_exam.py because these classes import
guiskindose.gui.* (which requires nicegui). They live under tests/gui/ so the
core CI matrix (installed without the `gui` extra, run with --ignore=tests/gui)
does not try to collect them; tests/gui/conftest.py skips them when nicegui is
absent. The non-GUI multi-exam tests remain in tests/unittests/test_multi_exam.py.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

_FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "tabular_inputs"


# ── GUI per-exam patient offsets (Phase 2.3) ──────────────────────────────


class TestGuiPerExamOffsets:
    """The GUI seeds a per-exam patient offset into each loaded_exam_meta entry
    (defaulting to the global offset) and run_calculation forwards them to
    analyze_multiple_exams. These tests pin the loader/wiring contract without
    needing the NiceGUI runtime."""

    def _fresh_state(self, d_lon=0.0, d_ver=0.0, d_lat=0.0):
        from guiskindose.gui.state import AppState

        st = AppState()
        st.d_lon, st.d_ver, st.d_lat = d_lon, d_ver, d_lat
        st.input_schema = "auto"
        st.input_source_type = "csv"
        return st

    def test_loader_seeds_offset_defaults_from_global(self):
        from guiskindose.gui.helpers import load_tabular

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

        from guiskindose.gui.helpers import load_tabular, run_calculation

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
            result.exams = [MagicMock(output=MagicMock(air_kerma=0.0)) for _ in exams]
            result.warnings = []
            result.exams_attempted = len(exams)
            result.exams_excluded = 0
            return result

        with patch(
            "guiskindose.analyze_data.analyze_multiple_exams", side_effect=_fake_analyze
        ):
            ok, _ = run_calculation(st)

        assert ok
        assert st.calc_run_id == 1
        assert st.dosemap_fig is None
        assert captured["per_exam_offsets"] == [[5.0, 0.0, 0.0], [0.0, 0.0, -4.0]]


# ── GUI per-exam coordinate transforms (Phase 2.2) ────────────────────────


class TestGuiPerExamTransforms:
    """Per-exam swap/flip overrides operate on each exam's pristine base copy
    independently. Pins the helpers.py engine contract without the NiceGUI runtime."""

    def _state_with_two_exams(self, schema="radimetrics"):
        from types import SimpleNamespace

        import pandas as pd

        from guiskindose.gui.state import AppState

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
        from guiskindose.gui.helpers import apply_exam_transforms

        st = self._state_with_two_exams()
        st.loaded_exam_meta[0]["swap_lat_lon"] = True
        apply_exam_transforms(st, 0)

        assert st.loaded_exams[0].normalized_data["Tx"].iloc[0] == 2.0
        assert st.loaded_exams[0].normalized_data["Tz"].iloc[0] == 1.0
        # Second exam is untouched.
        assert st.loaded_exams[1].normalized_data["Tx"].iloc[0] == 3.0
        assert st.loaded_exams[1].normalized_data["Tz"].iloc[0] == 4.0

    def test_swap_is_reversible_from_base(self):
        from guiskindose.gui.helpers import apply_exam_transforms

        st = self._state_with_two_exams()
        st.loaded_exam_meta[0]["swap_lat_lon"] = True
        apply_exam_transforms(st, 0)
        # Toggle back off: re-derives from the pristine base, not the swapped frame.
        st.loaded_exam_meta[0]["swap_lat_lon"] = False
        apply_exam_transforms(st, 0)

        assert st.loaded_exams[0].normalized_data["Tx"].iloc[0] == 1.0
        assert st.loaded_exams[0].normalized_data["Tz"].iloc[0] == 2.0

    def test_flip_ap1_negates_angle(self):
        from guiskindose.gui.helpers import apply_exam_transforms

        st = self._state_with_two_exams()
        st.loaded_exam_meta[1]["flip_ap1"] = True
        apply_exam_transforms(st, 1)

        assert st.loaded_exams[1].normalized_data["Ap1"].iloc[0] == -10.0
        assert st.loaded_exams[0].normalized_data["Ap1"].iloc[0] == 10.0

    def test_normalized_schema_skips_swap(self):
        from guiskindose.gui.helpers import apply_exam_transforms

        st = self._state_with_two_exams(schema="normalized")
        st.loaded_exam_meta[0]["swap_lat_lon"] = True
        apply_exam_transforms(st, 0)

        # Swap is a no-op for the already-canonical normalized schema.
        assert st.loaded_exams[0].normalized_data["Tx"].iloc[0] == 1.0
        assert st.loaded_exams[0].normalized_data["Tz"].iloc[0] == 2.0

    def test_rebuilds_concatenated_preview(self):
        from guiskindose.gui.helpers import apply_exam_transforms

        st = self._state_with_two_exams()
        st.loaded_exam_meta[0]["swap_lat_lon"] = True
        apply_exam_transforms(st, 0)

        assert st.rdsr_df is not None
        assert len(st.rdsr_df) == 2
        assert st.rdsr_df["Tx"].iloc[0] == 2.0  # exam 0 swapped
        assert st.rdsr_df["Tx"].iloc[1] == 3.0  # exam 1 unchanged

    def test_supports_transforms_gating(self):
        from guiskindose.gui.helpers import exam_supports_transforms

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
        from guiskindose.gui.helpers import load_tabular
        from guiskindose.gui.state import AppState

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
        from types import SimpleNamespace

        import pandas as pd

        from guiskindose.gui.state import AppState

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
        from guiskindose.gui.helpers import apply_exam_transforms

        # detected origin (1, 2, 3); override to (4, 2, 3) → +3 on Tx only.
        st = self._state_one_exam({"x": 1.0, "y": 2.0, "z": 3.0})
        st.loaded_exam_meta[0]["table_origin_override"] = {"x": 4.0, "y": 2.0, "z": 3.0}
        apply_exam_transforms(st, 0)

        df = st.loaded_exams[0].normalized_data
        assert df["Tx"].iloc[0] == 13.0  # 10 + (4 - 1)
        assert df["Ty"].iloc[0] == 20.0  # unchanged
        assert df["Tz"].iloc[0] == 30.0  # unchanged

    def test_reset_to_none_restores_base(self):
        from guiskindose.gui.helpers import apply_exam_transforms

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
        from guiskindose.gui.helpers import exam_supports_table_origin

        st = self._state_one_exam({"x": 0.0, "y": 0.0, "z": 0.0})
        assert exam_supports_table_origin(st.loaded_exams[0], st.loaded_exam_meta[0])
        # No base_data → unsupported.
        assert not exam_supports_table_origin(st.loaded_exams[0], {"base_data": None})

    def test_override_note_only_when_active(self):
        from guiskindose.gui.helpers import _table_origin_override_note

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
        from guiskindose.gui.helpers import load_tabular
        from guiskindose.gui.state import AppState

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
        from types import SimpleNamespace

        import pandas as pd

        from guiskindose.gui.state import AppState

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
        from guiskindose.gui.helpers import apply_exam_transforms

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
        from guiskindose.gui.helpers import apply_exam_transforms

        st = self._state_with_two_exams()
        st.loaded_exam_meta[0]["flip_ty"] = True
        apply_exam_transforms(st, 0)
        st.loaded_exam_meta[0]["flip_ty"] = False
        apply_exam_transforms(st, 0)

        assert st.loaded_exams[0].normalized_data["Ty"].iloc[0] == 5.0

    def test_flip_pivots_about_detected_origin(self):
        from guiskindose.gui.helpers import apply_exam_transforms

        # Non-zero detected origin (DICOM-like): col → 2·detected − col.
        st = self._state_with_two_exams(detected={"x": 10.0, "y": 0.0, "z": 0.0})
        st.loaded_exam_meta[0]["flip_tx"] = True
        apply_exam_transforms(st, 0)

        assert st.loaded_exams[0].normalized_data["Tx"].iloc[0] == 19.0  # 2*10 - 1

    def test_normalized_schema_skips_flip(self):
        from guiskindose.gui.helpers import apply_exam_transforms

        st = self._state_with_two_exams(schema="normalized")
        st.loaded_exam_meta[0]["flip_tx"] = True
        apply_exam_transforms(st, 0)

        # No-op for the already-canonical normalized schema.
        assert st.loaded_exams[0].normalized_data["Tx"].iloc[0] == 1.0

    def test_flip_then_swap_compose(self):
        from guiskindose.gui.helpers import apply_exam_transforms

        # flip_tx applied first (Tx → −1), then swap Tx ↔ Tz.
        st = self._state_with_two_exams()
        st.loaded_exam_meta[0]["flip_tx"] = True
        st.loaded_exam_meta[0]["swap_lat_lon"] = True
        apply_exam_transforms(st, 0)

        df = st.loaded_exams[0].normalized_data
        assert df["Tx"].iloc[0] == 2.0   # Tz value moved in
        assert df["Tz"].iloc[0] == -1.0  # flipped Tx value moved out

    def test_flip_then_origin_override_compose(self):
        from guiskindose.gui.helpers import apply_exam_transforms

        # detected x=1, base Tx=1: flip about detected → 2*1-1 = 1; then
        # override x=4 adds (4-1)=+3 → 4.
        st = self._state_with_two_exams(detected={"x": 1.0, "y": 0.0, "z": 0.0})
        st.loaded_exam_meta[0]["flip_tx"] = True
        st.loaded_exam_meta[0]["table_origin_override"] = {"x": 4.0, "y": 0.0, "z": 0.0}
        apply_exam_transforms(st, 0)

        assert st.loaded_exams[0].normalized_data["Tx"].iloc[0] == 4.0

    def test_loader_seeds_axis_flags_off(self):
        from guiskindose.gui.helpers import load_tabular
        from guiskindose.gui.state import AppState

        st = AppState()
        st.input_schema = "auto"
        ok, _ = load_tabular(_FIXTURES / "normalized_events_multistudy.csv", st)
        assert ok
        for meta in st.loaded_exam_meta:
            assert meta["flip_tx"] is False
            assert meta["flip_ty"] is False
            assert meta["flip_tz"] is False
