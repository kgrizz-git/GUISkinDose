"""Run-state v2 pending consumption: raw-load lifecycles (no UI).

Covers the pre-load path end to end: staging via import, FIFO consumption by
accepted single-exam raw loads (DICOM and vendor tabular) with replay and
post-transform confirmation, null-slot flag seeding, multi-study and
conflict refusals, pop-on-success, and failure retention. Calculation parity
uses the existing threading with PSD/map/match comparison. Real approved
fixtures back every capture; synthetic inputs use tmp text only.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pytest

# These workflow tests need the optional GUI extra; core CI skips the module.
pytest.importorskip("nicegui")

from guiskindose.analyze_data import analyze_data
from guiskindose.equipment_capture import capture_to_mapping
from guiskindose.equipment_profiles import assemble_session
from guiskindose.gui.exam_loaders import load_rdsr, load_tabular
from guiskindose.gui.helpers import run_calculation
from guiskindose.gui.run_state import apply_run_state, serialize_run_state
from guiskindose.gui.settings_builder import bind_equipment_session, build_settings
from guiskindose.gui.state import AppState

_DICOM = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "guiskindose"
    / "example_data"
    / "RDSR"
    / "siemens_axiom_artis.dcm"
)
_NORMALIZED_MULTI = (
    Path(__file__).resolve().parent.parent / "fixtures" / "tabular_inputs" / "normalized_events_multistudy.csv"
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
                "profile_id": "v2-pending",
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


def _export_document(state: AppState) -> dict[str, Any]:
    """Serialize a realistic v2 document for the given live state."""
    return serialize_run_state(build_settings(state), state, created="2026-10-14T00:00:00+00:00")


def _mapping_of(state: AppState, index: int = 0) -> dict[str, Any]:
    """Canonical producer mapping of one loaded exam's capture."""
    return capture_to_mapping(state.loaded_exams[index].equipment_capture)


def _import_and_consume_dicom(mapping: dict[str, Any]) -> tuple[AppState, dict[str, Any]]:
    """Stage one capture slot, then consume it with the approved DICOM."""
    document = _export_document(AppState())
    document["equipment"] = {"schema_version": 1, "mode": "coordinates", "captures": [mapping]}
    document["gui_state"]["exams"] = [{}]
    state = _plane_state(None)
    result = apply_run_state(document, state)
    assert result.applied_exams == 0
    assert state.equipment_pending is not None
    assert len(state.equipment_pending) == 1
    ok, _ = load_rdsr(_DICOM, state)
    assert ok
    return state, document


def test_dicom_pending_lifecycle_parity(session: Any) -> None:
    """Stage → replay → confirm → calculate matches the direct API exactly."""
    donor = _plane_state(session)
    assert load_rdsr(_DICOM, donor)[0]
    mapping = _mapping_of(donor)
    state, _ = _import_and_consume_dicom(mapping)
    exam = state.loaded_exams[0]
    assert exam.equipment_capture == donor.loaded_exams[0].equipment_capture
    assert exam.normalization_snapshot is not None
    assert exam.equipment_receipt is None
    assert state.equipment_pending is None
    assert run_calculation(state)[0]
    expected: Any = analyze_data(
        exam.normalized_data.copy(),
        build_settings(state),
        equipment_capture_context=exam.equipment_capture,
    )
    assert state.output is not None
    assert state.output["psd"] == pytest.approx(expected["psd"])
    np.testing.assert_allclose(state.output["dose_map"], expected["dose_map"])
    assert state.output["equipment_profile_match"] == expected["equipment_profile_match"]


def test_csv_null_consumption_seeds_flags(tmp_path: Path) -> None:
    """A null slot loads plainly but seeds the document's flags and offsets."""
    document = _export_document(AppState())
    document["equipment"] = {"schema_version": 1, "mode": "coordinates", "captures": [None]}
    document["gui_state"]["exams"] = [{"swap_lat_lon": True, "d_lon": 9.0}]
    state = _plane_state(None)
    apply_run_state(document, state)
    assert state.equipment_pending is not None
    assert load_tabular(_write_csv(tmp_path / "null.csv"), state)[0]
    meta = state.loaded_exam_meta[0]
    assert meta["swap_lat_lon"] is True
    assert meta["d_lon"] == 9.0
    assert state.d_lon == 9.0
    assert state.swap_lat_lon is True
    exam = state.loaded_exams[0]
    assert exam.equipment_capture is None
    base = meta["base_data"]
    assert exam.normalized_data["Tx"].iloc[0] == base["Tz"].iloc[0]
    assert exam.normalized_data["Tz"].iloc[0] == base["Tx"].iloc[0]
    assert state.equipment_pending is None


