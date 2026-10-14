"""Tests for multi-exam analysis from captured authorities.

Captures flow from real raw loaders (DICOM Siemens/Philips, raw CSV) through
the capture producer; the multi run then calls ``analyze_multiple_exams``
directly with positional contexts and no live session. Covers per-exam and
aggregate dose-map/PSD parity with separate live runs (Siemens CFA plus
Philips ASD with different leaves, reversed order, patient offsets,
partial/default/missing-identity captures), a mixed null baseline entry,
offline analysis after source removal and bundle changes, a bad later capture
failing before any calculation, argument bounds, and caller-state
preservation. No tracked binary fixtures are used.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from guiskindose import get_path_to_example_rdsr_files, load_settings_example_json
from guiskindose.analyze_data import analyze_multiple_exams
from guiskindose.equipment_profiles import FileSource, assemble_session
from guiskindose.equipment_profiles.capture import (
    CODE_EQUIPMENT_GEOMETRY_MISMATCH,
    CODE_INVALID_EQUIPMENT_CAPTURE,
    CaptureError,
)
from guiskindose.helpers.read_and_normalize_rdsr_data import read_and_normalise_rdsr_data
from guiskindose.input_adapters.models import InputAdapterResult, InputProvenance
from guiskindose.input_adapters.registry import read_and_normalize_input
from guiskindose.main import analyze_data, analyze_input_file
from guiskindose.settings import PyskindoseSettings

_SIEMENS_DICOM = get_path_to_example_rdsr_files() / "siemens_axiom_artis.dcm"
_PHILIPS_DICOM = get_path_to_example_rdsr_files() / "philips_allura_clarity_u104.dcm"

_RAW_HEADER = (
    "Manufacturer,ManufacturerModelName,IrradiationEventType,AcquisitionPlane,"
    "DistanceSourcetoDetector_mm,DistanceSourcetoIsocenter_mm,"
    "TableLongitudinalPosition_mm,TableLateralPosition_mm,TableHeightPosition_mm,CollimatedFieldArea_m2,"
    "XRayFilterMaterial,XRayFilterThicknessMinimum_mm,XRayFilterThicknessMaximum_mm,"
    "PositionerPrimaryAngle_deg,PositionerSecondaryAngle_deg,KVP_kV,DoseRP_Gy"
)
_RAW_ROW = (
    "{maker},{model},Fluoroscopy,Single Plane,1198,785,37.8,40.6,294.1,0.01,"
    "Copper or Copper compound,0.6,0.6,-0.1,-1.1,77.0,0.00003"
)


def _siemens_coordinates() -> dict[str, Any]:
    return {
        "translation_offset": {"x": 5.0, "y": -3.5, "z": 0.0},
        "translation_direction": {"x": "-", "y": "+", "z": "+"},
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
    }


def _philips_coordinates() -> dict[str, Any]:
    return {
        "translation_offset": {"x": 1.0, "y": 2.0, "z": 3.0},
        "translation_direction": {"x": "+", "y": "+", "z": "+"},
        "rotation_direction": {
            "Ap1": "+",
            "Ap2": "-",
            "Ap3": "+",
            "At1": "+",
            "At2": "+",
            "At3": "-",
        },
        "swap_lateral_longitudinal": True,
        "field_size_mode": "ASD",
        "detector_side_length": 25.0,
    }


def _siemens_doc(profile_id: str = "m-siemens") -> dict[str, Any]:
    return {
        "schema_version": 1,
        "profiles": [
            {
                "profile_id": profile_id,
                "manufacturer": "Siemens",
                "models": ["AXIOM-Artis"],
                "coordinates": _siemens_coordinates(),
            }
        ],
    }


def _philips_doc(profile_id: str = "m-philips") -> dict[str, Any]:
    return {
        "schema_version": 1,
        "profiles": [
            {
                "profile_id": profile_id,
                "manufacturer": "Philips",
                "models": ["Allura Clarity"],
                "coordinates": _philips_coordinates(),
            }
        ],
    }


def _dose_settings(session: Any = None) -> PyskindoseSettings:
    config = load_settings_example_json()
    config["mode"] = "calculate_dose"
    if session is None:
        return PyskindoseSettings(settings=config, output_format="dict")
    return PyskindoseSettings(
        settings=config, output_format="dict", equipment_profile_session=session
    )


def _dicom_capture(dicom: Path, session: Any) -> tuple[Any, Any, PyskindoseSettings]:
    """Real DICOM normalizer receipt produced into a validated capture (no calculation)."""
    from guiskindose.equipment_capture import capture_from_receipt

    settings = _dose_settings(session)
    out: list[Any] = []
    frame = read_and_normalise_rdsr_data(str(dicom), settings, equipment_receipt_out=out)
    assert len(out) == 1
    receipt = out[0]
    context = capture_from_receipt(receipt=receipt, frame=frame, settings=settings)
    return context, frame, settings


def _wrap_exam(frame: Any, name: str) -> InputAdapterResult:
    """Wrap a normalized frame as an adapter result without live provenance."""
    provenance = InputProvenance(
        source_type="dcm",
        schema_name="rdsr",
        original_filename=name,
        header_row_index=0,
        detected_encoding="n/a",
        detected_delimiter=None,
        sheet_name=None,
        column_map={},
        unit_conversions={},
        warnings=[],
    )
    return InputAdapterResult(normalized_data=frame, raw_data=None, provenance=provenance, warnings=[])


def _densify(sparse: list[Any], size: int) -> np.ndarray:
    """Expand a sparse [(index, dose)] dose map into a dense array."""
    dense = np.zeros(size)
    for position, dose in sparse:
        dense[int(position)] = float(dose)
    return dense


def _match_profile_id(exam: Any) -> Any:
    """One exam's stored match profile ID for order-independent comparison."""
    match: Any = exam.equipment_profile_match
    return match["profile_id"]


