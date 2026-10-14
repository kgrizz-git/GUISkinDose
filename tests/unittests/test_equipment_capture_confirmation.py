"""Tests for captured-application preparation and confirmation.

Every capture flows from a real raw loader (DICOM or raw CSV) through the
capture producer — never from hand-built resolutions. Covers full/partial/
default/wildcard and missing-maker captures, offline parsing after source
deletion with changed bundles having no effect, stale geometry/count/
identity rejections, per-leaf candidate mismatches, immutability and
privacy-safe reprs, zero/False recipes, and norm/frame equivalence after a
failed confirmation. No tracked binary fixtures are used.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any

import pytest

from guiskindose import load_settings_example_json
from guiskindose.equipment_capture import capture_to_mapping
from guiskindose.equipment_confirmation import (
    CapturedApplicationReceipt,
    confirm_captured_application,
    prepare_captured_candidate,
)
from guiskindose.equipment_profiles import assemble_session
from guiskindose.equipment_profiles.capture import (
    CODE_EQUIPMENT_GEOMETRY_MISMATCH,
    CODE_INVALID_EQUIPMENT_CAPTURE,
    CaptureError,
)
from guiskindose.equipment_profiles.resolver import LEAF_ORDER
from guiskindose.helpers.read_and_normalize_rdsr_data import read_and_normalise_rdsr_data
from guiskindose.input_adapters.registry import read_and_normalize_input
from guiskindose.settings import PyskindoseSettings

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
    "{maker},{model},Fluoroscopy,Single Plane,1198,785,37.8,40.6,294.1,0.01,"
    "Copper or Copper compound,0.6,0.6,-0.1,-1.1,77.0,0.00003"
)


def _full_coordinates() -> dict[str, Any]:
    return {
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


def _session(doc: dict[str, Any]) -> Any:
    return assemble_session(documents=[doc])


def _settings(session: Any) -> PyskindoseSettings:
    return PyskindoseSettings(
        settings=load_settings_example_json(),
        output_format="dict",
        equipment_profile_session=session,
    )


def _dicom_capture(session: Any) -> tuple[Any, Any, PyskindoseSettings]:
    """Real DICOM normalizer receipt produced into a validated capture."""
    from guiskindose.equipment_capture import capture_from_receipt

    settings = _settings(session)
    out: list[Any] = []
    frame = read_and_normalise_rdsr_data(str(_DICOM), settings, equipment_receipt_out=out)
    assert len(out) == 1
    receipt = out[0]
    context = capture_from_receipt(receipt=receipt, frame=frame, settings=settings)
    return context, frame, settings


def _csv_capture(maker: str, model: str, session: Any, tmp_path: Path) -> tuple[Any, Any]:
    """Real raw CSV adapter receipt produced into a validated capture."""
    from guiskindose.equipment_capture import capture_from_receipt

    path = tmp_path / "raw.csv"
    path.write_text(
        _RAW_HEADER + "\n" + _RAW_ROW.format(maker=maker, model=model) + "\n",
        encoding="utf-8",
    )
    settings = _settings(session)
    result = read_and_normalize_input(path, input_schema="generic_rdsr_like", settings=settings)
    assert not isinstance(result, list)
    assert result.equipment_receipt is not None
    receipt = result.equipment_receipt
    frame = result.normalized_data
    context = capture_from_receipt(receipt=receipt, frame=frame, settings=settings)
    return context, frame


def _code(excinfo: pytest.ExceptionInfo[CaptureError]) -> str:
    return excinfo.value.code


def _force_attr(target: Any, name: str, value: Any) -> None:
    """Deliberately hostile attribute assignment for strictness tests.

    Bypasses static typing on purpose (production code never does this);
    the confirmation boundary must still reject every hostile value closed.
    """
    setattr(target, name, value)


def _norm_snapshot(norm: Any) -> dict[str, Any]:
    """Comparable snapshot of every candidate-carried value."""
    snapshot = {
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
    return snapshot


# ---------------------------------------------------------------------------
# Real-loader prepare/confirm paths
# ---------------------------------------------------------------------------


def test_full_custom_prepare_confirm() -> None:
    context, frame, settings = _dicom_capture(_session(_profile_doc("c-full", _full_coordinates())))
    norm = settings.normalization_settings
    candidate = prepare_captured_candidate(context=context, norm=norm)
    assert candidate is not norm
    assert candidate.trans_offset.x == 5.0
    assert candidate.trans_dir.x == 1
    assert candidate.trans_dir.y == -1
    assert candidate.rot_dir.Ap1 == -1
    assert candidate.swap_lateral_longitudinal is False
    assert candidate.field_size_mode == "CFA"
    assert candidate.detector_side_length == 30.0
    assert candidate.input_manufacturer == "Siemens"
    assert candidate.matched_model == "AXIOM-Artis"
    assert candidate.normalization_method == "Matched"
    receipt, mapping = confirm_captured_application(context=context, frame=frame, candidate=candidate)
    assert isinstance(receipt, CapturedApplicationReceipt)
    assert receipt.method == "Matched"
    assert receipt.event_count == len(frame)
    assert receipt.capture_hash == context.capture_hash
    assert receipt.geometry_hash == context.geometry_hash
    assert (receipt.maker_key, receipt.model_key) == ("siemens", "axiom artis")
    assert mapping == capture_to_mapping(context)["match"]


def test_prepare_is_pure_and_leaves_norm_untouched() -> None:
    context, _frame, settings = _dicom_capture(_session(_profile_doc("c-full", _full_coordinates())))
    norm = settings.normalization_settings
    before = _norm_snapshot(norm)
    first = prepare_captured_candidate(context=context, norm=norm)
    second = prepare_captured_candidate(context=context, norm=norm)
    assert first.attrs_str == second.attrs_str
    assert _norm_snapshot(norm) == before


def test_partial_prepare_confirm() -> None:
    context, frame, settings = _dicom_capture(
        _session(_profile_doc("c-partial", {"detector_side_length": 30.0}))
    )
    assert context.notice_kind == "partial"
    candidate = prepare_captured_candidate(context=context, norm=settings.normalization_settings)
    assert candidate.detector_side_length == 30.0
    receipt, mapping = confirm_captured_application(context=context, frame=frame, candidate=candidate)
    assert receipt.method == "Matched"
    assert mapping == capture_to_mapping(context)["match"]


def test_default_missing_maker_csv(tmp_path: Path) -> None:
    context, frame = _csv_capture("", "AXIOM-Artis", _session(_profile_doc("c-full", _full_coordinates())), tmp_path)
    assert context.source == "default"
    assert context.input_identity.manufacturer is None
    candidate = prepare_captured_candidate(
        context=context, norm=_settings(_session(_profile_doc("c-full", _full_coordinates()))).normalization_settings
    )
    receipt, mapping = confirm_captured_application(context=context, frame=frame, candidate=candidate)
    assert receipt.method == "Fallback"
    assert (receipt.maker_key, receipt.model_key) == ("", "axiom artis")
    assert mapping == capture_to_mapping(context)["match"]


def test_wildcard_csv(tmp_path: Path) -> None:
    context, frame = _csv_capture(
        "GE Healthcare", "Unlisted-Model-ZZZ", _session(_profile_doc("c-full", _full_coordinates())), tmp_path
    )
    assert context.source == "bundled"
    assert context.notice_kind == "complete"
    assert "GE Healthcare *" in context.notice_text
    candidate = prepare_captured_candidate(
        context=context, norm=_settings(_session(_profile_doc("c-full", _full_coordinates()))).normalization_settings
    )
    receipt, mapping = confirm_captured_application(context=context, frame=frame, candidate=candidate)
    assert receipt.method == "Matched"
    assert mapping == capture_to_mapping(context)["match"]


def test_zero_false_recipe_prepare_confirm() -> None:
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
    context, frame, settings = _dicom_capture(_session(_profile_doc("c-zero", coordinates)))
    candidate = prepare_captured_candidate(context=context, norm=settings.normalization_settings)
    assert candidate.trans_offset.x == 0.0
    assert candidate.swap_lateral_longitudinal is False
    receipt, _ = confirm_captured_application(context=context, frame=frame, candidate=candidate)
    assert receipt.event_count == len(frame)


# ---------------------------------------------------------------------------
# Offline reuse: no bundles, no sources
# ---------------------------------------------------------------------------


def test_offline_parse_confirm_after_source_deletion(tmp_path: Path) -> None:
    import json

    from guiskindose.equipment_capture import capture_to_json
    from guiskindose.equipment_profiles.capture_codec import capture_from_json

    doc = _profile_doc("c-full", _full_coordinates())
    path = tmp_path / "profiles.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    from guiskindose.equipment_profiles import FileSource

    session = assemble_session(files=[FileSource(path)])
    context, frame, _ = _dicom_capture(session)
    saved = capture_to_mapping(context)
    path.unlink()
    parsed = capture_from_json(capture_to_json(context))
    assert parsed == context
    fresh_norm = _settings(session).normalization_settings
    candidate = prepare_captured_candidate(context=parsed, norm=fresh_norm)
    receipt, mapping = confirm_captured_application(context=parsed, frame=frame, candidate=candidate)
    assert mapping == saved["match"]
    assert receipt.capture_hash == context.capture_hash
    fresh_norm.normalization_settings_list.clear()
    again = prepare_captured_candidate(context=parsed, norm=fresh_norm)
    receipt_again, _ = confirm_captured_application(context=parsed, frame=frame, candidate=again)
    assert receipt_again == receipt


# ---------------------------------------------------------------------------
# Stale frames must reject
# ---------------------------------------------------------------------------


def test_stale_geometry_same_count_rejected() -> None:
    context, frame, settings = _dicom_capture(_session(_profile_doc("c-full", _full_coordinates())))
    candidate = prepare_captured_candidate(context=context, norm=settings.normalization_settings)
    stale = frame.copy()
    stale["Tx"] = [float(value) + 100.0 for value in frame["Tx"]]
    with pytest.raises(CaptureError) as excinfo:
        confirm_captured_application(context=context, frame=stale, candidate=candidate)
    assert _code(excinfo) == CODE_EQUIPMENT_GEOMETRY_MISMATCH


def test_short_frame_rejected() -> None:
    context, frame, settings = _dicom_capture(_session(_profile_doc("c-full", _full_coordinates())))
    candidate = prepare_captured_candidate(context=context, norm=settings.normalization_settings)
    short = frame.iloc[:2].copy()
    with pytest.raises(CaptureError) as excinfo:
        confirm_captured_application(context=context, frame=short, candidate=candidate)
    assert _code(excinfo) == CODE_INVALID_EQUIPMENT_CAPTURE


def test_changed_identity_rejected() -> None:
    context, frame, settings = _dicom_capture(_session(_profile_doc("c-full", _full_coordinates())))
    candidate = prepare_captured_candidate(context=context, norm=settings.normalization_settings)
    renamed = frame.copy()
    renamed["manufacturer"] = ["Philips"] * len(frame)
    with pytest.raises(CaptureError) as excinfo:
        confirm_captured_application(context=context, frame=renamed, candidate=candidate)
    assert _code(excinfo) == CODE_INVALID_EQUIPMENT_CAPTURE


def test_failed_confirmation_leaves_norm_and_frame_equivalent() -> None:
    context, frame, settings = _dicom_capture(_session(_profile_doc("c-full", _full_coordinates())))
    norm = settings.normalization_settings
    candidate = prepare_captured_candidate(context=context, norm=norm)
    before_norm = _norm_snapshot(norm)
    before_candidate = _norm_snapshot(candidate)
    before_frame = frame.copy(deep=True)
    stale = frame.copy()
    stale["Tx"] = [float(value) + 100.0 for value in frame["Tx"]]
    with pytest.raises(CaptureError):
        confirm_captured_application(context=context, frame=stale, candidate=candidate)
    assert _norm_snapshot(norm) == before_norm
    assert _norm_snapshot(candidate) == before_candidate
    assert frame.equals(before_frame)


# ---------------------------------------------------------------------------
# Per-leaf candidate mismatches
# ---------------------------------------------------------------------------


_LEAF_MUTATIONS: dict[str, Any] = {
    "translation_offset.x": 9999.0,
    "translation_offset.y": 9999.0,
    "translation_offset.z": 9999.0,
    "translation_direction.x": "-",
    "translation_direction.y": "+",
    "translation_direction.z": "-",
    "rotation_direction.Ap1": "+",
    "rotation_direction.Ap2": "-",
    "rotation_direction.Ap3": "-",
    "rotation_direction.At1": "-",
    "rotation_direction.At2": "+",
    "rotation_direction.At3": "-",
    "swap_lateral_longitudinal": True,
    "field_size_mode": "ASD",
    "detector_side_length": 31.0,
}

_ROT_KEYS = ("Ap1", "Ap2", "Ap3", "At1", "At2", "At3")
_SIGN_BACK = {1: "+", -1: "-"}


def _mutated_candidate(context: Any, norm: Any, path: str, value: Any) -> Any:
    candidate = prepare_captured_candidate(context=context, norm=norm)
    block, _, name = path.partition(".")
    if block == "translation_offset":
        values = {axis: getattr(candidate.trans_offset, axis) for axis in ("x", "y", "z")}
        values[name] = value
        candidate.trans_offset.update_translation_offset(values)
    elif block == "translation_direction":
        home = candidate.trans_dir
        values = {axis: _SIGN_BACK[getattr(home, axis)] for axis in ("x", "y", "z")}
        values[name] = value
        home.update_translation_direction(values)
    elif block == "rotation_direction":
        home = candidate.rot_dir
        values = {key: _SIGN_BACK[getattr(home, key)] for key in _ROT_KEYS}
        values[name] = value
        home.update_rotation_direction(values)
    elif path == "swap_lateral_longitudinal":
        candidate.swap_lateral_longitudinal = value
    elif path == "field_size_mode":
        candidate.field_size_mode = value
    elif path == "detector_side_length":
        candidate.detector_side_length = value
    return candidate


@pytest.mark.parametrize("path", list(LEAF_ORDER))
def test_each_leaf_mismatch_rejected(path: str) -> None:
    context, frame, settings = _dicom_capture(_session(_profile_doc("c-full", _full_coordinates())))
    candidate = _mutated_candidate(context, settings.normalization_settings, path, _LEAF_MUTATIONS[path])
    with pytest.raises(CaptureError) as excinfo:
        confirm_captured_application(context=context, frame=frame, candidate=candidate)
    assert _code(excinfo) == CODE_INVALID_EQUIPMENT_CAPTURE


def test_label_mismatch_rejected() -> None:
    context, frame, settings = _dicom_capture(_session(_profile_doc("c-full", _full_coordinates())))
    candidate = prepare_captured_candidate(context=context, norm=settings.normalization_settings)
    candidate.matched_model = "Something Else"
    with pytest.raises(CaptureError) as excinfo:
        confirm_captured_application(context=context, frame=frame, candidate=candidate)
    assert _code(excinfo) == CODE_INVALID_EQUIPMENT_CAPTURE


# ---------------------------------------------------------------------------
# Types, reprs, invalid inputs
# ---------------------------------------------------------------------------


def test_receipt_validated_construction_and_repr() -> None:
    context, frame, settings = _dicom_capture(_session(_profile_doc("c-full", _full_coordinates())))
    candidate = prepare_captured_candidate(context=context, norm=settings.normalization_settings)
    receipt, _ = confirm_captured_application(context=context, frame=frame, candidate=candidate)
    rendered = repr(receipt)
    assert "Matched" in rendered
    assert context.capture_hash not in rendered
    assert context.geometry_hash not in rendered
    assert "siemens" not in rendered
    with pytest.raises(CaptureError):
        dataclasses.replace(receipt, method="Forged")
    with pytest.raises(CaptureError):
        dataclasses.replace(receipt, event_count=0)
    with pytest.raises(CaptureError):
        CapturedApplicationReceipt(
            capture_hash="0" * 64,
            geometry_hash="0" * 64,
            event_count=1,
            maker_key="siemens!",
            model_key="",
            method="Matched",
        )


def test_invalid_inputs_rejected() -> None:
    context, frame, settings = _dicom_capture(_session(_profile_doc("c-full", _full_coordinates())))
    candidate = prepare_captured_candidate(context=context, norm=settings.normalization_settings)
    with pytest.raises(CaptureError) as excinfo:
        confirm_captured_application(context=None, frame=frame, candidate=candidate)
    assert _code(excinfo) == CODE_INVALID_EQUIPMENT_CAPTURE
    with pytest.raises(CaptureError) as excinfo:
        confirm_captured_application(context=context, frame=frame, candidate=None)
    assert _code(excinfo) == CODE_INVALID_EQUIPMENT_CAPTURE
    with pytest.raises(CaptureError) as excinfo:
        prepare_captured_candidate(context=context, norm=None)
    assert _code(excinfo) == CODE_INVALID_EQUIPMENT_CAPTURE
    with pytest.raises(CaptureError) as excinfo:
        prepare_captured_candidate(context="not-a-context", norm=settings.normalization_settings)
    assert _code(excinfo) == CODE_INVALID_EQUIPMENT_CAPTURE
    with pytest.raises(CaptureError):
        dataclasses.replace(context, source="SYNTHETIC")


def test_nested_reprs_hide_values() -> None:
    context, _, _ = _dicom_capture(_session(_profile_doc("c-full", _full_coordinates())))
    assert "capture-full" not in repr(context)
    for leaf in context.fields:
        assert leaf.profile_id not in repr(leaf)
    assert "Siemens" not in repr(context.input_identity)


# ---------------------------------------------------------------------------
# All-rows identity: variation and mixes reject, spelling variants pass
# ---------------------------------------------------------------------------


def test_row_two_maker_variation_rejected() -> None:
    context, frame, settings = _dicom_capture(_session(_profile_doc("c-full", _full_coordinates())))
    candidate = prepare_captured_candidate(context=context, norm=settings.normalization_settings)
    varied = frame.copy()
    varied.loc[frame.index[1], "manufacturer"] = "Different Synthetic Maker"
    with pytest.raises(CaptureError) as excinfo:
        confirm_captured_application(context=context, frame=varied, candidate=candidate)
    assert _code(excinfo) == CODE_INVALID_EQUIPMENT_CAPTURE


def test_row_two_model_variation_rejected() -> None:
    context, frame, settings = _dicom_capture(_session(_profile_doc("c-full", _full_coordinates())))
    candidate = prepare_captured_candidate(context=context, norm=settings.normalization_settings)
    varied = frame.copy()
    varied.loc[frame.index[1], "model"] = "Different Model"
    with pytest.raises(CaptureError) as excinfo:
        confirm_captured_application(context=context, frame=varied, candidate=candidate)
    assert _code(excinfo) == CODE_INVALID_EQUIPMENT_CAPTURE


def test_known_unknown_mix_rejected() -> None:
    context, frame, settings = _dicom_capture(_session(_profile_doc("c-full", _full_coordinates())))
    candidate = prepare_captured_candidate(context=context, norm=settings.normalization_settings)
    varied = frame.copy()
    varied.loc[frame.index[1], "manufacturer"] = ""
    with pytest.raises(CaptureError) as excinfo:
        confirm_captured_application(context=context, frame=varied, candidate=candidate)
    assert _code(excinfo) == CODE_INVALID_EQUIPMENT_CAPTURE


def test_canonical_spelling_variant_accepted() -> None:
    context, frame, settings = _dicom_capture(_session(_profile_doc("c-full", _full_coordinates())))
    candidate = prepare_captured_candidate(context=context, norm=settings.normalization_settings)
    varied = frame.copy()
    varied["manufacturer"] = ["SIEMENS"] * len(frame)
    receipt, mapping = confirm_captured_application(context=context, frame=varied, candidate=candidate)
    assert (receipt.maker_key, receipt.model_key) == ("siemens", "axiom artis")
    assert mapping == capture_to_mapping(context)["match"]


# ---------------------------------------------------------------------------
# Strict live field types: no truthiness, coercion, or permissive equality
# ---------------------------------------------------------------------------


def test_swap_truthiness_rejected() -> None:
    context, frame, settings = _dicom_capture(_session(_profile_doc("c-full", _full_coordinates())))
    candidate = prepare_captured_candidate(context=context, norm=settings.normalization_settings)
    _force_attr(candidate, "swap_lateral_longitudinal", 0)
    with pytest.raises(CaptureError) as excinfo:
        confirm_captured_application(context=context, frame=frame, candidate=candidate)
    assert _code(excinfo) == CODE_INVALID_EQUIPMENT_CAPTURE


def test_swap_one_rejected() -> None:
    context, frame, settings = _dicom_capture(_session(_profile_doc("c-full", _full_coordinates())))
    candidate = prepare_captured_candidate(context=context, norm=settings.normalization_settings)
    _force_attr(candidate, "swap_lateral_longitudinal", 1)
    with pytest.raises(CaptureError) as excinfo:
        confirm_captured_application(context=context, frame=frame, candidate=candidate)
    assert _code(excinfo) == CODE_INVALID_EQUIPMENT_CAPTURE


def test_string_offset_rejected() -> None:
    context, frame, settings = _dicom_capture(_session(_profile_doc("c-full", _full_coordinates())))
    candidate = prepare_captured_candidate(context=context, norm=settings.normalization_settings)
    _force_attr(candidate.trans_offset, "x", "5.0")
    with pytest.raises(CaptureError) as excinfo:
        confirm_captured_application(context=context, frame=frame, candidate=candidate)
    assert _code(excinfo) == CODE_INVALID_EQUIPMENT_CAPTURE


def test_bool_direction_rejected() -> None:
    context, frame, settings = _dicom_capture(_session(_profile_doc("c-full", _full_coordinates())))
    candidate = prepare_captured_candidate(context=context, norm=settings.normalization_settings)
    candidate.trans_dir.x = True
    with pytest.raises(CaptureError) as excinfo:
        confirm_captured_application(context=context, frame=frame, candidate=candidate)
    assert _code(excinfo) == CODE_INVALID_EQUIPMENT_CAPTURE


def test_out_of_range_direction_rejected() -> None:
    context, frame, settings = _dicom_capture(_session(_profile_doc("c-full", _full_coordinates())))
    candidate = prepare_captured_candidate(context=context, norm=settings.normalization_settings)
    candidate.rot_dir.Ap1 = 2
    with pytest.raises(CaptureError) as excinfo:
        confirm_captured_application(context=context, frame=frame, candidate=candidate)
    assert _code(excinfo) == CODE_INVALID_EQUIPMENT_CAPTURE


def test_nan_offset_rejected() -> None:
    context, frame, settings = _dicom_capture(_session(_profile_doc("c-full", _full_coordinates())))
    candidate = prepare_captured_candidate(context=context, norm=settings.normalization_settings)
    candidate.trans_offset.y = float("nan")
    with pytest.raises(CaptureError) as excinfo:
        confirm_captured_application(context=context, frame=frame, candidate=candidate)
    assert _code(excinfo) == CODE_INVALID_EQUIPMENT_CAPTURE


def test_non_string_mode_rejected() -> None:
    context, frame, settings = _dicom_capture(_session(_profile_doc("c-full", _full_coordinates())))
    candidate = prepare_captured_candidate(context=context, norm=settings.normalization_settings)
    _force_attr(candidate, "field_size_mode", 5)
    with pytest.raises(CaptureError) as excinfo:
        confirm_captured_application(context=context, frame=frame, candidate=candidate)
    assert _code(excinfo) == CODE_INVALID_EQUIPMENT_CAPTURE


def test_string_subclass_mode_rejected() -> None:
    context, frame, settings = _dicom_capture(_session(_profile_doc("c-full", _full_coordinates())))
    candidate = prepare_captured_candidate(context=context, norm=settings.normalization_settings)

    class _Mode(str):
        pass

    candidate.field_size_mode = _Mode("CFA")
    with pytest.raises(CaptureError) as excinfo:
        confirm_captured_application(context=context, frame=frame, candidate=candidate)
    assert _code(excinfo) == CODE_INVALID_EQUIPMENT_CAPTURE


def test_non_string_label_rejected() -> None:
    context, frame, settings = _dicom_capture(_session(_profile_doc("c-full", _full_coordinates())))
    candidate = prepare_captured_candidate(context=context, norm=settings.normalization_settings)
    _force_attr(candidate, "input_manufacturer", 5)
    with pytest.raises(CaptureError) as excinfo:
        confirm_captured_application(context=context, frame=frame, candidate=candidate)
    assert _code(excinfo) == CODE_INVALID_EQUIPMENT_CAPTURE


# ---------------------------------------------------------------------------
# Receipt construction: exact method type, bounded keys
# ---------------------------------------------------------------------------


class _EvilStr(str):
    pass


class _AlwaysEqual:
    def __eq__(self, other: object) -> bool:
        return True

    def __repr__(self) -> str:
        return "LEAK-METHOD"


def test_receipt_method_exact_builtin_str() -> None:
    context, frame, settings = _dicom_capture(_session(_profile_doc("c-full", _full_coordinates())))
    candidate = prepare_captured_candidate(context=context, norm=settings.normalization_settings)
    receipt, _ = confirm_captured_application(context=context, frame=frame, candidate=candidate)
    evil = _EvilStr("Matched")
    with pytest.raises(CaptureError) as excinfo:
        dataclasses.replace(receipt, method=evil)
    assert _code(excinfo) == CODE_INVALID_EQUIPMENT_CAPTURE
    always_equal = _AlwaysEqual()
    with pytest.raises(CaptureError) as excinfo:
        dataclasses.replace(receipt, method=always_equal)
    assert _code(excinfo) == CODE_INVALID_EQUIPMENT_CAPTURE
    assert "LEAK-METHOD" not in str(excinfo.value)


def test_receipt_huge_keys_rejected_before_normalization() -> None:
    context, frame, settings = _dicom_capture(_session(_profile_doc("c-full", _full_coordinates())))
    candidate = prepare_captured_candidate(context=context, norm=settings.normalization_settings)
    receipt, _ = confirm_captured_application(context=context, frame=frame, candidate=candidate)
    with pytest.raises(CaptureError) as excinfo:
        dataclasses.replace(receipt, maker_key="x" * 1000)
    assert _code(excinfo) == CODE_INVALID_EQUIPMENT_CAPTURE
    with pytest.raises(CaptureError) as excinfo:
        dataclasses.replace(receipt, model_key="y" * 1000)
    assert _code(excinfo) == CODE_INVALID_EQUIPMENT_CAPTURE


# ---------------------------------------------------------------------------
# Clone purity: shared handles reject, ordinary subclasses still work
# ---------------------------------------------------------------------------


class _SharedOffset:
    def __init__(self, inner: Any) -> None:
        self._inner = inner

    def __deepcopy__(self, memo: Any) -> Any:
        return self


class _BoomClone:
    pass


def test_shared_nested_clone_rejected_and_caller_unchanged() -> None:
    from guiskindose.settings.normalization_settings import NormalizationSettings

    context, _frame, settings = _dicom_capture(_session(_profile_doc("c-full", _full_coordinates())))
    norm = settings.normalization_settings
    assert isinstance(norm, NormalizationSettings)
    inner = norm.trans_offset
    before = (inner.x, inner.y, inner.z)
    wrapper = _SharedOffset(inner)
    norm.trans_offset = wrapper  # type: ignore[assignment]
    with pytest.raises(CaptureError) as excinfo:
        prepare_captured_candidate(context=context, norm=norm)
    assert _code(excinfo) == CODE_INVALID_EQUIPMENT_CAPTURE
    actual_offsets = (inner.x, inner.y, inner.z)
    assert actual_offsets == before
    assert norm.trans_offset is wrapper


def test_plain_subclass_still_prepares() -> None:
    from guiskindose.settings.normalization_settings import NormalizationSettings

    class _PlainSub(NormalizationSettings):
        pass

    context, frame, settings = _dicom_capture(_session(_profile_doc("c-full", _full_coordinates())))
    sub = _PlainSub(settings.normalization_settings.normalization_settings_list)
    candidate = prepare_captured_candidate(context=context, norm=sub)
    assert type(candidate) is _PlainSub
    assert candidate.trans_offset.x == 5.0
    receipt, _ = confirm_captured_application(context=context, frame=frame, candidate=candidate)
    assert receipt.method == "Matched"


def test_deepcopy_failure_closed_without_raw_cause() -> None:
    from guiskindose.settings.normalization_settings import NormalizationSettings

    class _Boom(NormalizationSettings):
        def __deepcopy__(self, memo: Any) -> Any:
            raise RuntimeError("boom")

    context, _frame, settings = _dicom_capture(_session(_profile_doc("c-full", _full_coordinates())))
    sub = _Boom(settings.normalization_settings.normalization_settings_list)
    with pytest.raises(CaptureError) as excinfo:
        prepare_captured_candidate(context=context, norm=sub)
    assert _code(excinfo) == CODE_INVALID_EQUIPMENT_CAPTURE
    assert "boom" not in str(excinfo.value)
