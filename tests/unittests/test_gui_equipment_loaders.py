"""GUI loader authority: receipts, mint-on-final-frame, atomicity, bounds."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest import mock

import pytest

from guiskindose.equipment_capture import frame_geometry_rows, geometry_digest_v1
from guiskindose.equipment_profiles import assemble_session
from guiskindose.gui.exam_loaders import (
    _check_session_event_total,
    _check_session_exam_count,
    load_rdsr,
    load_tabular,
)
from guiskindose.gui.settings_builder import bind_equipment_session
from guiskindose.gui.state import AppState
from guiskindose.input_adapters.models import InputAdapterResult

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
_UNKNOWN_ROW = _RAW_ROW.replace("Siemens,AXIOM-Artis", "Acme,Unknown-Model")


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
    return assemble_session(documents=[_profile_doc("gui-loader")])


def _bound_state(session: Any) -> AppState:
    """Empty state with the session bound (import-before-load satisfied)."""
    state = AppState()
    bind_equipment_session(state, session)
    return state


def _write_csv(path: Path, rows: list[str]) -> Path:
    """Write a synthetic raw CSV (tmp only, never tracked)."""
    path.write_text(_RAW_HEADER + "\n" + "\n".join(rows) + "\n", encoding="utf-8")
    return path


def test_dicom_mints_capture_on_final_frame(session: Any) -> None:
    """A bound DICOM load attaches a capture over the accepted frame."""
    state = _bound_state(session)
    ok, _ = load_rdsr(_DICOM, state)
    assert ok
    exam = state.loaded_exams[0]
    assert exam.equipment_capture is not None
    assert exam.equipment_capture.event_count == len(exam.normalized_data)
    assert exam.equipment_receipt is None


def test_dicom_pure_load_unchanged() -> None:
    """Without a session no receipt is requested and no capture is minted."""
    state = AppState()
    ok, _ = load_rdsr(_DICOM, state)
    assert ok
    exam = state.loaded_exams[0]
    assert exam.equipment_capture is None
    assert exam.equipment_receipt is None


def test_tabular_mint_honors_transform_flags(session: Any, tmp_path: Path) -> None:
    """GUI import flags shape the final frame the capture digests."""
    state = _bound_state(session)
    state.swap_lat_lon = True
    state.flip_ap1 = True
    ok, _ = load_tabular(_write_csv(tmp_path / "flags.csv", [_RAW_ROW]), state)
    assert ok
    exam = state.loaded_exams[0]
    assert exam.equipment_capture is not None
    assert exam.equipment_receipt is None
    frame = exam.normalized_data
    assert exam.equipment_capture.geometry_hash == geometry_digest_v1(frame_geometry_rows(frame, len(frame)))
    assert exam.equipment_capture.event_count == len(frame)


def test_tabular_fallback_exam_mints_default_capture(session: Any, tmp_path: Path) -> None:
    """An unmatched scanner under an active session captures default provenance."""
    state = _bound_state(session)
    ok, _ = load_tabular(_write_csv(tmp_path / "unknown.csv", [_UNKNOWN_ROW]), state)
    assert ok
    capture = state.loaded_exams[0].equipment_capture
    assert capture is not None
    assert capture.level == "default"


def test_normalized_schema_refuses_session(session: Any) -> None:
    """Pre-transformed input under an active session fails closed, state kept."""
    state = _bound_state(session)
    state.d_lon = 5.0
    ok, _ = load_tabular(_NORMALIZED_MULTI, state)
    assert not ok
    assert state.loaded_exams == []
    assert state.d_lon == 5.0


def test_replace_failure_restores_dropped_exams(session: Any, tmp_path: Path) -> None:
    """A failed re-parse restores the dropped exams at exact positions."""
    first = _write_csv(tmp_path / "one.csv", [_RAW_ROW])
    state = _bound_state(session)
    assert load_tabular(first, state)[0]
    assert load_tabular(_write_csv(tmp_path / "two.csv", [_RAW_ROW]), state)[0]
    assert len(state.loaded_exams) == 2
    first.write_text("not,a\nvalid,row\n", encoding="utf-8")
    ok, _ = load_tabular(first, state, replace_existing=True)
    assert not ok
    assert len(state.loaded_exams) == 2
    assert [m["file_name"] for m in state.loaded_exam_meta] == ["one.csv", "two.csv"]


def test_mint_failure_truncates_file_appends(session: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A late mint breach drops only this file's exams; prior state survives."""
    import guiskindose.gui.exam_loaders as loaders

    calls: list[str] = []
    real_mint = loaders.capture_from_receipt

    def _fail_second(*args: Any, **kwargs: Any) -> Any:
        calls.append("mint")
        if len(calls) == 2:
            from guiskindose.equipment_profiles.capture import CODE_INVALID_EQUIPMENT_CAPTURE, CaptureError

            raise CaptureError("boom", CODE_INVALID_EQUIPMENT_CAPTURE)
        return real_mint(*args, **kwargs)

    monkeypatch.setattr(loaders, "capture_from_receipt", _fail_second)
    state = _bound_state(session)
    assert load_tabular(_write_csv(tmp_path / "keep.csv", [_RAW_ROW]), state)[0]
    state.d_lon = 7.0
    ok, msg = load_tabular(_write_csv(tmp_path / "drop.csv", [_RAW_ROW]), state)
    assert not ok
    assert "drop.csv" not in msg
    assert len(state.loaded_exams) == 1
    assert state.loaded_exam_meta[0]["file_name"] == "keep.csv"
    assert state.d_lon == 7.0
    assert calls == ["mint", "mint"]