def test_dicom_null_consumption_seeds_globals() -> None:
    """A null DICOM slot mirrors staged per-exam offsets into globals for calculation."""
    document = _export_document(AppState())
    document["equipment"] = {"schema_version": 1, "mode": "coordinates", "captures": [None]}
    document["gui_state"]["exams"] = [{"swap_lat_lon": True, "d_lon": 9.0}]
    state = _plane_state(None)
    apply_run_state(document, state)
    assert state.equipment_pending is not None
    ok, _ = load_rdsr(_DICOM, state)
    assert ok
    meta = state.loaded_exam_meta[0]
    assert meta["swap_lat_lon"] is True
    assert meta["d_lon"] == 9.0
    assert state.d_lon == 9.0
    assert state.swap_lat_lon is True
    assert state.equipment_pending is None


def test_csv_capture_lifecycle_parity(session: Any, tmp_path: Path) -> None:
    """Vendor-tabular replay consumes, confirms, and calculates identically."""
    donor = _plane_state(session)
    assert load_tabular(_write_csv(tmp_path / "donor.csv"), donor)[0]
    mapping = _mapping_of(donor)
    document = _export_document(AppState())
    document["equipment"] = {"schema_version": 1, "mode": "coordinates", "captures": [mapping]}
    document["gui_state"]["exams"] = [{}]
    state = _plane_state(None)
    apply_run_state(document, state)
    assert load_tabular(_write_csv(tmp_path / "live.csv"), state)[0]
    exam = state.loaded_exams[0]
    assert exam.equipment_capture == donor.loaded_exams[0].equipment_capture
    assert run_calculation(state)[0]
    expected: Any = analyze_data(
        exam.normalized_data.copy(),
        build_settings(state),
        equipment_capture_context=exam.equipment_capture,
    )
    assert state.output is not None
    assert state.output["psd"] == pytest.approx(expected["psd"])
    np.testing.assert_allclose(state.output["dose_map"], expected["dose_map"])


def _null_staged_state(session: Any, tmp_path: Path, flags: dict[str, Any], name: str) -> tuple[AppState, Path]:
    """Stage one null slot, then load under session so the mint covers flags.

    Null slots carry document flags into session loads: the adapter
    normalizes plain, the entry flags transform, and the fresh mint digests
    the transformed frame. Returns the loaded state and its file.
    """
    document = _export_document(AppState())
    document["equipment"] = {"schema_version": 1, "mode": "coordinates", "captures": [None]}
    document["gui_state"]["exams"] = [dict(flags)]
    state = _plane_state(session)
    apply_run_state(document, state)
    assert state.equipment_pending is not None
    path = _write_csv(tmp_path / f"{name}.csv")
    assert load_tabular(path, state)[0]
    assert state.equipment_pending is None
    return state, path


def _parity_check(state: AppState, index: int = 0) -> None:
    """Loaded capture must reproduce the direct API on PSD, map, and match."""
    exam = state.loaded_exams[index]
    assert exam.equipment_capture is not None
    assert run_calculation(state)[0]
    expected: Any = analyze_data(
        exam.normalized_data.copy(),
        build_settings(state),
        equipment_capture_context=exam.equipment_capture,
    )
    assert state.output is not None
    assert state.output["psd"] == pytest.approx(expected["psd"])
    np.testing.assert_allclose(state.output["dose_map"], expected["dose_map"])
    assert state.output["equipment_profile_match"] == expected["equipment_profile_match"]


def _roundtrip_through_export(donor: AppState, path: Path) -> AppState:
    """Export a loaded state, re-import empty, and replay the same file."""
    document = _export_document(donor)
    assert document["equipment"] is not None
    assert len(document["equipment"]["captures"]) == 1
    state = _plane_state(None)
    result = apply_run_state(document, state)
    assert result.applied_exams == 0
    assert state.equipment_pending is not None
    assert len(state.equipment_pending) == 1
    assert load_tabular(path, state)[0]
    assert state.equipment_pending is None
    return state


