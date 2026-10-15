"""Tests for the standalone capture codec/validation foundation.

Producer regressions use successful receipts from the real raw normalizer
(DICOM) and the real raw CSV adapter — never hand-built resolutions. Covers
JSON round-trips, effective-scalar equivalence with live API resolutions,
file/store/memory session captures, portable dtype/negative-zero geometry
hashes, stale-geometry/identity/session/live-field/forged-notice rejection,
tamper and type rejections with recomputed checksums, limit enforcement
before copying, future versions/modes, immutability and forgery resistance,
privacy-safe reprs/errors, offline reuse without reopening sources, JSON
depth/node/unicode/overflow guards, lying lengths, and the intact
coordinate-only capability gate. No tracked binary fixtures are used.
"""

from __future__ import annotations

import copy
import dataclasses
import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from guiskindose import load_settings_example_json
from guiskindose.equipment_capture import (
    capture_from_receipt,
    capture_to_json,
    capture_to_mapping,
    envelope_to_json,
    envelope_to_mapping,
    geometry_digest_v1,
)
from guiskindose.equipment_profiles import (
    EquipmentProfileError,
    FileSource,
    ProfileErrorCode,
    ProfileStore,
    assemble_session,
    parse_memory_document,
)
from guiskindose.equipment_profiles.canonical import canonical_json_bytes
from guiskindose.equipment_profiles.capture import (
    CAPTURE_ENVELOPE_SCHEMA_VERSION,
    CODE_INVALID_EQUIPMENT_CAPTURE,
    CODE_UNSUPPORTED_EQUIPMENT_CAPTURE_VERSION,
    GEOMETRY_COLUMNS_V1,
    CapturedCoordinates,
    CapturedIdentity,
    CaptureError,
    validate_constructed_context,
)
from guiskindose.equipment_profiles.capture_codec import (
    capture_from_json,
    capture_from_mapping,
    envelope_from_json,
    parse_envelope,
)
from guiskindose.equipment_profiles.resolver import LEAF_ORDER, ResolutionNotice
from guiskindose.equipment_resolution import (
    EquipmentApplicationReceipt,
    first_published_equipment_receipt,
    receipt_to_mapping,
)
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
    "Siemens,AXIOM-Artis,Fluoroscopy,Single Plane,1198,785,37.8,40.6,294.1,0.01,"
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


def _memory_session() -> Any:
    return assemble_session(documents=[_profile_doc("capture-full", _full_coordinates())])


def _settings(session: Any) -> PyskindoseSettings:
    return PyskindoseSettings(
        settings=load_settings_example_json(), equipment_profile_session=session
    )


def _dicom_receipt(
    session: Any,
) -> tuple[EquipmentApplicationReceipt, pd.DataFrame, PyskindoseSettings]:
    """Run the real DICOM normalizer with a bound session; return receipt, frame, settings."""
    settings = _settings(session)
    out: list[Any] = []
    frame = read_and_normalise_rdsr_data(str(_DICOM), settings, equipment_receipt_out=out)
    assert len(out) == 1
    return out[0], frame, settings


def _csv_receipt(
    session: Any, tmp_path: Path
) -> tuple[EquipmentApplicationReceipt, pd.DataFrame, PyskindoseSettings]:
    """Run the real raw CSV adapter with a bound session."""
    path = tmp_path / "raw.csv"
    path.write_text(_RAW_HEADER + "\n" + _RAW_ROW + "\n", encoding="utf-8")
    settings = _settings(session)
    result = read_and_normalize_input(
        path, input_schema="generic_rdsr_like", settings=settings
    )
    assert not isinstance(result, list)
    assert result.equipment_receipt is not None
    return result.equipment_receipt, result.normalized_data, settings


def _code(excinfo: pytest.ExceptionInfo[CaptureError]) -> str:
    return excinfo.value.code


def _rehashed(mapping: dict[str, Any]) -> dict[str, Any]:
    """Recompute a valid checksum over mutated content so semantic checks fire, not hash checks."""
    body = {key: value for key, value in mapping.items() if key != "capture_hash"}
    mapping["capture_hash"] = hashlib.sha256(canonical_json_bytes(body)).hexdigest()
    return mapping


