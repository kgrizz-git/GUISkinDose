"""Run-state v2 equipment: writer, reader, trial, and staging (no consumption).

Covers the document side of the migration slice: always-v2 emission with
null-when-empty, v1 preservation plus retention warnings, strict v2
validation, trial confirmation of loaded frames, pending staging, and the
pure headless gates. Raw-load consumption lives in
``test_run_state_v2_pending.py``. Real approved fixtures back every capture;
handcrafted documents use inline dicts (no files).
"""

from __future__ import annotations

import copy
import dataclasses
from pathlib import Path
from typing import Any

import pytest

# These workflow tests need the optional GUI extra; core CI skips the module.
pytest.importorskip("nicegui")

from guiskindose.equipment_capture import capture_to_mapping
from guiskindose.equipment_profiles import assemble_session
from guiskindose.gui.exam_loaders import load_rdsr
from guiskindose.gui.run_state import (
    RUN_STATE_SCHEMA,
    RUN_STATE_SCHEMA_VERSION,
    RunStateError,
    apply_run_state,
    restore_app_state_snapshot,
    serialize_run_state,
    snapshot_app_state,
    validate_run_state_document,
)
from guiskindose.gui.run_state_equipment import PendingEntry, build_pending
from guiskindose.gui.run_state_trial import trial_confirm_equipment
from guiskindose.gui.settings_builder import bind_equipment_session, build_settings
from guiskindose.gui.state import AppState, abandon_staged_equipment

_DICOM = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "guiskindose"
    / "example_data"
    / "RDSR"
    / "siemens_axiom_artis.dcm"
)