def _code(excinfo: pytest.ExceptionInfo[CaptureError]) -> str:
    return excinfo.value.code


def _snapshot_norm(norm: Any) -> dict[str, Any]:
    return {
        "offset": (norm.trans_offset.x, norm.trans_offset.y, norm.trans_offset.z),
        "trans_dir": (norm.trans_dir.x, norm.trans_dir.y, norm.trans_dir.z),
        "rot_dir": (
            norm.rot_dir.Ap1,
            norm.rot_dir.Ap2,
            norm.rot_dir.Ap3,
            norm.rot_dir.At1,
            norm.rot_dir.At2,
            norm.rot_dir.At3,
        ),
        "mode": norm.field_size_mode,
        "size": norm.detector_side_length,
        "swap": norm.swap_lateral_longitudinal,
        "input": (norm.input_manufacturer, norm.input_model),
        "matched": (norm.matched_manufacturer, norm.matched_model),
        "method": norm.normalization_method,
        "summary": norm.attrs_str,
    }


# ---------------------------------------------------------------------------
# Parity with separate live runs
# ---------------------------------------------------------------------------


def test_two_exam_cfa_asd_parity() -> None:
    siemens_session = assemble_session(documents=[_siemens_doc()])
    philips_session = assemble_session(documents=[_philips_doc()])
    siemens_live = analyze_input_file(str(_SIEMENS_DICOM), settings=_dose_settings(siemens_session))
    philips_live = analyze_input_file(str(_PHILIPS_DICOM), settings=_dose_settings(philips_session))
    siemens_context, siemens_frame, _ = _dicom_capture(_SIEMENS_DICOM, siemens_session)
    philips_context, philips_frame, _ = _dicom_capture(_PHILIPS_DICOM, philips_session)
    exams = [_wrap_exam(siemens_frame, "siemens.dcm"), _wrap_exam(philips_frame, "philips.dcm")]
    actual_result = analyze_multiple_exams(
        exams, _dose_settings(), equipment_capture_contexts=[siemens_context, philips_context]
    )
    siemens_exam = actual_result.exams[0]
    philips_exam = actual_result.exams[1]
    assert siemens_exam.output.psd == siemens_live["psd"]
    assert philips_exam.output.psd == philips_live["psd"]
    assert np.array_equal(siemens_exam.output.dose_map, _densify(siemens_live["dose_map"], siemens_exam.output.dose_map.size))
    assert np.array_equal(philips_exam.output.dose_map, _densify(philips_live["dose_map"], philips_exam.output.dose_map.size))
    assert siemens_exam.equipment_profile_match == siemens_live["equipment_profile_match"]
    assert philips_exam.equipment_profile_match == philips_live["equipment_profile_match"]
    siemens_match: Any = siemens_exam.equipment_profile_match
    philips_match: Any = philips_exam.equipment_profile_match
    assert siemens_match["profile_id"] == "m-siemens"
    assert philips_match["profile_id"] == "m-philips"
    expected_aggregate = _densify(siemens_live["dose_map"], siemens_exam.output.dose_map.size) + _densify(
        philips_live["dose_map"], philips_exam.output.dose_map.size
    )
    assert actual_result.aggregate_psd == float(expected_aggregate.max())
    assert actual_result.total_events == siemens_exam.event_count + philips_exam.event_count
    assert actual_result.exams_attempted == 2
    assert actual_result.exams_excluded == 0