def _mapping() -> dict[str, Any]:
    receipt, frame, settings = _dicom_receipt(_memory_session())
    context = capture_from_receipt(receipt=receipt, frame=frame, settings=settings)
    return copy.deepcopy(capture_to_mapping(context))


# ---------------------------------------------------------------------------
# Real-normalizer producer paths
# ---------------------------------------------------------------------------


def test_dicom_capture_round_trip() -> None:
    receipt, frame, settings = _dicom_receipt(_memory_session())
    context = capture_from_receipt(receipt=receipt, frame=frame, settings=settings)
    assert isinstance(context, CapturedCoordinates)
    assert context.event_count == len(frame) > 0
    assert context.profile_id == "capture-full"
    assert context.source == "custom"
    assert context.notice_kind == "complete"
    assert context.notice_text == receipt.resolution.notice.text
    assert [leaf.field for leaf in context.fields] == list(LEAF_ORDER)
    live = {leaf.field: leaf.value for leaf in receipt.resolution.record.fields}
    for path in LEAF_ORDER:
        assert context.effective_value(path) == live[path]
    with pytest.raises(CaptureError):
        context.effective_value("translation_offset.w")
    assert capture_from_mapping(capture_to_mapping(context)) == context
    assert capture_from_json(capture_to_json(context)) == context


def test_producer_match_matches_bridge_mapping() -> None:
    receipt, frame, settings = _dicom_receipt(_memory_session())
    context = capture_from_receipt(receipt=receipt, frame=frame, settings=settings)
    bridge = receipt_to_mapping(receipt=receipt, frame=frame, settings=settings)
    assert capture_to_mapping(context)["match"] == bridge


def test_csv_capture_round_trip(tmp_path: Path) -> None:
    receipt, frame, settings = _csv_receipt(_memory_session(), tmp_path)
    context = capture_from_receipt(receipt=receipt, frame=frame, settings=settings)
    assert context.event_count == len(frame) == 1
    assert context.notice_text == receipt.resolution.notice.text
    assert capture_from_mapping(capture_to_mapping(context)) == context


def _partial_mapping() -> dict[str, Any]:
    session = assemble_session(
        documents=[_profile_doc("capture-partial", {"detector_side_length": 30.0})]
    )
    receipt, frame, settings = _dicom_receipt(session)
    context = capture_from_receipt(receipt=receipt, frame=frame, settings=settings)
    assert context.notice_kind == "partial"
    return copy.deepcopy(capture_to_mapping(context))


def test_partial_notice_reconstruction() -> None:
    session = assemble_session(
        documents=[_profile_doc("capture-partial", {"detector_side_length": 30.0})]
    )
    receipt, frame, settings = _dicom_receipt(session)
    context = capture_from_receipt(receipt=receipt, frame=frame, settings=settings)
    assert context.notice_kind == "partial"
    assert context.notice_text == receipt.resolution.notice.text
    assert [item.field for item in context.notice_entries] == [
        leaf.field for leaf in receipt.resolution.record.fields if leaf.inherited
    ]


def test_file_store_memory_captures_share_authority(tmp_path: Path) -> None:
    doc = _profile_doc("capture-full", _full_coordinates())
    file_path = tmp_path / "capture.json"
    file_path.write_text(json.dumps(doc), encoding="utf-8")
    file_session = assemble_session(files=[FileSource(file_path)])
    store = ProfileStore.open(tmp_path / "capture.sqlite3")
    store.save_new_revision(parse_memory_document(doc).profiles[0])
    store.set_enabled("capture-full", True)
    store_session = assemble_session(snapshots=[store.selected_snapshot(["capture-full"])])
    contexts = []
    for session in (_memory_session(), file_session, store_session):
        receipt, frame, settings = _dicom_receipt(session)
        contexts.append(capture_from_receipt(receipt=receipt, frame=frame, settings=settings))
    kinds = [context.session_sources[0][0] for context in contexts]
    assert kinds == ["memory", "file", "store"]
    first, second, third = (capture_to_mapping(context) for context in contexts)
    for mapping in (first, second, third):
        assert [leaf["value"] for leaf in mapping["match"]["fields"]] == [
            leaf["value"] for leaf in first["match"]["fields"]
        ]
        assert mapping["geometry_hash"] == first["geometry_hash"]
        assert mapping["event_count"] == first["event_count"]
    assert first["match"]["fields"][0]["source_kind"] == "memory"
    assert second["match"]["fields"][0]["source_kind"] == "json"
    assert third["match"]["fields"][0]["source_kind"] == "store"
    file_path.unlink()
    assert capture_from_mapping(first) == contexts[0]