def _profile_doc(profile_id: str) -> dict[str, Any]:
    """Single memory profile matching the approved Siemens fixture."""
    return {
        "schema_version": 1,
        "profiles": [
            {
                "profile_id": profile_id,
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
    return assemble_session(documents=[_profile_doc("v2-doc")])


def _plane_state(session: Any | None) -> AppState:
    """Fast plane-phantom state, optionally with the session bound."""
    state = AppState()
    state.phantom_model = "plane"
    if session is not None:
        bind_equipment_session(state, session)
    return state


def _loaded_state(session: Any) -> AppState:
    """State with one session-minted DICOM exam loaded."""
    state = _plane_state(session)
    assert load_rdsr(_DICOM, state)[0]
    return state


def _mapping_of(state: AppState, index: int = 0) -> dict[str, Any]:
    """Canonical producer mapping of one loaded exam's capture."""
    return capture_to_mapping(state.loaded_exams[index].equipment_capture)


def _document(state: AppState) -> dict[str, Any]:
    """Serialize a realistic v2 document for the given live state."""
    return serialize_run_state(build_settings(state), state, created="2026-10-14T00:00:00+00:00")


def test_writer_always_v2_with_null() -> None:
    """Equipment-less exports are v2 with an explicit null section."""
    document = _document(AppState())
    assert document["schema"] == RUN_STATE_SCHEMA
    assert document["schema_version"] == RUN_STATE_SCHEMA_VERSION == 2
    assert "equipment" in document
    assert document["equipment"] is None


def test_writer_envelope_from_results(session: Any) -> None:
    """Loaded captures serialize positionally with full revalidation."""
    state = _loaded_state(session)
    document = _document(state)
    section = document["equipment"]
    assert section["schema_version"] == 1
    assert section["mode"] == "coordinates"
    assert len(section["captures"]) == 1
    assert section["captures"][0]["event_count"] == len(state.loaded_exams[0].normalized_data)


def test_writer_passthrough_excludes_equipment(session: Any) -> None:
    """The writer owns equipment: passthrough never carries it forward."""
    state = _loaded_state(session)
    document = _document(state)
    document["mystery"] = {"note": "kept"}
    fresh = AppState()
    result = apply_run_state(document, fresh)
    assert result.passthrough == {"mystery": {"note": "kept"}}
    assert fresh.equipment_pending is not None
    assert len(fresh.equipment_pending) == 1


def test_validate_v1_with_equipment_warns_not_errors() -> None:
    """A v1 document carrying equipment keeps the tolerant reader plus warning."""
    document = _document(AppState())
    document["schema_version"] = 1
    document["equipment"] = {"schema_version": 1, "mode": "coordinates", "captures": []}
    document["gui_state"]["exams"] = []
    validate_run_state_document(document)
    fresh = AppState()
    result = apply_run_state(document, fresh)
    assert any("newer version" in warning for warning in result.warnings)
    assert fresh.equipment_pending is None


def test_validate_v1_session_warns_and_retains(session: Any) -> None:
    """v1 imports warn on live equipment and retain every home."""
    state = _plane_state(session)
    document = _document(AppState())
    document["schema_version"] = 1
    document.pop("equipment", None)
    result = apply_run_state(document, state)
    assert any("predates equipment capture" in warning for warning in result.warnings)
    assert state.equipment_profile_session is session


def test_validate_bad_envelope_codes(session: Any) -> None:
    """Tampered and future-versioned envelopes map to stable codes."""
    state = _loaded_state(session)
    good = _mapping_of(state)
    tampered = copy.deepcopy(good)
    tampered["effective_coordinates"]["translation_offset"]["x"] += 1.0
    document = _document(AppState())
    document["equipment"] = {"schema_version": 1, "mode": "coordinates", "captures": [tampered]}
    document["gui_state"]["exams"] = [{}]
    with pytest.raises(RunStateError) as excinfo:
        validate_run_state_document(document)
    assert excinfo.value.code == "invalid_equipment_capture"
    future = copy.deepcopy(document)
    future["equipment"] = {"schema_version": 2, "mode": "coordinates", "captures": [good]}
    with pytest.raises(RunStateError) as excinfo:
        validate_run_state_document(future)
    assert excinfo.value.code == "unsupported_equipment_capture_version"


def test_null_absent_skip_silently() -> None:
    """Absent or null v2 equipment validates without staging or equipment notices."""
    document = _document(AppState())
    document["equipment"] = None
    validate_run_state_document(document)
    fresh = AppState()
    result = apply_run_state(document, fresh)
    assert fresh.equipment_pending is None
    assert not any("equipment" in warning for warning in result.warnings)
    document2 = _document(AppState())
    del document2["equipment"]
    validate_run_state_document(document2)
    result2 = apply_run_state(document2, AppState())
    assert not any("equipment" in warning for warning in result2.warnings)


def _staged_document(state: AppState, extra_exam: dict[str, Any], extra_capture: Any) -> dict[str, Any]:
    """v2 document pairing the live exam with one unloaded tail position."""
    document = _document(state)
    live_mapping = _mapping_of(state)
    document["equipment"] = {
        "schema_version": 1,
        "mode": "coordinates",
        "captures": [live_mapping, extra_capture],
    }
    document["gui_state"]["exams"] = [{}, extra_exam]
    return document


def test_apply_stages_pending_tail(session: Any) -> None:
    """Unloaded tail positions stage validated entries with carried fields."""
    state = _loaded_state(session)
    document = _staged_document(
        state,
        {"swap_lat_lon": True, "d_lon": 9.0, "table_origin_override": None},
        None,
    )
    result = apply_run_state(document, state)
    assert result.applied_exams == 1
    pending = state.equipment_pending
    assert pending is not None
    assert len(pending) == 1
    assert pending[0].capture is None
    assert pending[0].swap_lat_lon is True
    assert pending[0].d_lon == 9.0
    assert state.loaded_exams[0].equipment_capture is not None


def test_apply_mismatch_rolls_back_with_prior_pending(session: Any) -> None:
    """A trial breach preserves results, session, and previously staged entries."""
    empty = assemble_session(documents=[])
    state = _plane_state(empty)
    donor = _loaded_state(session)
    first = _staged_document(donor, {}, None)
    staged = apply_run_state(first, state)
    assert staged.applied_exams == 0
    assert state.equipment_pending is not None
    held_pending = state.equipment_pending
    state.psd = 5.0
    state.output = {"sentinel": True}
    broken = copy.deepcopy(first)
    broken["equipment"]["captures"][0]["event_count"] += 1
    with pytest.raises(RunStateError) as excinfo:
        apply_run_state(broken, state)
    assert excinfo.value.code == "invalid_equipment_capture"
    assert state.equipment_pending is held_pending
    assert state.psd == 5.0
    assert state.output == {"sentinel": True}
    assert state.equipment_profile_session is empty
    assert state.loaded_exams == []


def test_apply_flags_differ_refuses_atomically(session: Any) -> None:
    """A geometry-changing flag request refuses before any mutation."""
    state = _loaded_state(session)
    document = _document(state)
    document["equipment"] = {
        "schema_version": 1,
        "mode": "coordinates",
        "captures": [_mapping_of(state)],
    }
    document["gui_state"]["exams"] = [{"swap_lat_lon": True}]
    document["gui_state"]["swap_lat_lon"] = True
    with pytest.raises(RunStateError) as excinfo:
        apply_run_state(document, state)
    assert excinfo.value.code == "equipment_geometry_mismatch"
    assert state.loaded_exam_meta[0]["swap_lat_lon"] is False
    assert state.equipment_pending is None


@pytest.mark.parametrize("section_kind", ["captured", "null_slot", "null_section", "absent"])
def test_global_flag_change_cannot_bypass_capture_geometry(session: Any, section_kind: str) -> None:
    """Single-exam global coupling is part of the pre-mutation proof."""
    state = _loaded_state(session)
    capture = state.loaded_exams[0].equipment_capture
    document = _document(state)
    if section_kind == "null_slot":
        document["equipment"]["captures"] = [None]
    elif section_kind == "null_section":
        document["equipment"] = None
    elif section_kind == "absent":
        del document["equipment"]
    document["gui_state"]["swap_lat_lon"] = True
    with pytest.raises(RunStateError) as excinfo:
        apply_run_state(document, state)
    assert excinfo.value.code == "equipment_geometry_mismatch"
    assert state.swap_lat_lon is False
    assert state.loaded_exam_meta[0]["swap_lat_lon"] is False
    assert state.loaded_exams[0].equipment_capture is capture


def test_null_loaded_preserves_authority(session: Any) -> None:
    """A null entry over a loaded exam preserves its capture and snapshot."""
    state = _loaded_state(session)
    capture = state.loaded_exams[0].equipment_capture
    snapshot = state.loaded_exams[0].normalization_snapshot
    document = _document(state)
    document["equipment"] = {"schema_version": 1, "mode": "coordinates", "captures": [None]}
    document["gui_state"]["exams"] = [{}]
    result = apply_run_state(document, state)
    assert result.applied_exams == 1
    assert state.loaded_exams[0].equipment_capture is capture
    assert state.loaded_exams[0].normalization_snapshot is snapshot


def test_loaded_multi_restore_confirms_and_publishes(session: Any, tmp_path: Path) -> None:
    """Already-loaded multi-exam restores match positionally and calculates."""
    from guiskindose.gui.exam_loaders import load_tabular
    from guiskindose.gui.helpers import run_calculation

    header = (
        "Manufacturer,ManufacturerModelName,IrradiationEventType,AcquisitionPlane,"
        "DistanceSourcetoDetector_mm,DistanceSourcetoIsocenter_mm,"
        "TableLongitudinalPosition_mm,TableLateralPosition_mm,TableHeightPosition_mm,CollimatedFieldArea_m2,"
        "XRayFilterMaterial,XRayFilterThicknessMinimum_mm,XRayFilterThicknessMaximum_mm,"
        "PositionerPrimaryAngle_deg,PositionerSecondaryAngle_deg,KVP_kV,DoseRP_Gy"
    )
    row = (
        "Siemens,AXIOM-Artis,Fluoroscopy,Single Plane,1198,785,37.8,40.6,294.1,0.01,"
        "Copper or Copper compound,0.6,0.6,-0.1,-1.1,77.0,0.00003"
    )
    first = tmp_path / "first.csv"
    first.write_text(header + "\n" + row + "\n", encoding="utf-8")
    second = tmp_path / "second.csv"
    second.write_text(header + "\n" + row + "\n", encoding="utf-8")
    state = _plane_state(session)
    assert load_tabular(first, state)[0]
    assert load_tabular(second, state)[0]
    document = _document(state)
    result = apply_run_state(document, state)
    assert result.applied_exams == 2
    assert state.equipment_pending is None
    assert all(e.equipment_capture is not None for e in state.loaded_exams)
    assert run_calculation(state)[0]
    assert state.multi_exam_result is not None
    assert len(state.multi_exam_result.exams) == 2


def test_session_pending_conflict_rejects_at_import(session: Any) -> None:
    """Nonempty session plus staged captures refuse pre-mutation, zero I/O."""
    state = _plane_state(session)
    donor = _loaded_state(session)
    document = _document(AppState())
    document["equipment"] = {
        "schema_version": 1,
        "mode": "coordinates",
        "captures": [_mapping_of(donor)],
    }
    document["gui_state"]["exams"] = [{}]
    with pytest.raises(RunStateError) as excinfo:
        apply_run_state(document, state)
    assert excinfo.value.code == "invalid_equipment_capture"
    assert state.equipment_pending is None
    assert state.equipment_profile_session is session
    assert state.loaded_exams == []


def test_empty_session_null_envelope_stages() -> None:
    """An empty session behaves session-free: null tails stage normally."""
    empty = assemble_session(documents=[])
    state = _plane_state(empty)
    document = _document(AppState())
    document["equipment"] = {"schema_version": 1, "mode": "coordinates", "captures": [None]}
    document["gui_state"]["exams"] = [{}]
    result = apply_run_state(document, state)
    assert result.applied_exams == 0
    assert state.equipment_pending is not None
    assert len(state.equipment_pending) == 1


def test_live_gt_doc_rejects_with_equipment(session: Any) -> None:
    """More live exams than document exams always fails, equipment or not."""
    state = _loaded_state(session)
    document = _document(AppState())
    document["gui_state"]["exams"] = []
    document["equipment"] = {"schema_version": 1, "mode": "coordinates", "captures": []}
    with pytest.raises(RunStateError, match=r"0 exam.*1 loaded"):
        apply_run_state(document, state)


def test_resequence_gate_is_headless() -> None:
    """The re-parse refusal rule needs no UI to evaluate."""
    pytest.importorskip("nicegui")
    from guiskindose.gui.tabs._run_config import _equipment_blocks_resequence

    assert _equipment_blocks_resequence(AppState()) is False


def test_export_gate_is_headless() -> None:
    """The save refusal rule needs no UI to evaluate."""
    pytest.importorskip("nicegui")
    from guiskindose.gui.tabs._run_config import _pending_blocks_export

    assert _pending_blocks_export(AppState()) is False


def test_import_messages_cover_equipment_codes() -> None:
    """Every locked capture code maps to a fixed user-facing message."""
    pytest.importorskip("nicegui")
    from guiskindose.gui.tabs._run_config import _IMPORT_ERROR_MESSAGES

    for code in (
        "invalid_equipment_capture",
        "unsupported_equipment_capture_version",
        "equipment_geometry_mismatch",
    ):
        assert code in _IMPORT_ERROR_MESSAGES
        assert isinstance(_IMPORT_ERROR_MESSAGES[code], str)


def test_pending_entry_validation() -> None:
    """Pending entries refuse mistyped flags, offsets, and overrides."""
    base = {
        "capture": None,
        "swap_lat_lon": False,
        "flip_ap1": False,
        "flip_ap2": False,
        "flip_tx": False,
        "flip_ty": False,
        "flip_tz": False,
        "d_lon": 0.0,
        "d_ver": 0.0,
        "d_lat": 0.0,
        "table_origin_override": None,
    }
    assert PendingEntry(**base).swap_lat_lon is False
    bad_flag: Any = dict(base, swap_lat_lon=1)
    with pytest.raises(RunStateError):
        PendingEntry(**bad_flag)
    bad_offset: Any = dict(base, d_lon=float("nan"))
    with pytest.raises(RunStateError):
        PendingEntry(**bad_offset)
    huge_offset: Any = dict(base, d_lon=10**400)
    with pytest.raises(RunStateError):
        PendingEntry(**huge_offset)
    bad_override: Any = dict(base, table_origin_override="elsewhere")
    with pytest.raises(RunStateError):
        PendingEntry(**bad_override)
    hostile_override: Any = dict(base, table_origin_override={"x": 0.0, "note": "SENTINEL_PRIVATE_TEXT"})
    with pytest.raises(RunStateError):
        PendingEntry(**hostile_override)
    frozen = PendingEntry(**base)
    with pytest.raises(dataclasses.FrozenInstanceError):
        frozen.__setattr__("d_lon", 1.0)


def test_pending_override_is_immutable_and_copyable() -> None:
    """Staged overrides cannot be rewritten through retained references."""
    from guiskindose.gui.run_state_equipment import _FrozenOverride

    source = {"x": 1.0, "y": 2.0, "z": -3.0}
    entry = PendingEntry(
        capture=None,
        swap_lat_lon=False,
        flip_ap1=False,
        flip_ap2=False,
        flip_tx=False,
        flip_ty=False,
        flip_tz=False,
        d_lon=0.0,
        d_ver=0.0,
        d_lat=0.0,
        table_origin_override=dict(source),
    )
    assert source == {"x": 1.0, "y": 2.0, "z": -3.0}
    stored = entry.table_origin_override
    assert isinstance(stored, _FrozenOverride)
    assert stored is not source
    with pytest.raises(TypeError):
        stored["x"] = 99.0
    import copy

    assert copy.deepcopy(entry).table_origin_override == stored
    text = repr(entry)
    assert "PendingEntry(" in text
    assert "1.0" not in text
    assert "2.0" not in text
    assert "-3.0" not in text


def test_pending_entry_rejects_forged_capture(session: Any) -> None:
    """Full capture revalidation (not a type check) guards construction."""
    state = _loaded_state(session)
    genuine = state.loaded_exams[0].equipment_capture
    forged = copy.copy(genuine)
    object.__setattr__(forged, "event_count", genuine.event_count + 1)
    base = {
        "capture": forged,
        "swap_lat_lon": False,
        "flip_ap1": False,
        "flip_ap2": False,
        "flip_tx": False,
        "flip_ty": False,
        "flip_tz": False,
        "d_lon": 0.0,
        "d_ver": 0.0,
        "d_lat": 0.0,
        "table_origin_override": None,
    }
    with pytest.raises(RunStateError) as excinfo:
        PendingEntry(**base)
    assert excinfo.value.code == "invalid_equipment_capture"
    assert genuine.event_count != forged.event_count


def test_revalidate_rebuilds_before_io() -> None:
    """The consuming-boundary rebuild re-runs full validation cheaply."""
    from guiskindose.gui.run_state_equipment import revalidate_pending

    entry = PendingEntry(
        capture=None,
        swap_lat_lon=True,
        flip_ap1=False,
        flip_ap2=False,
        flip_tx=False,
        flip_ty=False,
        flip_tz=False,
        d_lon=1.0,
        d_ver=0.0,
        d_lat=0.0,
        table_origin_override=None,
    )
    rebuilt = revalidate_pending(entry)
    assert rebuilt == entry
    assert rebuilt is not entry
    with pytest.raises(RunStateError):
        revalidate_pending({"capture": None})


def test_build_pending_units() -> None:
    """Pending assembly needs decoded contexts plus document exams."""
    assert build_pending(None, []) is None
    assert build_pending(None, "nope") is None
    assert build_pending((), []) is None
    with pytest.raises(RunStateError):
        build_pending((None,), [])


def test_snapshot_covers_pending() -> None:
    """Failed-import rollback restores staged entries alongside results."""
    state = AppState()
    entry = PendingEntry(
        capture=None,
        swap_lat_lon=False,
        flip_ap1=False,
        flip_ap2=False,
        flip_tx=False,
        flip_ty=False,
        flip_tz=False,
        d_lon=0.0,
        d_ver=0.0,
        d_lat=0.0,
        table_origin_override=None,
    )
    state.equipment_pending = (entry,)
    snap = snapshot_app_state(state)
    state.equipment_pending = None
    state.psd = 1.0
    restore_app_state_snapshot(state, snap)
    assert state.equipment_pending is not None
    assert len(state.equipment_pending) == 1
    # Results are not snapshotted (left alone by rollback, never rewritten).
    assert state.psd == 1.0


def test_abandon_helper_is_conservative() -> None:
    """Abandoning reports whether anything was staged; nothing else moves."""
    state = AppState()
    assert abandon_staged_equipment(state) is False
    state.equipment_pending = (
        PendingEntry(
            capture=None,
            swap_lat_lon=False,
            flip_ap1=False,
            flip_ap2=False,
            flip_tx=False,
            flip_ty=False,
            flip_tz=False,
            d_lon=0.0,
            d_ver=0.0,
            d_lat=0.0,
            table_origin_override=None,
        ),
    )
    state.psd = 2.0
    assert abandon_staged_equipment(state) is True
    assert state.equipment_pending is None
    assert state.psd == 2.0


def test_writer_refuses_pending() -> None:
    """The public writer refuses staged entries instead of dropping them."""
    from guiskindose.gui.run_state_equipment import PendingEntry

    state = AppState()
    state.equipment_pending = (
        PendingEntry(
            capture=None,
            swap_lat_lon=False,
            flip_ap1=False,
            flip_ap2=False,
            flip_tx=False,
            flip_ty=False,
            flip_tz=False,
            d_lon=0.0,
            d_ver=0.0,
            d_lat=0.0,
            table_origin_override=None,
        ),
    )
    with pytest.raises(RunStateError) as excinfo:
        _document(state)
    assert excinfo.value.code == "invalid_equipment_capture"
    assert state.equipment_pending is not None


def test_emission_bounds_before_comprehension() -> None:
    """Oversized exam lists refuse before any entry is materialized."""
    from guiskindose.gui.run_state_equipment import equipment_section_for_document

    with pytest.raises(RunStateError) as excinfo:
        equipment_section_for_document([object()] * 65)
    assert excinfo.value.code == "invalid_equipment_capture"
    assert equipment_section_for_document([object()] * 64) is None


def test_pending_bounds_before_materialization() -> None:
    """Oversized staging inputs refuse before any entry is validated."""
    with pytest.raises(RunStateError) as excinfo:
        build_pending([None] * 65, [{}] * 65)
    assert excinfo.value.code == "invalid_equipment_capture"


def test_trial_needs_document_exams() -> None:
    """Trial rejects non-list exam homes before decoding anything."""
    state = AppState()
    with pytest.raises(RunStateError):
        trial_confirm_equipment(None, doc_exams="nope", app_state=state)


def _dup_profile_doc(profile_id: str) -> dict[str, Any]:
    """Same Siemens leaves under a different profile identity."""
    doc = _profile_doc("unused-id")
    doc["profiles"][0]["profile_id"] = profile_id
    return doc


def test_equivalent_capture_preserves_live(session: Any) -> None:
    """A canonically identical import validates and preserves live authority."""
    state = _loaded_state(session)
    live_capture = state.loaded_exams[0].equipment_capture
    document = _document(state)
    result = apply_run_state(document, state)
    assert result.applied_exams == 1
    assert state.loaded_exams[0].equipment_capture is live_capture
    assert state.equipment_pending is None


def test_conflicting_provenance_rejects_before_mutation() -> None:
    """Same geometry but different provenance refuses as conflicting import.

    Two profiles share maker, model, and leaves but differ in identity, so
    both confirm against one frame while their canonical mappings disagree:
    the trial must reject rather than silently keep the live authority.
    """
    session_a = assemble_session(documents=[_dup_profile_doc("dup-a")])
    session_b = assemble_session(documents=[_dup_profile_doc("dup-b")])
    live = _plane_state(session_a)
    assert load_rdsr(_DICOM, live)[0]
    donor = _plane_state(session_b)
    assert load_rdsr(_DICOM, donor)[0]
    assert live.loaded_exams[0].equipment_capture != donor.loaded_exams[0].equipment_capture
    document = _document(AppState())
    document["equipment"] = {
        "schema_version": 1,
        "mode": "coordinates",
        "captures": [_mapping_of(donor)],
    }
    document["gui_state"]["exams"] = [{}]
    old_meta = dict(live.loaded_exam_meta[0])
    with pytest.raises(RunStateError) as excinfo:
        apply_run_state(document, live)
    assert excinfo.value.code == "invalid_equipment_capture"
    assert "Exam 1" in str(excinfo.value)
    assert live.loaded_exam_meta[0] == old_meta
    assert live.loaded_exams[0].equipment_capture is not None
    assert live.equipment_pending is None


def test_publish_partial_failure_rolls_back(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """A late snapshot failure restores original exams and metas atomically."""
    import guiskindose.gui.run_state_equipment as equipment_module

    header = (
        "Manufacturer,ManufacturerModelName,IrradiationEventType,AcquisitionPlane,"
        "DistanceSourcetoDetector_mm,DistanceSourcetoIsocenter_mm,"
        "TableLongitudinalPosition_mm,TableLateralPosition_mm,TableHeightPosition_mm,CollimatedFieldArea_m2,"
        "XRayFilterMaterial,XRayFilterThicknessMinimum_mm,XRayFilterThicknessMaximum_mm,"
        "PositionerPrimaryAngle_deg,PositionerSecondaryAngle_deg,KVP_kV,DoseRP_Gy"
    )
    row = (
        "Siemens,AXIOM-Artis,Fluoroscopy,Single Plane,1198,785,37.8,40.6,294.1,0.01,"
        "Copper or Copper compound,0.6,0.6,-0.1,-1.1,77.0,0.00003"
    )
    from guiskindose.gui.exam_loaders import load_tabular

    session = assemble_session(documents=[_profile_doc("v2-pub")])
    state = _plane_state(session)
    for name in ("p1.csv", "p2.csv"):
        path = tmp_path / name
        path.write_text(header + "\n" + row + "\n", encoding="utf-8")
        assert load_tabular(path, state)[0]
    mapping = _mapping_of(state, 0)
    for exam in state.loaded_exams:
        exam.equipment_capture = None
    document = _document(AppState())
    document["equipment"] = {"schema_version": 1, "mode": "coordinates", "captures": [mapping, mapping]}
    document["gui_state"]["exams"] = [{}, {}]
    old_exams = list(state.loaded_exams)
    old_metas = [dict(meta) for meta in state.loaded_exam_meta]
    calls: list[str] = []
    real_prepare = equipment_module.prepare_captured_candidate

    def _fail_second(*args: Any, **kwargs: Any) -> Any:
        calls.append("prepare")
        if len(calls) == 2:
            raise ValueError("injected snapshot fault")
        return real_prepare(*args, **kwargs)

    monkeypatch.setattr(equipment_module, "prepare_captured_candidate", _fail_second)
    snap = snapshot_app_state(state)
    with pytest.raises(ValueError, match="injected snapshot fault"):
        apply_run_state(document, state)
    restore_app_state_snapshot(state, snap)
    assert len(state.loaded_exams) == len(old_exams)
    assert all(current is original for current, original in zip(state.loaded_exams, old_exams, strict=True))
    assert [exam.equipment_capture for exam in state.loaded_exams] == [None, None]
    assert len(state.loaded_exam_meta) == len(old_metas)
    assert [m["file_name"] for m in state.loaded_exam_meta] == [m["file_name"] for m in old_metas]
    assert [m["d_lon"] for m in state.loaded_exam_meta] == [m["d_lon"] for m in old_metas]
    assert calls.count("prepare") == 2