def test_dicom_rebuild_failure_preserves_state(session: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """A post-append publication fault leaves every live home identical."""
    import guiskindose.gui.exam_loaders as loaders

    state = _bound_state(session)
    assert load_rdsr(_DICOM, state)[0]
    sentinel_raw: Any = object()
    state.rdsr_raw_df = sentinel_raw
    old_exams = state.loaded_exams
    old_metas = state.loaded_exam_meta
    old_df = state.rdsr_df
    state.psd = 4.25
    state.output = {"sentinel": True}

    def _boom(candidate: Any) -> Any:
        raise RuntimeError("injected publication fault")

    monkeypatch.setattr(loaders, "rebuild_rdsr_df", _boom)
    ok, _ = load_rdsr(_DICOM, state)
    assert not ok
    assert state.loaded_exams is old_exams
    assert state.loaded_exam_meta is old_metas
    assert state.rdsr_df is old_df
    assert state.rdsr_raw_df is sentinel_raw
    assert state.psd == 4.25
    assert state.output == {"sentinel": True}
    assert state.equipment_profile_session is session


def test_dicom_mint_failure_preserves_raw(session: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """B1 repro: a mint breach must not publish the raw preview either."""
    import guiskindose.gui.exam_loaders as loaders

    state = _bound_state(session)
    assert load_rdsr(_DICOM, state)[0]
    sentinel_raw: Any = object()
    state.rdsr_raw_df = sentinel_raw
    old_exams = state.loaded_exams

    def _boom(*args: Any, **kwargs: Any) -> Any:
        raise ValueError("injected mint fault")

    monkeypatch.setattr(loaders, "capture_from_receipt", _boom)
    ok, _ = load_rdsr(_DICOM, state)
    assert not ok
    assert state.loaded_exams is old_exams
    assert len(state.loaded_exams) == 1
    assert state.rdsr_raw_df is sentinel_raw


def test_tabular_finalize_failure_preserves_state(session: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A finalization fault after appends still publishes nothing."""
    import guiskindose.gui.exam_loaders as loaders

    state = _bound_state(session)
    assert load_tabular(_write_csv(tmp_path / "keep.csv", [_RAW_ROW]), state)[0]
    old_exams = state.loaded_exams
    old_name = state.file_name
    old_provenance = state.import_provenance

    def _boom(candidate: Any, *args: Any) -> Any:
        raise RuntimeError("injected finalize fault")

    monkeypatch.setattr(loaders, "rebuild_rdsr_df", _boom)
    ok, _ = load_tabular(_write_csv(tmp_path / "drop.csv", [_RAW_ROW]), state)
    assert not ok
    assert state.loaded_exams is old_exams
    assert len(state.loaded_exams) == 1
    assert state.file_name == old_name
    assert state.import_provenance is old_provenance


@pytest.mark.parametrize("escape", [KeyboardInterrupt, SystemExit])
def test_dicom_cancellation_rolls_back_and_propagates(
    session: Any, monkeypatch: pytest.MonkeyPatch, escape: Any
) -> None:
    """Cancellation during publication propagates with live state identical."""
    import guiskindose.gui.exam_loaders as loaders

    state = _bound_state(session)
    assert load_rdsr(_DICOM, state)[0]
    old_exams = state.loaded_exams
    sentinel_raw: Any = object()
    state.rdsr_raw_df = sentinel_raw

    def _cancel(candidate: Any) -> Any:
        raise escape()

    monkeypatch.setattr(loaders, "rebuild_rdsr_df", _cancel)
    with pytest.raises(escape):
        load_rdsr(_DICOM, state)
    assert state.loaded_exams is old_exams
    assert state.rdsr_raw_df is sentinel_raw


def test_tabular_cancellation_rolls_back_and_propagates(
    session: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cancellation during finalization propagates with live state identical."""
    import guiskindose.gui.exam_loaders as loaders

    state = _bound_state(session)
    assert load_tabular(_write_csv(tmp_path / "keep.csv", [_RAW_ROW]), state)[0]
    old_exams = state.loaded_exams

    def _cancel(candidate: Any, *args: Any) -> Any:
        raise SystemExit()

    monkeypatch.setattr(loaders, "rebuild_rdsr_df", _cancel)
    drop = _write_csv(tmp_path / "drop.csv", [_RAW_ROW])
    with pytest.raises(SystemExit):
        load_tabular(drop, state)
    assert state.loaded_exams is old_exams
    assert len(state.loaded_exams) == 1


def test_pure_failure_preserves_every_home(tmp_path: Path) -> None:
    """A failed pure load leaves exams, preview, raw, display, offsets, results."""
    state = AppState()
    assert load_tabular(_write_csv(tmp_path / "keep.csv", [_RAW_ROW]), state)[0]
    state.d_lon = 7.0
    state.psd = 3.5
    state.output = {"sentinel": True}
    old_exams = state.loaded_exams
    old_metas = state.loaded_exam_meta
    old_df = state.rdsr_df
    old_raw = state.rdsr_raw_df
    old_name = state.file_name
    bad = tmp_path / "bad.csv"
    bad.write_text("not,a\nvalid,row\n", encoding="utf-8")
    ok, _ = load_tabular(bad, state)
    assert not ok
    assert state.loaded_exams is old_exams
    assert state.loaded_exam_meta is old_metas
    assert state.rdsr_df is old_df
    assert state.rdsr_raw_df is old_raw
    assert state.file_name == old_name
    assert state.d_lon == 7.0
    assert state.psd == 3.5
    assert state.output == {"sentinel": True}


def test_replace_preserves_existing_order(tmp_path: Path) -> None:
    """Re-parse drops and re-appends at the end: existing order behavior."""
    state = AppState()
    assert load_tabular(_write_csv(tmp_path / "one.csv", [_RAW_ROW]), state)[0]
    assert load_tabular(_write_csv(tmp_path / "two.csv", [_RAW_ROW]), state)[0]
    ok, _ = load_tabular(tmp_path / "one.csv", state, replace_existing=True)
    assert ok
    assert [m["file_name"] for m in state.loaded_exam_meta] == ["two.csv", "one.csv"]
    assert [len(e.normalized_data) for e in state.loaded_exams] == [1, 1]


def test_registry_interception_is_effective(session: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The tabular spy patches the actual bound lookup, with a call-count proof."""
    import guiskindose.input_adapters.registry as registry

    calls: list[str] = []
    real_load = registry.read_and_normalize_input

    def _spy(*args: Any, **kwargs: Any) -> Any:
        calls.append("registry")
        return real_load(*args, **kwargs)

    monkeypatch.setattr(registry, "read_and_normalize_input", _spy)
    state = _bound_state(session)
    assert load_tabular(_write_csv(tmp_path / "spy.csv", [_RAW_ROW]), state)[0]
    assert calls == ["registry"]
    assert state.loaded_exams[0].equipment_capture is not None


def test_dicom_loader_call_is_effective(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The DICOM normalizer spy patches the loader's bound reference."""
    import guiskindose.gui.exam_loaders as loaders

    calls: list[str] = []
    real_normalize = loaders.rdsr_normalizer

    def _spy(*args: Any, **kwargs: Any) -> Any:
        calls.append("normalizer")
        return real_normalize(*args, **kwargs)

    monkeypatch.setattr(loaders, "rdsr_normalizer", _spy)
    state = AppState()
    assert load_rdsr(_DICOM, state)[0]
    assert calls == ["normalizer"]


def test_session_exam_ceiling_refuses_before_raw_read(session: Any) -> None:
    """A 65th session exam refuses before the raw read; the file is untouched."""
    import pydicom

    state = _bound_state(session)
    assert load_rdsr(_DICOM, state)[0]
    exam = state.loaded_exams[0]
    state.loaded_exams = [exam] * 64
    state.loaded_exam_meta = state.loaded_exam_meta * 64
    with mock.patch.object(pydicom, "dcmread", wraps=pydicom.dcmread) as spy:
        ok, msg = load_rdsr(_DICOM, state)
    assert not ok
    assert "authority" in msg
    spy.assert_not_called()
    assert len(state.loaded_exams) == 64


def test_tabular_fresh_load_refuses_before_raw_read(session: Any, tmp_path: Path) -> None:
    """A 65th fresh tabular exam refuses before the adapter reads anything."""
    import guiskindose.input_adapters.registry as registry

    state = _bound_state(session)
    assert load_rdsr(_DICOM, state)[0]
    exam = state.loaded_exams[0]
    state.loaded_exams = [exam] * 64
    state.loaded_exam_meta = state.loaded_exam_meta * 64
    real_read = registry.read_and_normalize_input
    with mock.patch.object(registry, "read_and_normalize_input", wraps=real_read) as spy:
        ok, _ = load_tabular(_write_csv(tmp_path / "late.csv", [_RAW_ROW]), state)
    assert not ok
    spy.assert_not_called()
    assert len(state.loaded_exams) == 64


def test_session_event_ceiling_refuses_oversize_file(session: Any, tmp_path: Path) -> None:
    """An over-ceiling retained set refuses loudly with state untouched."""
    state = _bound_state(session)
    state.d_lon = 3.0
    big = _write_csv(tmp_path / "big.csv", [_RAW_ROW] * 10001)
    ok, _ = load_tabular(big, state)
    assert not ok
    assert state.loaded_exams == []
    assert state.d_lon == 3.0


def _shell_exam(rows: int, captured: bool = True) -> Any:
    """Loaded-exam shell (lengths only; never digested)."""
    import pandas as pd

    from guiskindose.input_adapters.models import InputProvenance

    provenance = InputProvenance(
        source_type="csv",
        schema_name="generic_rdsr_like",
        original_filename="edge.csv",
        header_row_index=0,
        detected_encoding="utf-8",
        detected_delimiter=",",
        sheet_name=None,
        column_map={},
        unit_conversions={},
    )
    exam: Any = InputAdapterResult(
        normalized_data=pd.DataFrame({"Tx": [0.0] * rows}),
        raw_data=None,
        provenance=provenance,
    )
    if captured:
        exam.equipment_capture = object()
    return exam


def test_bounds_helpers_exact_edges() -> None:
    """Ceilings admit exactly 64 exams / 10,000 events, refusing above.

    The event ceiling counts every retained row, captured or not: a null
    entry is unspecified authority, never a smaller footprint.
    """
    from guiskindose.privacy import UserFacingInputError

    state = AppState()
    marker: Any = object()
    _check_session_exam_count(0, 64, session=marker)
    with pytest.raises(UserFacingInputError, match="authority"):
        _check_session_exam_count(0, 65, session=marker)
    _check_session_exam_count(0, 1000, session=None)
    tiny = _shell_exam(2).normalized_data
    _check_session_event_total(state, [tiny] * 64, session=marker)
    state.loaded_exams = [_shell_exam(156) for _ in range(64)]
    _check_session_event_total(state, [], session=marker)
    state.loaded_exams = [_shell_exam(157) for _ in range(64)]
    with pytest.raises(UserFacingInputError, match="authority"):
        _check_session_event_total(state, [], session=marker)
    state.loaded_exams = [_shell_exam(157, captured=False) for _ in range(64)]
    with pytest.raises(UserFacingInputError, match="authority"):
        _check_session_event_total(state, [], session=marker)
    _check_session_event_total(state, [tiny] * 1000, session=None)


def test_oversized_candidate_refuses_before_list_copy(session: Any) -> None:
    class NoTraversal(list):
        def __iter__(self):
            raise AssertionError("Oversized candidate must not be copied")

    state = _bound_state(session)
    state.loaded_exams = NoTraversal([None] * 65)
    with mock.patch("guiskindose.gui.exam_loaders.pydicom.dcmread") as reader:
        ok, message = load_rdsr(_DICOM, state)
    assert not ok
    assert "authority" in message
    reader.assert_not_called()