def test_reversed_order_matches_by_exam() -> None:
    siemens_session = assemble_session(documents=[_siemens_doc()])
    philips_session = assemble_session(documents=[_philips_doc()])
    siemens_context, siemens_frame, _ = _dicom_capture(_SIEMENS_DICOM, siemens_session)
    philips_context, philips_frame, _ = _dicom_capture(_PHILIPS_DICOM, philips_session)
    forward = analyze_multiple_exams(
        [_wrap_exam(siemens_frame, "siemens.dcm"), _wrap_exam(philips_frame, "philips.dcm")],
        _dose_settings(),
        equipment_capture_contexts=[siemens_context, philips_context],
    )
    reversed_result = analyze_multiple_exams(
        [_wrap_exam(philips_frame, "philips.dcm"), _wrap_exam(siemens_frame, "siemens.dcm")],
        _dose_settings(),
        equipment_capture_contexts=[philips_context, siemens_context],
    )
    forward_psds = sorted(exam.output.psd for exam in forward.exams)
    reversed_psds = sorted(exam.output.psd for exam in reversed_result.exams)
    assert forward_psds == reversed_psds
    forward_ids = sorted(_match_profile_id(exam) for exam in forward.exams)
    reversed_ids = sorted(_match_profile_id(exam) for exam in reversed_result.exams)
    assert forward_ids == reversed_ids
    assert forward_ids == ["m-philips", "m-siemens"]
    assert reversed_result.aggregate_psd == forward.aggregate_psd


def test_patient_offsets_parity() -> None:
    siemens_session = assemble_session(documents=[_siemens_doc()])
    philips_session = assemble_session(documents=[_philips_doc()])
    offsets = [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]]
    siemens_expected = analyze_input_file(
        str(_SIEMENS_DICOM), settings=_offset_settings(siemens_session, offsets[0])
    )
    philips_expected = analyze_input_file(
        str(_PHILIPS_DICOM), settings=_offset_settings(philips_session, offsets[1])
    )
    siemens_context, siemens_frame, _ = _dicom_capture(_SIEMENS_DICOM, siemens_session)
    philips_context, philips_frame, _ = _dicom_capture(_PHILIPS_DICOM, philips_session)
    actual_result = analyze_multiple_exams(
        [_wrap_exam(siemens_frame, "siemens.dcm"), _wrap_exam(philips_frame, "philips.dcm")],
        _dose_settings(),
        per_exam_offsets=offsets,
        equipment_capture_contexts=[siemens_context, philips_context],
    )
    siemens_exam = actual_result.exams[0]
    philips_exam = actual_result.exams[1]
    assert siemens_exam.output.psd == siemens_expected["psd"]
    assert philips_exam.output.psd == philips_expected["psd"]
    assert siemens_exam.patient_offset == offsets[0]
    assert philips_exam.patient_offset == offsets[1]


def _offset_settings(session: Any, offset: list[float]) -> PyskindoseSettings:
    """Live settings with one global patient offset (mirrors per-exam expectations)."""
    settings = _dose_settings(session)
    settings.phantom.patient_offset.d_lon = offset[0]
    settings.phantom.patient_offset.d_ver = offset[1]
    settings.phantom.patient_offset.d_lat = offset[2]
    return settings


def test_partial_default_missing_identity(tmp_path: Path) -> None:
    siemens_session = assemble_session(
        documents=[
            {
                "schema_version": 1,
                "profiles": [
                    {
                        "profile_id": "m-partial",
                        "manufacturer": "Siemens",
                        "models": ["AXIOM-Artis"],
                        "coordinates": {"detector_side_length": 30.0},
                    }
                ],
            }
        ]
    )
    partial_live = analyze_input_file(str(_SIEMENS_DICOM), settings=_dose_settings(siemens_session))
    partial_context, partial_frame, _ = _dicom_capture(_SIEMENS_DICOM, siemens_session)
    assert partial_context.notice_kind == "partial"
    default_context, default_frame = _blank_maker_capture(tmp_path)
    actual_result = analyze_multiple_exams(
        [_wrap_exam(partial_frame, "siemens.dcm"), _wrap_exam(default_frame, "blank.csv")],
        _dose_settings(),
        equipment_capture_contexts=[partial_context, default_context],
    )
    partial_exam = actual_result.exams[0]
    default_exam = actual_result.exams[1]
    assert partial_exam.output.psd == partial_live["psd"]
    assert partial_exam.equipment_profile_match == partial_live["equipment_profile_match"]
    default_match: Any = default_exam.equipment_profile_match
    assert default_match["source"] == "default"
    assert default_match["matched_input_key"] == {
        "manufacturer": "",
        "model": "axiom artis",
    }


