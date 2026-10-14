"""GUI calculation with captured authority: parity, baselines, stale refusal."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest import mock

import numpy as np
import pytest

# These workflow tests need the optional GUI extra; core CI skips the module.
pytest.importorskip("nicegui")

from guiskindose.analyze_data import analyze_data, analyze_multiple_exams
from guiskindose.equipment_profiles import assemble_session
from guiskindose.gui.exam_loaders import load_rdsr, load_tabular
from guiskindose.gui.exam_transforms import apply_exam_transforms
from guiskindose.gui.helpers import run_calculation
from guiskindose.gui.settings_builder import (
    bind_equipment_session,
    build_settings,
    prepare_calculation_authority,
)
from guiskindose.gui.state import AppState, reset_results

_DICOM = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "guiskindose"
    / "example_data"
    / "RDSR"
    / "siemens_axiom_artis.dcm"
)

_RAW_HEADER = (
    "Manufacturer,ManufacturerModelName,IrradiationEventType,AcquisitionPlane,"
    "DistanceSourcetoDetector_mm,DistanceSourcetoIsocenter_mm,"
    "TableLongitudinalPosition_mm,TableLateralPosition_mm,TableHeightPosition_mm,CollimatedFieldArea_m2,"
    "XRayFilterMaterial,XRayFilterThicknessMinimum_mm,XRayFilterThicknessMaximum_mm,"
    "PositionerPrimaryAngle_deg,PositionerSecondaryAngle_deg,KVP_kV,DoseRP_Gy"
)
_RAW_ROW = (
    "Siemens,AXIOM-Artis,Fluoroscopy,Single Plane,1198,785,37.8,40.6,294.1,0.01,"
    "Copper or Copper compound,0.6,0.6,-0.1,-1.1,77.0,0.00003"
)


def _profile_doc() -> dict[str, Any]:
    """Single memory profile matching the approved Siemens fixture."""
    return {
        "schema_version": 1,
        "profiles": [
            {
                "profile_id": "gui-calc",
                "manufacturer": "Siemens",
                "models": ["AXIOM-Artis"],
                "coordinates": {
                    "translation_offset": {"x": 5.0, "y": -3.5, "z": 0.0},
                    "translation_direction": {"x": "+", "y": "-", "z": "+"},
                    "rotation_direction": {
                        "Ap1": "-",
                        "Ap2": "+",
                        "Ap3": "+",
                        "At1": "+",
                        "At2": "-",
                        "At3": "+",
                    },
                    "swap_lateral_longitudinal": False,
                    "field_size_mode": "CFA",
                    "detector_side_length": 30.0,
                },
            }
        ],
    }


@pytest.fixture(scope="module")
def session() -> Any:
    """Assembled immutable memory session (no files opened)."""
    return assemble_session(documents=[_profile_doc()])


def _plane_state(session: Any | None) -> AppState:
    """Fast plane-phantom state, optionally with the session bound."""
    state = AppState()
    state.phantom_model = "plane"
    if session is not None:
        bind_equipment_session(state, session)
    return state


def _write_csv(path: Path, rows: list[str] | None = None) -> Path:
    """Write a synthetic raw CSV (tmp only, never tracked)."""
    body = rows if rows is not None else [_RAW_ROW]
    path.write_text(_RAW_HEADER + "\n" + "\n".join(body) + "\n", encoding="utf-8")
    return path


def _stripped_settings(state: AppState) -> Any:
    """Fresh settings with the live session removed (mirrors calc isolation)."""
    settings = build_settings(state, mode="calculate_dose", output_format="dict")
    settings.equipment_profile_session = None
    return settings


def test_single_captured_parity(session: Any) -> None:
    """GUI captured calculation matches the API on PSD, map, and match."""
    state = _plane_state(session)
    assert load_rdsr(_DICOM, state)[0]
    assert run_calculation(state)[0]
    exam = state.loaded_exams[0]
    expected: Any = analyze_data(
        exam.normalized_data.copy(),
        _stripped_settings(state),
        equipment_capture_context=exam.equipment_capture,
    )
    assert state.output is not None
    assert state.output["psd"] == pytest.approx(expected["psd"])
    np.testing.assert_allclose(state.output["dose_map"], expected["dose_map"])
    assert state.output["equipment_profile_match"] == expected["equipment_profile_match"]
    assert state.output["equipment_profile_match"]["profile_id"] == "gui-calc"


def test_single_pure_parity() -> None:
    """The threading delta leaves session-free calculation byte-identical."""
    state = _plane_state(None)
    assert load_rdsr(_DICOM, state)[0]
    assert run_calculation(state)[0]
    exam = state.loaded_exams[0]
    expected: Any = analyze_data(exam.normalized_data.copy(), build_settings(state))
    assert state.output is not None
    assert state.output["psd"] == pytest.approx(expected["psd"])
    np.testing.assert_allclose(state.output["dose_map"], expected["dose_map"])
    assert expected.get("equipment_profile_match") is None


def test_multi_captured_parity(session: Any, tmp_path: Path) -> None:
    """Multi-exam captured runs match direct API aggregation."""
    state = _plane_state(session)
    assert load_tabular(_write_csv(tmp_path / "a.csv"), state)[0]
    assert load_tabular(_write_csv(tmp_path / "b.csv"), state)[0]
    assert run_calculation(state)[0]
    result = state.multi_exam_result
    assert result is not None
    offsets = [
        [float(m.get("d_lon", 0.0)), float(m.get("d_ver", 0.0)), float(m.get("d_lat", 0.0))]
        for m in state.loaded_exam_meta
    ]
    expected: Any = analyze_multiple_exams(
        exams=state.loaded_exams,
        settings=_stripped_settings(state),
        per_exam_offsets=offsets,
        equipment_capture_contexts=[e.equipment_capture for e in state.loaded_exams],
    )
    assert result.aggregate_psd == pytest.approx(expected.aggregate_psd)
    np.testing.assert_allclose(result.aggregate_dose_map, expected.aggregate_dose_map)
    assert [e.equipment_profile_match is not None for e in result.exams] == [True, True]


def test_mixed_baseline_uses_private_snapshot(session: Any, tmp_path: Path) -> None:
    """A null entry calculates on its own baseline, never shared last-load state.

    The null entry simulates a future unspecified slot (run-state ``null``):
    loaders always mint under an active session, so it is assigned directly.
    """
    state = _plane_state(session)
    assert load_tabular(_write_csv(tmp_path / "a.csv"), state)[0]
    assert load_tabular(_write_csv(tmp_path / "b.csv"), state)[0]
    null_exam = state.loaded_exams[1]
    null_exam.equipment_capture = None
    settings = build_settings(state, mode="calculate_dose", output_format="dict")
    _, contexts, baselines = prepare_calculation_authority(state, settings)
    assert contexts is not None
    assert contexts[1] is None
    assert baselines is not None
    assert baselines[0] is None
    assert baselines[1] is not None
    assert baselines[1] is not settings.normalization_settings
    assert run_calculation(state)[0]
    result = state.multi_exam_result
    assert result is not None
    assert result.exams[0].equipment_profile_match is not None
    assert result.exams[1].equipment_profile_match is None
    expected: Any = analyze_data(null_exam.normalized_data.copy(), _stripped_settings(state))
    assert result.exams[1].output.psd == pytest.approx(expected["psd"])


def test_stale_toggle_refuses_before_dose(session: Any) -> None:
    """A post-load geometry edit retains authority and fails closed at calc."""
    state = _plane_state(session)
    assert load_rdsr(_DICOM, state)[0]
    state.loaded_exam_meta[0]["swap_lat_lon"] = True
    apply_exam_transforms(state, 0)
    assert state.loaded_exams[0].equipment_capture is not None
    with mock.patch("guiskindose.analyze_data.calculate_dose") as spy:
        ok, msg = run_calculation(state)
    assert not ok
    assert "failed" in msg
    spy.assert_not_called()
    assert state.loaded_exams[0].equipment_capture is not None


def test_dose_spy_is_effective(session: Any) -> None:
    """Positive control: the zero-dose spy observes real calculation."""
    import sys

    analyze_module = sys.modules["guiskindose.analyze_data"]

    state = _plane_state(session)
    assert load_rdsr(_DICOM, state)[0]
    real_calculate = analyze_module.calculate_dose
    with mock.patch.object(analyze_module, "calculate_dose", wraps=real_calculate) as spy:
        assert run_calculation(state)[0]
    spy.assert_called()
    assert state.output is not None


_PHILIPS_ROW = _RAW_ROW.replace("Siemens,AXIOM-Artis", "Philips,Allura Clarity")


def _philips_doc() -> dict[str, Any]:
    """Custom Philips profile with distinct offsets/signs (CFA for the synthetic row).

    ASD would need shutter columns the single-row synthetic CSV lacks; the
    contract allows equivalent distinct fields, and offsets/signs move dose.
    """
    doc = _profile_doc()
    profile = doc["profiles"][0]
    profile["profile_id"] = "gui-calc-philips"
    profile["manufacturer"] = "Philips"
    profile["models"] = ["Allura Clarity"]
    coordinates = profile["coordinates"]
    coordinates["translation_offset"] = {"x": 1.5, "y": 2.5, "z": -3.5}
    coordinates["rotation_direction"]["Ap2"] = "-"
    return doc


@pytest.fixture(scope="module")
def dual_session() -> Any:
    """Session covering the Siemens and Philips fixtures (no files opened)."""
    return assemble_session(documents=[_profile_doc(), _philips_doc()])


def _oracle_psd(frame: Any, snapshot: Any, state: AppState) -> Any:
    """Independent single-exam baseline oracle on a private snapshot norm."""
    import copy

    settings = build_settings(state, mode="calculate_dose", output_format="dict")
    settings.equipment_profile_session = None
    settings.normalization_settings = copy.deepcopy(snapshot)
    result: Any = analyze_data(frame.copy(), settings)
    return result["psd"]


@pytest.mark.parametrize("first", ["siemens", "philips"])
def test_mixed_baseline_per_exam_snapshots(dual_session: Any, tmp_path: Path, first: str) -> None:
    """Each null entry calculates on its genuine per-exam baseline, either order.

    The nulled entry simulates a future unspecified slot: its retained
    snapshot (not shared last-load state) must reproduce the independent
    single-exam baseline oracle, and the snapshot offsets must show each
    exam's own recipe (Siemens vs Philips) regardless of load order.
    """
    rows = {"siemens": _RAW_ROW, "philips": _PHILIPS_ROW}
    second = "philips" if first == "siemens" else "siemens"
    state = _plane_state(dual_session)
    assert load_tabular(_write_csv(tmp_path / "a.csv", [rows[first]]), state)[0]
    assert load_tabular(_write_csv(tmp_path / "b.csv", [rows[second]]), state)[0]
    snapshots = [exam.normalization_snapshot for exam in state.loaded_exams]
    assert all(s is not None for s in snapshots)
    offsets = [(s.trans_offset.x, s.trans_offset.y, s.trans_offset.z) for s in snapshots]
    siemens_offsets = (5.0, -3.5, 0.0)
    philips_offsets = (1.5, 2.5, -3.5)
    expected_offsets = [siemens_offsets, philips_offsets] if first == "siemens" else [philips_offsets, siemens_offsets]
    assert offsets == expected_offsets
    null_exam = state.loaded_exams[1]
    null_exam.equipment_capture = None
    assert run_calculation(state)[0]
    result = state.multi_exam_result
    assert result is not None
    assert result.exams[0].equipment_profile_match is not None
    assert result.exams[1].equipment_profile_match is None
    assert result.exams[1].output.psd == pytest.approx(
        _oracle_psd(null_exam.normalized_data, null_exam.normalization_snapshot, state)
    )


def test_missing_snapshot_refuses_loudly(dual_session: Any, tmp_path: Path) -> None:
    """A nulled capture without its snapshot is inconsistent: refuse, no dose."""
    from unittest import mock

    state = _plane_state(dual_session)
    assert load_tabular(_write_csv(tmp_path / "a.csv", [_RAW_ROW]), state)[0]
    assert load_tabular(_write_csv(tmp_path / "b.csv", [_RAW_ROW]), state)[0]
    null_exam = state.loaded_exams[1]
    null_exam.equipment_capture = None
    null_exam.normalization_snapshot = None
    import sys

    analyze_module = sys.modules["guiskindose.analyze_data"]
    with mock.patch.object(analyze_module, "calculate_dose") as spy:
        ok, msg = run_calculation(state)
    assert not ok
    assert "failed" in msg
    spy.assert_not_called()


def test_result_repr_hides_snapshot_contents(dual_session: Any, tmp_path: Path) -> None:
    """The snapshot field never renders through exam reprs.

    (Frame content itself renders in result reprs by pre-existing adapter
    behavior; the snapshot home stays out via ``repr=False``.)
    """
    state = _plane_state(dual_session)
    assert load_tabular(_write_csv(tmp_path / "a.csv", [_RAW_ROW]), state)[0]
    text = repr(state.loaded_exams[0])
    assert "normalization_snapshot" not in text
    assert "field_size_mode" not in text
    assert "translation_offset" not in text


def test_reset_preserves_authority_end_to_end(session: Any) -> None:
    """Settings-only invalidation keeps captures, session, and calculability."""
    state = _plane_state(session)
    assert load_rdsr(_DICOM, state)[0]
    reset_results(state)
    assert state.equipment_profile_session is session
    assert state.loaded_exams[0].equipment_capture is not None
    assert run_calculation(state)[0]
    assert state.output is not None


def test_authority_count_checked_before_copy(session: Any) -> None:
    from guiskindose.equipment_profiles.capture import CaptureError

    class NoTraversal(list):
        def __iter__(self):
            raise AssertionError("Oversized authority must not be traversed")

    state = _plane_state(session)
    state.loaded_exams = NoTraversal([None] * 65)
    settings = build_settings(state)
    with pytest.raises(CaptureError):
        prepare_calculation_authority(state, settings)
    assert settings.equipment_profile_session is session


def test_current_frame_rows_bounded_before_baseline_copy(session: Any, tmp_path: Path) -> None:
    import pandas as pd

    from guiskindose.equipment_profiles.capture import CaptureError

    state = _plane_state(session)
    assert load_tabular(_write_csv(tmp_path / "a.csv", [_RAW_ROW]), state)[0]
    assert load_tabular(_write_csv(tmp_path / "b.csv", [_RAW_ROW]), state)[0]
    state.loaded_exams[0].equipment_capture = None
    second = state.loaded_exams[1]
    second.normalized_data = pd.concat([second.normalized_data] * 10000, ignore_index=True)
    settings = build_settings(state)
    with mock.patch("guiskindose.gui.settings_builder.copy.deepcopy") as copier, pytest.raises(CaptureError):
        prepare_calculation_authority(state, settings)
    copier.assert_not_called()
    assert settings.equipment_profile_session is session


def test_forged_capture_count_rejected_closed(session: Any) -> None:
    from guiskindose.equipment_profiles.capture import CaptureError

    state = _plane_state(session)
    assert load_rdsr(_DICOM, state)[0]
    capture = state.loaded_exams[0].equipment_capture
    assert capture is not None
    object.__setattr__(capture, "event_count", "PRIVATE COUNT SENTINEL")
    settings = build_settings(state)
    with pytest.raises(CaptureError) as caught:
        prepare_calculation_authority(state, settings)
    assert "PRIVATE COUNT SENTINEL" not in str(caught.value)
    assert settings.equipment_profile_session is session
