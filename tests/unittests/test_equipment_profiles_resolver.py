"""Tests for the canonical bundled adapter and the custom-exact coordinate resolver.

Covers: bundled conversion of the shipped settings (deterministic IDs/hashes,
alias-expanded slots, separate Default, swap handling), no-custom parity with
runtime settings selection (Siemens/Philips/GE-family/Default), miss paths
(wildcard/Default), missing-maker bypass, custom partial/complete resolution
with zero/False preservation, capability-gate failures, store context
propagation, closed fallbacks, immutability, and value-free diagnostics. No
application wiring is exercised: resolution never touches the normalizer,
settings objects, or dose code.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from guiskindose.equipment_profiles import (
    COORDINATE_LEAF_COUNT,
    EquipmentProfileError,
    ExamCoordinateIdentity,
    IndexedProfile,
    ProfileErrorCode,
    build_profile_indexes,
    bundled_coordinate_set,
    parse_memory_document,
    prepare_bundled_context,
    prepare_custom_context,
    profile_hash,
    resolve_coordinate_leaves,
    resolve_with_prepared,
)

SETTINGS_PATH = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "guiskindose"
    / "normalization_settings.json"
)


def _shipped_entries():
    return json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))["normalization_settings"]


def _bundled():
    return bundled_coordinate_set(_shipped_entries())


def _custom(raw_profiles, *, source_kind="json", revision=None):
    profiles = parse_memory_document({"schema_version": 1, "profiles": raw_profiles}).profiles
    entries = [
        IndexedProfile(
            profile=profile, source_kind=source_kind, revision=revision, profile_hash=profile_hash(profile)
        )
        for profile in profiles
    ]
    return build_profile_indexes(entries)


def _empty_custom():
    return build_profile_indexes([])


def _profile(profile_id, **overrides):
    base = {
        "profile_id": profile_id,
        "manufacturer": "Acme Imaging",
        "models": ["DemoScope 2000"],
    }
    base.update(overrides)
    return base


def _resolve(maker, model, *, custom=None, events=12):
    return resolve_coordinate_leaves(
        identity=ExamCoordinateIdentity(manufacturer=maker, model=model, event_count=events),
        custom=custom if custom is not None else _empty_custom(),
        bundled=_bundled(),
    )


def _settings_selected(maker, model):
    """Runtime selection for one pair through the real NormalizationSettings."""
    from guiskindose.settings.normalization_settings import NormalizationSettings

    settings = NormalizationSettings(_shipped_entries())
    frame = pd.DataFrame({"Manufacturer": [maker], "ManufacturerModelName": [model]})
    settings.update_used_settings(data_parsed=frame)
    return settings


def _runtime_leaves(settings):
    """Canonical-form leaves from a matched runtime settings object."""
    sign = {1: "+", -1: "-"}
    leaves = {
        "translation_offset.x": settings.trans_offset.x,
        "translation_offset.y": settings.trans_offset.y,
        "translation_offset.z": settings.trans_offset.z,
        "translation_direction.x": sign[settings.trans_dir.x],
        "translation_direction.y": sign[settings.trans_dir.y],
        "translation_direction.z": sign[settings.trans_dir.z],
        "rotation_direction.Ap1": sign[settings.rot_dir.Ap1],
        "rotation_direction.Ap2": sign[settings.rot_dir.Ap2],
        "rotation_direction.Ap3": sign[settings.rot_dir.Ap3],
        "rotation_direction.At1": sign[settings.rot_dir.At1],
        "rotation_direction.At2": sign[settings.rot_dir.At2],
        "rotation_direction.At3": sign[settings.rot_dir.At3],
        "swap_lateral_longitudinal": settings.swap_lateral_longitudinal,
        "field_size_mode": settings.field_size_mode,
        "detector_side_length": float(settings.detector_side_length),
    }
    return leaves


# ---------------------------------------------------------------------------
# Bundled adapter
# ---------------------------------------------------------------------------


def test_bundled_ids_hashes_and_default_separation() -> None:
    bundled = _bundled()
    assert [entry.profile.profile_id for entry in bundled.profiles] == [
        "bundled-ge-healthcare-wildcard",
        "bundled-philips-allura-clarity",
        "bundled-siemens-axiom-artis",
    ]
    assert bundled.default is not None
    assert bundled.default.profile.profile_id == "bundled-default-default"
    assert all(entry.source_kind == "json" for entry in bundled.profiles)
    assert all(entry.revision is None for entry in bundled.profiles)
    # Default is not a claimable slot.
    assert "bundled-default-default" not in [entry.profile.profile_id for entry in bundled.exact.profiles]
    # Deterministic: same entries recompile to identical IDs and hashes.
    again = _bundled()
    assert [e.profile_hash for e in bundled.profiles] == [e.profile_hash for e in again.profiles]
    assert bundled.default is not None
    assert again.default is not None
    assert bundled.default.profile_hash == again.default.profile_hash


def test_bundled_entries_carry_all_leaves_with_materialized_swap() -> None:
    bundled = _bundled()
    by_id = {entry.profile.profile_id: entry for entry in bundled.exact.profiles}
    # Every bundled entry is complete: shipped switches preserved, omitted
    # switches materialized as False (the runtime default for each entry).
    assert len(by_id["bundled-siemens-axiom-artis"].profile.coordinate_leaves()) == COORDINATE_LEAF_COUNT
    assert len(by_id["bundled-philips-allura-clarity"].profile.coordinate_leaves()) == COORDINATE_LEAF_COUNT
    assert len(by_id["bundled-ge-healthcare-wildcard"].profile.coordinate_leaves()) == COORDINATE_LEAF_COUNT
    siemens = by_id["bundled-siemens-axiom-artis"].profile
    assert siemens.coordinates is not None
    assert siemens.coordinates.swap_lateral_longitudinal is False
    ge_swap = by_id["bundled-ge-healthcare-wildcard"].profile.coordinates
    assert ge_swap is not None
    assert ge_swap.swap_lateral_longitudinal is True
    siemens = next(e for e in bundled.exact.profiles if e.profile.manufacturer == "Siemens")
    assert siemens.profile.coordinates is not None
    assert siemens.profile.coordinates.swap_lateral_longitudinal is False
    assert bundled.default is not None
    assert bundled.default.profile.coordinates is not None
    assert bundled.default.profile.coordinates.swap_lateral_longitudinal is False
    assert len(bundled.default.profile.coordinate_leaves()) == COORDINATE_LEAF_COUNT


def test_bundled_ge_aliases_reach_wildcard_without_custom_inheritance() -> None:
    bundled = _bundled()
    claim = bundled.exact.coordinates.lookup_wildcard("GE Medical Systems")
    assert claim is not None
    assert claim.profile_id == "bundled-ge-healthcare-wildcard"
    assert claim.via_alias is True
    assert claim.is_wildcard is True
    siemens = bundled.exact.coordinates.lookup_exact("Siemens Healthcare", "AXIOM-Artis")
    assert siemens is not None
    assert siemens.profile_id == "bundled-siemens-axiom-artis"


def test_bundled_second_default_fails_closed() -> None:
    entries = _shipped_entries()
    default = next(e for e in entries if e["manufacturer"] == "Default")
    with pytest.raises(EquipmentProfileError) as excinfo:
        bundled_coordinate_set([*entries, dict(default)])
    assert excinfo.value.code is ProfileErrorCode.DUPLICATE_PROFILE_ID


@pytest.mark.parametrize(
    "bad",
    ["bundled", b"bundled", None, {"manufacturer": "Siemens"}],
)
def test_bundled_non_sequence_entries_rejected(bad) -> None:
    with pytest.raises(EquipmentProfileError) as excinfo:
        bundled_coordinate_set(bad)  # type: ignore[arg-type]
    assert excinfo.value.code is ProfileErrorCode.INVALID_TYPE


def test_bundled_missing_manufacturer_fails_closed() -> None:
    with pytest.raises(EquipmentProfileError) as excinfo:
        bundled_coordinate_set([{"models": ["X"], "coordinates": {"detector_side_length": 40.0}}])
    assert excinfo.value.code is ProfileErrorCode.MISSING_REQUIRED_FIELD


def test_bundled_leaf_order_covers_all_fifteen() -> None:
    from guiskindose.equipment_profiles.resolver import LEAF_ORDER

    assert len(LEAF_ORDER) == COORDINATE_LEAF_COUNT == 15
    assert len(set(LEAF_ORDER)) == 15


# ---------------------------------------------------------------------------
# No-custom parity with runtime settings selection
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("maker", "model", "source", "level"),
    [
        ("Siemens", "AXIOM-Artis", "bundled", "exact"),
        ("Philips", "Allura Clarity", "bundled", "exact"),
        ("GE Medical Systems", "Unknown GE Model", "bundled", "wildcard"),
        ("Unknown Maker", "Unknown Model", "default", "default"),
        ("Siemens", "Unknown Model", "default", "default"),
    ],
)
def test_no_custom_resolution_matches_runtime_selection(maker, model, source, level) -> None:
    resolution = _resolve(maker, model)
    record = resolution.record
    assert (record.source, record.level) == (source, level)
    expected = _runtime_leaves(_settings_selected(maker, model))
    assert len(record.fields) == COORDINATE_LEAF_COUNT
    for leaf in record.fields:
        assert leaf.value == expected[leaf.field], leaf.field
    assert record.affected_event_count == 12
    assert record.domain == "coordinate"


def test_ge_wildcard_swap_true_not_inherited() -> None:
    resolution = _resolve("GE Medical Systems", "Unknown GE Model")
    swap = resolution.record.leaf("swap_lateral_longitudinal")
    assert swap is not None
    assert swap.value is True
    assert swap.inherited is False
    assert resolution.notice.kind == "complete"


def test_siemens_no_custom_is_complete_with_bundled_swap() -> None:
    """Shipped exact entries are complete: swap resolves from the exact entry itself."""
    resolution = _resolve("Siemens", "AXIOM-Artis")
    swap = resolution.record.leaf("swap_lateral_longitudinal")
    assert swap is not None
    assert swap.value is False
    assert swap.inherited is False
    assert (swap.source, swap.level, swap.profile_id) == (
        "bundled",
        "exact",
        "bundled-siemens-axiom-artis",
    )
    assert resolution.record.is_complete_match
    assert resolution.notice.kind == "complete"
    assert "swap_lateral_longitudinal" not in resolution.record.inherited_fields


def test_missing_maker_bypasses_to_legacy_default() -> None:
    resolution = _resolve(None, "AXIOM-Artis")
    record = resolution.record
    assert (record.source, record.level) == ("default", "default")
    assert record.matched_input_key.manufacturer == ""
    assert record.matched_input_key.model == "axiom artis"


def test_blank_model_falls_to_ge_wildcard_or_default() -> None:
    wildcard = _resolve("GE Healthcare", "")
    assert (wildcard.record.source, wildcard.record.level) == ("bundled", "wildcard")
    default = _resolve("Siemens", "")
    assert (default.record.source, default.record.level) == ("default", "default")


# ---------------------------------------------------------------------------
# Custom exact resolution
# ---------------------------------------------------------------------------


def test_custom_partial_swap_inherits_all_lower_leaves() -> None:
    custom = _custom(
        [_profile("my-scope", coordinates={"swap_lateral_longitudinal": True})]
    )
    resolution = resolve_coordinate_leaves(
        identity=ExamCoordinateIdentity(manufacturer="Acme Imaging", model="DemoScope 2000", event_count=9),
        custom=custom,
        bundled=_bundled(),
    )
    record = resolution.record
    assert (record.source, record.level, record.profile_id) == ("custom", "exact", "my-scope")
    assert record.affected_event_count == 9
    assert record.matched_input_key.as_mapping() == {"manufacturer": "acme imaging", "model": "demoscope 2000"}
    swap = record.leaf("swap_lateral_longitudinal")
    assert swap is not None
    assert swap.value is True
    assert swap.inherited is False
    assert (swap.source_kind, swap.revision) == ("json", None)
    # No bundled exact covers Acme/DemoScope: the other 14 come from Default.
    assert len(record.inherited_fields) == COORDINATE_LEAF_COUNT - 1
    assert resolution.notice.kind == "partial"
    assert len(resolution.notice.entries) == COORDINATE_LEAF_COUNT - 1
    assert "`swap_lateral_longitudinal`" not in resolution.notice.text
    assert "`translation_offset.x` from default default" in resolution.notice.text


def test_custom_partial_over_bundled_exact_uses_bundled_leaves() -> None:
    custom = _custom(
        [
            _profile(
                "siemens-tweak",
                manufacturer="Siemens",
                models=["AXIOM-Artis"],
                coordinates={"swap_lateral_longitudinal": True},
            )
        ]
    )
    resolution = resolve_coordinate_leaves(
        identity=ExamCoordinateIdentity(manufacturer="Siemens", model="AXIOM-Artis", event_count=4),
        custom=custom,
        bundled=_bundled(),
    )
    record = resolution.record
    assert (record.source, record.level, record.profile_id) == ("custom", "exact", "siemens-tweak")
    offset = record.leaf("translation_offset.x")
    assert offset is not None
    assert offset.value == 0.0
    assert offset.inherited is True
    assert (offset.source, offset.level, offset.profile_id) == (
        "bundled",
        "exact",
        "bundled-siemens-axiom-artis",
    )
    assert "`translation_offset.x` from bundled exact `AXIOM-Artis`" in resolution.notice.text


def test_complete_custom_has_no_inheritance() -> None:
    custom = _custom(
        [
            _profile(
                "full-scope",
                coordinates={
                    "translation_offset": {"x": 0.0, "y": 1.5, "z": -2.0},
                    "translation_direction": {"x": "-", "y": "+", "z": "+"},
                    "rotation_direction": {"Ap1": "-", "Ap2": "+", "Ap3": "+", "At1": "+", "At2": "+", "At3": "+"},
                    "swap_lateral_longitudinal": False,
                    "field_size_mode": "ASD",
                    "detector_side_length": 40.0,
                },
            )
        ]
    )
    resolution = resolve_coordinate_leaves(
        identity=ExamCoordinateIdentity(manufacturer="Acme Imaging", model="DemoScope 2000", event_count=3),
        custom=custom,
        bundled=_bundled(),
    )
    record = resolution.record
    assert record.is_complete_match
    assert record.inherited_fields == ()
    assert resolution.notice.kind == "complete"
    assert resolution.notice.entries == ()
    assert "Complete match" in resolution.notice.text
    # Explicit False and 0.0 survive: they are supplied, not missing.
    swap_leaf = record.leaf("swap_lateral_longitudinal")
    offset_leaf = record.leaf("translation_offset.x")
    assert swap_leaf is not None
    assert offset_leaf is not None
    assert swap_leaf.value is False
    assert swap_leaf.inherited is False
    assert offset_leaf.value == 0.0
    assert offset_leaf.inherited is False


def test_custom_keys_normalize_like_bundled() -> None:
    custom = _custom(
        [
            _profile(
                "spaced",
                manufacturer="Siemens",
                models=["AXIOM-Artis"],
                coordinates={"detector_side_length": 30.0},
            )
        ]
    )
    resolution = resolve_coordinate_leaves(
        identity=ExamCoordinateIdentity(manufacturer="SIEMENS ", model="AXIOM Artis", event_count=1),
        custom=custom,
        bundled=_bundled(),
    )
    assert resolution.record.profile_id == "spaced"
    assert resolution.record.source == "custom"


def test_custom_exact_miss_resolves_bundled_or_default_with_attribution() -> None:
    custom = _custom([_profile("other", coordinates={"detector_side_length": 30.0})])
    bundled_hit = resolve_coordinate_leaves(
        identity=ExamCoordinateIdentity(manufacturer="Siemens", model="AXIOM-Artis", event_count=2),
        custom=custom,
        bundled=_bundled(),
    )
    assert (bundled_hit.record.source, bundled_hit.record.level) == ("bundled", "exact")
    assert bundled_hit.record.profile_id == "bundled-siemens-axiom-artis"
    default_hit = resolve_coordinate_leaves(
        identity=ExamCoordinateIdentity(manufacturer="Nope", model="Nope", event_count=2),
        custom=custom,
        bundled=_bundled(),
    )
    assert (default_hit.record.source, default_hit.record.level) == ("default", "default")


# ---------------------------------------------------------------------------
# Capability gate
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("extra", "capability"),
    [
        ({"manufacturer_aliases": ["Acme"]}, "manufacturer_alias"),
        ({"model_aliases": ["DS2000"]}, "model_alias"),
        ({"models": ["*"]}, "model_wildcard"),
        # Promotion requires wildcard models to validate, and the gate checks
        # the wildcard first — so a promoting profile reports model_wildcard.
        ({"models": ["*"], "coordinates": {"detector_side_length": 40.0}, "promote_coordinate_wildcard": True}, "model_wildcard"),
        (
            {
                "coordinates": {"detector_side_length": 40.0},
                "transmission": [
                    {
                        "device_model": "DemoScope 2000",
                        "acquisition_plane": "Single Plane",
                        "kvp_kv": 80,
                        "filtration_added_mmcu": 0.0,
                        "filtration_added_mmal": 0.0,
                        "k_patient_support": 0.5,
                        "evidence_status": "estimated",
                    }
                ],
            },
            "transmission_domain",
        ),
    ],
)
def test_unsupported_custom_capabilities_fail_closed(extra, capability) -> None:
    raw = _profile("gated", **extra)
    if "coordinates" not in raw and "transmission" not in raw:
        raw["coordinates"] = {"detector_side_length": 40.0}
    if extra.get("models") == ["*"] and "coordinates" not in raw:
        raw["coordinates"] = {"detector_side_length": 40.0}
    custom = _custom([raw])
    identity = ExamCoordinateIdentity(manufacturer="Acme Imaging", model="DemoScope 2000", event_count=1)
    bundled = _bundled()
    with pytest.raises(EquipmentProfileError) as excinfo:
        resolve_coordinate_leaves(
            identity=identity,
            custom=custom,
            bundled=bundled,
        )
    assert excinfo.value.code is ProfileErrorCode.UNSUPPORTED_PROFILE_CAPABILITY
    assert excinfo.value.capability == capability


# ---------------------------------------------------------------------------
# Context, fallbacks, and malformed input
# ---------------------------------------------------------------------------


def test_store_context_propagates_to_leaves_and_record() -> None:
    custom = _custom(
        [_profile("stored", coordinates={"swap_lateral_longitudinal": True})],
        source_kind="store",
        revision=5,
    )
    resolution = resolve_coordinate_leaves(
        identity=ExamCoordinateIdentity(manufacturer="Acme Imaging", model="DemoScope 2000", event_count=6),
        custom=custom,
        bundled=_bundled(),
    )
    record = resolution.record
    assert (record.source_kind, record.revision) == ("store", 5)
    swap = record.leaf("swap_lateral_longitudinal")
    assert swap is not None
    assert (swap.source_kind, swap.revision, swap.profile_hash) == (
        "store",
        5,
        record.profile_hash,
    )


def test_missing_default_fails_closed() -> None:
    entries = [entry for entry in _shipped_entries() if entry["manufacturer"] != "Default"]
    bundled = bundled_coordinate_set(entries)
    assert bundled.default is None
    identity = ExamCoordinateIdentity(manufacturer="Nope", model="Nope", event_count=1)
    custom = _empty_custom()
    with pytest.raises(EquipmentProfileError) as excinfo:
        resolve_coordinate_leaves(
            identity=identity,
            custom=custom,
            bundled=bundled,
        )
    assert excinfo.value.code is ProfileErrorCode.MISSING_REQUIRED_FIELD


def test_bad_bundled_leaf_fails_closed() -> None:
    bundled = bundled_coordinate_set(
        [
            {
                "manufacturer": "Default",
                "models": ["Default"],
                "translation_offset": {"x": 1.0},
            }
        ]
    )
    identity = ExamCoordinateIdentity(manufacturer="Nope", model="Nope", event_count=1)
    custom = _empty_custom()
    with pytest.raises(EquipmentProfileError) as excinfo:
        resolve_coordinate_leaves(
            identity=identity,
            custom=custom,
            bundled=bundled,
        )
    error = excinfo.value
    assert error.code is ProfileErrorCode.MISSING_REQUIRED_FIELD
    assert error.field_path == ("translation_offset", "y")
    assert "Nope" not in str(error)
    assert "Nope" not in repr(error)


@pytest.mark.parametrize(
    ("identity", "code", "field_path"),
    [
        ("not-an-identity", ProfileErrorCode.INVALID_TYPE, ()),
        (
            ExamCoordinateIdentity(manufacturer=123, model="X", event_count=1),  # type: ignore[arg-type]
            ProfileErrorCode.INVALID_TYPE,
            ("manufacturer",),
        ),
        (
            ExamCoordinateIdentity(manufacturer="A", model="X", event_count=-1),
            ProfileErrorCode.VALUE_OUT_OF_RANGE,
            ("event_count",),
        ),
    ],
)
def test_malformed_identity_rejected(identity, code, field_path) -> None:
    custom = _empty_custom()
    bundled = _bundled()
    with pytest.raises(EquipmentProfileError) as excinfo:
        resolve_coordinate_leaves(identity=identity, custom=custom, bundled=bundled)
    assert excinfo.value.code is code
    assert excinfo.value.field_path == field_path


def test_malformed_resolver_inputs_rejected() -> None:
    identity = ExamCoordinateIdentity(manufacturer="A", model="B", event_count=1)
    bundled = _bundled()
    with pytest.raises(EquipmentProfileError) as excinfo:
        resolve_coordinate_leaves(identity=identity, custom="nope", bundled=bundled)  # type: ignore[arg-type]
    assert excinfo.value.code is ProfileErrorCode.INVALID_TYPE
    custom = _empty_custom()
    with pytest.raises(EquipmentProfileError) as excinfo:
        resolve_coordinate_leaves(identity=identity, custom=custom, bundled="nope")  # type: ignore[arg-type]
    assert excinfo.value.code is ProfileErrorCode.INVALID_TYPE


# ---------------------------------------------------------------------------
# Missing-identity artifacts can never match, even literally-named profiles
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("artifact", ["none", "NONE", " None ", "nan", "NaN", "nat", "NAT", "", "   "])
def test_artifact_maker_identity_bypasses_custom(artifact) -> None:
    """An exam whose maker is a missing-value artifact resolves the fallback.

    Even a custom profile literally manufactured `"none"` stays unreachable:
    the artifact cleans to missing before any key is derived.
    """
    custom = _custom(
        [
            _profile(
                "none-maker",
                manufacturer="none",
                models=["NoSuch"],
                coordinates={"detector_side_length": 30.0},
            )
        ]
    )
    resolution = resolve_coordinate_leaves(
        identity=ExamCoordinateIdentity(manufacturer=artifact, model="NoSuch", event_count=1),
        custom=custom,
        bundled=_bundled(),
    )
    assert resolution.record.profile_id == "bundled-default-default"
    assert resolution.record.source == "default"


@pytest.mark.parametrize("artifact", ["nan", "NaN", "none", "NONE"])
def test_artifact_model_identity_never_matches_literal(artifact) -> None:
    """An exam whose model is a missing-value artifact cannot hit a same-named slot."""
    custom = _custom(
        [
            _profile(
                "nan-model",
                manufacturer="Acme Imaging",
                models=["nan"],
                coordinates={"detector_side_length": 30.0},
            )
        ]
    )
    resolution = resolve_coordinate_leaves(
        identity=ExamCoordinateIdentity(manufacturer="Acme Imaging", model=artifact, event_count=1),
        custom=custom,
        bundled=_bundled(),
    )
    assert resolution.record.profile_id == "bundled-default-default"


def test_shared_identity_convention_cleans_artifacts() -> None:
    from guiskindose.equipment_profiles.keys import clean_identity_text

    assert clean_identity_text(None) is None
    assert clean_identity_text("  ") is None
    assert clean_identity_text("NaN") is None
    assert clean_identity_text("NONE") is None
    assert clean_identity_text("nat") is None
    assert clean_identity_text("Siemens ") == "Siemens"


# ---------------------------------------------------------------------------
# Bundled bounds and order-independent IDs
# ---------------------------------------------------------------------------


def test_bundled_overcount_fails_before_conversion() -> None:
    entries = _shipped_entries()
    with pytest.raises(EquipmentProfileError) as excinfo:
        bundled_coordinate_set(entries * 20)
    assert excinfo.value.code is ProfileErrorCode.PROFILE_LIMIT_EXCEEDED


def test_bundled_overcount_of_invalid_entries_still_reports_limit() -> None:
    """The count bound fires before any entry is read — not a shape error."""
    with pytest.raises(EquipmentProfileError) as excinfo:
        bundled_coordinate_set(["not-a-mapping"] * 65)  # type: ignore[list-item]
    assert excinfo.value.code is ProfileErrorCode.PROFILE_LIMIT_EXCEEDED


def test_bundled_model_list_bound_before_id_derivation() -> None:
    entry = {
        "manufacturer": "Siemens",
        "models": [f"Model{i}" for i in range(40)],
        "translation_offset": {"x": 0.0},
    }
    with pytest.raises(EquipmentProfileError) as excinfo:
        bundled_coordinate_set([entry])
    assert excinfo.value.code is ProfileErrorCode.MODEL_LIMIT_EXCEEDED


def test_bundled_reordered_models_compile_identically() -> None:
    """IDs, payloads, and hashes derive from canonical order, not input order."""
    base = {
        "manufacturer": "Siemens",
        "translation_offset": {"x": 1.0, "y": 2.0, "z": 3.0},
        "translation_direction": {"x": "+", "y": "+", "z": "+"},
        "rotation_direction": {"Ap1": "+", "Ap2": "+", "Ap3": "+", "At1": "+", "At2": "+", "At3": "+"},
        "field_size_mode": "CFA",
        "detector_side_length": 40.0,
    }
    first = bundled_coordinate_set([{**base, "models": ["Zed", "Alpha"]}])
    second = bundled_coordinate_set([{**base, "models": ["Alpha", "Zed"]}])
    assert first.profiles[0].profile.profile_id == second.profiles[0].profile.profile_id
    assert first.profiles[0].profile_hash == second.profiles[0].profile_hash
    assert first.exact.coordinates.keys == second.exact.coordinates.keys


# ---------------------------------------------------------------------------
# Resolver preparation boundary: corrupt hand-built inputs fail closed
# ---------------------------------------------------------------------------


def _hand_built_index(profiles, *, claims=(), keys=()):
    from guiskindose.equipment_profiles.indexes import CoordinateIndex, ProfileIndexes, TransmissionIndex

    return ProfileIndexes(
        coordinates=CoordinateIndex(keys=tuple(keys), claims=tuple(claims), profiles=tuple(profiles)),
        transmission=TransmissionIndex(keys=(), node_groups=(), profiles=tuple(profiles)),
        profiles=tuple(profiles),
    )


def test_resolver_rejects_dangling_claim_reference() -> None:
    from guiskindose.equipment_profiles.indexes import CoordinateClaim

    bundled = _bundled()
    dangling = CoordinateClaim(
        profile_id="no-such-profile",
        source_kind="json",
        revision=None,
        profile_hash="0" * 64,
        manufacturer_key="siemens",
        model_key="axiom artis",
        is_wildcard=False,
        via_alias=False,
        promote_wildcard=False,
    )
    tampered = _hand_built_index(
        bundled.exact.profiles,
        claims=(*bundled.exact.coordinates.claims, dangling),
        keys=(*bundled.exact.coordinates.keys, ("siemens", "axiom artis")),
    )
    import dataclasses

    patched = dataclasses.replace(bundled, exact=tampered)
    identity = ExamCoordinateIdentity(manufacturer="Siemens", model="AXIOM-Artis", event_count=1)
    custom = _empty_custom()
    with pytest.raises(EquipmentProfileError) as excinfo:
        resolve_coordinate_leaves(
            identity=identity,
            custom=custom,
            bundled=patched,
        )
    assert excinfo.value.code is ProfileErrorCode.INVALID_TYPE
    assert excinfo.value.field_path == ("bundled", "claims")


def test_resolver_rejects_corrupt_default_hash() -> None:
    import dataclasses

    bundled = _bundled()
    assert bundled.default is not None
    corrupt = dataclasses.replace(bundled.default, profile_hash="0" * 64)
    patched = dataclasses.replace(bundled, default=corrupt)
    identity = ExamCoordinateIdentity(manufacturer="Nope", model="Nope", event_count=1)
    custom = _empty_custom()
    with pytest.raises(EquipmentProfileError) as excinfo:
        resolve_coordinate_leaves(
            identity=identity,
            custom=custom,
            bundled=patched,
        )
    assert excinfo.value.code is ProfileErrorCode.CONFLICTING_PROFILE_METADATA


def test_resolver_rejects_invalid_default_profile() -> None:
    import dataclasses

    from guiskindose.equipment_profiles.indexes import IndexedProfile

    bundled = _bundled()
    bad = IndexedProfile(
        profile="not-a-profile",  # type: ignore[arg-type]
        source_kind="json",
        revision=None,
        profile_hash="0" * 64,
    )
    patched = dataclasses.replace(bundled, default=bad)
    identity = ExamCoordinateIdentity(manufacturer="Nope", model="Nope", event_count=1)
    custom = _empty_custom()
    with pytest.raises(EquipmentProfileError) as excinfo:
        resolve_coordinate_leaves(
            identity=identity,
            custom=custom,
            bundled=patched,
        )
    assert excinfo.value.code is ProfileErrorCode.INVALID_TYPE


def test_resolver_rejects_mutable_model_container() -> None:
    from dataclasses import replace

    from guiskindose.equipment_profiles.indexes import IndexedProfile

    bundled = _bundled()
    victim = next(e for e in bundled.exact.profiles if e.profile.manufacturer == "Siemens")
    mutable = replace(victim.profile, models=["AXIOM-Artis"])
    entry = IndexedProfile(
        profile=mutable, source_kind="json", revision=None, profile_hash=victim.profile_hash
    )
    tampered = _hand_built_index([entry])
    patched = bundled_coordinate_set(_shipped_entries())
    import dataclasses

    patched = dataclasses.replace(patched, exact=tampered)
    identity = ExamCoordinateIdentity(manufacturer="Siemens", model="AXIOM-Artis", event_count=1)
    custom = _empty_custom()
    with pytest.raises(EquipmentProfileError) as excinfo:
        resolve_coordinate_leaves(
            identity=identity,
            custom=custom,
            bundled=patched,
        )
    assert excinfo.value.code is ProfileErrorCode.INVALID_TYPE


def test_resolver_rejects_non_float_leaf() -> None:
    from dataclasses import replace

    from guiskindose.equipment_profiles.indexes import IndexedProfile

    bundled = _bundled()
    victim = next(e for e in bundled.exact.profiles if e.profile.manufacturer == "Siemens")
    assert victim.profile.coordinates is not None
    bad_coords = replace(victim.profile.coordinates, detector_side_length=40)
    bad_profile = replace(victim.profile, coordinates=bad_coords)
    entry = IndexedProfile(
        profile=bad_profile, source_kind="json", revision=None, profile_hash="0" * 64
    )
    tampered = _hand_built_index([entry])
    import dataclasses

    patched = dataclasses.replace(bundled_coordinate_set(_shipped_entries()), exact=tampered)
    identity = ExamCoordinateIdentity(manufacturer="Siemens", model="AXIOM-Artis", event_count=1)
    custom = _empty_custom()
    with pytest.raises(EquipmentProfileError) as excinfo:
        resolve_coordinate_leaves(
            identity=identity,
            custom=custom,
            bundled=patched,
        )
    assert excinfo.value.code in (ProfileErrorCode.INVALID_TYPE, ProfileErrorCode.CONFLICTING_PROFILE_METADATA)


# ---------------------------------------------------------------------------
# Repr safety across all new public types
# ---------------------------------------------------------------------------


def test_all_new_public_reprs_hide_identity() -> None:
    """Sentinel maker/model/notes appear in no new public repr.

    The sentinel uses odd capitalization so a mere lowercase leak is still
    caught: lowercasing is not privacy.
    """
    custom = _custom(
        [
            _profile(
                "sentinel-zz",
                manufacturer="SENTINEL Maker ZZ",
                models=["SENTINEL Model ZZ"],
                provenance={"source": "SENTINEL Source ZZ", "notes": "SENTINEL Notes ZZ"},
                coordinates={"detector_side_length": 30.0},
            )
        ]
    )
    resolution = resolve_coordinate_leaves(
        identity=ExamCoordinateIdentity(
            manufacturer="SENTINEL Maker ZZ", model="SENTINEL Model ZZ", event_count=7
        ),
        custom=custom,
        bundled=_bundled(),
    )
    bundled = _bundled()
    texts = [
        repr(ExamCoordinateIdentity(manufacturer="SENTINEL Maker ZZ", model="SENTINEL Model ZZ", event_count=7)),
        repr(resolution.notice.entries[0]),
        repr(resolution.notice),
        repr(resolution),
        repr(bundled),
    ]
    for text in texts:
        for sentinel in (
            "SENTINEL Maker ZZ",
            "sentinel maker zz",
            "SENTINEL Model ZZ",
            "sentinel model zz",
            "SENTINEL Source ZZ",
            "SENTINEL Notes ZZ",
            "sentinel-zz",
        ):
            assert sentinel not in text, (sentinel, text)
    # Kinds and counts are the permitted content.
    assert "event_count=7" in texts[0]
    assert "kind='partial'" in texts[2]
    assert "leaves=15" in texts[3]
    assert "has_default=True" in texts[4]


# ---------------------------------------------------------------------------
# Immutability and privacy
# ---------------------------------------------------------------------------


def test_resolution_types_are_immutable() -> None:
    from dataclasses import FrozenInstanceError

    resolution = _resolve("Siemens", "AXIOM-Artis")
    with pytest.raises(FrozenInstanceError):
        resolution.record.profile_id = "mutated"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        resolution.notice.text = "mutated"  # type: ignore[misc]


def test_identity_repr_shows_count_only() -> None:
    identity = ExamCoordinateIdentity(manufacturer="  ACME Imaging  ", model="DemoScope-2000 ", event_count=4)
    text = repr(identity)
    assert "  ACME" not in text
    assert "2000 " not in text
    # Canonical keys are not privacy either: lowercasing is not redaction.
    assert "acme imaging" not in text
    assert "demoscope 2000" not in text
    assert text == "ExamCoordinateIdentity(event_count=4)"


def test_notice_text_uses_permitted_labels_only() -> None:
    """Notice text may name permitted labels (fields, sources, maker/model/profile
    labels) — never notes, source paths, or raw source text."""
    custom = _custom(
        [_profile("acme-swap", coordinates={"swap_lateral_longitudinal": True})]
    )
    resolution = resolve_coordinate_leaves(
        identity=ExamCoordinateIdentity(manufacturer="Acme Imaging", model="DemoScope 2000", event_count=2),
        custom=custom,
        bundled=_bundled(),
    )
    assert resolution.notice.kind == "partial"
    text = resolution.notice.text + repr(resolution.notice)
    assert ".json" not in text
    assert ".py" not in text
    assert "notes" not in text.lower()
    # The only slash is SPEC §6's own "bundled/Default" phrasing, not a path
    # (checked on the text alone; the repr embeds the text a second time).
    assert resolution.notice.text.count("/") == 1


def test_resolver_rejects_retargeted_claim_key() -> None:
    from dataclasses import replace

    bundled = _bundled()
    table = bundled.exact.coordinates
    bad_key = ("unrelated maker", "unrelated model")
    tampered = replace(table, keys=(bad_key, *table.keys[1:]))
    patched = replace(bundled, exact=replace(bundled.exact, coordinates=tampered))
    identity = ExamCoordinateIdentity("unrelated maker", "unrelated model", 1)
    custom = _empty_custom()
    with pytest.raises(EquipmentProfileError):
        resolve_coordinate_leaves(identity=identity,
                                  custom=custom, bundled=patched)


def test_resolver_revalidates_default_vocabulary_even_with_matching_hash() -> None:
    from dataclasses import replace

    bundled = _bundled()
    assert bundled.default is not None
    profile = bundled.default.profile
    assert profile.coordinates is not None
    direction = profile.coordinates.translation_direction
    assert direction is not None
    malformed = replace(profile, coordinates=replace(profile.coordinates,
                        translation_direction=replace(direction, x="invalid-sign")))
    default = replace(bundled.default, profile=malformed, profile_hash=profile_hash(malformed))
    patched = replace(bundled, default=default)
    identity = ExamCoordinateIdentity("unknown maker", "unknown model", 1)
    custom = _empty_custom()
    with pytest.raises(EquipmentProfileError):
        resolve_coordinate_leaves(identity=identity,
                                  custom=custom, bundled=patched)


# ---------------------------------------------------------------------------
# Public preparation seam: prepare once, resolve per exam without recompiling
# ---------------------------------------------------------------------------


def test_resolve_with_prepared_matches_direct_resolution() -> None:
    custom = _custom([_profile("seamed", coordinates={"swap_lateral_longitudinal": True})])
    bundled = _bundled()
    identity = ExamCoordinateIdentity(manufacturer="Acme Imaging", model="DemoScope 2000", event_count=2)
    direct = resolve_coordinate_leaves(identity=identity, custom=custom, bundled=bundled)
    prepared = resolve_with_prepared(
        identity=identity,
        custom=prepare_custom_context(custom),
        bundled=prepare_bundled_context(bundled),
    )
    assert prepared == direct


def test_prepare_custom_context_rejects_non_index() -> None:
    with pytest.raises(EquipmentProfileError) as excinfo:
        prepare_custom_context("not-an-index")
    assert excinfo.value.code is ProfileErrorCode.INVALID_TYPE


def test_prepare_bundled_context_rejects_non_set() -> None:
    with pytest.raises(EquipmentProfileError) as excinfo:
        prepare_bundled_context("not-a-set")
    assert excinfo.value.code is ProfileErrorCode.INVALID_TYPE


def test_resolve_with_prepared_rejects_wrong_context_types() -> None:
    custom = prepare_custom_context(_empty_custom())
    bundled = prepare_bundled_context(_bundled())
    identity = ExamCoordinateIdentity(manufacturer="A", model="B", event_count=1)
    with pytest.raises(EquipmentProfileError) as excinfo:
        resolve_with_prepared(identity=identity, custom="nope", bundled=bundled)  # type: ignore[arg-type]
    assert excinfo.value.code is ProfileErrorCode.INVALID_TYPE
    with pytest.raises(EquipmentProfileError) as excinfo:
        resolve_with_prepared(identity=identity, custom=custom, bundled="nope")  # type: ignore[arg-type]
    assert excinfo.value.code is ProfileErrorCode.INVALID_TYPE


def test_prepared_contexts_are_immutable_and_counted() -> None:
    from dataclasses import FrozenInstanceError

    custom = prepare_custom_context(_empty_custom())
    bundled = prepare_bundled_context(_bundled())
    assert repr(custom) == "PreparedCustomContext(profiles=0, lead_kind='')"
    assert "profiles=3" in repr(bundled)
    assert "has_default=True" in repr(bundled)
    with pytest.raises(FrozenInstanceError):
        custom.lead_kind = "json"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Forged prepared contexts fail closed at construction, not at resolve time
# ---------------------------------------------------------------------------


def test_forged_custom_context_with_dangling_table_rejected() -> None:
    import dataclasses

    from guiskindose.equipment_profiles import prepare_custom_context

    prepared = prepare_custom_context(_empty_custom())
    forged = dataclasses.replace(prepared, entries=prepared.entries)
    assert forged == prepared
    custom = _custom([_profile("real", coordinates={"detector_side_length": 30.0})])
    good = prepare_custom_context(custom)
    table = good.index.coordinates
    assert len(table.keys) == 1
    bad_table = dataclasses.replace(table, keys=(("other maker", "other model"),))
    bad_index = dataclasses.replace(good.index, coordinates=bad_table)
    with pytest.raises(EquipmentProfileError) as excinfo:
        dataclasses.replace(good, index=bad_index)
    assert excinfo.value.code is ProfileErrorCode.INVALID_TYPE


def test_forged_custom_context_with_raw_lead_kind_rejected() -> None:
    import dataclasses

    from guiskindose.equipment_profiles import prepare_custom_context

    good = prepare_custom_context(_empty_custom())
    with pytest.raises(EquipmentProfileError) as excinfo:
        dataclasses.replace(good, lead_kind="bogus-kind")
    assert excinfo.value.code is ProfileErrorCode.INVALID_ENUM
    with pytest.raises(EquipmentProfileError) as excinfo:
        dataclasses.replace(good, lead_kind=123)
    assert excinfo.value.code is ProfileErrorCode.INVALID_ENUM


def test_forged_bundled_context_with_invalid_default_rejected() -> None:
    import dataclasses

    from guiskindose.equipment_profiles import prepare_bundled_context
    from guiskindose.equipment_profiles.indexes import IndexedProfile

    good = prepare_bundled_context(_bundled())
    bad_default = IndexedProfile(
        profile="not-a-profile",  # type: ignore[arg-type]
        source_kind="json",
        revision=None,
        profile_hash="0" * 64,
    )
    with pytest.raises(EquipmentProfileError) as excinfo:
        dataclasses.replace(good, default=bad_default)
    assert excinfo.value.code is ProfileErrorCode.INVALID_TYPE


def test_forged_bundled_context_with_list_entries_rejected() -> None:
    import dataclasses

    from guiskindose.equipment_profiles import prepare_bundled_context

    good = prepare_bundled_context(_bundled())
    with pytest.raises(EquipmentProfileError) as excinfo:
        dataclasses.replace(good, entries=list(good.entries))
    assert excinfo.value.code is ProfileErrorCode.INVALID_TYPE