def _blank_maker_capture(directory: Path) -> tuple[Any, Any]:
    """Real raw CSV adapter capture with a missing maker (Default fallback)."""
    from guiskindose.equipment_capture import capture_from_receipt

    session = assemble_session(documents=[_siemens_doc()])
    path = directory / "blank.csv"
    path.write_text(
        _RAW_HEADER + "\n" + _RAW_ROW.format(maker="", model="AXIOM-Artis") + "\n",
        encoding="utf-8",
    )
    settings = _dose_settings(session)
    result = read_and_normalize_input(path, input_schema="generic_rdsr_like", settings=settings)
    assert not isinstance(result, list)
    assert result.equipment_receipt is not None
    receipt = result.equipment_receipt
    frame = result.normalized_data
    context = capture_from_receipt(receipt=receipt, frame=frame, settings=settings)
    assert context.source == "default"
    return context, frame


# ---------------------------------------------------------------------------
# Mixed null baseline entries
# ---------------------------------------------------------------------------


def test_mixed_null_baseline_entry() -> None:
    siemens_session = assemble_session(documents=[_siemens_doc()])
    siemens_live = analyze_input_file(str(_SIEMENS_DICOM), settings=_dose_settings(siemens_session))
    siemens_context, siemens_frame, _ = _dicom_capture(_SIEMENS_DICOM, siemens_session)
    plain_settings = _dose_settings()
    plain_frame = read_and_normalise_rdsr_data(str(_PHILIPS_DICOM), plain_settings)
    baseline: Any = analyze_data(plain_frame, _dose_settings())
    actual_result = analyze_multiple_exams(
        [_wrap_exam(siemens_frame, "siemens.dcm"), _wrap_exam(plain_frame, "philips.dcm")],
        _dose_settings(),
        equipment_capture_contexts=[siemens_context, None],
    )
    captured_exam = actual_result.exams[0]
    baseline_exam = actual_result.exams[1]
    assert captured_exam.output.psd == siemens_live["psd"]
    assert captured_exam.equipment_profile_match == siemens_live["equipment_profile_match"]
    assert baseline_exam.equipment_profile_match is None
    assert baseline_exam.output.psd == baseline["psd"]


# ---------------------------------------------------------------------------
# Offline analysis: no files, stores, or bundles
# ---------------------------------------------------------------------------


def test_offline_after_source_removal_and_bundle_change(tmp_path: Path) -> None:
    siemens_path = tmp_path / "siemens.json"
    philips_path = tmp_path / "philips.json"
    siemens_path.write_text(json.dumps(_siemens_doc()), encoding="utf-8")
    philips_path.write_text(json.dumps(_philips_doc()), encoding="utf-8")
    siemens_session = assemble_session(files=[FileSource(siemens_path)])
    philips_session = assemble_session(files=[FileSource(philips_path)])
    siemens_live = analyze_input_file(str(_SIEMENS_DICOM), settings=_dose_settings(siemens_session))
    siemens_context, siemens_frame, _ = _dicom_capture(_SIEMENS_DICOM, siemens_session)
    philips_context, philips_frame, _ = _dicom_capture(_PHILIPS_DICOM, philips_session)
    from guiskindose.equipment_capture import capture_to_json
    from guiskindose.equipment_profiles.capture_codec import capture_from_json

    siemens_parsed = capture_from_json(capture_to_json(siemens_context))
    philips_parsed = capture_from_json(capture_to_json(philips_context))
    siemens_path.unlink()
    philips_path.unlink()
    fresh = _dose_settings()
    fresh.normalization_settings.normalization_settings_list.clear()
    actual_result = analyze_multiple_exams(
        [_wrap_exam(siemens_frame, "siemens.dcm"), _wrap_exam(philips_frame, "philips.dcm")],
        fresh,
        equipment_capture_contexts=[siemens_parsed, philips_parsed],
    )
    actual_siemens = actual_result.exams[0]
    assert actual_siemens.output.psd == siemens_live["psd"]
    assert actual_siemens.equipment_profile_match == siemens_live["equipment_profile_match"]


# ---------------------------------------------------------------------------
# Bad later captures fail before any calculation
# ---------------------------------------------------------------------------


def test_bad_late_capture_rejects_before_any_calculation(monkeypatch: Any) -> None:
    import sys as _sys

    analyze_module = _sys.modules["guiskindose.analyze_data"]
    siemens_session = assemble_session(documents=[_siemens_doc()])
    philips_session = assemble_session(documents=[_philips_doc()])
    siemens_context, siemens_frame, _ = _dicom_capture(_SIEMENS_DICOM, siemens_session)
    philips_context, philips_frame, _ = _dicom_capture(_PHILIPS_DICOM, philips_session)
    tampered = philips_frame.copy()
    tampered["Tx"] = [float(value) + 100.0 for value in philips_frame["Tx"]]
    calls: list[str] = []
    real_calculate = analyze_module.calculate_dose

    def _spy(**kwargs: Any) -> Any:
        calls.append("calculate_dose")
        return real_calculate(**kwargs)

    monkeypatch.setattr(analyze_module, "calculate_dose", _spy)
    prepared_exams = [_wrap_exam(siemens_frame, "siemens.dcm"), _wrap_exam(tampered, "philips.dcm")]
    prepared_settings = _dose_settings()
    with pytest.raises(CaptureError) as excinfo:
        analyze_multiple_exams(
            prepared_exams,
            prepared_settings,
            equipment_capture_contexts=[siemens_context, philips_context],
        )
    assert _code(excinfo) == CODE_EQUIPMENT_GEOMETRY_MISMATCH
    assert calls == []