@pytest.mark.parametrize(
    "flags",
    [
        {"swap_lat_lon": True},
        {"flip_ap1": True, "flip_ap2": True},
        {"table_origin_override": {"x": 1.5, "y": 2.5, "z": -3.5}},
        {
            "swap_lat_lon": True,
            "flip_ap1": True,
            "flip_ap2": True,
            "table_origin_override": {"x": 1.5, "y": 2.5, "z": -3.5},
        },
    ],
    ids=["swap", "flips", "override", "combined"],
)
def test_transform_lifecycle_parity(session: Any, tmp_path: Path, flags: dict[str, Any]) -> None:
    """Transformed frames round-trip: null-mint, export, replay, calculate.

    The export session mints over the transformed frame (no rehash
    workaround — the capture genuinely digests it); the replay confirms the
    same transforms and calculates identically to the direct API.
    """
    donor, path = _null_staged_state(session, tmp_path, flags, "export")
    exam = donor.loaded_exams[0]
    assert exam.equipment_capture is not None
    for key, value in flags.items():
        if key == "table_origin_override":
            assert donor.loaded_exam_meta[0][key] == value
        else:
            assert donor.loaded_exam_meta[0][key] is True
    state = _roundtrip_through_export(donor, path)
    live = state.loaded_exams[0]
    assert live.equipment_capture == exam.equipment_capture
    for key, value in flags.items():
        if key == "table_origin_override":
            assert state.loaded_exam_meta[0][key] == value
        else:
            assert state.loaded_exam_meta[0][key] is True
    _parity_check(state)


def test_fifo_two_slots_ordered(session: Any) -> None:
    """Two staged slots consume in order with per-slot document fields."""
    donor = _plane_state(session)
    assert load_rdsr(_DICOM, donor)[0]
    mapping = _mapping_of(donor)
    document = _export_document(AppState())
    document["equipment"] = {"schema_version": 1, "mode": "coordinates", "captures": [mapping, mapping]}
    document["gui_state"]["exams"] = [{"d_lon": 1.0}, {"d_lon": 2.0}]
    state = _plane_state(None)
    apply_run_state(document, state)
    assert state.equipment_pending is not None
    assert len(state.equipment_pending) == 2
    assert load_rdsr(_DICOM, state)[0]
    assert len(state.equipment_pending) == 1
    assert load_rdsr(_DICOM, state)[0]
    assert state.equipment_pending is None
    assert [m["d_lon"] for m in state.loaded_exam_meta] == [1.0, 2.0]
    assert all(e.equipment_capture is not None for e in state.loaded_exams)


def test_failed_load_retains_pending(session: Any, tmp_path: Path) -> None:
    """A refused file leaves staged slots identical for a later retry."""
    donor = _plane_state(session)
    assert load_rdsr(_DICOM, donor)[0]
    document = _export_document(AppState())
    document["equipment"] = {
        "schema_version": 1,
        "mode": "coordinates",
        "captures": [_mapping_of(donor)],
    }
    document["gui_state"]["exams"] = [{}]
    fresh = _plane_state(None)
    apply_run_state(document, fresh)
    held = fresh.equipment_pending
    assert held is not None
    bad = tmp_path / "bad.csv"
    bad.write_text("not,a\nvalid,row\n", encoding="utf-8")
    ok, _ = load_tabular(bad, fresh)
    assert not ok
    assert fresh.equipment_pending is held
    assert fresh.loaded_exams == []


def test_multistudy_pending_refusal() -> None:
    """A multi-study split with staged entries refuses the whole file.

    Null slots reach the consumption gate (a capture slot would already
    refuse inside the replay adapter for normalized frames).
    """
    document = _export_document(AppState())
    document["equipment"] = {"schema_version": 1, "mode": "coordinates", "captures": [None]}
    document["gui_state"]["exams"] = [{}]
    state = _plane_state(None)
    apply_run_state(document, state)
    held = state.equipment_pending
    assert held is not None
    ok, msg = load_tabular(_NORMALIZED_MULTI, state)
    assert not ok
    assert "multi-study" in msg
    assert state.equipment_pending is held
    assert state.loaded_exams == []


def test_replace_pending_refusal(session: Any, tmp_path: Path) -> None:
    """Re-parsing with staged entries refuses before the drop runs."""
    donor = _plane_state(session)
    assert load_rdsr(_DICOM, donor)[0]
    mapping = _mapping_of(donor)
    document = _export_document(AppState())
    document["equipment"] = {"schema_version": 1, "mode": "coordinates", "captures": [None, mapping]}
    document["gui_state"]["exams"] = [{}, {}]
    state = _plane_state(None)
    apply_run_state(document, state)
    assert state.equipment_pending is not None
    assert len(state.equipment_pending) == 2
    assert load_tabular(_write_csv(tmp_path / "plain.csv"), state)[0]
    assert len(state.loaded_exams) == 1
    assert len(state.equipment_pending) == 1
    held = state.equipment_pending
    old_exams = state.loaded_exams
    ok, _ = load_tabular(tmp_path / "plain.csv", state, replace_existing=True)
    assert not ok
    assert state.equipment_pending is held
    assert state.loaded_exams is old_exams
    assert len(state.loaded_exams) == 1


