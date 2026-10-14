"""Tests for DICOM-only loader replay from captured authorities.

Every capture flows from a real raw DICOM load through the capture producer;
replay then re-reads the same raw source with no live session. Covers
Siemens-CFA and Philips-ASD byte/numeric geometry plus PSD/dose-map parity,
offline replay with bundled selection and resolution forcibly broken,
full/partial/default/zero-False/negative-At2 recipes, confirm-after-filter
ordering via a monkeypatched parser, remove-invalid-rows policy divergence,
captured-mode concept enforcement in both modes, changed raw geometry and
identity rejection, direct-normalizer non-publication, mismatched and
unsupported contexts, JSON refusal, and caller-state preservation. No tracked
binary fixtures are used.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from guiskindose import get_path_to_example_rdsr_files, load_settings_example_json
from guiskindose.equipment_profiles import FileSource, assemble_session
from guiskindose.equipment_profiles.capture import (
    CODE_EQUIPMENT_GEOMETRY_MISMATCH,
    CODE_INVALID_EQUIPMENT_CAPTURE,
    CaptureError,
)
from guiskindose.helpers.read_and_normalize_rdsr_data import read_and_normalise_rdsr_data
from guiskindose.main import analyze_data, analyze_input_file
from guiskindose.settings import PyskindoseSettings

_SIEMENS_DICOM = get_path_to_example_rdsr_files() / "siemens_axiom_artis.dcm"
_PHILIPS_DICOM = get_path_to_example_rdsr_files() / "philips_allura_clarity_u104.dcm"
_FAKE_DICOM = get_path_to_example_rdsr_files() / "fake_scanner.dcm"


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


def _siemens_doc(profile_id: str = "r-siemens") -> dict[str, Any]:
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


def _philips_doc() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "profiles": [
            {
                "profile_id": "r-philips",
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


def _live_capture(dicom: Path, session: Any) -> tuple[Any, Any, PyskindoseSettings]:
    """Real raw load plus validated capture (no calculation)."""
    from guiskindose.equipment_capture import capture_from_receipt

    settings = _dose_settings(session)
    out: list[Any] = []
    frame = read_and_normalise_rdsr_data(str(dicom), settings, equipment_receipt_out=out)
    assert len(out) == 1
    receipt = out[0]
    context = capture_from_receipt(receipt=receipt, frame=frame, settings=settings)
    return context, frame, settings


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
# Real-loader replay parity
# ---------------------------------------------------------------------------


def test_siemens_cfa_replay_parity() -> None:
    session = assemble_session(documents=[_siemens_doc()])
    live_output = analyze_input_file(str(_SIEMENS_DICOM), settings=_dose_settings(session))
    context, frame, _ = _live_capture(_SIEMENS_DICOM, session)
    fresh = _dose_settings()
    replayed = read_and_normalise_rdsr_data(str(_SIEMENS_DICOM), fresh, equipment_capture_context=context)
    assert replayed.equals(frame)
    actual: Any = analyze_data(replayed, fresh, equipment_capture_context=context)
    assert actual["psd"] == live_output["psd"]
    assert actual["dose_map"] == live_output["dose_map"]
    assert actual["equipment_profile_match"] == live_output["equipment_profile_match"]


def test_philips_asd_replay_parity() -> None:
    session = assemble_session(documents=[_philips_doc()])
    live_output = analyze_input_file(str(_PHILIPS_DICOM), settings=_dose_settings(session))
    context, frame, _ = _live_capture(_PHILIPS_DICOM, session)
    assert context.source == "custom"
    fresh = _dose_settings()
    replayed = read_and_normalise_rdsr_data(str(_PHILIPS_DICOM), fresh, equipment_capture_context=context)
    assert replayed.equals(frame)
    actual: Any = analyze_data(replayed, fresh, equipment_capture_context=context)
    assert actual["psd"] == live_output["psd"]
    assert actual["dose_map"] == live_output["dose_map"]
    assert actual["equipment_profile_match"] == live_output["equipment_profile_match"]


def test_partial_replay_parity() -> None:
    doc = {
        "schema_version": 1,
        "profiles": [
            {
                "profile_id": "r-partial",
                "manufacturer": "Siemens",
                "models": ["AXIOM-Artis"],
                "coordinates": {"detector_side_length": 30.0},
            }
        ],
    }
    session = assemble_session(documents=[doc])
    live_output = analyze_input_file(str(_SIEMENS_DICOM), settings=_dose_settings(session))
    context, _, _ = _live_capture(_SIEMENS_DICOM, session)
    assert context.notice_kind == "partial"
    fresh = _dose_settings()
    replayed = read_and_normalise_rdsr_data(str(_SIEMENS_DICOM), fresh, equipment_capture_context=context)
    actual: Any = analyze_data(replayed, fresh, equipment_capture_context=context)
    assert actual["psd"] == live_output["psd"]
    assert actual["equipment_profile_match"] == live_output["equipment_profile_match"]


def test_default_replay_parity() -> None:
    session = assemble_session(documents=[_siemens_doc()])
    live_output = analyze_input_file(str(_FAKE_DICOM), settings=_dose_settings(session))
    assert live_output["equipment_profile_match"]["source"] == "default"
    context, frame, _ = _live_capture(_FAKE_DICOM, session)
    assert context.source == "default"
    fresh = _dose_settings()
    replayed = read_and_normalise_rdsr_data(str(_FAKE_DICOM), fresh, equipment_capture_context=context)
    assert replayed.equals(frame)
    actual: Any = analyze_data(replayed, fresh, equipment_capture_context=context)
    assert actual["psd"] == live_output["psd"]
    assert actual["equipment_profile_match"] == live_output["equipment_profile_match"]


def test_zero_false_negative_at2_replay_parity() -> None:
    coordinates = {
        "translation_offset": {"x": 0.0, "y": 0.0, "z": 0.0},
        "translation_direction": {"x": "+", "y": "+", "z": "+"},
        "rotation_direction": {
            "Ap1": "+",
            "Ap2": "+",
            "Ap3": "+",
            "At1": "+",
            "At2": "-",
            "At3": "+",
        },
        "swap_lateral_longitudinal": False,
        "field_size_mode": "CFA",
        "detector_side_length": 20.0,
    }
    doc = {
        "schema_version": 1,
        "profiles": [
            {
                "profile_id": "r-zero",
                "manufacturer": "Siemens",
                "models": ["AXIOM-Artis"],
                "coordinates": coordinates,
            }
        ],
    }
    session = assemble_session(documents=[doc])
    live_output = analyze_input_file(str(_SIEMENS_DICOM), settings=_dose_settings(session))
    context, frame, _ = _live_capture(_SIEMENS_DICOM, session)
    fresh = _dose_settings()
    replayed = read_and_normalise_rdsr_data(str(_SIEMENS_DICOM), fresh, equipment_capture_context=context)
    assert replayed.equals(frame)
    actual: Any = analyze_data(replayed, fresh, equipment_capture_context=context)
    assert actual["psd"] == live_output["psd"]
    assert actual["dose_map"] == live_output["dose_map"]


# ---------------------------------------------------------------------------
# Offline replay: bundled selection and resolution forcibly broken
# ---------------------------------------------------------------------------


def test_no_bundle_or_resolver_consultation(monkeypatch: Any, tmp_path: Path) -> None:
    from guiskindose.settings import normalization_settings as normalization_module

    doc = _siemens_doc()
    path = tmp_path / "profiles.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    session = assemble_session(files=[FileSource(path)])
    context, frame, _ = _live_capture(_SIEMENS_DICOM, session)
    path.unlink()

    def _raise_selection(self: Any, data_parsed: Any) -> Any:
        raise AssertionError("bundled selection consulted during replay")

    def _raise_resolve(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("live resolver consulted during replay")

    monkeypatch.setattr(
        normalization_module.NormalizationSettings, "update_used_settings", _raise_selection
    )
    monkeypatch.setattr(
        "guiskindose.equipment_resolution.resolve_exam_coordinates", _raise_resolve
    )
    fresh = _dose_settings()
    replayed = read_and_normalise_rdsr_data(str(_SIEMENS_DICOM), fresh, equipment_capture_context=context)
    assert replayed.equals(frame)


# ---------------------------------------------------------------------------
# Confirm-after-filter ordering via a monkeypatched parser
# ---------------------------------------------------------------------------


def _injecting_parser(make_row: Any) -> Any:
    """Wrap the real DICOM parser appending one crafted parsed row."""
    import guiskindose.helpers.read_and_normalize_rdsr_data as helper_module

    real_parser = helper_module.rdsr_parser

    def _parser(data_raw: Any, silence_pydicom_warnings: bool = True) -> Any:
        parsed = real_parser(data_raw, silence_pydicom_warnings=silence_pydicom_warnings)
        extra = parsed.iloc[[0]].copy()
        make_row(extra)
        return pd.concat([parsed, extra], ignore_index=True)

    return _parser


def test_dropped_row_replay_accepts() -> None:
    import numpy as _np

    import guiskindose.helpers.read_and_normalize_rdsr_data as helper_module

    session = assemble_session(documents=[_siemens_doc()])
    context, frame, _ = _live_capture(_SIEMENS_DICOM, session)

    def _make_droppable(extra: Any) -> None:
        extra["DoseRP_Gy"] = 0.0
        extra["CollimatedFieldArea_m2"] = _np.nan

    parser = _injecting_parser(_make_droppable)
    fresh = _dose_settings()
    original = helper_module.rdsr_parser
    helper_module.rdsr_parser = parser
    try:
        replayed = read_and_normalise_rdsr_data(str(_SIEMENS_DICOM), fresh, equipment_capture_context=context)
    finally:
        helper_module.rdsr_parser = original
    assert replayed.equals(frame)


def test_kvp_policy_flip_fails_closed() -> None:
    import guiskindose.helpers.read_and_normalize_rdsr_data as helper_module

    session = assemble_session(documents=[_siemens_doc()])
    _, plain_frame, _ = _live_capture(_SIEMENS_DICOM, session)
    plain_count = len(plain_frame)

    def _make_kvp_zero(extra: Any) -> None:
        extra["KVP_kV"] = 0.0

    parser = _injecting_parser(_make_kvp_zero)
    original = helper_module.rdsr_parser
    helper_module.rdsr_parser = parser
    try:
        capture_settings = _dose_settings(session)
        capture_settings.remove_invalid_rows = False
        out: list[Any] = []
        injected = read_and_normalise_rdsr_data(str(_SIEMENS_DICOM), capture_settings, equipment_receipt_out=out)
        assert len(out) == 1
        from guiskindose.equipment_capture import capture_from_receipt

        injected_context = capture_from_receipt(receipt=out[0], frame=injected, settings=capture_settings)
        assert len(injected) == plain_count + 1
        strict = _dose_settings()
        strict.remove_invalid_rows = True
        prepared_path = str(_SIEMENS_DICOM)
        with pytest.raises(CaptureError) as excinfo:
            read_and_normalise_rdsr_data(prepared_path, strict, equipment_capture_context=injected_context)
        assert _code(excinfo) == CODE_INVALID_EQUIPMENT_CAPTURE
        lenient = _dose_settings()
        lenient.remove_invalid_rows = False
        replayed = read_and_normalise_rdsr_data(str(_SIEMENS_DICOM), lenient, equipment_capture_context=injected_context)
        assert replayed.equals(injected)
    finally:
        helper_module.rdsr_parser = original


# ---------------------------------------------------------------------------
# Captured mode enforcement, tampering, and authority conflicts
# ---------------------------------------------------------------------------


def test_mismatched_mode_rejected() -> None:
    import hashlib

    from guiskindose.equipment_capture import capture_to_mapping
    from guiskindose.equipment_profiles.canonical import canonical_json_bytes
    from guiskindose.equipment_profiles.capture_codec import (
        capture_from_mapping,
        normalize_capture_body,
    )

    session = assemble_session(documents=[_philips_doc()])
    context, _, _ = _live_capture(_PHILIPS_DICOM, session)
    mapping = capture_to_mapping(context)
    mapping["effective_coordinates"]["field_size_mode"] = "CFA"
    mapping["match"]["fields"] = [
        {**leaf, "value": "CFA"} if leaf["field"] == "field_size_mode" else leaf
        for leaf in mapping["match"]["fields"]
    ]
    body = {key: value for key, value in mapping.items() if key != "capture_hash"}
    normalized = normalize_capture_body(body)
    normalized["capture_hash"] = hashlib.sha256(canonical_json_bytes(normalized)).hexdigest()
    cfa_context = capture_from_mapping(normalized)
    fresh = _dose_settings()
    prepared_path = str(_PHILIPS_DICOM)
    with pytest.raises(CaptureError) as excinfo:
        read_and_normalise_rdsr_data(prepared_path, fresh, equipment_capture_context=cfa_context)
    assert _code(excinfo) == CODE_INVALID_EQUIPMENT_CAPTURE


def test_changed_raw_geometry_rejected() -> None:
    import guiskindose.helpers.read_and_normalize_rdsr_data as helper_module
    from guiskindose.rdsr_parser import rdsr_parser as real_parser

    session = assemble_session(documents=[_siemens_doc()])
    context, _, _ = _live_capture(_SIEMENS_DICOM, session)

    def _shifted(data_raw: Any, silence_pydicom_warnings: bool = True) -> Any:
        parsed = real_parser(data_raw, silence_pydicom_warnings=silence_pydicom_warnings)
        shifted = parsed.copy()
        shifted["TableLongitudinalPosition_mm"] = [float(value) + 1000.0 for value in parsed["TableLongitudinalPosition_mm"]]
        return shifted

    original = helper_module.rdsr_parser
    helper_module.rdsr_parser = _shifted
    try:
        fresh = _dose_settings()
        prepared_path = str(_SIEMENS_DICOM)
        with pytest.raises(CaptureError) as excinfo:
            read_and_normalise_rdsr_data(prepared_path, fresh, equipment_capture_context=context)
        assert _code(excinfo) == CODE_EQUIPMENT_GEOMETRY_MISMATCH
    finally:
        helper_module.rdsr_parser = original


def test_changed_raw_identity_rejected() -> None:
    import guiskindose.helpers.read_and_normalize_rdsr_data as helper_module
    from guiskindose.rdsr_parser import rdsr_parser as real_parser

    session = assemble_session(documents=[_siemens_doc()])
    context, _, _ = _live_capture(_SIEMENS_DICOM, session)

    def _renamed(data_raw: Any, silence_pydicom_warnings: bool = True) -> Any:
        parsed = real_parser(data_raw, silence_pydicom_warnings=silence_pydicom_warnings)
        renamed = parsed.copy()
        renamed["Manufacturer"] = ["Philips"] * len(parsed)
        return renamed

    original = helper_module.rdsr_parser
    helper_module.rdsr_parser = _renamed
    try:
        fresh = _dose_settings()
        prepared_path = str(_SIEMENS_DICOM)
        with pytest.raises(CaptureError) as excinfo:
            read_and_normalise_rdsr_data(prepared_path, fresh, equipment_capture_context=context)
        assert _code(excinfo) == CODE_INVALID_EQUIPMENT_CAPTURE
    finally:
        helper_module.rdsr_parser = original


def test_direct_normalizer_publishes_nothing() -> None:
    from guiskindose.equipment_confirmation import prepare_replay_settings
    from guiskindose.rdsr_normalizer import rdsr_normalizer
    from guiskindose.rdsr_parser import rdsr_parser as real_parser

    session = assemble_session(documents=[_siemens_doc()])
    context, _, _ = _live_capture(_SIEMENS_DICOM, session)
    parsed = real_parser(_read_raw(_SIEMENS_DICOM), silence_pydicom_warnings=True)
    prepared = prepare_replay_settings(context=context, settings=_dose_settings())
    published: list[Any] = []
    with pytest.raises(CaptureError) as excinfo:
        rdsr_normalizer(
            parsed, prepared, equipment_receipt_out=published, equipment_capture_context=context
        )
    assert _code(excinfo) == CODE_INVALID_EQUIPMENT_CAPTURE
    assert published == []


def _read_raw(dicom: Path) -> Any:
    """Read one raw DICOM dataset outside any raises block."""
    import pydicom

    return pydicom.dcmread(str(dicom))


def test_prepare_replay_settings_rejects_bound_session() -> None:
    from guiskindose.equipment_confirmation import prepare_replay_settings

    session = assemble_session(documents=[_siemens_doc()])
    context, _, _ = _live_capture(_SIEMENS_DICOM, session)
    settings = _dose_settings(session)
    before = _snapshot_norm(settings.normalization_settings)
    with pytest.raises(CaptureError) as excinfo:
        prepare_replay_settings(context=context, settings=settings)
    assert _code(excinfo) == CODE_INVALID_EQUIPMENT_CAPTURE
    assert _snapshot_norm(settings.normalization_settings) == before


def test_direct_hook_unprepared_settings_rejected() -> None:
    from guiskindose.rdsr_normalizer import rdsr_normalizer
    from guiskindose.rdsr_parser import rdsr_parser as real_parser

    session = assemble_session(documents=[_siemens_doc()])
    context, _, _ = _live_capture(_SIEMENS_DICOM, session)
    parsed = real_parser(_read_raw(_SIEMENS_DICOM), silence_pydicom_warnings=True)
    fresh = _dose_settings()
    before = _snapshot_norm(fresh.normalization_settings)
    with pytest.raises(CaptureError) as excinfo:
        rdsr_normalizer(parsed, fresh, equipment_capture_context=context)
    assert _code(excinfo) == CODE_INVALID_EQUIPMENT_CAPTURE
    assert _snapshot_norm(fresh.normalization_settings) == before


def test_direct_hook_malformed_capture_rejected_before_work() -> None:
    import copy as _copy

    from guiskindose.rdsr_normalizer import rdsr_normalizer
    from guiskindose.rdsr_parser import rdsr_parser as real_parser

    session = assemble_session(documents=[_siemens_doc()])
    context, _, _ = _live_capture(_SIEMENS_DICOM, session)
    forged = _copy.copy(context)
    object.__setattr__(forged, "event_count", "bad")
    parsed = real_parser(_read_raw(_SIEMENS_DICOM), silence_pydicom_warnings=True)
    fresh = _dose_settings()
    before = _snapshot_norm(fresh.normalization_settings)
    with pytest.raises(CaptureError) as excinfo:
        rdsr_normalizer(parsed, fresh, equipment_capture_context=forged)
    assert _code(excinfo) == CODE_INVALID_EQUIPMENT_CAPTURE
    assert _snapshot_norm(fresh.normalization_settings) == before


def test_corrupted_context_reads_zero_sources(monkeypatch: Any) -> None:
    import copy as _copy

    import guiskindose.helpers.read_and_normalize_rdsr_data as helper_module

    session = assemble_session(documents=[_siemens_doc()])
    context, _, _ = _live_capture(_SIEMENS_DICOM, session)
    forged = _copy.copy(context)
    object.__setattr__(forged, "event_count", "bad")
    real_read = helper_module.pydicom.dcmread
    reads: list[str] = []

    def _spy(path: Any, *args: Any, **kwargs: Any) -> Any:
        reads.append(str(path))
        return real_read(path, *args, **kwargs)

    monkeypatch.setattr(helper_module.pydicom, "dcmread", _spy)
    fresh = _dose_settings()
    prepared_path = str(_SIEMENS_DICOM)
    with pytest.raises(CaptureError) as excinfo:
        read_and_normalise_rdsr_data(prepared_path, fresh, equipment_capture_context=forged)
    assert _code(excinfo) == CODE_INVALID_EQUIPMENT_CAPTURE
    assert reads == []


def test_receipt_out_conflict_rejected_before_io(tmp_path: Path) -> None:
    session = assemble_session(documents=[_siemens_doc()])
    context, _, _ = _live_capture(_SIEMENS_DICOM, session)
    missing = tmp_path / "missing.dcm"
    published: list[Any] = []
    prepared_path = str(missing)
    prepared_settings = _dose_settings()
    with pytest.raises(CaptureError) as excinfo:
        read_and_normalise_rdsr_data(
            prepared_path, prepared_settings, equipment_receipt_out=published, equipment_capture_context=context
        )
    assert _code(excinfo) == CODE_INVALID_EQUIPMENT_CAPTURE
    assert published == []


def test_session_conflict_rejected_before_io(tmp_path: Path) -> None:
    session = assemble_session(documents=[_siemens_doc()])
    context, _, _ = _live_capture(_SIEMENS_DICOM, session)
    missing = tmp_path / "missing.dcm"
    prepared_path = str(missing)
    prepared_settings = _dose_settings(session)
    with pytest.raises(CaptureError) as excinfo:
        read_and_normalise_rdsr_data(
            prepared_path, prepared_settings, equipment_capture_context=context
        )
    assert _code(excinfo) == CODE_INVALID_EQUIPMENT_CAPTURE


def test_mismatched_and_unsupported_contexts() -> None:
    siemens_session = assemble_session(documents=[_siemens_doc()])
    philips_session = assemble_session(documents=[_philips_doc()])
    philips_context, _, _ = _live_capture(_PHILIPS_DICOM, philips_session)
    fresh = _dose_settings()
    prepared_path = str(_SIEMENS_DICOM)
    with pytest.raises(CaptureError) as excinfo:
        read_and_normalise_rdsr_data(prepared_path, fresh, equipment_capture_context=philips_context)
    assert _code(excinfo) == CODE_INVALID_EQUIPMENT_CAPTURE
    bad: Any = "not-a-context"
    prepared_path = str(_SIEMENS_DICOM)
    with pytest.raises(CaptureError) as excinfo:
        read_and_normalise_rdsr_data(prepared_path, fresh, equipment_capture_context=bad)
    assert _code(excinfo) == CODE_INVALID_EQUIPMENT_CAPTURE
    forged = _forged_context(siemens_session)
    prepared_path = str(_SIEMENS_DICOM)
    with pytest.raises(CaptureError) as excinfo:
        read_and_normalise_rdsr_data(prepared_path, fresh, equipment_capture_context=forged)
    assert _code(excinfo) == CODE_INVALID_EQUIPMENT_CAPTURE


def _forged_context(session: Any) -> Any:
    import copy as _copy

    context, _, _ = _live_capture(_SIEMENS_DICOM, session)
    forged = _copy.copy(context)
    object.__setattr__(forged, "event_count", 9999)
    return forged


def test_json_refusal_before_io(tmp_path: Path) -> None:
    session = assemble_session(documents=[_siemens_doc()])
    context, _, _ = _live_capture(_SIEMENS_DICOM, session)
    missing = tmp_path / "missing.json"
    prepared_path = str(missing)
    prepared_settings = _dose_settings()
    with pytest.raises(CaptureError) as excinfo:
        read_and_normalise_rdsr_data(prepared_path, prepared_settings, equipment_capture_context=context)
    assert _code(excinfo) == CODE_INVALID_EQUIPMENT_CAPTURE


def test_caller_settings_preserved() -> None:
    session = assemble_session(documents=[_siemens_doc()])
    context, frame, _ = _live_capture(_SIEMENS_DICOM, session)
    fresh = _dose_settings()
    before = _snapshot_norm(fresh.normalization_settings)
    replayed = read_and_normalise_rdsr_data(str(_SIEMENS_DICOM), fresh, equipment_capture_context=context)
    assert replayed.equals(frame)
    assert _snapshot_norm(fresh.normalization_settings) == before
    tampered = dict(_siemens_doc())
    bad_session = assemble_session(documents=[tampered])
    bad_context, _, _ = _live_capture(_SIEMENS_DICOM, bad_session)
    prepared_path = str(_PHILIPS_DICOM)
    with pytest.raises(CaptureError):
        read_and_normalise_rdsr_data(prepared_path, fresh, equipment_capture_context=bad_context)
    assert _snapshot_norm(fresh.normalization_settings) == before