def test_live_session_rejected_in_capture_mode() -> None:
    siemens_session = assemble_session(documents=[_siemens_doc()])
    siemens_context, siemens_frame, _ = _dicom_capture(_SIEMENS_DICOM, siemens_session)
    settings = _dose_settings(siemens_session)
    prepared_exams = [_wrap_exam(siemens_frame, "siemens.dcm")]
    with pytest.raises(CaptureError) as excinfo:
        analyze_multiple_exams(
            prepared_exams,
            settings,
            equipment_capture_contexts=[siemens_context],
        )
    assert _code(excinfo) == CODE_INVALID_EQUIPMENT_CAPTURE


def test_live_receipt_rejected_in_capture_mode() -> None:
    siemens_session = assemble_session(documents=[_siemens_doc()])
    settings = _dose_settings(siemens_session)
    out: list[Any] = []
    frame = read_and_normalise_rdsr_data(str(_SIEMENS_DICOM), settings, equipment_receipt_out=out)
    assert len(out) == 1
    from guiskindose.equipment_capture import capture_from_receipt

    context = capture_from_receipt(receipt=out[0], frame=frame, settings=settings)
    receipt_exam = _wrap_exam(frame, "siemens.dcm")
    receipt_exam.equipment_receipt = out[0]
    fresh = _dose_settings()
    with pytest.raises(CaptureError) as excinfo:
        analyze_multiple_exams(
            [receipt_exam], fresh, equipment_capture_contexts=[context]
        )
    assert _code(excinfo) == CODE_INVALID_EQUIPMENT_CAPTURE


# ---------------------------------------------------------------------------
# Argument shape boundaries
# ---------------------------------------------------------------------------


def test_context_argument_boundaries() -> None:
    siemens_session = assemble_session(documents=[_siemens_doc()])
    siemens_context, siemens_frame, _ = _dicom_capture(_SIEMENS_DICOM, siemens_session)
    exams = [_wrap_exam(siemens_frame, "siemens.dcm"), _wrap_exam(siemens_frame, "siemens.dcm")]
    fresh = _dose_settings()
    with pytest.raises(CaptureError) as excinfo:
        analyze_multiple_exams(exams, fresh, equipment_capture_contexts=[siemens_context])
    assert _code(excinfo) == CODE_INVALID_EQUIPMENT_CAPTURE
    generator: Any = (entry for entry in [siemens_context, siemens_context])
    with pytest.raises(CaptureError) as excinfo:
        analyze_multiple_exams(exams, fresh, equipment_capture_contexts=generator)
    assert _code(excinfo) == CODE_INVALID_EQUIPMENT_CAPTURE
    bad_text: Any = "not-contexts"
    with pytest.raises(CaptureError) as excinfo:
        analyze_multiple_exams(exams, fresh, equipment_capture_contexts=bad_text)
    assert _code(excinfo) == CODE_INVALID_EQUIPMENT_CAPTURE
    bad_mapping: Any = {"contexts": []}
    with pytest.raises(CaptureError) as excinfo:
        analyze_multiple_exams(exams, fresh, equipment_capture_contexts=bad_mapping)
    assert _code(excinfo) == CODE_INVALID_EQUIPMENT_CAPTURE
    bad_entry: Any = "nope"
    with pytest.raises(CaptureError) as excinfo:
        analyze_multiple_exams(exams, fresh, equipment_capture_contexts=[siemens_context, bad_entry])
    assert _code(excinfo) == CODE_INVALID_EQUIPMENT_CAPTURE


def test_context_count_boundary() -> None:
    siemens_session = assemble_session(documents=[_siemens_doc()])
    _, siemens_frame, _ = _dicom_capture(_SIEMENS_DICOM, siemens_session)
    exam = _wrap_exam(siemens_frame, "siemens.dcm")
    fresh = _dose_settings()
    nulls: Any = [None] * 65
    with pytest.raises(CaptureError) as excinfo:
        analyze_multiple_exams([exam] * 65, fresh, equipment_capture_contexts=nulls)
    assert _code(excinfo) == CODE_INVALID_EQUIPMENT_CAPTURE