# ---------------------------------------------------------------------------
# Stale live state must not be blessed
# ---------------------------------------------------------------------------


def test_stale_geometry_same_count_rejected() -> None:
    receipt, frame, settings = _dicom_receipt(_memory_session())
    stale = frame.copy()
    stale["Tx"] = [float(value) + 100.0 for value in frame["Tx"]]
    with pytest.raises(CaptureError) as excinfo:
        capture_from_receipt(receipt=receipt, frame=stale, settings=settings)
    assert _code(excinfo) == CODE_INVALID_EQUIPMENT_CAPTURE


def test_changed_identity_rejected() -> None:
    receipt, frame, settings = _dicom_receipt(_memory_session())
    renamed = frame.copy()
    renamed["manufacturer"] = ["Philips"] * len(frame)
    with pytest.raises(CaptureError) as excinfo:
        capture_from_receipt(receipt=receipt, frame=renamed, settings=settings)
    assert _code(excinfo) == CODE_INVALID_EQUIPMENT_CAPTURE


def test_wrong_session_rejected() -> None:
    receipt, frame, settings = _dicom_receipt(_memory_session())
    altered = _full_coordinates()
    altered["translation_offset"] = {"x": 6.0, "y": -3.5, "z": 0.0}
    other_session = assemble_session(documents=[_profile_doc("capture-full", altered)])
    other_settings = _settings(other_session)
    with pytest.raises(CaptureError) as excinfo:
        capture_from_receipt(receipt=receipt, frame=frame, settings=other_settings)
    assert _code(excinfo) == CODE_INVALID_EQUIPMENT_CAPTURE
    short = frame.iloc[:2].copy()
    with pytest.raises(CaptureError):
        capture_from_receipt(receipt=receipt, frame=short, settings=settings)


def test_changed_live_effective_fields_rejected() -> None:
    receipt, frame, settings = _dicom_receipt(_memory_session())
    settings.normalization_settings.trans_offset.update_translation_offset(
        {"x": 999.0, "y": 999.0, "z": 999.0}
    )
    with pytest.raises(CaptureError) as excinfo:
        capture_from_receipt(receipt=receipt, frame=frame, settings=settings)
    assert _code(excinfo) == CODE_INVALID_EQUIPMENT_CAPTURE


def test_forged_well_typed_notice_rejected() -> None:
    receipt, frame, settings = _dicom_receipt(_memory_session())
    forged_resolution = dataclasses.replace(
        receipt.resolution,
        notice=ResolutionNotice(
            kind=receipt.resolution.notice.kind,
            entries=receipt.resolution.notice.entries,
            text="Complete match — all 15 leaves from custom exact `forged`.",
        ),
    )
    forged = dataclasses.replace(receipt, resolution=forged_resolution)
    with pytest.raises(CaptureError) as excinfo:
        capture_from_receipt(receipt=forged, frame=frame, settings=settings)
    assert _code(excinfo) == CODE_INVALID_EQUIPMENT_CAPTURE


# ---------------------------------------------------------------------------
# Geometry portability
# ---------------------------------------------------------------------------


def test_geometry_dtype_and_negative_zero_portability() -> None:
    rows_float = [
        [float(index * 100 + position) for position in range(len(GEOMETRY_COLUMNS_V1))]
        for index in range(3)
    ]
    rows_int = [
        [index * 100 + position for position in range(len(GEOMETRY_COLUMNS_V1))]
        for index in range(3)
    ]
    assert geometry_digest_v1(rows_float) == geometry_digest_v1(rows_int)
    negated = [list(row) for row in rows_float]
    negated[0][0] = -0.0
    assert geometry_digest_v1(negated) == geometry_digest_v1(rows_float)
    short = [[1.0] * (len(GEOMETRY_COLUMNS_V1) - 1)]
    with pytest.raises(CaptureError):
        geometry_digest_v1(short)
    with pytest.raises(CaptureError):
        geometry_digest_v1([])