def test_null_consumption_mints_under_session(session: Any, tmp_path: Path) -> None:
    """A null slot under a bound session mints fresh authority with doc flags."""
    donor = _plane_state(session)
    assert load_rdsr(_DICOM, donor)[0]
    document = _export_document(AppState())
    document["equipment"] = {"schema_version": 1, "mode": "coordinates", "captures": [None]}
    document["gui_state"]["exams"] = [{"swap_lat_lon": True}]
    state = _plane_state(session)
    apply_run_state(document, state)
    assert state.equipment_pending is not None
    assert load_tabular(_write_csv(tmp_path / "fresh.csv"), state)[0]
    exam = state.loaded_exams[0]
    assert exam.equipment_capture is not None
    assert state.loaded_exam_meta[0]["swap_lat_lon"] is True
    assert state.equipment_pending is None
    assert run_calculation(state)[0]


def test_mixed_aggregate_counts_captured(session: Any, tmp_path: Path) -> None:
    """Previously captured rows join the aggregate ceiling with new frames."""
    state = _plane_state(session)
    assert load_tabular(_write_csv(tmp_path / "one.csv"), state)[0]
    mapping = _mapping_of(state)
    document = _export_document(AppState())
    document["equipment"] = {"schema_version": 1, "mode": "coordinates", "captures": [mapping, None]}
    document["gui_state"]["exams"] = [{}, {}]
    apply_run_state(document, state)
    assert state.equipment_pending is not None
    assert len(state.equipment_pending) == 1
    big = _write_csv(tmp_path / "big.csv", [_RAW_ROW] * 10001)
    ok, _ = load_tabular(big, state)
    assert not ok
    assert len(state.loaded_exams) == 1
    assert len(state.equipment_pending) == 1


def test_null_aggregate_counts_uncaptured(tmp_path: Path) -> None:
    """Uncaptured retained rows count too: nulls are not a smaller footprint."""
    state = _plane_state(None)
    assert load_tabular(_write_csv(tmp_path / "a.csv"), state)[0]
    assert load_tabular(_write_csv(tmp_path / "b.csv"), state)[0]
    document = _export_document(AppState())
    document["equipment"] = {"schema_version": 1, "mode": "coordinates", "captures": [None, None, None]}
    document["gui_state"]["exams"] = [{}, {}, {}]
    apply_run_state(document, state)
    assert state.equipment_pending is not None
    assert len(state.equipment_pending) == 1
    big = _write_csv(tmp_path / "big.csv", [_RAW_ROW] * 10001)
    ok, _ = load_tabular(big, state)
    assert not ok
    assert len(state.loaded_exams) == 2
    assert len(state.equipment_pending) == 1


def test_forged_entry_fails_before_read(tmp_path: Path) -> None:
    """A mutated bypass entry fails at the consuming boundary before any I/O."""
    from unittest import mock

    import pydicom

    from guiskindose.gui.run_state_equipment import PendingEntry

    document = _export_document(AppState())
    document["equipment"] = {"schema_version": 1, "mode": "coordinates", "captures": [None]}
    document["gui_state"]["exams"] = [{}]
    state = _plane_state(None)
    apply_run_state(document, state)
    assert state.equipment_pending is not None
    forged = state.equipment_pending[0]
    object.__setattr__(forged, "swap_lat_lon", "yes")
    state.equipment_pending = (forged,)
    with mock.patch.object(pydicom, "dcmread", wraps=pydicom.dcmread) as spy:
        ok, msg = load_rdsr(_DICOM, state)
    assert not ok
    assert "invalid" in msg
    spy.assert_not_called()
    assert state.loaded_exams == []
    assert state.equipment_pending is not None
    assert isinstance(state.equipment_pending[0], PendingEntry)


def test_tampered_frozen_override_fails_before_read() -> None:
    """Base-dict mutation cannot bypass the loader's pending revalidation."""
    from unittest import mock

    import pydicom

    document = _export_document(AppState())
    document["equipment"] = {"schema_version": 1, "mode": "coordinates", "captures": [None]}
    document["gui_state"]["exams"] = [{"table_origin_override": {"x": 0.0}}]
    state = _plane_state(None)
    apply_run_state(document, state)
    assert state.equipment_pending is not None
    override = state.equipment_pending[0].table_origin_override
    assert override is not None
    dict.__setitem__(override, "x", "PRIVATE_SENTINEL")
    with mock.patch.object(pydicom, "dcmread", wraps=pydicom.dcmread) as spy:
        ok, message = load_rdsr(_DICOM, state)
    assert not ok
    assert "PRIVATE_SENTINEL" not in message
    spy.assert_not_called()
    assert state.loaded_exams == []
    assert state.equipment_pending is not None