def test_context_tuple_accepted() -> None:
    siemens_session = assemble_session(documents=[_siemens_doc()])
    siemens_context, siemens_frame, _ = _dicom_capture(_SIEMENS_DICOM, siemens_session)
    siemens_live = analyze_input_file(str(_SIEMENS_DICOM), settings=_dose_settings(siemens_session))
    actual_result = analyze_multiple_exams(
        [_wrap_exam(siemens_frame, "siemens.dcm")],
        _dose_settings(),
        equipment_capture_contexts=(siemens_context,),
    )
    actual_exam = actual_result.exams[0]
    assert actual_exam.output.psd == siemens_live["psd"]


def test_aggregate_event_boundary() -> None:
    from guiskindose.equipment_capture import capture_from_receipt
    from guiskindose.equipment_profiles.resolver import ExamCoordinateIdentity
    from guiskindose.equipment_resolution import (
        EquipmentApplicationReceipt,
        apply_resolution_to_settings,
        bind_receipt_frame,
        resolve_exam_coordinates,
    )

    siemens_session = assemble_session(documents=[_siemens_doc()])
    settings = _dose_settings(siemens_session)
    out: list[Any] = []
    frame = read_and_normalise_rdsr_data(str(_SIEMENS_DICOM), settings, equipment_receipt_out=out)
    assert len(out) == 1
    tiled = frame.iloc[list(range(len(frame))) * 286].reset_index(drop=True)
    assert len(tiled) == 6006
    identity = ExamCoordinateIdentity(manufacturer="Siemens", model="AXIOM-Artis", event_count=len(tiled))
    resolution, matched_maker, matched_model = resolve_exam_coordinates(
        manufacturer="Siemens",
        model="AXIOM-Artis",
        event_count=len(tiled),
        session=siemens_session,
        bundled_entries=[],
    )
    apply_resolution_to_settings(
        resolution,
        settings.normalization_settings,
        input_maker="Siemens",
        input_model="AXIOM-Artis",
        matched_maker=matched_maker,
        matched_model=matched_model,
    )
    receipt = EquipmentApplicationReceipt(
        resolution=resolution,
        session_hash=siemens_session.active_set_hash,
        maker_key=identity.manufacturer_key,
        model_key=identity.model_key,
        event_count=len(tiled),
        input_maker="Siemens",
        input_model="AXIOM-Artis",
        matched_maker=matched_maker,
        matched_model=matched_model,
    )
    bound = bind_receipt_frame(receipt, tiled)
    big_context = capture_from_receipt(receipt=bound, frame=tiled, settings=settings)
    assert big_context.event_count == 6006
    fresh = _dose_settings()
    prepared_exams = [_wrap_exam(tiled, "big-a.dcm"), _wrap_exam(tiled, "big-b.dcm")]
    with pytest.raises(CaptureError) as excinfo:
        analyze_multiple_exams(
            prepared_exams, fresh, equipment_capture_contexts=[big_context, big_context]
        )
    assert _code(excinfo) == CODE_INVALID_EQUIPMENT_CAPTURE


# ---------------------------------------------------------------------------
# Working-copy isolation: hostile clone hooks reject with zero production
# ---------------------------------------------------------------------------


class _SelfCopySettings(PyskindoseSettings):
    def __deepcopy__(self, memo: Any) -> Any:
        return self


class _BoomCopySettings(PyskindoseSettings):
    def __deepcopy__(self, memo: Any) -> Any:
        raise RuntimeError("boom")


class _SharedChild:
    def __init__(self, inner: Any) -> None:
        self._inner = inner

    def __deepcopy__(self, memo: Any) -> Any:
        return self


def _hostile_dose_settings(cls: Any) -> PyskindoseSettings:
    config = load_settings_example_json()
    config["mode"] = "calculate_dose"
    return cls(settings=config, output_format="dict")


def _spy_no_calculate(monkeypatch: Any) -> list[str]:
    import sys as _sys

    analyze_module = _sys.modules["guiskindose.analyze_data"]
    calls: list[str] = []
    real_calculate = analyze_module.calculate_dose

    def _spy(**kwargs: Any) -> Any:
        calls.append("calculate_dose")
        return real_calculate(**kwargs)

    monkeypatch.setattr(analyze_module, "calculate_dose", _spy)
    return calls


def test_self_returning_root_all_null_rejected(monkeypatch: Any) -> None:
    _, siemens_frame, _ = _dicom_capture(
        _SIEMENS_DICOM, assemble_session(documents=[_siemens_doc()])
    )
    hostile = _hostile_dose_settings(_SelfCopySettings)
    before_norm = _snapshot_norm(hostile.normalization_settings)
    before_frame = siemens_frame.copy(deep=True)
    calls = _spy_no_calculate(monkeypatch)
    prepared_exams = [_wrap_exam(siemens_frame, "siemens.dcm"), _wrap_exam(siemens_frame, "siemens.dcm")]
    with pytest.raises(CaptureError) as excinfo:
        analyze_multiple_exams(
            prepared_exams,
            hostile,
            equipment_capture_contexts=[None, None],
        )
    assert _code(excinfo) == CODE_INVALID_EQUIPMENT_CAPTURE
    assert calls == []
    assert _snapshot_norm(hostile.normalization_settings) == before_norm
    assert siemens_frame.equals(before_frame)