def test_geometry_rejects_nonfinite_and_bools() -> None:
    good = [[1.0] * len(GEOMETRY_COLUMNS_V1)]
    assert geometry_digest_v1(good) != geometry_digest_v1([[2.0] * len(GEOMETRY_COLUMNS_V1)])
    with pytest.raises(CaptureError):
        geometry_digest_v1([[float("inf")] * len(GEOMETRY_COLUMNS_V1)])
    with pytest.raises(CaptureError):
        geometry_digest_v1([[True] * len(GEOMETRY_COLUMNS_V1)])


def test_geometry_row_cap_and_lying_lengths() -> None:
    wide = [[1.0] * len(GEOMETRY_COLUMNS_V1)] * 3

    class LyingRows(list):
        def __len__(self) -> int:
            return 3

    lying = LyingRows(wide + wide)
    with pytest.raises(CaptureError):
        geometry_digest_v1(lying)
    assert geometry_digest_v1(wide) == geometry_digest_v1([list(row) for row in wide])
    huge = [[1.0] * len(GEOMETRY_COLUMNS_V1)] * 10001
    with pytest.raises(CaptureError):
        geometry_digest_v1(huge)


# ---------------------------------------------------------------------------
# Tamper rejection (semantic checks isolated with recomputed checksums)
# ---------------------------------------------------------------------------


def test_changed_geometry_hash_rejected() -> None:
    mapping = _mapping()
    mapping["geometry_hash"] = "0" * 64
    with pytest.raises(CaptureError) as excinfo:
        capture_from_mapping(mapping)
    assert _code(excinfo) == CODE_INVALID_EQUIPMENT_CAPTURE


def test_changed_recipe_leaf_rejected() -> None:
    mapping = _rehashed(_mapping())
    mapping["effective_coordinates"]["translation_offset"]["x"] = 6.0
    rehashed_mapping = _rehashed(mapping)
    with pytest.raises(CaptureError) as excinfo:
        capture_from_mapping(rehashed_mapping)
    assert _code(excinfo) == CODE_INVALID_EQUIPMENT_CAPTURE


def test_changed_notice_text_rejected() -> None:
    mapping = _mapping()
    mapping["match"]["notice"]["text"] = "Complete match — all leaves from nowhere."
    with pytest.raises(CaptureError) as excinfo:
        capture_from_mapping(mapping)
    assert _code(excinfo) == CODE_INVALID_EQUIPMENT_CAPTURE


def test_entry_leaf_mismatch_rejected_with_valid_checksum() -> None:
    mapping = _partial_mapping()
    assert mapping["match"]["notice"]["entries"]
    mapping["match"]["notice"]["entries"][0]["source"] = "custom"
    rehashed_mapping = _rehashed(mapping)
    with pytest.raises(CaptureError) as excinfo:
        capture_from_mapping(rehashed_mapping)
    assert _code(excinfo) == CODE_INVALID_EQUIPMENT_CAPTURE
    mapping = _mapping()
    entry = mapping["match"]["notice"]
    assert entry["kind"] == "complete"
    mapping = _mapping()
    leaf = mapping["match"]["fields"][0]
    leaf["source"] = "bundled"
    leaf["level"] = "wildcard"
    rehashed_mapping = _rehashed(mapping)
    with pytest.raises(CaptureError) as excinfo:
        capture_from_mapping(rehashed_mapping)
    assert _code(excinfo) == CODE_INVALID_EQUIPMENT_CAPTURE


def test_complete_custom_foreign_leaf_rejected_with_valid_checksum() -> None:
    mapping = _rehashed(_mapping())
    mapping["match"]["fields"][3]["profile_id"] = "bundled-siemens-axiom-artis"
    mapping["match"]["fields"][3]["source"] = "bundled"
    mapping["match"]["fields"][3]["level"] = "exact"
    rehashed_mapping = _rehashed(mapping)
    with pytest.raises(CaptureError) as excinfo:
        capture_from_mapping(rehashed_mapping)
    assert _code(excinfo) == CODE_INVALID_EQUIPMENT_CAPTURE


def test_changed_counts_rejected() -> None:
    mapping = _mapping()
    mapping["event_count"] = mapping["event_count"] + 1
    with pytest.raises(CaptureError) as excinfo:
        capture_from_mapping(mapping)
    assert _code(excinfo) == CODE_INVALID_EQUIPMENT_CAPTURE


