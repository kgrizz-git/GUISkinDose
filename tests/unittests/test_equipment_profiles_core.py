"""Unit tests for the equipment-profile core package.

Covers the JSON/core slice only: canonical models, JSON and in-memory parsing, full-v1 structural validation,
canonical serialization and hashes, across-source duplicate/conflict validation, immutable match-record
types, and the initial capability gate. No adapter, store, GUI, CLI, or dose path is exercised.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from guiskindose.equipment_profiles import (
    COORDINATE_LEAF_COUNT,
    EquipmentProfileError,
    Profile,
    ProfileErrorCode,
    active_set_hash,
    canonical_json_bytes,
    canonical_profile_dict,
    check_initial_capabilities,
    combine_documents,
    first_unsupported_capability,
    normalize_manufacturer_key,
    normalize_model_key,
    parse_json_bytes,
    parse_json_file,
    parse_memory_document,
    profile_hash,
    source_bytes_hash,
    supported_profiles,
    validate_profile_set,
)

EXAMPLE_PATH = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "guiskindose"
    / "example_data"
    / "equipment_profiles"
    / "equipment_profile_example.json"
)


def _envelope(profiles: object) -> dict[str, object]:
    return {"schema_version": 1, "profiles": profiles}


def _profile(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "profile_id": "demo-partial",
        "manufacturer": "Acme Imaging",
        "models": ["DemoScope 2000"],
    }
    base.update(overrides)
    return base


def _full_coordinates() -> dict[str, object]:
    return {
        "translation_offset": {"x": 0.0, "y": 0.0, "z": 0.0},
        "translation_direction": {"x": "+", "y": "+", "z": "+"},
        "rotation_direction": {"Ap1": "+", "Ap2": "+", "Ap3": "+", "At1": "+", "At2": "+", "At3": "+"},
        "swap_lateral_longitudinal": False,
        "field_size_mode": "CFA",
        "detector_side_length": 40,
    }


def _error_code(excinfo: pytest.ExceptionInfo[EquipmentProfileError]) -> ProfileErrorCode:
    assert excinfo.value.code is not None
    return excinfo.value.code


# ---------------------------------------------------------------------------
# Packaged example
# ---------------------------------------------------------------------------


def test_packaged_example_parses_three_profiles_sixteen_leaves_five_rows() -> None:
    document = parse_json_file(EXAMPLE_PATH)

    assert len(document.profiles) == 3
    assert document.source_kind == "json"
    assert document.source_hash is not None

    leaves = sum(len(profile.coordinate_leaves()) for profile in document.profiles)
    rows = sum(len(profile.transmission) for profile in document.profiles)
    assert leaves == 16
    assert rows == 5
    assert document.logical_rows == 3 + 16 + 5


def test_packaged_example_full_profile_supplies_all_fifteen_leaves() -> None:
    document = parse_json_file(EXAMPLE_PATH)
    full = next(profile for profile in document.profiles if profile.profile_id == "demo-scope-2000")

    assert len(full.coordinate_leaves()) == COORDINATE_LEAF_COUNT == 15


def test_packaged_example_wildcard_profile_supplies_only_one_nested_leaf() -> None:
    document = parse_json_file(EXAMPLE_PATH)
    partial = next(profile for profile in document.profiles if profile.profile_id == "demo-scope-wildcard")

    assert partial.coordinate_leaves() == (("translation_offset.z", -12.5),)
    assert partial.models == ("*",)


def test_packaged_example_shorthand_alias_array_is_accepted() -> None:
    document = parse_json_file(EXAMPLE_PATH)
    full = next(profile for profile in document.profiles if profile.profile_id == "demo-scope-2000")

    assert full.manufacturer_aliases == ("AcmeImaging",)
    assert full.model_aliases == (("DemoScope2000", "DemoScope 2000"), ("DS2000", "DemoScope 2000"))


# ---------------------------------------------------------------------------
# Partial coordinate omission
# ---------------------------------------------------------------------------


def test_partial_coordinate_omission_is_valid_inheritance() -> None:
    document = parse_memory_document(_envelope([_profile(coordinates=_full_coordinates() | {"detector_side_length": None}) if False else _profile(coordinates=_full_coordinates())]))

    # Omit rather than null: drop the detector leaf from a full block.
    coordinates = _full_coordinates()
    del coordinates["detector_side_length"]
    document = parse_memory_document(_envelope([_profile(coordinates=coordinates)]))

    assert len(document.profiles) == 1
    assert "detector_side_length" not in dict(document.profiles[0].coordinate_leaves())


def test_coordinate_block_present_but_empty_is_rejected() -> None:
    document = _envelope([_profile(coordinates={"translation_offset": {}})])
    with pytest.raises(EquipmentProfileError) as excinfo:
        parse_memory_document(document)

    assert _error_code(excinfo) is ProfileErrorCode.EMPTY_COORDINATE_BLOCK


def test_coordinates_object_with_no_block_is_rejected() -> None:
    document = _envelope([_profile(coordinates={})])
    with pytest.raises(EquipmentProfileError) as excinfo:
        parse_memory_document(document)

    assert _error_code(excinfo) is ProfileErrorCode.EMPTY_COORDINATE_BLOCK


def test_profile_with_no_domain_is_rejected() -> None:
    document = _envelope([_profile()])
    with pytest.raises(EquipmentProfileError) as excinfo:
        parse_memory_document(document)

    assert _error_code(excinfo) is ProfileErrorCode.EMPTY_DOMAIN


# ---------------------------------------------------------------------------
# Alias shorthand vs explicit map
# ---------------------------------------------------------------------------


def test_alias_shorthand_and_explicit_map_normalize_identically() -> None:
    shorthand = parse_memory_document(
        _envelope([_profile(coordinates=_full_coordinates(), model_aliases=["DemoScope2000", "DS2000"])])
    ).profiles[0]
    explicit = parse_memory_document(
        _envelope(
            [
                _profile(
                    coordinates=_full_coordinates(),
                    model_aliases={"DemoScope2000": "DemoScope 2000", "DS2000": "DemoScope 2000"},
                )
            ]
        )
    ).profiles[0]

    assert shorthand.model_aliases == explicit.model_aliases
    assert profile_hash(shorthand) == profile_hash(explicit)


def test_alias_shorthand_with_multiple_models_is_rejected() -> None:
    document = _envelope(
                [
                    _profile(
                        models=["DemoScope 2000", "DemoScope 3000"],
                        model_aliases=["DemoScope2000"],
                    )
                ]
            )
    with pytest.raises(EquipmentProfileError) as excinfo:
        parse_memory_document(
            document
        )

    assert _error_code(excinfo) is ProfileErrorCode.ALIAS_AMBIGUOUS_TARGET


def test_alias_map_target_must_be_a_listed_model() -> None:
    document = _envelope([_profile(coordinates=_full_coordinates(), model_aliases={"A": "Other"})])
    with pytest.raises(EquipmentProfileError) as excinfo:
        parse_memory_document(document)

    assert _error_code(excinfo) is ProfileErrorCode.ALIAS_TARGET_MISMATCH


def test_normalize_colliding_aliases_are_rejected() -> None:
    document = _envelope([_profile(coordinates=_full_coordinates(), model_aliases=["DS-2000", "ds 2000"])])
    with pytest.raises(EquipmentProfileError) as excinfo:
        parse_memory_document(
            document
        )

    assert _error_code(excinfo) is ProfileErrorCode.ALIAS_AMBIGUOUS_TARGET


def test_empty_aliases_normalize_to_absent() -> None:
    profile = parse_memory_document(
        _envelope([_profile(coordinates=_full_coordinates(), manufacturer_aliases=[], model_aliases=[])])
    ).profiles[0]

    assert profile.manufacturer_aliases == ()
    assert profile.model_aliases == ()
    assert "manufacturer_aliases" not in canonical_profile_dict(profile)
    assert "model_aliases" not in canonical_profile_dict(profile)


def test_empty_optional_text_and_false_promotion_are_omitted() -> None:
    profile = parse_memory_document(
        _envelope(
            [
                _profile(
                    coordinates=_full_coordinates(),
                    provenance={"source": "", "notes": ""},
                    promote_coordinate_wildcard=False,
                )
            ]
        )
    ).profiles[0]

    canonical = canonical_profile_dict(profile)
    assert "provenance" not in canonical
    assert "promote_coordinate_wildcard" not in canonical


# ---------------------------------------------------------------------------
# Hashes
# ---------------------------------------------------------------------------


def _raw_example() -> dict[str, object]:
    return json.loads(EXAMPLE_PATH.read_text(encoding="utf-8"))


def test_profile_hash_is_numeric_and_order_independent() -> None:
    ordered = _raw_example()["profiles"]
    reordered = _raw_example()
    reordered["profiles"] = list(reversed(ordered))  # type: ignore[index]

    forward = parse_json_bytes(json.dumps(_raw_example()).encode("utf-8")).profiles
    backward = parse_json_bytes(json.dumps(reordered).encode("utf-8")).profiles

    assert {p.profile_id: profile_hash(p) for p in forward} == {
        p.profile_id: profile_hash(p) for p in backward
    }
    assert active_set_hash(forward) == active_set_hash(backward)


def test_profile_hash_is_source_kind_independent() -> None:
    payload = _raw_example()
    pretty = json.dumps(payload, indent=4).encode("utf-8")

    from_file = parse_json_bytes(pretty)
    from_memory = parse_memory_document(payload)

    assert from_file.source_hash == source_bytes_hash(pretty)
    assert from_memory.source_hash is None
    assert profile_hash(from_file.profiles[0]) == profile_hash(from_memory.profiles[0])
    assert active_set_hash(from_file.profiles) == active_set_hash(from_memory.profiles)


def _coordinate_profile(profile_id: str = "demo-partial") -> Profile:
    document = parse_memory_document(_envelope([_profile(profile_id=profile_id, coordinates=_full_coordinates())]))
    return document.profiles[0]


def test_numeric_spelling_does_not_change_the_hash() -> None:
    base = _coordinate_profile()
    spelling = parse_memory_document(
        _envelope([_profile(coordinates=_full_coordinates() | {"detector_side_length": 40.0})])
    ).profiles[0]

    assert base.coordinates is not None
    assert spelling.coordinates is not None
    assert base.coordinates.detector_side_length == spelling.coordinates.detector_side_length == 40.0
    assert isinstance(base.coordinates.detector_side_length, float)
    assert profile_hash(base) == profile_hash(spelling)


def test_negative_zero_normalizes_to_positive_zero() -> None:
    profile = parse_memory_document(
        _envelope([_profile(coordinates={"translation_offset": {"x": -0.0}})])
    ).profiles[0]

    assert profile.coordinates is not None
    assert profile.coordinates.translation_offset is not None
    assert profile.coordinates.translation_offset.x == 0.0
    assert "-0.0" not in canonical_json_bytes(canonical_profile_dict(profile)).decode("utf-8")


def test_source_byte_hash_differs_for_different_bytes() -> None:
    one = b'{"schema_version":1,"profiles":[]}'
    two = b'{"schema_version":1,"profiles":[]} '

    assert source_bytes_hash(one) != source_bytes_hash(two)


def test_schema_version_serializes_as_integer_not_float() -> None:
    from guiskindose.equipment_profiles.canonical import profile_wrapper

    text = canonical_json_bytes(profile_wrapper(_coordinate_profile())).decode("utf-8")

    assert '"schema_version":1' in text
    assert "1.0" not in text


# ---------------------------------------------------------------------------
# Immutability
# ---------------------------------------------------------------------------


def test_parsed_profiles_are_immutable() -> None:
    from dataclasses import FrozenInstanceError

    profile = _coordinate_profile()

    with pytest.raises(FrozenInstanceError):
        profile.profile_id = "changed"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        profile.coordinates.detector_side_length = 10  # type: ignore[union-attr, misc]


def test_mutating_input_mapping_after_parse_does_not_change_the_profile() -> None:
    payload = _envelope([_profile(coordinates=_full_coordinates())])
    document = parse_memory_document(payload)
    before = profile_hash(document.profiles[0])

    payload["profiles"][0]["manufacturer"] = "Mutated Imaging"  # type: ignore[index]
    payload["profiles"][0]["coordinates"]["detector_side_length"] = 1  # type: ignore[index]

    assert profile_hash(document.profiles[0]) == before
    assert document.profiles[0].manufacturer == "Acme Imaging"


def test_profile_repr_suppresses_provenance_text() -> None:
    profile = parse_memory_document(
        _envelope(
            [
                _profile(
                    coordinates=_full_coordinates(),
                    provenance={"source": "sensitive-source", "notes": "sensitive-notes"},
                )
            ]
        )
    ).profiles[0]

    assert "sensitive-source" not in repr(profile)
    assert "sensitive-notes" not in repr(profile)


# ---------------------------------------------------------------------------
# Duplicates
# ---------------------------------------------------------------------------


def test_duplicate_json_object_keys_are_rejected() -> None:
    raw = b'{"schema_version":1,"schema_version":1,"profiles":[]}'

    with pytest.raises(EquipmentProfileError) as excinfo:
        parse_json_bytes(raw)

    assert _error_code(excinfo) is ProfileErrorCode.DUPLICATE_JSON_KEY


def test_duplicate_profile_ids_fail_even_when_identical() -> None:
    document = parse_memory_document(_envelope([_profile(coordinates=_full_coordinates())]))

    with pytest.raises(EquipmentProfileError) as excinfo:
        combine_documents([document, document])

    assert _error_code(excinfo) is ProfileErrorCode.DUPLICATE_PROFILE_ID


def test_duplicate_coordinate_claims_fail_even_when_identical() -> None:
    first = parse_memory_document(_envelope([_profile(profile_id="a", coordinates=_full_coordinates())])).profiles[0]
    second = parse_memory_document(_envelope([_profile(profile_id="b", coordinates=_full_coordinates())])).profiles[0]

    with pytest.raises(EquipmentProfileError) as excinfo:
        validate_profile_set((first, second), source_kind="json")

    assert _error_code(excinfo) is ProfileErrorCode.DUPLICATE_COORDINATE_CLAIM


def test_duplicate_transmission_keys_fail_across_profiles_and_manufacturers() -> None:
    row = {
        "device_model": "DemoScope 2000",
        "acquisition_plane": "Single Plane",
        "kvp_kv": 80,
        "filtration_added_mmcu": 0.0,
        "filtration_added_mmal": 0,
        "k_patient_support": 0.71,
        "evidence_status": "estimated",
        "date": "1901-01-01",
    }
    first = parse_memory_document(
        _envelope([_profile(profile_id="a", manufacturer="Acme Imaging", transmission=[dict(row)])])
    ).profiles[0]
    second = parse_memory_document(
        _envelope([_profile(profile_id="b", manufacturer="Other Imaging", transmission=[dict(row)])])
    ).profiles[0]

    with pytest.raises(EquipmentProfileError) as excinfo:
        validate_profile_set((first, second), source_kind="json")

    assert _error_code(excinfo) is ProfileErrorCode.DUPLICATE_TRANSMISSION_KEY


def test_duplicate_transmission_keys_fail_within_one_profile() -> None:
    row = {
        "device_model": "DemoScope 2000",
        "acquisition_plane": "Single Plane",
        "kvp_kv": 80,
        "filtration_added_mmcu": 0.0,
        "filtration_added_mmal": 0,
        "k_patient_support": 0.71,
        "evidence_status": "estimated",
        "date": "1901-01-01",
    }
    profiles = parse_memory_document(
        _envelope([_profile(transmission=[dict(row), dict(row)])])
    ).profiles

    parsed = [parse_memory_document(_envelope([_profile(transmission=[dict(row), dict(row)])]))]
    with pytest.raises(EquipmentProfileError) as excinfo:
        combine_documents(parsed)

    assert _error_code(excinfo) is ProfileErrorCode.DUPLICATE_TRANSMISSION_KEY
    assert len(profiles) == 1


# ---------------------------------------------------------------------------
# Unknown fields and value-free errors
# ---------------------------------------------------------------------------


def test_unknown_field_is_rejected_and_key_is_not_echoed() -> None:
    malicious = "EVIL_PATIENT_12345"

    document = _envelope([_profile(coordinates=_full_coordinates(), **{malicious: "x"})])
    with pytest.raises(EquipmentProfileError) as excinfo:
        parse_memory_document(document)

    assert _error_code(excinfo) is ProfileErrorCode.UNKNOWN_FIELD
    assert malicious not in str(excinfo.value)
    assert malicious not in repr(excinfo.value)


def test_unknown_nested_field_names_the_closest_allowlisted_parent() -> None:
    malicious_key = "malicious_key"
    coordinates = _full_coordinates()
    coordinates["translation_offset"] = {"x": 0.0, malicious_key: 1.0}  # type: ignore[dict-item]

    document = _envelope([_profile(coordinates=coordinates)])
    with pytest.raises(EquipmentProfileError) as excinfo:
        parse_memory_document(document)

    assert _error_code(excinfo) is ProfileErrorCode.UNKNOWN_FIELD
    assert excinfo.value.field_path == ("coordinates", "translation_offset")
    assert malicious_key not in str(excinfo.value)
    assert malicious_key not in repr(excinfo.value)


def test_error_message_contains_no_file_path(tmp_path: Path) -> None:
    target = tmp_path / "profiles.json"
    target.write_text('{"schema_version":1,"profiles":[{"unknown":"x"}]}', encoding="utf-8")

    with pytest.raises(EquipmentProfileError) as excinfo:
        parse_json_file(target)

    assert str(target) not in str(excinfo.value)
    assert "profiles.json" not in str(excinfo.value)


def test_unreadable_source_is_value_free(tmp_path: Path) -> None:
    with pytest.raises(EquipmentProfileError) as excinfo:
        parse_json_file(tmp_path / "missing.json")

    assert _error_code(excinfo) is ProfileErrorCode.UNREADABLE_SOURCE


def test_unsupported_suffix_is_value_free() -> None:
    path = Path("/nonexistent/profile.csv")
    with pytest.raises(EquipmentProfileError) as excinfo:
        parse_json_file(path)

    assert _error_code(excinfo) is ProfileErrorCode.UNSUPPORTED_SOURCE_SUFFIX


def test_malformed_json_cause_is_suppressed() -> None:
    with pytest.raises(EquipmentProfileError) as excinfo:
        parse_json_bytes(b'{"schema_version":1,')

    assert _error_code(excinfo) is ProfileErrorCode.MALFORMED_JSON
    assert excinfo.value.__cause__ is None
    assert "Expecting" not in str(excinfo.value)


# ---------------------------------------------------------------------------
# Types, numbers, ranges
# ---------------------------------------------------------------------------


def test_boolean_is_not_a_number() -> None:
    coordinates = _full_coordinates()
    coordinates["detector_side_length"] = True

    document = _envelope([_profile(coordinates=coordinates)])
    with pytest.raises(EquipmentProfileError) as excinfo:
        parse_memory_document(document)

    assert _error_code(excinfo) is ProfileErrorCode.INVALID_NUMBER


def test_number_is_not_a_boolean() -> None:
    coordinates = _full_coordinates()
    coordinates["swap_lateral_longitudinal"] = 1

    document = _envelope([_profile(coordinates=coordinates)])
    with pytest.raises(EquipmentProfileError) as excinfo:
        parse_memory_document(document)

    assert _error_code(excinfo) is ProfileErrorCode.INVALID_TYPE


def test_null_is_not_omission() -> None:
    document = _envelope([_profile(manufacturer=None)])
    with pytest.raises(EquipmentProfileError) as excinfo:
        parse_memory_document(document)

    assert _error_code(excinfo) is ProfileErrorCode.INVALID_TYPE


def test_nan_and_infinity_literals_are_rejected() -> None:
    with pytest.raises(EquipmentProfileError) as excinfo:
        parse_json_bytes(
            b'{"schema_version":1,"profiles":[{"profile_id":"p","manufacturer":"A",'
            b'"models":["M"],"coordinates":{"detector_side_length":NaN}}]}'
        )

    assert _error_code(excinfo) is ProfileErrorCode.INVALID_NUMBER

    with pytest.raises(EquipmentProfileError) as excinfo:
        parse_json_bytes(
            b'{"schema_version":1,"profiles":[{"profile_id":"p","manufacturer":"A",'
            b'"models":["M"],"coordinates":{"detector_side_length":Infinity}}]}'
        )

    assert _error_code(excinfo) is ProfileErrorCode.INVALID_NUMBER


def test_overflowing_exponent_is_rejected_as_non_finite() -> None:
    with pytest.raises(EquipmentProfileError) as excinfo:
        parse_json_bytes(
            b'{"schema_version":1,"profiles":[{"profile_id":"p","manufacturer":"A",'
            b'"models":["M"],"coordinates":{"detector_side_length":1e999}}]}'
        )

    assert _error_code(excinfo) is ProfileErrorCode.INVALID_NUMBER


def test_offset_out_of_range_is_rejected() -> None:
    document = _envelope([_profile(coordinates={"translation_offset": {"x": 5000.0}})])
    with pytest.raises(EquipmentProfileError) as excinfo:
        parse_memory_document(document)

    assert _error_code(excinfo) is ProfileErrorCode.VALUE_OUT_OF_RANGE


def test_detector_side_length_must_be_positive() -> None:
    document = _envelope([_profile(coordinates={"detector_side_length": 0})])
    with pytest.raises(EquipmentProfileError) as excinfo:
        parse_memory_document(document)

    assert _error_code(excinfo) is ProfileErrorCode.VALUE_OUT_OF_RANGE


def test_transmission_factor_must_be_in_unit_interval() -> None:
    row = {
        "device_model": "DemoScope 2000",
        "acquisition_plane": "Single Plane",
        "kvp_kv": 80,
        "filtration_added_mmcu": 0.0,
        "filtration_added_mmal": 0,
        "k_patient_support": 1.5,
        "evidence_status": "estimated",
    }

    document = _envelope([_profile(transmission=[row])])
    with pytest.raises(EquipmentProfileError) as excinfo:
        parse_memory_document(document)

    assert _error_code(excinfo) is ProfileErrorCode.VALUE_OUT_OF_RANGE


def test_transmission_device_model_must_target_a_listed_model() -> None:
    row = {
        "device_model": "Unlisted 9000",
        "acquisition_plane": "Single Plane",
        "kvp_kv": 80,
        "filtration_added_mmcu": 0.0,
        "filtration_added_mmal": 0,
        "k_patient_support": 0.71,
        "evidence_status": "estimated",
    }

    document = _envelope([_profile(transmission=[row])])
    with pytest.raises(EquipmentProfileError) as excinfo:
        parse_memory_document(document)

    assert _error_code(excinfo) is ProfileErrorCode.ALIAS_TARGET_MISMATCH


def test_measured_rows_require_source_and_date() -> None:
    row = {
        "device_model": "DemoScope 2000",
        "acquisition_plane": "Single Plane",
        "kvp_kv": 80,
        "filtration_added_mmcu": 0.0,
        "filtration_added_mmal": 0,
        "k_patient_support": 0.71,
        "evidence_status": "measured",
    }

    document = _envelope([_profile(transmission=[row])])
    with pytest.raises(EquipmentProfileError) as excinfo:
        parse_memory_document(document)

    assert _error_code(excinfo) is ProfileErrorCode.MISSING_REQUIRED_FIELD


def test_dates_must_be_strict_calendar_dates() -> None:
    row = {
        "device_model": "DemoScope 2000",
        "acquisition_plane": "Single Plane",
        "kvp_kv": 80,
        "filtration_added_mmcu": 0.0,
        "filtration_added_mmal": 0,
        "k_patient_support": 0.71,
        "evidence_status": "measured",
        "source": "reviewed",
        "date": "2026-02-30",
    }

    document = _envelope([_profile(transmission=[row])])
    with pytest.raises(EquipmentProfileError) as excinfo:
        parse_memory_document(document)

    assert _error_code(excinfo) is ProfileErrorCode.INVALID_DATE


def test_schema_version_must_be_exact_integer_one() -> None:
    document = {"schema_version": True, "profiles": [_profile(coordinates=_full_coordinates())]}
    with pytest.raises(EquipmentProfileError) as excinfo:
        parse_memory_document(document)

    assert _error_code(excinfo) is ProfileErrorCode.UNSUPPORTED_SCHEMA_VERSION

    document = {"schema_version": 2, "profiles": [_profile(coordinates=_full_coordinates())]}
    with pytest.raises(EquipmentProfileError) as excinfo:
        parse_memory_document(document)

    assert _error_code(excinfo) is ProfileErrorCode.UNSUPPORTED_SCHEMA_VERSION


def test_unknown_root_key_is_rejected() -> None:
    envelope = _envelope([_profile(coordinates=_full_coordinates())])
    envelope["extra"] = 1  # type: ignore[index]

    with pytest.raises(EquipmentProfileError) as excinfo:
        parse_memory_document(envelope)

    assert _error_code(excinfo) is ProfileErrorCode.UNKNOWN_FIELD
    assert excinfo.value.field_path == ()


def test_empty_profiles_array_is_rejected() -> None:
    document = _envelope([])
    with pytest.raises(EquipmentProfileError) as excinfo:
        parse_memory_document(document)

    assert _error_code(excinfo) is ProfileErrorCode.EMPTY_SOURCE


def test_profile_id_form_is_enforced() -> None:
    document = _envelope([_profile(profile_id="../escape", coordinates=_full_coordinates())])
    with pytest.raises(EquipmentProfileError) as excinfo:
        parse_memory_document(document)

    assert _error_code(excinfo) is ProfileErrorCode.INVALID_PROFILE_ID


def test_wildcard_models_are_rejected_outside_the_permitted_shape() -> None:
    document = _envelope([_profile(models=["*", "Other"], coordinates=_full_coordinates())])
    with pytest.raises(EquipmentProfileError) as excinfo:
        parse_memory_document(document)

    assert _error_code(excinfo) is ProfileErrorCode.WILDCARD_NOT_PERMITTED


# ---------------------------------------------------------------------------
# Capability gate
# ---------------------------------------------------------------------------


def test_initial_gate_rejects_every_alias_wildcard_and_transmission_capability() -> None:
    transmission_row = {
        "device_model": "DemoScope 2000",
        "acquisition_plane": "Single Plane",
        "kvp_kv": 80,
        "filtration_added_mmcu": 0.0,
        "filtration_added_mmal": 0,
        "k_patient_support": 0.71,
        "evidence_status": "estimated",
        "date": "1901-01-01",
    }
    cases: dict[str, dict[str, object]] = {
        "model_wildcard": _profile(models=["*"], coordinates=_full_coordinates()),
        "manufacturer_alias": _profile(coordinates=_full_coordinates(), manufacturer_aliases=["AcmeImaging"]),
        "model_alias": _profile(coordinates=_full_coordinates(), model_aliases=["DemoScope2000"]),
        "transmission_domain": _profile(transmission=[transmission_row]),
    }
    for capability, payload in cases.items():
        profiles = parse_memory_document(_envelope([payload])).profiles
        assert first_unsupported_capability(profiles[0]) == capability
        assert supported_profiles(profiles) == ()
        with pytest.raises(EquipmentProfileError) as excinfo:
            check_initial_capabilities(profiles, source_kind="memory")
        assert _error_code(excinfo) is ProfileErrorCode.UNSUPPORTED_PROFILE_CAPABILITY
        assert excinfo.value.capability == capability


def test_wildcard_profile_with_promotion_is_refused_by_the_gate() -> None:
    profiles = parse_memory_document(
        _envelope([_profile(models=["*"], coordinates=_full_coordinates(), promote_coordinate_wildcard=True)])
    ).profiles

    assert first_unsupported_capability(profiles[0]) == "model_wildcard"
    with pytest.raises(EquipmentProfileError) as excinfo:
        check_initial_capabilities(profiles, source_kind="memory")
    assert _error_code(excinfo) is ProfileErrorCode.UNSUPPORTED_PROFILE_CAPABILITY


def test_promotion_is_only_valid_beside_a_wildcard_model() -> None:
    document = _envelope([_profile(coordinates=_full_coordinates(), promote_coordinate_wildcard=True)])
    with pytest.raises(EquipmentProfileError) as excinfo:
        parse_memory_document(
            document
        )

    assert _error_code(excinfo) is ProfileErrorCode.WILDCARD_NOT_PERMITTED


def test_initial_gate_accepts_exact_coordinate_only_profile() -> None:
    document = parse_json_file(EXAMPLE_PATH)
    assert document.profiles  # the packaged example exists and parsed

    memory_only = parse_memory_document(_envelope([_profile(coordinates=_full_coordinates())])).profiles
    check_initial_capabilities(memory_only, source_kind="memory")  # must not raise
    assert supported_profiles(memory_only) == memory_only
    assert first_unsupported_capability(memory_only[0]) is None


def test_gate_rejection_does_not_partially_apply(recwarn: pytest.WarningsRecorder) -> None:
    payload = _profile(coordinates=_full_coordinates(), transmission=[
        {
            "device_model": "DemoScope 2000",
            "acquisition_plane": "Single Plane",
            "kvp_kv": 80,
            "filtration_added_mmcu": 0.0,
            "filtration_added_mmal": 0,
            "k_patient_support": 0.71,
            "evidence_status": "estimated",
            "date": "1901-01-01",
        }
    ])
    profiles = parse_memory_document(_envelope([payload])).profiles

    with pytest.raises(EquipmentProfileError):
        check_initial_capabilities(profiles, source_kind="memory")

    # The parsed profile keeps its content exactly; the gate refuses, it does not strip.
    assert profiles[0].transmission[0].kvp_kv == 80.0
    assert profiles[0].coordinates is not None
    assert profiles[0].coordinates.field_size_mode == "CFA"
    assert len(list(recwarn)) == 0


# ---------------------------------------------------------------------------
# Key parity with the existing normalization helpers
# ---------------------------------------------------------------------------


def test_identity_keys_match_the_existing_normalization_algorithms() -> None:
    from guiskindose.settings.normalization_settings import (
        normalize_manufacturer_key as settings_manufacturer_key,
    )
    from guiskindose.settings.normalization_settings import (
        normalize_model_key as settings_model_key,
    )

    samples = [
        "Siemens",
        "Siemens Healthineers",
        "GE Healthcare",
        "Acme  Imaging---Systems",
        "PHILIPS",
        "  spaced   out  ",
    ]
    for sample in samples:
        assert normalize_manufacturer_key(sample) == settings_manufacturer_key(sample), sample
        assert normalize_model_key(sample) == settings_model_key(sample), sample

    assert normalize_model_key("*") == settings_model_key("*") == "*"
    assert normalize_model_key("DemoScope 2000") == settings_model_key("DemoScope 2000")


# ---------------------------------------------------------------------------
# Match records
# ---------------------------------------------------------------------------


def test_match_record_leaf_provenance_and_inherited_semantics() -> None:
    from guiskindose.equipment_profiles import (
        CoordinateMatchRecord,
        MatchedInputKey,
        build_leaf_provenance,
    )

    selected = build_leaf_provenance(
        dotted_path="translation_offset.x",
        value=0.0,
        profile_id="demo-partial",
        source="custom",
        level="exact",
        source_kind="json",
        profile_hash="a" * 64,
        is_selected_profile=True,
    )
    inherited = build_leaf_provenance(
        dotted_path="rotation_direction.Ap2",
        value="+",
        profile_id="bundled-exact",
        source="bundled",
        level="exact",
        source_kind="json",
        profile_hash="b" * 64,
        is_selected_profile=False,
    )
    assert selected.inherited is False
    assert inherited.inherited is True

    record = CoordinateMatchRecord(
        profile_id="demo-partial",
        source="custom",
        level="exact",
        source_kind="json",
        profile_hash="a" * 64,
        matched_input_key=MatchedInputKey.from_raw("Acme Imaging", "DemoScope 2000"),
        affected_event_count=12,
        fields=(selected, inherited),
    )
    assert record.matched_input_key.as_mapping() == {"manufacturer": "acme imaging", "model": "demoscope 2000"}
    assert record.inherited_fields == ("rotation_direction.Ap2",)
    assert record.is_complete_match is False
    assert record.leaf("translation_offset.x") is selected
    assert record.leaf("missing.leaf") is None
    # The mapping is a fresh copy; the record stays immutable.
    record.matched_input_key.as_mapping()["model"] = "mutated"
    assert record.matched_input_key.model == "demoscope 2000"


def test_complete_match_record_claims_no_inheritance() -> None:
    from guiskindose.equipment_profiles import CoordinateMatchRecord, MatchedInputKey

    record = CoordinateMatchRecord(
        profile_id="demo-partial",
        source="custom",
        level="exact",
        source_kind="json",
        profile_hash="c" * 64,
        matched_input_key=MatchedInputKey.from_raw("Acme Imaging", "DemoScope 2000"),
        affected_event_count=0,
        fields=(),
    )
    assert record.is_complete_match is True
    assert record.inherited_fields == ()


# ---------------------------------------------------------------------------
# Commit-blocking fixes from parent review
# ---------------------------------------------------------------------------


def test_canonical_alias_map_is_a_json_object_that_reloads_to_the_same_hash() -> None:
    payload = _envelope(
        [
            _profile(
                coordinates=_full_coordinates(),
                manufacturer_aliases=["DemoScope2000"],
                provenance={"source": "s", "notes": "n"},
            )
        ]
    )
    original = parse_memory_document(payload).profiles[0]

    reloaded = parse_memory_document(
        {
            "schema_version": 1,
            "profiles": [
                {
                    "profile_id": original.profile_id,
                    "manufacturer": original.manufacturer,
                    "models": list(original.models),
                    "manufacturer_aliases": list(original.manufacturer_aliases),
                    "provenance": {"source": "s", "notes": "n"},
                    "coordinates": _full_coordinates(),
                }
            ],
        }
    ).profiles[0]

    assert reloaded.model_aliases == original.model_aliases
    assert profile_hash(reloaded) == profile_hash(original)


def test_active_set_canonical_form_reloads_to_an_equal_hash() -> None:
    from guiskindose.equipment_profiles import parse_json_bytes

    raw = EXAMPLE_PATH.read_bytes()
    first = parse_json_bytes(raw)

    # Serialize the active set canonically and reload it: aliases, provenance, partial coordinate fields,
    # and transmission rows must all survive the round trip with identical hashes.
    canonical = {
        "schema_version": 1,
        "profiles": [profile.canonical_dict() for profile in first.profiles],
    }
    second = parse_json_bytes(json.dumps(canonical, indent=2).encode("utf-8"))

    assert active_set_hash(second.profiles) == active_set_hash(first.profiles)
    assert second.source_hash == source_bytes_hash(json.dumps(canonical, indent=2).encode("utf-8"))
    for left, right in zip(first.profiles, second.profiles, strict=True):
        assert profile_hash(left) == profile_hash(right)


def test_alias_map_target_with_equivalent_normalized_spelling_matches_shorthand() -> None:
    from guiskindose.equipment_profiles import normalize_model_key

    assert normalize_model_key("DemoScope 2000") != normalize_model_key("DemoScope2000")

    shorthand = parse_memory_document(
        _envelope([_profile(coordinates=_full_coordinates(), model_aliases=["DemoScope2000"])])
    ).profiles[0]
    equivalent = parse_memory_document(
        _envelope(
            [_profile(coordinates=_full_coordinates(), model_aliases={"DemoScope2000": "DemoScope 2000"})]
        )
    ).profiles[0]

    assert profile_hash(shorthand) == profile_hash(equivalent)


def test_every_required_transmission_field_missing_is_a_closed_error() -> None:
    row = {
        "device_model": "DemoScope 2000",
        "acquisition_plane": "Single Plane",
        "kvp_kv": 80,
        "filtration_added_mmcu": 0.0,
        "filtration_added_mmal": 0,
        "k_patient_support": 0.71,
        "evidence_status": "estimated",
        "date": "1901-01-01",
    }
    expected_paths = {
        "device_model": ("transmission", "device_model"),
        "acquisition_plane": ("transmission", "acquisition_plane"),
        "kvp_kv": ("transmission", "kvp_kv"),
        "filtration_added_mmcu": ("transmission", "filtration_added_mmcu"),
        "filtration_added_mmal": ("transmission", "filtration_added_mmal"),
        "k_patient_support": ("transmission", "k_patient_support"),
        "evidence_status": ("transmission", "evidence_status"),
    }
    for missing, field_path in expected_paths.items():
        partial = {key: value for key, value in row.items() if key != missing}
        document = _envelope([_profile(transmission=[partial])])
        with pytest.raises(EquipmentProfileError) as excinfo:
            parse_memory_document(document)
        assert _error_code(excinfo) is ProfileErrorCode.MISSING_REQUIRED_FIELD, missing
        assert excinfo.value.field_path == field_path, missing


def test_huge_integers_are_rejected_as_non_finite_numbers() -> None:
    document = _envelope([_profile(coordinates={"detector_side_length": 10**400})])
    with pytest.raises(EquipmentProfileError) as excinfo:
        parse_memory_document(document)

    assert _error_code(excinfo) is ProfileErrorCode.INVALID_NUMBER
    assert excinfo.value.__cause__ is None

    huge_json = (
        b'{"schema_version":1,"profiles":[{"profile_id":"p","manufacturer":"A","models":["M"],'
        b'"coordinates":{"detector_side_length":1' + b"0" * 400 + b"}}]}"
    )
    with pytest.raises(EquipmentProfileError) as excinfo:
        parse_json_bytes(huge_json)

    assert _error_code(excinfo) is ProfileErrorCode.INVALID_NUMBER


def test_empty_model_alias_list_means_no_aliases_for_every_profile_shape() -> None:
    wildcard = parse_memory_document(
        _envelope(
            [
                {
                    "profile_id": "p",
                    "manufacturer": "Acme Imaging",
                    "models": ["*"],
                    "coordinates": {"translation_offset": {"z": -12.5}},
                    "model_aliases": [],
                }
            ]
        )
    ).profiles[0]
    assert wildcard.model_aliases == ()

    multi = parse_memory_document(
        _envelope([_profile(models=["A", "B"], coordinates=_full_coordinates(), model_aliases=[])])
    ).profiles[0]
    assert multi.model_aliases == ()

    empty_map = parse_memory_document(
        _envelope([_profile(coordinates=_full_coordinates(), model_aliases={})])
    ).profiles[0]
    assert empty_map.model_aliases == ()


def test_packaged_wildcard_example_with_empty_alias_list_parses() -> None:
    payload = _raw_example()
    profiles = payload["profiles"]
    assert isinstance(profiles, list)
    wildcard = next(p for p in profiles if p["profile_id"] == "demo-scope-wildcard")
    wildcard["model_aliases"] = []

    document = parse_json_bytes(json.dumps(payload).encode("utf-8"))

    assert len(document.profiles) == 3
    assert document.profiles[1].model_aliases == ()


def test_degenerate_model_keys_are_rejected() -> None:
    for bad in ["!!!", "   ", "-", "_"]:
        document = _envelope([_profile(models=[bad], coordinates=_full_coordinates())])
        with pytest.raises(EquipmentProfileError) as excinfo:
            parse_memory_document(document)

        assert _error_code(excinfo) is ProfileErrorCode.INVALID_MODEL_LIST, bad


def test_wildcard_variants_are_treated_as_the_wildcard_consistently() -> None:
    for spelling in ["*", " * ", "* ", "\t*"]:
        document = parse_memory_document(
            _envelope([_profile(models=[spelling], coordinates=_full_coordinates())])
        )
        assert document.profiles[0].models == ("*",), spelling

    # A wildcard variant mixed with real models is still refused.
    document = _envelope([_profile(models=[" * ", "DemoScope 2000"], coordinates=_full_coordinates())])
    with pytest.raises(EquipmentProfileError) as excinfo:
        parse_memory_document(
            document
        )
    assert _error_code(excinfo) is ProfileErrorCode.WILDCARD_NOT_PERMITTED


def test_transmission_row_cannot_target_the_wildcard() -> None:
    row = {
        "device_model": "*",
        "acquisition_plane": "Single Plane",
        "kvp_kv": 80,
        "filtration_added_mmcu": 0.0,
        "filtration_added_mmal": 0,
        "k_patient_support": 0.71,
        "evidence_status": "estimated",
        "date": "1901-01-01",
    }
    document = _envelope([{"profile_id": "p", "manufacturer": "A", "models": ["*"], "transmission": [row]}])
    with pytest.raises(EquipmentProfileError) as excinfo:
        parse_memory_document(document)

    assert _error_code(excinfo) is ProfileErrorCode.ALIAS_TARGET_MISMATCH


def test_file_read_is_bounded_and_rejects_oversized_sources(tmp_path: Path) -> None:
    from guiskindose.equipment_profiles.constants import MAX_SOURCE_BYTES

    good = {"schema_version": 1, "profiles": [_profile(coordinates=_full_coordinates())]}
    at_limit = tmp_path / "at_limit.json"
    at_limit.write_bytes(json.dumps(good).encode("utf-8").ljust(MAX_SOURCE_BYTES, b" "))

    assert len(parse_json_file(at_limit).profiles) == 1

    over = tmp_path / "over.json"
    over.write_bytes(b"x" * (MAX_SOURCE_BYTES + 1))
    with pytest.raises(EquipmentProfileError) as excinfo:
        parse_json_file(over)
    assert _error_code(excinfo) is ProfileErrorCode.OVERSIZED_SOURCE


def test_transmission_only_and_coordinate_only_profiles_may_share_an_identity() -> None:
    from guiskindose.equipment_profiles import validate_profile_set

    row = {
        "device_model": "M",
        "acquisition_plane": "Single Plane",
        "kvp_kv": 80,
        "filtration_added_mmcu": 0.0,
        "filtration_added_mmal": 0,
        "k_patient_support": 0.71,
        "evidence_status": "estimated",
        "date": "1901-01-01",
    }
    transmission_only = parse_memory_document(
        _envelope([_profile(profile_id="a", models=["M"], transmission=[row])])
    ).profiles[0]
    coordinate_only = parse_memory_document(
        _envelope([_profile(profile_id="b", models=["M"], coordinates=_full_coordinates())])
    ).profiles[0]

    # Neither claims the other's slot, so this is safe.
    validate_profile_set((transmission_only, coordinate_only), source_kind="json")

    # A second coordinate claimant of the same identity fails, even with identical content.
    other_coordinate = parse_memory_document(
        _envelope([_profile(profile_id="c", models=["M"], coordinates=_full_coordinates())])
    ).profiles[0]
    with pytest.raises(EquipmentProfileError) as excinfo:
        validate_profile_set((coordinate_only, other_coordinate), source_kind="json")
    assert _error_code(excinfo) is ProfileErrorCode.DUPLICATE_COORDINATE_CLAIM


def test_alias_claims_conflict_across_profiles_even_when_identical() -> None:
    from guiskindose.equipment_profiles import validate_profile_set

    base = _profile(coordinates=_full_coordinates(), model_aliases=["shared-alias"])
    first = parse_memory_document(_envelope([{**base, "profile_id": "a"}])).profiles[0]
    second = parse_memory_document(
        _envelope([{**base, "profile_id": "b", "models": ["Other"], "model_aliases": {"shared-alias": "Other"}}])
    ).profiles[0]

    with pytest.raises(EquipmentProfileError) as excinfo:
        validate_profile_set((first, second), source_kind="json")

    assert _error_code(excinfo) is ProfileErrorCode.DUPLICATE_COORDINATE_CLAIM


def test_manufacturer_alias_claims_also_participate() -> None:
    from guiskindose.equipment_profiles import validate_profile_set

    first = parse_memory_document(
        _envelope(
            [
                {
                    "profile_id": "a",
                    "manufacturer": "Acme Imaging",
                    "manufacturer_aliases": ["SharedMfr"],
                    "models": ["M"],
                    "coordinates": _full_coordinates(),
                }
            ]
        )
    ).profiles[0]
    second = parse_memory_document(
        _envelope(
            [
                {
                    "profile_id": "b",
                    "manufacturer": "SharedMfr",
                    "models": ["M"],
                    "coordinates": _full_coordinates(),
                }
            ]
        )
    ).profiles[0]

    with pytest.raises(EquipmentProfileError) as excinfo:
        validate_profile_set((first, second), source_kind="json")

    assert _error_code(excinfo) is ProfileErrorCode.DUPLICATE_COORDINATE_CLAIM


def test_packaged_alias_does_not_falsely_collide_with_its_own_model() -> None:
    from guiskindose.equipment_profiles import validate_profile_set
    from guiskindose.equipment_profiles.keys import normalize_model_key

    # The bundled example's alias and its model canonicalize differently, so there is no self-collision.
    assert normalize_model_key("DemoScope2000") != normalize_model_key("DemoScope 2000")

    document = parse_json_file(EXAMPLE_PATH)
    validate_profile_set(document.profiles, source_kind="json")  # must not raise


def test_alias_named_like_its_own_target_model_is_harmless() -> None:
    from guiskindose.equipment_profiles.keys import normalize_model_key

    # ``DemoScope-2000`` and ``DemoScope 2000`` canonicalize identically, so the alias key collides with a
    # listed model key. Because it resolves to that very model, the collision is harmless.
    assert normalize_model_key("DemoScope-2000") == normalize_model_key("DemoScope 2000")

    profile = parse_memory_document(
        _envelope([_profile(coordinates=_full_coordinates(), model_aliases=["DemoScope-2000"])])
    ).profiles[0]
    assert ("DemoScope-2000", "DemoScope 2000") in profile.model_aliases


def test_alias_named_like_a_different_listed_model_is_rejected() -> None:
    from guiskindose.equipment_profiles.keys import normalize_model_key

    # The alias key ``DemoScope 3000`` canonicalizes to the same key as the listed model ``DemoScope-3000``,
    # but the alias resolves to ``DemoScope 2000``. That is indistinguishable on lookup, so it is rejected.
    assert normalize_model_key("DemoScope 3000") == normalize_model_key("DemoScope-3000")

    document = _envelope(
                [
                    _profile(
                        models=["DemoScope 2000", "DemoScope-3000"],
                        coordinates=_full_coordinates(),
                        model_aliases={"DemoScope 3000": "DemoScope 2000"},
                    )
                ]
            )
    with pytest.raises(EquipmentProfileError) as excinfo:
        parse_memory_document(
            document
        )

    assert _error_code(excinfo) is ProfileErrorCode.ALIAS_AMBIGUOUS_TARGET


def test_transmission_duplicates_are_case_and_punctuation_independent() -> None:
    from guiskindose.equipment_profiles import validate_profile_set

    def _row(device_model: str) -> dict[str, object]:
        return {
            "device_model": device_model,
            "acquisition_plane": "Single Plane",
            "kvp_kv": 80,
            "filtration_added_mmcu": 0.0,
            "filtration_added_mmal": 0,
            "k_patient_support": 0.71,
            "evidence_status": "estimated",
            "date": "1901-01-01",
        }

    # Each profile lists and names its own exact model; the two spellings differ only by punctuation,
    # so their normalized transmission keys collide even though the manufacturers differ.
    first = parse_memory_document(
        _envelope([_profile(profile_id="a", manufacturer="Acme Imaging", models=["DemoScope 2000"],
                            transmission=[_row("DemoScope 2000")])])
    ).profiles[0]
    second = parse_memory_document(
        _envelope([_profile(profile_id="b", manufacturer="Other Imaging", models=["DemoScope-2000"],
                            transmission=[_row("DemoScope-2000")])])
    ).profiles[0]
    assert first.transmission[0].key[:1] != second.transmission[0].key[:1]

    with pytest.raises(EquipmentProfileError) as excinfo:
        validate_profile_set((first, second), source_kind="json")

    assert _error_code(excinfo) is ProfileErrorCode.DUPLICATE_TRANSMISSION_KEY


def test_memory_depth_error_uses_the_memory_source_kind() -> None:
    deep: dict[str, object] = {}
    current: dict[str, object] = deep
    for _ in range(20):
        nested: dict[str, object] = {"schema_version": 1, "profiles": []}
        current["a"] = nested
        current = nested

    with pytest.raises(EquipmentProfileError) as excinfo:
        parse_memory_document(deep)

    assert _error_code(excinfo) is ProfileErrorCode.NESTING_LIMIT_EXCEEDED
    assert excinfo.value.source_kind == "memory"


def test_single_document_enforces_the_aggregate_row_ceiling() -> None:
    rows = [
        {
            "device_model": "M",
            "acquisition_plane": "Single Plane",
            "kvp_kv": 80,
            "filtration_added_mmcu": float(index % 50),
            "filtration_added_mmal": 0,
            "k_patient_support": 0.71,
            "evidence_status": "estimated",
        }
        for index in range(200)
    ]
    payload = {
        "schema_version": 1,
        "profiles": [
            {
                "profile_id": f"p{index}",
                "manufacturer": "A",
                "models": [f"M{index}"],
                "coordinates": {"detector_side_length": 40},
                "transmission": [{**row, "device_model": f"M{index}"} for row in rows],
            }
            for index in range(64)
        ],
    }

    with pytest.raises(EquipmentProfileError) as excinfo:
        parse_memory_document(payload)

    assert _error_code(excinfo) is ProfileErrorCode.ROW_LIMIT_EXCEEDED


def test_parsed_document_profiles_are_typed_profiles() -> None:
    from guiskindose.equipment_profiles.json_source import ParsedDocument

    document = parse_json_file(EXAMPLE_PATH)

    assert isinstance(document, ParsedDocument)
    assert all(isinstance(profile, Profile) for profile in document.profiles)
    assert isinstance(document.profiles, tuple)


def test_early_checks_bound_work_before_traversal() -> None:
    """A huge in-memory mapping is rejected by a cheap or bounded check, never walked exhaustively."""
    from guiskindose.equipment_profiles.constants import MAX_PROFILES, MAX_TRAVERSAL_NODES

    # 1) A profile list longer than the ceiling is rejected before any traversal.
    too_many = {"schema_version": 1, "profiles": [{"profile_id": f"p{i}", "manufacturer": "A", "models": ["M"]} for i in range(MAX_PROFILES + 1)]}
    with pytest.raises(EquipmentProfileError) as excinfo:
        parse_memory_document(too_many)
    assert _error_code(excinfo) is ProfileErrorCode.PROFILE_LIMIT_EXCEEDED

    # 2) A broad-but-shallow structure exceeding the node budget is rejected by the budget, not by walking it.
    broad = {"schema_version": 1, "profiles": [], "pad": {f"k{i}": {"v": [1, 2, 3]} for i in range(MAX_TRAVERSAL_NODES)}}
    with pytest.raises(EquipmentProfileError) as excinfo:
        parse_memory_document(broad)
    assert _error_code(excinfo) in (
        ProfileErrorCode.NESTING_LIMIT_EXCEEDED,
        ProfileErrorCode.UNKNOWN_FIELD,
        ProfileErrorCode.ROW_LIMIT_EXCEEDED,
    )


def test_packaged_example_still_parses_after_conflict_rule_change() -> None:
    from guiskindose.equipment_profiles import validate_profile_set

    document = parse_json_file(EXAMPLE_PATH)

    assert len(document.profiles) == 3
    leaves = sum(len(profile.coordinate_leaves()) for profile in document.profiles)
    rows = sum(len(profile.transmission) for profile in document.profiles)
    assert (leaves, rows, document.logical_rows) == (16, 5, 3 + 16 + 5)
    validate_profile_set(document.profiles, source_kind="json")


@pytest.mark.parametrize("adapter", [parse_memory_document, parse_json_bytes])
def test_unpaired_surrogate_is_rejected_without_raw_error(adapter: object) -> None:
    document = _envelope([_profile(coordinates=_full_coordinates(), provenance={"notes": "\ud800"})])
    raw = json.dumps(document).encode("utf-8")
    from functools import partial

    if adapter is parse_json_bytes:
        operation = partial(parse_json_bytes, raw)
    else:
        operation = partial(parse_memory_document, document)
    with pytest.raises(EquipmentProfileError) as excinfo:
        operation()
    assert excinfo.value.code == ProfileErrorCode.UNSUPPORTED_SOURCE_ENCODING
    assert excinfo.value.__suppress_context__


def test_measured_source_cannot_be_whitespace() -> None:
    row = {
        "device_model": "DemoScope 2000", "acquisition_plane": "Single Plane",
        "kvp_kv": 80, "filtration_added_mmcu": 0, "filtration_added_mmal": 0,
        "k_patient_support": 0.7, "evidence_status": "measured", "source": "   ", "date": "1901-01-01",
    }
    document = _envelope([_profile(transmission=[row])])
    with pytest.raises(EquipmentProfileError) as excinfo:
        parse_memory_document(document)
    assert excinfo.value.code == ProfileErrorCode.BLANK_REQUIRED_CELL