def test_self_returning_root_mixed_rejected(monkeypatch: Any) -> None:
    siemens_session = assemble_session(documents=[_siemens_doc()])
    siemens_context, siemens_frame, _ = _dicom_capture(_SIEMENS_DICOM, siemens_session)
    hostile = _hostile_dose_settings(_SelfCopySettings)
    before_norm = _snapshot_norm(hostile.normalization_settings)
    calls = _spy_no_calculate(monkeypatch)
    prepared_exams = [_wrap_exam(siemens_frame, "siemens.dcm"), _wrap_exam(siemens_frame, "siemens.dcm")]
    with pytest.raises(CaptureError) as excinfo:
        analyze_multiple_exams(
            prepared_exams,
            hostile,
            equipment_capture_contexts=[siemens_context, None],
        )
    assert _code(excinfo) == CODE_INVALID_EQUIPMENT_CAPTURE
    assert calls == []
    assert _snapshot_norm(hostile.normalization_settings) == before_norm


def test_raising_root_deepcopy_rejected(monkeypatch: Any) -> None:
    siemens_context, siemens_frame, _ = _dicom_capture(
        _SIEMENS_DICOM, assemble_session(documents=[_siemens_doc()])
    )
    hostile = _hostile_dose_settings(_BoomCopySettings)
    calls = _spy_no_calculate(monkeypatch)
    prepared_exams = [_wrap_exam(siemens_frame, "siemens.dcm")]
    with pytest.raises(CaptureError) as excinfo:
        analyze_multiple_exams(
            prepared_exams,
            hostile,
            equipment_capture_contexts=[siemens_context],
        )
    assert _code(excinfo) == CODE_INVALID_EQUIPMENT_CAPTURE
    assert "boom" not in str(excinfo.value)
    assert calls == []


def test_shared_translation_offset_child_rejected_and_caller_unchanged(monkeypatch: Any) -> None:
    siemens_context, siemens_frame, _ = _dicom_capture(
        _SIEMENS_DICOM, assemble_session(documents=[_siemens_doc()])
    )
    fresh = _dose_settings()
    inner = fresh.normalization_settings.trans_offset
    before = (inner.x, inner.y, inner.z)
    wrapper = _SharedChild(inner)
    malformed_home: Any = fresh.normalization_settings
    malformed_home.trans_offset = wrapper
    calls = _spy_no_calculate(monkeypatch)
    prepared_exams = [_wrap_exam(siemens_frame, "siemens.dcm")]
    with pytest.raises(CaptureError) as excinfo:
        analyze_multiple_exams(
            prepared_exams,
            fresh,
            equipment_capture_contexts=[siemens_context],
        )
    assert _code(excinfo) == CODE_INVALID_EQUIPMENT_CAPTURE
    assert calls == []
    actual_offsets = (inner.x, inner.y, inner.z)
    assert actual_offsets == before
    assert fresh.normalization_settings.trans_offset is wrapper


def test_shared_patient_offset_rejected_before_offset_assignment(monkeypatch: Any) -> None:
    context, frame, _ = _dicom_capture(
        _SIEMENS_DICOM, assemble_session(documents=[_siemens_doc()])
    )
    fresh = _dose_settings()
    patient_offset = fresh.phantom.patient_offset
    before = (patient_offset.d_lon, patient_offset.d_ver, patient_offset.d_lat)
    monkeypatch.setattr(type(patient_offset), "__deepcopy__", lambda self, memo: self, raising=False)
    exams = [_wrap_exam(frame, "siemens.dcm")]
    calls = _spy_no_calculate(monkeypatch)
    with pytest.raises(CaptureError) as excinfo:
        analyze_multiple_exams(
            exams, fresh, per_exam_offsets=[[3.0, 4.0, 5.0]], equipment_capture_contexts=[context]
        )
    assert _code(excinfo) == CODE_INVALID_EQUIPMENT_CAPTURE
    assert calls == []
    actual_offsets = (patient_offset.d_lon, patient_offset.d_ver, patient_offset.d_lat)
    assert actual_offsets == before
    assert fresh.phantom.patient_offset is patient_offset