def test_changed_capture_identity_rejected() -> None:
    mapping = _mapping()
    mapping["input_identity"]["manufacturer"] = "Philips"
    with pytest.raises(CaptureError) as excinfo:
        capture_from_mapping(mapping)
    assert _code(excinfo) == CODE_INVALID_EQUIPMENT_CAPTURE
    mapping = _rehashed(_mapping())
    mapping["match"]["matched_input_key"]["model"] = "other model"
    rehashed_mapping = _rehashed(mapping)
    with pytest.raises(CaptureError) as excinfo:
        capture_from_mapping(rehashed_mapping)
    assert _code(excinfo) == CODE_INVALID_EQUIPMENT_CAPTURE


def test_session_contradictions_rejected_with_valid_checksum() -> None:
    mapping = _rehashed(_mapping())
    mapping["match"]["session"]["total_profiles"] += 1
    rehashed_mapping = _rehashed(mapping)
    with pytest.raises(CaptureError) as excinfo:
        capture_from_mapping(rehashed_mapping)
    assert _code(excinfo) == CODE_INVALID_EQUIPMENT_CAPTURE
    mapping = _rehashed(_mapping())
    mapping["match"]["session"]["sources"][0]["format"] = "store"
    rehashed_mapping = _rehashed(mapping)
    with pytest.raises(CaptureError) as excinfo:
        capture_from_mapping(rehashed_mapping)
    assert _code(excinfo) == CODE_INVALID_EQUIPMENT_CAPTURE
    mapping = _rehashed(_mapping())
    mapping["match"]["session"]["sources"][0]["profile_ids"].append("capture-full")
    rehashed_mapping = _rehashed(mapping)
    with pytest.raises(CaptureError) as excinfo:
        capture_from_mapping(rehashed_mapping)
    assert _code(excinfo) == CODE_INVALID_EQUIPMENT_CAPTURE


def test_bogus_checksums_rejected() -> None:
    mapping = _mapping()
    mapping["capture_hash"] = "f" * 64
    with pytest.raises(CaptureError) as excinfo:
        capture_from_mapping(mapping)
    assert _code(excinfo) == CODE_INVALID_EQUIPMENT_CAPTURE


def test_reordered_leaves_rejected() -> None:
    mapping = _mapping()
    fields = mapping["match"]["fields"]
    fields[0], fields[1] = fields[1], fields[0]
    with pytest.raises(CaptureError) as excinfo:
        capture_from_mapping(mapping)
    assert _code(excinfo) == CODE_INVALID_EQUIPMENT_CAPTURE


# ---------------------------------------------------------------------------
# Scalar strictness
# ---------------------------------------------------------------------------


def test_nonfinite_huge_and_bool_scalars_rejected() -> None:
    mapping = _mapping()
    mapping["effective_coordinates"]["translation_offset"]["x"] = float("inf")
    with pytest.raises(CaptureError):
        capture_from_mapping(mapping)
    mapping = _mapping()
    mapping["effective_coordinates"]["translation_offset"]["x"] = 10**400
    with pytest.raises(CaptureError):
        capture_from_mapping(mapping)
    mapping = _mapping()
    mapping["event_count"] = 2**70
    with pytest.raises(CaptureError):
        capture_from_mapping(mapping)
    mapping = _mapping()
    mapping["event_count"] = True
    with pytest.raises(CaptureError):
        capture_from_mapping(mapping)
    mapping = _mapping()
    mapping["effective_coordinates"]["translation_offset"]["x"] = True
    with pytest.raises(CaptureError):
        capture_from_mapping(mapping)
    mapping = _mapping()
    mapping["match"]["fields"][0]["revision"] = 2**70
    with pytest.raises(CaptureError):
        capture_from_mapping(mapping)


def test_json_int_recipe_accepted_as_portable_double() -> None:
    from guiskindose.equipment_profiles.capture_codec import normalize_capture_body

    mapping = _mapping()
    mapping["effective_coordinates"]["translation_offset"]["x"] = 5
    mapping["match"]["fields"][0]["value"] = 5
    context = capture_from_mapping(_rehashed(normalize_capture_body(mapping)))
    assert context.effective_value("translation_offset.x") == 5.0


