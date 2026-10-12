"""Tests for single-exam direct analysis from a captured authority.

Every capture flows from a real raw loader (DICOM or raw CSV) through the
capture producer; the capture run then calls single-exam ``analyze_data``
directly with no live session. Covers PSD/dose-map parity with the original
live raw run (including zero/False recipes, custom offsets/signs/modes, and
partial/default captures), offline analysis after source removal and bundle
changes, tamper rejections before any calculation, forged-receipt
non-authority, dict/JSON match parity, no-capture keysets, unsupported
context types, and caller-state preservation. No tracked binary fixtures.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from guiskindose import load_settings_example_json
from guiskindose.equipment_profiles import FileSource, assemble_session
from guiskindose.equipment_profiles.capture import (
    CODE_EQUIPMENT_GEOMETRY_MISMATCH,
    CODE_INVALID_EQUIPMENT_CAPTURE,
    CaptureError,
)
from guiskindose.helpers.read_and_normalize_rdsr_data import read_and_normalise_rdsr_data
from guiskindose.input_adapters.registry import read_and_normalize_input
from guiskindose.main import analyze_data, analyze_input_file
from guiskindose.settings import PyskindoseSettings

_DICOM = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "guiskindose"
    / "example_data"
    / "RDSR"
    / "siemens_axiom_artis.dcm"
)
_PHILIPS_DICOM = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "guiskindose"
    / "example_data"
    / "RDSR"
    / "philips_allura_clarity_u104.dcm"
)

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


def _full_coordinates() -> dict[str, Any]:
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


def _asd_coordinates() -> dict[str, Any]:
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


def _philips_doc() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "profiles": [
            {
                "profile_id": "a-asd",
                "manufacturer": "Philips",
                "models": ["Allura Clarity"],
                "coordinates": _asd_coordinates(),
            }
        ],
    }


def _profile_doc(profile_id: str, coordinates: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "profiles": [
            {
                "profile_id": profile_id,
                "manufacturer": "Siemens",
                "models": ["AXIOM-Artis"],
                "coordinates": coordinates,
            }
        ],
    }


def _live_settings(session: Any) -> PyskindoseSettings:
    config = load_settings_example_json()
    config["mode"] = "calculate_dose"
    return PyskindoseSettings(
        settings=config, output_format="dict", equipment_profile_session=session
    )


def _fresh_settings() -> PyskindoseSettings:
    config = load_settings_example_json()
    config["mode"] = "calculate_dose"
    return PyskindoseSettings(settings=config, output_format="dict")


def _dicom_capture(session: Any) -> tuple[Any, Any, PyskindoseSettings]:
    """Real DICOM normalizer receipt produced into a validated capture (no calculation)."""
    from guiskindose.equipment_capture import capture_from_receipt

    settings = _live_settings(session)
    out: list[Any] = []
    frame = read_and_normalise_rdsr_data(str(_DICOM), settings, equipment_receipt_out=out)
    assert len(out) == 1
    receipt = out[0]
    context = capture_from_receipt(receipt=receipt, frame=frame, settings=settings)
    return context, frame, settings


def _live_dicom_run(session: Any, dicom: Path = _DICOM) -> tuple[Any, Any, Any, PyskindoseSettings]:
    """Original live raw run: output, receipt, retained frame, and settings."""
    from guiskindose.equipment_capture import capture_from_receipt

    settings = _live_settings(session)
    output = analyze_input_file(str(dicom), settings=settings)
    out: list[Any] = []
    frame = read_and_normalise_rdsr_data(str(dicom), settings, equipment_receipt_out=out)
    assert len(out) == 1
    receipt = out[0]
    context = capture_from_receipt(receipt=receipt, frame=frame, settings=settings)
    return output, context, frame, settings


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


def _code(excinfo: pytest.ExceptionInfo[CaptureError]) -> str:
    return excinfo.value.code


# ---------------------------------------------------------------------------
# Parity with the original live raw run
# ---------------------------------------------------------------------------


def test_capture_run_matches_live_run() -> None:
    live_output, context, frame, _ = _live_dicom_run(
        assemble_session(documents=[_profile_doc("a-full", _full_coordinates())])
    )
    actual: Any = analyze_data(frame, _fresh_settings(), equipment_capture_context=context)
    assert actual["psd"] == live_output["psd"]
    assert actual["dose_map"] == live_output["dose_map"]
    assert actual["equipment_profile_match"] == live_output["equipment_profile_match"]


def test_zero_false_recipe_parity() -> None:
    coordinates = {
        "translation_offset": {"x": 0.0, "y": 0.0, "z": 0.0},
        "translation_direction": {"x": "+", "y": "+", "z": "+"},
        "rotation_direction": {
            "Ap1": "+",
            "Ap2": "+",
            "Ap3": "+",
            "At1": "+",
            "At2": "+",
            "At3": "+",
        },
        "swap_lateral_longitudinal": False,
        "field_size_mode": "CFA",
        "detector_side_length": 20.0,
    }
    live_output, context, frame, _ = _live_dicom_run(
        assemble_session(documents=[_profile_doc("a-zero", coordinates)])
    )
    actual: Any = analyze_data(frame, _fresh_settings(), equipment_capture_context=context)
    assert actual["psd"] == live_output["psd"]
    assert actual["dose_map"] == live_output["dose_map"]


def test_partial_capture_parity() -> None:
    live_output, context, frame, _ = _live_dicom_run(
        assemble_session(documents=[_profile_doc("a-partial", {"detector_side_length": 30.0})])
    )
    assert context.notice_kind == "partial"
    actual: Any = analyze_data(frame, _fresh_settings(), equipment_capture_context=context)
    assert actual["psd"] == live_output["psd"]
    assert actual["equipment_profile_match"] == live_output["equipment_profile_match"]


def test_default_capture_parity_csv(tmp_path: Path) -> None:
    session = assemble_session(documents=[_profile_doc("a-full", _full_coordinates())])
    path = tmp_path / "raw.csv"
    path.write_text(
        _RAW_HEADER + "\n" + _RAW_ROW.format(maker="", model="AXIOM-Artis") + "\n",
        encoding="utf-8",
    )
    live_settings = _live_settings(session)
    live_output = analyze_input_file(str(path), settings=live_settings, input_schema="generic_rdsr_like")
    assert live_output["equipment_profile_match"]["source"] == "default"
    result = read_and_normalize_input(path, input_schema="generic_rdsr_like", settings=live_settings)
    assert not isinstance(result, list)
    assert result.equipment_receipt is not None
    from guiskindose.equipment_capture import capture_from_receipt

    context = capture_from_receipt(
        receipt=result.equipment_receipt, frame=result.normalized_data, settings=live_settings
    )
    actual: Any = analyze_data(
        result.normalized_data, _fresh_settings(), equipment_capture_context=context
    )
    assert actual["psd"] == live_output["psd"]
    assert actual["equipment_profile_match"] == live_output["equipment_profile_match"]


def test_asd_capture_parity() -> None:
    live_output, context, frame, _ = _live_dicom_run(
        assemble_session(documents=[_philips_doc()]), _PHILIPS_DICOM
    )
    assert context.source == "custom"
    actual: Any = analyze_data(frame, _fresh_settings(), equipment_capture_context=context)
    assert actual["psd"] == live_output["psd"]
    assert actual["dose_map"] == live_output["dose_map"]
    assert actual["equipment_profile_match"] == live_output["equipment_profile_match"]


def test_json_match_parity() -> None:
    live_output, context, frame, _ = _live_dicom_run(
        assemble_session(documents=[_profile_doc("a-full", _full_coordinates())])
    )
    fresh = _fresh_settings()
    fresh.output_format = "json"
    import json as jsonlib

    actual: Any = analyze_data(frame, fresh, equipment_capture_context=context)
    parsed = jsonlib.loads(actual)
    assert parsed["psd"] == live_output["psd"]
    assert parsed["equipment_profile_match"] == live_output["equipment_profile_match"]


# ---------------------------------------------------------------------------
# Offline analysis: no sources, no bundles
# ---------------------------------------------------------------------------


def test_offline_after_source_removal_and_bundle_change(tmp_path: Path) -> None:
    doc = _profile_doc("a-full", _full_coordinates())
    path = tmp_path / "profiles.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    session = assemble_session(files=[FileSource(path)])
    live_output, context, frame, _ = _live_dicom_run(session)
    path.unlink()
    fresh = _fresh_settings()
    fresh.normalization_settings.normalization_settings_list.clear()
    actual: Any = analyze_data(frame, fresh, equipment_capture_context=context)
    assert actual["psd"] == live_output["psd"]
    assert actual["dose_map"] == live_output["dose_map"]


# ---------------------------------------------------------------------------
# Tampering rejects before any calculation
# ---------------------------------------------------------------------------


def test_simultaneous_session_rejected() -> None:
    _, context, frame, live_settings = _live_dicom_run(
        assemble_session(documents=[_profile_doc("a-full", _full_coordinates())])
    )
    with pytest.raises(CaptureError) as excinfo:
        analyze_data(frame, live_settings, equipment_capture_context=context)
    assert _code(excinfo) == CODE_INVALID_EQUIPMENT_CAPTURE


def test_simultaneous_receipt_rejected() -> None:
    from guiskindose.equipment_capture import capture_from_receipt

    session = assemble_session(documents=[_profile_doc("a-full", _full_coordinates())])
    settings = _live_settings(session)
    out: list[Any] = []
    frame = read_and_normalise_rdsr_data(str(_DICOM), settings, equipment_receipt_out=out)
    assert len(out) == 1
    context = capture_from_receipt(receipt=out[0], frame=frame, settings=settings)
    fresh = _fresh_settings()
    with pytest.raises(CaptureError) as excinfo:
        analyze_data(
            frame, fresh, equipment_receipt=out[0], equipment_capture_context=context
        )
    assert _code(excinfo) == CODE_INVALID_EQUIPMENT_CAPTURE


def test_unsupported_context_type_rejected() -> None:
    _, frame, _ = _dicom_capture(
        assemble_session(documents=[_profile_doc("a-full", _full_coordinates())])
    )
    raw: Any = "not-a-context"
    fresh = _fresh_settings()
    with pytest.raises(CaptureError) as excinfo:
        analyze_data(frame, fresh, equipment_capture_context=raw)
    assert _code(excinfo) == CODE_INVALID_EQUIPMENT_CAPTURE


def test_tampered_identity_rejected_before_calculation(monkeypatch: Any) -> None:
    import sys as _sys

    analyze_module = _sys.modules['guiskindose.analyze_data']

    context, frame, _ = _dicom_capture(
        assemble_session(documents=[_profile_doc("a-full", _full_coordinates())])
    )
    calls: list[str] = []
    real_calculate = analyze_module.calculate_dose

    def _spy(**kwargs: Any) -> Any:
        calls.append("calculate_dose")
        return real_calculate(**kwargs)

    monkeypatch.setattr(analyze_module, "calculate_dose", _spy)
    tampered = frame.copy()
    tampered.loc[frame.index[1], "manufacturer"] = "Philips"
    fresh = _fresh_settings()
    with pytest.raises(CaptureError) as excinfo:
        analyze_data(tampered, fresh, equipment_capture_context=context)
    assert _code(excinfo) == CODE_INVALID_EQUIPMENT_CAPTURE
    assert calls == []


def test_tampered_model_row_rejected_before_calculation(monkeypatch: Any) -> None:
    import sys as _sys

    analyze_module = _sys.modules["guiskindose.analyze_data"]
    context, frame, _ = _dicom_capture(
        assemble_session(documents=[_profile_doc("a-full", _full_coordinates())])
    )
    calls: list[str] = []
    real_calculate = analyze_module.calculate_dose

    def _spy(**kwargs: Any) -> Any:
        calls.append("calculate_dose")
        return real_calculate(**kwargs)

    monkeypatch.setattr(analyze_module, "calculate_dose", _spy)
    tampered = frame.copy()
    tampered.loc[frame.index[1], "model"] = "Different Model"
    fresh = _fresh_settings()
    with pytest.raises(CaptureError) as excinfo:
        analyze_data(tampered, fresh, equipment_capture_context=context)
    assert _code(excinfo) == CODE_INVALID_EQUIPMENT_CAPTURE
    assert calls == []


def test_tampered_count_rejected_before_calculation(monkeypatch: Any) -> None:
    import sys as _sys

    analyze_module = _sys.modules['guiskindose.analyze_data']

    context, frame, _ = _dicom_capture(
        assemble_session(documents=[_profile_doc("a-full", _full_coordinates())])
    )
    calls: list[str] = []
    real_calculate = analyze_module.calculate_dose

    def _spy(**kwargs: Any) -> Any:
        calls.append("calculate_dose")
        return real_calculate(**kwargs)

    monkeypatch.setattr(analyze_module, "calculate_dose", _spy)
    short = frame.iloc[:2].copy()
    fresh = _fresh_settings()
    with pytest.raises(CaptureError) as excinfo:
        analyze_data(short, fresh, equipment_capture_context=context)
    assert _code(excinfo) == CODE_INVALID_EQUIPMENT_CAPTURE
    assert calls == []


def test_tampered_geometry_rejected_before_calculation(monkeypatch: Any) -> None:
    import sys as _sys

    analyze_module = _sys.modules['guiskindose.analyze_data']

    context, frame, _ = _dicom_capture(
        assemble_session(documents=[_profile_doc("a-full", _full_coordinates())])
    )
    calls: list[str] = []
    real_calculate = analyze_module.calculate_dose

    def _spy(**kwargs: Any) -> Any:
        calls.append("calculate_dose")
        return real_calculate(**kwargs)

    monkeypatch.setattr(analyze_module, "calculate_dose", _spy)
    stale = frame.copy()
    stale["Tx"] = [float(value) + 100.0 for value in frame["Tx"]]
    fresh = _fresh_settings()
    with pytest.raises(CaptureError) as excinfo:
        analyze_data(stale, fresh, equipment_capture_context=context)
    assert _code(excinfo) == CODE_EQUIPMENT_GEOMETRY_MISMATCH
    assert calls == []


def test_tampered_context_rejected() -> None:
    import dataclasses

    context, _unused_frame, _ = _dicom_capture(
        assemble_session(documents=[_profile_doc("a-full", _full_coordinates())])
    )
    with pytest.raises(CaptureError) as excinfo:
        dataclasses.replace(context, event_count=1)
    assert _code(excinfo) == CODE_INVALID_EQUIPMENT_CAPTURE


def test_crossed_context_rejected_before_calculation(monkeypatch: Any, tmp_path: Path) -> None:
    import sys as _sys

    analyze_module = _sys.modules["guiskindose.analyze_data"]
    session = assemble_session(documents=[_profile_doc("a-full", _full_coordinates())])
    path = tmp_path / "raw.csv"
    path.write_text(
        _RAW_HEADER + "\n" + _RAW_ROW.format(maker="Siemens", model="AXIOM-Artis") + "\n",
        encoding="utf-8",
    )
    csv_settings = _live_settings(session)
    csv_result = read_and_normalize_input(path, input_schema="generic_rdsr_like", settings=csv_settings)
    assert not isinstance(csv_result, list)
    assert csv_result.equipment_receipt is not None
    from guiskindose.equipment_capture import capture_from_receipt

    csv_context = capture_from_receipt(
        receipt=csv_result.equipment_receipt,
        frame=csv_result.normalized_data,
        settings=csv_settings,
    )
    _, dicom_frame, _ = _dicom_capture(session)
    calls: list[str] = []
    real_calculate = analyze_module.calculate_dose

    def _spy(**kwargs: Any) -> Any:
        calls.append("calculate_dose")
        return real_calculate(**kwargs)

    monkeypatch.setattr(analyze_module, "calculate_dose", _spy)
    fresh = _fresh_settings()
    with pytest.raises(CaptureError) as excinfo:
        analyze_data(dicom_frame, fresh, equipment_capture_context=csv_context)
    assert _code(excinfo) == CODE_INVALID_EQUIPMENT_CAPTURE
    assert calls == []


# ---------------------------------------------------------------------------
# Working-copy isolation: hostile clone hooks reject, caller state preserved
# ---------------------------------------------------------------------------


class _SelfCopy(PyskindoseSettings):
    def __deepcopy__(self, memo: Any) -> Any:
        return self


class _BoomCopy(PyskindoseSettings):
    def __deepcopy__(self, memo: Any) -> Any:
        raise RuntimeError("boom")


class _SharedChild:
    def __init__(self, inner: Any) -> None:
        self._inner = inner

    def __deepcopy__(self, memo: Any) -> Any:
        return self


def _hostile_settings(cls: Any) -> PyskindoseSettings:
    config = load_settings_example_json()
    config["mode"] = "calculate_dose"
    return cls(settings=config, output_format="dict")


def _force_attr(target: Any, name: str, value: Any) -> None:
    """Inject an unsupported test value through the untrusted input boundary."""
    setattr(target, name, value)


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


def test_self_returning_deepcopy_rejected(monkeypatch: Any) -> None:
    context, frame, _ = _dicom_capture(
        assemble_session(documents=[_profile_doc("a-full", _full_coordinates())])
    )
    hostile = _hostile_settings(_SelfCopy)
    before_norm = _snapshot_norm(hostile.normalization_settings)
    before_frame = frame.copy(deep=True)
    calls = _spy_no_calculate(monkeypatch)
    with pytest.raises(CaptureError) as excinfo:
        analyze_data(frame, hostile, equipment_capture_context=context)
    assert _code(excinfo) == CODE_INVALID_EQUIPMENT_CAPTURE
    assert calls == []
    assert _snapshot_norm(hostile.normalization_settings) == before_norm
    assert frame.equals(before_frame)


def test_raising_deepcopy_rejected_without_raw_cause(monkeypatch: Any) -> None:
    context, frame, _ = _dicom_capture(
        assemble_session(documents=[_profile_doc("a-full", _full_coordinates())])
    )
    hostile = _hostile_settings(_BoomCopy)
    before_norm = _snapshot_norm(hostile.normalization_settings)
    calls = _spy_no_calculate(monkeypatch)
    with pytest.raises(CaptureError) as excinfo:
        analyze_data(frame, hostile, equipment_capture_context=context)
    assert _code(excinfo) == CODE_INVALID_EQUIPMENT_CAPTURE
    assert "boom" not in str(excinfo.value)
    assert calls == []
    assert _snapshot_norm(hostile.normalization_settings) == before_norm


def test_shared_offset_child_rejected_and_caller_unchanged(monkeypatch: Any) -> None:
    context, frame, _ = _dicom_capture(
        assemble_session(documents=[_profile_doc("a-full", _full_coordinates())])
    )
    fresh = _fresh_settings()
    inner = fresh.normalization_settings.trans_offset
    before = (inner.x, inner.y, inner.z)
    wrapper = _SharedChild(inner)
    # Deliberately inject an unsupported child to exercise the public boundary.
    _force_attr(fresh.normalization_settings, "trans_offset", wrapper)
    calls = _spy_no_calculate(monkeypatch)
    with pytest.raises(CaptureError) as excinfo:
        analyze_data(frame, fresh, equipment_capture_context=context)
    assert _code(excinfo) == CODE_INVALID_EQUIPMENT_CAPTURE
    assert calls == []
    actual_offsets = (inner.x, inner.y, inner.z)
    assert actual_offsets == before
    assert fresh.normalization_settings.trans_offset is wrapper


def test_shared_dimension_child_rejected_and_caller_unchanged(monkeypatch: Any) -> None:
    context, frame, _ = _dicom_capture(
        assemble_session(documents=[_profile_doc("a-full", _full_coordinates())])
    )
    fresh = _fresh_settings()
    inner = fresh.phantom.dimension
    before_plane = inner.plane_resolution
    before_cylinder = inner.cylinder_resolution
    wrapper = _SharedChild(inner)
    # Deliberately inject an unsupported child to exercise the public boundary.
    _force_attr(fresh.phantom, "dimension", wrapper)
    calls = _spy_no_calculate(monkeypatch)
    with pytest.raises(CaptureError) as excinfo:
        analyze_data(frame, fresh, equipment_capture_context=context)
    assert _code(excinfo) == CODE_INVALID_EQUIPMENT_CAPTURE
    assert calls == []
    assert inner.plane_resolution == before_plane
    assert inner.cylinder_resolution == before_cylinder
    assert fresh.phantom.dimension is wrapper


def test_forged_receipt_is_not_authority() -> None:
    from guiskindose.equipment_confirmation import CapturedApplicationReceipt

    context, frame, _ = _dicom_capture(
        assemble_session(documents=[_profile_doc("a-full", _full_coordinates())])
    )
    forged = CapturedApplicationReceipt(
        capture_hash=context.capture_hash,
        geometry_hash=context.geometry_hash,
        event_count=context.event_count,
        maker_key=context.matched_input_key[0],
        model_key=context.matched_input_key[1],
        method="Matched",
    )
    impostor: Any = forged
    fresh = _fresh_settings()
    with pytest.raises(CaptureError) as excinfo:
        analyze_data(frame, fresh, equipment_capture_context=impostor)
    assert _code(excinfo) == CODE_INVALID_EQUIPMENT_CAPTURE


# ---------------------------------------------------------------------------
# Caller state preservation and no-capture behavior
# ---------------------------------------------------------------------------


def test_caller_settings_and_frame_preserved() -> None:
    context, frame, _ = _dicom_capture(
        assemble_session(documents=[_profile_doc("a-full", _full_coordinates())])
    )
    fresh = _fresh_settings()
    before_norm = _snapshot_norm(fresh.normalization_settings)
    before_frame = frame.copy(deep=True)
    actual: Any = analyze_data(frame, fresh, equipment_capture_context=context)
    assert actual["psd"] > 0.0
    assert _snapshot_norm(fresh.normalization_settings) == before_norm
    assert frame.equals(before_frame)
    tampered = frame.copy()
    tampered["Tx"] = [float(value) + 100.0 for value in frame["Tx"]]
    with pytest.raises(CaptureError):
        analyze_data(tampered, fresh, equipment_capture_context=context)
    assert _snapshot_norm(fresh.normalization_settings) == before_norm
    assert frame.equals(before_frame)


def test_no_capture_keyset_unchanged() -> None:
    config = load_settings_example_json()
    config["mode"] = "calculate_dose"
    settings = PyskindoseSettings(settings=config, output_format="dict")
    frame = read_and_normalise_rdsr_data(str(_DICOM), settings)
    actual: Any = analyze_data(frame, settings)
    assert "equipment_profile_match" not in actual
    assert actual["psd"] > 0.0