def test_stateful_hook_sharing_second_copy_rejected(monkeypatch: Any) -> None:
    import copy as _copy_module

    from guiskindose.settings import PyskindoseSettings as _SettingsClass

    siemens_session = assemble_session(documents=[_siemens_doc()])
    siemens_context, siemens_frame, _ = _dicom_capture(_SIEMENS_DICOM, siemens_session)
    philips_session = assemble_session(documents=[_philips_doc()])
    philips_context, philips_frame, _ = _dicom_capture(_PHILIPS_DICOM, philips_session)
    fresh = _dose_settings()
    before_norm = _snapshot_norm(fresh.normalization_settings)
    before_philips = philips_frame.copy(deep=True)
    real_deepcopy = _copy_module.deepcopy
    state = {"copies": 0}

    def _hook(obj: Any, memo: Any = None) -> Any:
        if isinstance(obj, _SettingsClass):
            state["copies"] += 1
            if state["copies"] >= 2:
                return obj
        return real_deepcopy(obj, memo)

    monkeypatch.setattr(_copy_module, "deepcopy", _hook)
    calls = _spy_no_calculate(monkeypatch)
    prepared_exams = [_wrap_exam(siemens_frame, "siemens.dcm"), _wrap_exam(philips_frame, "philips.dcm")]
    with pytest.raises(CaptureError) as excinfo:
        analyze_multiple_exams(
            prepared_exams,
            fresh,
            equipment_capture_contexts=[siemens_context, philips_context],
        )
    assert _code(excinfo) == CODE_INVALID_EQUIPMENT_CAPTURE
    assert calls == []
    assert _snapshot_norm(fresh.normalization_settings) == before_norm
    assert philips_frame.equals(before_philips)


# ---------------------------------------------------------------------------
# Forged counts and corrupt shapes fail closed with cause-free errors
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad_count", ["bad", True, 2**70, -5])
def test_forged_event_count_rejected(bad_count: Any) -> None:
    import copy as _copy

    siemens_context, siemens_frame, _ = _dicom_capture(
        _SIEMENS_DICOM, assemble_session(documents=[_siemens_doc()])
    )
    forged = _copy.copy(siemens_context)
    object.__setattr__(forged, "event_count", bad_count)
    fresh = _dose_settings()
    prepared_exams = [_wrap_exam(siemens_frame, "siemens.dcm")]
    with pytest.raises(CaptureError) as excinfo:
        analyze_multiple_exams(
            prepared_exams,
            fresh,
            equipment_capture_contexts=[forged],
        )
    assert _code(excinfo) == CODE_INVALID_EQUIPMENT_CAPTURE


def test_corrupt_nested_shape_rejected() -> None:
    import copy as _copy

    siemens_context, siemens_frame, _ = _dicom_capture(
        _SIEMENS_DICOM, assemble_session(documents=[_siemens_doc()])
    )
    forged = _copy.copy(siemens_context)
    object.__setattr__(forged, "fields", list(forged.fields))
    fresh = _dose_settings()
    prepared_exams = [_wrap_exam(siemens_frame, "siemens.dcm")]
    with pytest.raises(CaptureError) as excinfo:
        analyze_multiple_exams(
            prepared_exams,
            fresh,
            equipment_capture_contexts=[forged],
        )
    assert _code(excinfo) == CODE_INVALID_EQUIPMENT_CAPTURE


def test_caller_homes_and_frames_preserved() -> None:
    siemens_session = assemble_session(documents=[_siemens_doc()])
    philips_session = assemble_session(documents=[_philips_doc()])
    siemens_context, siemens_frame, _ = _dicom_capture(_SIEMENS_DICOM, siemens_session)
    philips_context, philips_frame, _ = _dicom_capture(_PHILIPS_DICOM, philips_session)
    exams = [_wrap_exam(siemens_frame, "siemens.dcm"), _wrap_exam(philips_frame, "philips.dcm")]
    fresh = _dose_settings()
    before_norm = _snapshot_norm(fresh.normalization_settings)
    before_siemens = siemens_frame.copy(deep=True)
    before_philips = philips_frame.copy(deep=True)
    actual_result = analyze_multiple_exams(
        exams, fresh, equipment_capture_contexts=[siemens_context, philips_context]
    )
    assert actual_result.exams_attempted == 2
    assert _snapshot_norm(fresh.normalization_settings) == before_norm
    assert siemens_frame.equals(before_siemens)
    assert philips_frame.equals(before_philips)
    tampered = philips_frame.copy()
    tampered["Tx"] = [float(value) + 100.0 for value in philips_frame["Tx"]]
    bad_exams = [_wrap_exam(siemens_frame, "siemens.dcm"), _wrap_exam(tampered, "philips.dcm")]
    with pytest.raises(CaptureError):
        analyze_multiple_exams(
            bad_exams, fresh, equipment_capture_contexts=[siemens_context, philips_context]
        )
    assert _snapshot_norm(fresh.normalization_settings) == before_norm
    assert siemens_frame.equals(before_siemens)
    assert philips_frame.equals(before_philips)