def test_unknown_missing_keys_rejected() -> None:
    mapping = _mapping()
    mapping["extra"] = 1
    with pytest.raises(CaptureError):
        capture_from_mapping(mapping)
    mapping = _mapping()
    del mapping["match"]
    with pytest.raises(CaptureError):
        capture_from_mapping(mapping)
    mapping = _mapping()
    mapping["match"]["fields"][0]["extra"] = 1
    with pytest.raises(CaptureError):
        capture_from_mapping(mapping)


def test_duplicate_keys_constants_and_oversize_rejected() -> None:
    with pytest.raises(CaptureError):
        capture_from_json(
            '{"schema_version": 1, "schema_version": 1, "mode": "coordinates", "captures": []}'
        )
    with pytest.raises(CaptureError):
        capture_from_json('{"schema_version": 1, "value": NaN}')
    with pytest.raises(CaptureError):
        capture_from_json('"\\ud800"')
    with pytest.raises(CaptureError):
        capture_from_json("[" * 20000)
    with pytest.raises(CaptureError) as excinfo:
        capture_from_json(" " * (8 * 1024 * 1024 + 1))
    assert _code(excinfo) == CODE_INVALID_EQUIPMENT_CAPTURE


def test_nested_mapping_depth_and_node_budget() -> None:
    deep: Any = {}
    cursor = deep
    for _ in range(30):
        cursor["next"] = {}
        cursor = cursor["next"]
    with pytest.raises(CaptureError):
        capture_from_mapping(deep)
    wide = {"schema_version": 1, "padding": [0] * 300000}
    with pytest.raises(CaptureError):
        capture_from_mapping(wide)


# ---------------------------------------------------------------------------
# Envelope, versions, limits
# ---------------------------------------------------------------------------


def test_envelope_round_trip_with_null() -> None:
    receipt, frame, settings = _dicom_receipt(_memory_session())
    context = capture_from_receipt(receipt=receipt, frame=frame, settings=settings)
    envelope = envelope_to_mapping([context, None])
    assert envelope["schema_version"] == CAPTURE_ENVELOPE_SCHEMA_VERSION
    assert envelope["mode"] == "coordinates"
    assert parse_envelope(envelope) == (context, None)
    assert envelope_from_json(envelope_to_json([context, None])) == (context, None)


def test_envelope_limits_and_versions() -> None:
    mapping = _mapping()
    with pytest.raises(CaptureError):
        parse_envelope({"schema_version": 1, "mode": "coordinates", "captures": [mapping] * 65})
    with pytest.raises(CaptureError):
        parse_envelope({"schema_version": 1, "mode": "coordinates", "captures": (mapping,)})
    with pytest.raises(CaptureError) as excinfo:
        parse_envelope({"schema_version": 2, "mode": "coordinates", "captures": []})
    assert _code(excinfo) == CODE_UNSUPPORTED_EQUIPMENT_CAPTURE_VERSION
    with pytest.raises(CaptureError) as excinfo:
        parse_envelope({"schema_version": 2**70, "mode": "coordinates", "captures": []})
    assert _code(excinfo) == CODE_UNSUPPORTED_EQUIPMENT_CAPTURE_VERSION
    with pytest.raises(CaptureError) as excinfo:
        parse_envelope({"schema_version": 1, "mode": "transmission", "captures": []})
    assert _code(excinfo) == CODE_INVALID_EQUIPMENT_CAPTURE
    too_many_contexts = [_mapping_context()] * 65
    with pytest.raises(CaptureError):
        envelope_to_mapping(too_many_contexts)


def _mapping_context() -> Any:
    receipt, frame, settings = _dicom_receipt(_memory_session())
    return capture_from_receipt(receipt=receipt, frame=frame, settings=settings)


def test_envelope_emit_rejects_lying_sequences() -> None:
    context = _mapping_context()

    class LyingTuple(tuple):
        def __len__(self) -> int:
            return 1

    lying = LyingTuple([context, context])
    with pytest.raises(CaptureError):
        envelope_to_mapping(lying)  # type: ignore[arg-type]


def test_future_geometry_algorithm_rejected() -> None:
    mapping = _mapping()
    mapping["geometry_hash_algorithm"] = "normalized-geometry-v2"
    with pytest.raises(CaptureError) as excinfo:
        capture_from_mapping(mapping)
    assert _code(excinfo) == CODE_UNSUPPORTED_EQUIPMENT_CAPTURE_VERSION


def test_transmission_profile_still_gated() -> None:
    doc = _profile_doc("capture-full", _full_coordinates())
    doc["profiles"][0]["transmission"] = [
        {
            "device_model": "AXIOM-Artis",
            "acquisition_plane": "Single Plane",
            "kvp_kv": 80.0,
            "filtration_added_mmcu": 0.0,
            "filtration_added_mmal": 0.0,
            "k_patient_support": 0.9,
            "evidence_status": "measured",
            "source": "lab",
            "date": "2026-01-01",
        }
    ]
    with pytest.raises(EquipmentProfileError) as excinfo:
        assemble_session(documents=[doc])
    assert excinfo.value.code == ProfileErrorCode.UNSUPPORTED_PROFILE_CAPABILITY


# ---------------------------------------------------------------------------
# Immutability, forgery, privacy
# ---------------------------------------------------------------------------


def test_immutable_and_forgery_resistant() -> None:
    receipt, frame, settings = _dicom_receipt(_memory_session())
    context = capture_from_receipt(receipt=receipt, frame=frame, settings=settings)
    with pytest.raises(dataclasses.FrozenInstanceError):
        context.event_count = 99  # type: ignore[misc]
    with pytest.raises(CaptureError) as excinfo:
        dataclasses.replace(context, event_count=99)
    assert _code(excinfo) == CODE_INVALID_EQUIPMENT_CAPTURE
    with pytest.raises(CaptureError) as excinfo:
        dataclasses.replace(context, notice_text="forged")
    assert _code(excinfo) == CODE_INVALID_EQUIPMENT_CAPTURE
    with pytest.raises(CaptureError):
        dataclasses.replace(context, source="SYNTHETIC-PRIVATE-LABEL")
    with pytest.raises(CaptureError):
        dataclasses.replace(context, fields=list(context.fields))
    with pytest.raises(CaptureError):
        dataclasses.replace(
            context, notice_entries=list(context.notice_entries)
        )
    validate_constructed_context(context)


def test_nested_reprs_hide_values() -> None:
    identity = CapturedIdentity(manufacturer="SECRET-MAKER", model="SECRET-MODEL")
    assert 'SECRET-MAKER' not in repr(identity)
    assert 'SECRET-MODEL' not in repr(identity)
    receipt, frame, settings = _dicom_receipt(_memory_session())
    context = capture_from_receipt(receipt=receipt, frame=frame, settings=settings)
    for leaf in context.fields:
        rendered = repr(leaf)
        assert leaf.profile_id not in rendered
        assert context.profile_hash not in rendered
    for item in context.notice_entries:
        assert item.label not in repr(item)
        assert item.profile_id not in repr(item)
    rendered = repr(context)
    secrets = [
        context.profile_id,
        context.capture_hash,
        context.geometry_hash,
        context.active_set_hash,
        context.matched_identity.manufacturer or "",
        context.matched_identity.model or "",
    ]
    for secret in secrets:
        assert secret not in rendered


def test_errors_hide_values() -> None:
    mapping = _mapping()
    mapping["match"]["notice"]["kind"] = "partial"
    with pytest.raises(CaptureError) as excinfo:
        capture_from_mapping(mapping)
    assert "SECRET" not in str(excinfo.value)
    mapping = _mapping()
    mapping["match"]["fields"][0]["profile_id"] = "SECRET-PROFILE-99"
    rehashed_mapping = _rehashed(mapping)
    with pytest.raises(CaptureError) as excinfo:
        capture_from_mapping(rehashed_mapping)
    assert "SECRET-PROFILE-99" not in str(excinfo.value)



@pytest.mark.parametrize("maker,model", [("NoSuch", "NoSuch"), ("GE Healthcare", "Unknown GE Model"), ("", "Unknown Model")])
def test_capture_preserves_input_identity_for_default_and_wildcard(maker, model, tmp_path) -> None:
    path = tmp_path / "fallback.csv"
    row = _RAW_ROW.replace("Siemens,AXIOM-Artis", f"{maker},{model}", 1)
    path.write_text(_RAW_HEADER + "\n" + row + "\n", encoding="utf-8")
    settings = _settings(_memory_session())
    result = read_and_normalize_input(path, input_schema="generic_rdsr_like", settings=settings)
    assert not isinstance(result, list)
    context = capture_from_receipt(receipt=result.equipment_receipt, frame=result.normalized_data, settings=settings)
    assert context.source in ("bundled", "default")
    assert capture_from_json(capture_to_json(context)) == context


def test_geometry_row_actual_width_is_bounded() -> None:
    class LyingRow(list):
        def __len__(self):
            return len(GEOMETRY_COLUMNS_V1)

    row = LyingRow([0.0] * 1000)
    with pytest.raises(CaptureError):
        geometry_digest_v1([row])


def test_constructed_context_checks_input_identity_not_display_name() -> None:
    context = _mapping_context()
    identity = CapturedIdentity(manufacturer="Other Maker", model="Other Model")
    body = capture_to_mapping(context)
    body["input_identity"] = {"manufacturer": "Other Maker", "model": "Other Model"}
    digest = _rehashed(body)["capture_hash"]
    with pytest.raises(CaptureError):
        dataclasses.replace(context, input_identity=identity, capture_hash=digest)


def test_partial_capture_root_enum_cannot_be_blessed_by_checksum() -> None:
    session = assemble_session(documents=[_profile_doc("partial", {"detector_side_length": 30.0})])
    receipt, frame, settings = _dicom_receipt(session)
    context = capture_from_receipt(receipt=receipt, frame=frame, settings=settings)
    body = capture_to_mapping(context)
    body["match"]["source"] = "SYNTHETIC-PRIVATE-LABEL"
    digest = _rehashed(body)["capture_hash"]
    with pytest.raises(CaptureError):
        dataclasses.replace(context, source="SYNTHETIC-PRIVATE-LABEL", capture_hash=digest)


def test_json_limits_run_before_materialization(monkeypatch) -> None:
    from guiskindose.equipment_profiles import capture_checks

    def forbidden_decode(*args, **kwargs):
        raise AssertionError("JSON decoder must not run")

    monkeypatch.setattr(capture_checks.json, "loads", forbidden_decode)
    too_deep = "[" * 20000 + "0" + "]" * 20000
    with pytest.raises(CaptureError):
        capture_checks._load_strict_json(too_deep)
    oversized_utf8 = '"' + "界" * 3000000 + '"'
    with pytest.raises(CaptureError):
        capture_checks._load_strict_json(oversized_utf8)


def test_escaped_surrogate_in_permitted_field_fails_closed() -> None:
    mapping = _mapping()
    mapping["matched_identity"]["model"] = "\ud800"
    text = json.dumps(mapping)
    with pytest.raises(CaptureError):
        capture_from_json(text)



def test_public_leaf_construction_canonicalizes_numeric_equivalents() -> None:
    context = _mapping_context()
    leaf = context.fields[0]
    equivalent = dataclasses.replace(leaf, value=int(leaf.value))
    assert type(equivalent.value) is float
    assert equivalent == leaf


def test_partial_leaf_cannot_skip_selected_root_provenance() -> None:
    session = assemble_session(documents=[_profile_doc("partial", {"detector_side_length": 30.0})])
    receipt, frame, settings = _dicom_receipt(session)
    context = capture_from_receipt(receipt=receipt, frame=frame, settings=settings)
    body = capture_to_mapping(context)
    body["match"]["fields"][-1]["profile_hash"] = "a" * 64
    rehashed_mapping = _rehashed(body)
    with pytest.raises(CaptureError):
        capture_from_mapping(rehashed_mapping)



def test_custom_capture_must_appear_in_source_manifest() -> None:
    body = _mapping()
    body["match"]["session"]["sources"][0]["profile_ids"] = ["unrelated-profile"]
    rehashed_mapping = _rehashed(body)
    with pytest.raises(CaptureError):
        capture_from_mapping(rehashed_mapping)


def test_uninitialized_context_emission_fails_closed() -> None:
    incomplete = object.__new__(CapturedCoordinates)
    with pytest.raises(CaptureError):
        capture_to_mapping(incomplete)


def test_first_published_equipment_receipt_returns_first_or_none() -> None:
    assert first_published_equipment_receipt([]) is None
    first = object()
    second = object()
    assert first_published_equipment_receipt([first, second]) is first
