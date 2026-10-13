"""Unit tests for the compiled equipment-profile lookup indexes.

Covers the index slice only: bounded entry intake, strict source-context checks, compile-time re-validation
of hand-built profiles through the existing document boundary with claimed-hash verification, exact and
wildcard coordinate retrieval, per-plane transmission node retrieval, global conflict detection before
publishing, full-content source-order determinism, deterministic lookup cost without traversal, input/result
immutability, and value-free diagnostics and reprs. No matching precedence, inheritance, interpolation,
overlay, or evidence eligibility is implemented or exercised here.
"""

from __future__ import annotations

import itertools
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from guiskindose.equipment_profiles import (
    Coordinates,
    EquipmentProfileError,
    IndexedProfile,
    Profile,
    ProfileErrorCode,
    TransmissionRow,
    build_profile_indexes,
    parse_json_bytes,
    parse_memory_document,
    profile_hash,
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


def _profile(profile_id: str, **overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "profile_id": profile_id,
        "manufacturer": "Acme Imaging",
        "models": ["DemoScope 2000"],
    }
    base.update(overrides)
    return base


def _coordinates(**blocks: object) -> dict[str, object]:
    return dict(blocks)


def _transmission_row(device_model: str = "DemoScope 2000", plane: str = "Single Plane", **overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "device_model": device_model,
        "acquisition_plane": plane,
        "kvp_kv": 80,
        "filtration_added_mmcu": 0.0,
        "filtration_added_mmal": 0,
        "k_patient_support": 0.71,
        "evidence_status": "estimated",
        "source": "physicist",
        "date": "2026-01-01",
    }
    row.update(overrides)
    return row


def _parse(raw_profiles: list[dict[str, object]]):
    return parse_memory_document(_envelope(raw_profiles)).profiles


def _indexed(profile_id: str, raw: dict[str, object], *, source_kind: str = "memory", revision: int | None = None):
    profiles = _parse([{**_profile(profile_id), **raw}])
    profile = profiles[0]
    return IndexedProfile(
        profile=profile, source_kind=source_kind, revision=revision, profile_hash=profile_hash(profile)
    )


def _example_entries():
    document = parse_json_bytes(EXAMPLE_PATH.read_bytes())
    return [
        IndexedProfile(profile=p, source_kind="json", revision=None, profile_hash=profile_hash(p))
        for p in document.profiles
    ]


def _manual_entry(fields: dict[str, Any]) -> IndexedProfile:
    """Build an entry from a hand-constructed (never parsed) profile with a dummy claimed hash."""
    base: dict[str, Any] = {
        "profile_id": "manual-bad",
        "manufacturer": "Acme Imaging",
        "models": ("ManualScope",),
        "coordinates": Coordinates(detector_side_length=40.0),
    }
    base.update(fields)
    profile = Profile(**base)
    return IndexedProfile(profile=profile, source_kind="memory", revision=None, profile_hash="0" * 64)


# ---------------------------------------------------------------------------
# Compilation and basic retrieval
# ---------------------------------------------------------------------------


def test_packaged_example_compiles_and_resolves() -> None:
    indexes = build_profile_indexes(_example_entries())

    assert len(indexes) == 3
    assert len(indexes.profiles) == 3

    exact = indexes.coordinates.lookup_exact("Acme Imaging", "DemoScope 2000")
    assert exact is not None
    assert (exact.profile_id, exact.is_wildcard, exact.via_alias) == ("demo-scope-2000", False, False)
    assert exact.source_kind == "json"
    assert exact.revision is None

    wildcard = indexes.coordinates.lookup_wildcard("Acme Imaging")
    assert wildcard is not None
    assert (wildcard.profile_id, wildcard.is_wildcard) == ("demo-scope-wildcard", True)

    assert indexes.coordinates.lookup_exact("Unknown Maker", "Unknown Model") is None
    assert indexes.coordinates.lookup_wildcard("Unknown Maker") is None

    nodes = indexes.transmission.nodes_for("DemoScope 2000", "Single Plane")
    assert [node.row.kvp_kv for node in nodes] == [80, 100, 120]
    assert all(node.profile_id == "demo-scope-2000" for node in nodes)
    assert indexes.transmission.nodes_for("DemoScope 2000", "Plane A") == ()
    assert indexes.transmission.nodes_for("Unknown Model", "Single Plane") == ()


def test_alias_spellings_resolve_with_via_alias_set() -> None:
    indexes = build_profile_indexes(_example_entries())

    claim = indexes.coordinates.lookup_exact("AcmeImaging", "DS2000")
    assert claim is not None
    assert claim.profile_id == "demo-scope-2000"
    assert claim.via_alias is True
    assert claim.is_wildcard is False


def test_alias_spelling_identical_to_canonical_is_not_via_alias() -> None:
    entries = [
        _indexed(
            "same-spelling",
            {"models": ["DemoScope 2000"], "model_aliases": {"DemoScope 2000": "DemoScope 2000"},
             "coordinates": _coordinates(detector_side_length=40)},
        )
    ]
    indexes = build_profile_indexes(entries)

    claim = indexes.coordinates.lookup_exact("Acme Imaging", "DemoScope 2000")
    assert claim is not None
    assert claim.via_alias is False


def test_manufacturer_alias_slot_resolves() -> None:
    indexes = build_profile_indexes(_example_entries())

    claim = indexes.coordinates.lookup_exact("AcmeImaging", "DemoScope 2000")
    assert claim is not None
    assert claim.profile_id == "demo-scope-2000"
    assert claim.via_alias is True


def test_raw_rdsr_spellings_normalize_on_entry() -> None:
    indexes = build_profile_indexes(_example_entries())

    claim = indexes.coordinates.lookup_exact("ACME  imaging", "demoscope-2000")
    assert claim is not None
    assert claim.profile_id == "demo-scope-2000"


def test_literal_plane_is_retained_verbatim() -> None:
    indexes = build_profile_indexes(_example_entries())

    assert len(indexes.transmission.nodes_for("DemoScope Biplane 4000", "Plane A")) == 1
    assert len(indexes.transmission.nodes_for("DemoScope Biplane 4000", "Plane B")) == 1
    # Plane names are literal: a differently-cased plane is a different (absent) key.
    assert indexes.transmission.nodes_for("DemoScope Biplane 4000", "plane a") == ()


def test_transmission_only_and_coordinate_only_profiles_share_identity() -> None:
    coord = _indexed("coord-only", {"coordinates": _coordinates(detector_side_length=40)})
    tx = _indexed(
        "tx-only",
        {"transmission": [_transmission_row()]},
    )
    indexes = build_profile_indexes([coord, tx])

    assert len(indexes) == 2
    claim = indexes.coordinates.lookup_exact("Acme Imaging", "DemoScope 2000")
    assert claim is not None
    assert claim.profile_id == "coord-only"
    assert len(indexes.transmission.nodes_for("DemoScope 2000", "Single Plane")) == 1


def test_source_kind_revision_and_hash_context_is_preserved() -> None:
    entries = _example_entries()
    stamped = [
        IndexedProfile(profile=e.profile, source_kind="store", revision=7, profile_hash=e.profile_hash)
        for e in entries
    ]
    indexes = build_profile_indexes(stamped)

    claim = indexes.coordinates.lookup_exact("Acme Imaging", "DemoScope 2000")
    assert claim is not None
    assert (claim.source_kind, claim.revision, claim.profile_hash) == (
        "store",
        7,
        stamped[0].profile_hash,
    )
    node = indexes.transmission.nodes_for("DemoScope 2000", "Single Plane")[0]
    assert (node.source_kind, node.revision) == ("store", 7)


def test_valid_hand_built_profile_compiles() -> None:
    """A hand-constructed profile with exact immutable types and a correct hash compiles."""
    profile = Profile(
        profile_id="manual-ok",
        manufacturer="Acme Imaging",
        models=("ManualScope",),
        coordinates=Coordinates(detector_side_length=40.0),
    )
    entry = IndexedProfile(
        profile=profile, source_kind="memory", revision=None, profile_hash=profile_hash(profile)
    )
    indexes = build_profile_indexes([entry])

    claim = indexes.coordinates.lookup_exact("Acme Imaging", "ManualScope")
    assert claim is not None
    assert claim.profile_id == "manual-ok"


# ---------------------------------------------------------------------------
# Bounded entry intake
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad", ["memory", b"memory", None, 42, {"profiles": []}, (e for e in [])])
def test_non_sequence_entries_rejected(bad: Any) -> None:
    """Strings, bytes, mappings, one-shot iterables, and non-containers are not sequences."""
    with pytest.raises(EquipmentProfileError) as excinfo:
        build_profile_indexes(bad)
    assert excinfo.value.code is ProfileErrorCode.INVALID_TYPE


def test_over_profile_count_fails_before_copy() -> None:
    entry = _indexed("one", {"coordinates": _coordinates(detector_side_length=40)})
    with pytest.raises(EquipmentProfileError) as excinfo:
        build_profile_indexes([entry] * 65)
    assert excinfo.value.code is ProfileErrorCode.PROFILE_LIMIT_EXCEEDED


def test_lying_length_cannot_force_unbounded_copy() -> None:
    """A sequence whose length lies is still capped by bounded materialization."""
    entry = _indexed("one", {"coordinates": _coordinates(detector_side_length=40)})

    class _Lying(Sequence):
        def __len__(self) -> int:
            return 1

        def __getitem__(self, index: Any) -> Any:
            if isinstance(index, slice):
                return [entry] * 70
            if index < 70:
                return entry
            raise IndexError(index)

    lying = _Lying()  # type: ignore[arg-type]
    with pytest.raises(EquipmentProfileError) as excinfo:
        build_profile_indexes(lying)
    assert excinfo.value.code is ProfileErrorCode.PROFILE_LIMIT_EXCEEDED


def test_aggregate_rows_bound_before_expansion() -> None:
    """Six profiles of 2000 rows each exceed the aggregate ceiling before any claim is expanded."""
    base = _parse(
        [{"profile_id": "base", "manufacturer": "Acme", "models": ["Base"],
          "transmission": [_transmission_row(device_model="Base")]}]
    )[0]
    entries = []
    for index in range(6):
        model = f"OverRowsModel{index}"
        rows = tuple(
            TransmissionRow(
                device_model=model,
                acquisition_plane="Single Plane",
                kvp_kv=float((slot % 200) + 1),
                filtration_added_mmcu=float(slot // 200) * 0.5,
                filtration_added_mmal=0.0,
                k_patient_support=0.5,
                evidence_status="estimated",
            )
            for slot in range(2000)
        )
        profile = replace(base, profile_id=f"over-rows-{index}", models=(model,), transmission=rows)
        entries.append(
            IndexedProfile(
                profile=profile, source_kind="memory", revision=None, profile_hash=profile_hash(profile)
            )
        )
    with pytest.raises(EquipmentProfileError) as excinfo:
        build_profile_indexes(entries)
    assert excinfo.value.code is ProfileErrorCode.ROW_LIMIT_EXCEEDED


# ---------------------------------------------------------------------------
# Strict source context and claimed-hash verification
# ---------------------------------------------------------------------------


def test_entry_context_is_validated_with_closed_errors() -> None:
    profiles = _parse([{"profile_id": "ok", "manufacturer": "A", "models": ["M"],
                        "coordinates": _coordinates(detector_side_length=40)}])
    profile = profiles[0]

    with pytest.raises(EquipmentProfileError) as excinfo:
        build_profile_indexes(["not-an-entry"])  # type: ignore[list-item]
    assert excinfo.value.code is ProfileErrorCode.INVALID_TYPE

    bad_kind = IndexedProfile(profile=profile, source_kind="carrier-pigeon", revision=None,
                              profile_hash=profile_hash(profile))
    with pytest.raises(EquipmentProfileError) as excinfo:
        build_profile_indexes([bad_kind])
    assert excinfo.value.code is ProfileErrorCode.INVALID_ENUM

    bad_revision = IndexedProfile(profile=profile, source_kind="json", revision=0,
                                  profile_hash=profile_hash(profile))
    with pytest.raises(EquipmentProfileError) as excinfo:
        build_profile_indexes([bad_revision])
    assert excinfo.value.code is ProfileErrorCode.VALUE_OUT_OF_RANGE

    bad_profile = IndexedProfile(profile="not-a-profile", source_kind="json", revision=None,  # type: ignore[arg-type]
                                 profile_hash="0" * 64)
    with pytest.raises(EquipmentProfileError) as excinfo:
        build_profile_indexes([bad_profile])
    assert excinfo.value.code is ProfileErrorCode.INVALID_TYPE


def test_source_kind_must_be_an_exact_vocabulary_string() -> None:
    """Subclasses and objects with permissive equality are rejected even when they compare equal."""
    profile = _parse([{"profile_id": "ok", "manufacturer": "A", "models": ["M"],
                       "coordinates": _coordinates(detector_side_length=40)}])[0]
    claimed = profile_hash(profile)

    class _KindStr(str):
        pass

    class _AlwaysEqual:
        def __eq__(self, other: object) -> bool:
            return True

    for bad_kind in (_KindStr("json"), _AlwaysEqual()):
        entry = IndexedProfile(profile=profile, source_kind=bad_kind, revision=None,  # type: ignore[arg-type]
                               profile_hash=claimed)
        with pytest.raises(EquipmentProfileError) as excinfo:
            build_profile_indexes([entry])
        assert excinfo.value.code is ProfileErrorCode.INVALID_ENUM


@pytest.mark.parametrize("bad_revision", [True, False, 0, -3, 2**63])
def test_revision_must_be_a_bounded_positive_int(bad_revision: Any) -> None:
    profile = _parse([{"profile_id": "ok", "manufacturer": "A", "models": ["M"],
                       "coordinates": _coordinates(detector_side_length=40)}])[0]
    entry = IndexedProfile(profile=profile, source_kind="memory", revision=bad_revision,
                           profile_hash=profile_hash(profile))
    with pytest.raises(EquipmentProfileError) as excinfo:
        build_profile_indexes([entry])
    assert excinfo.value.code is ProfileErrorCode.VALUE_OUT_OF_RANGE


def test_maximum_revision_compiles() -> None:
    profile = _parse([{"profile_id": "ok", "manufacturer": "A", "models": ["M"],
                       "coordinates": _coordinates(detector_side_length=40)}])[0]
    entry = IndexedProfile(profile=profile, source_kind="memory", revision=2**63 - 1,
                           profile_hash=profile_hash(profile))
    assert len(build_profile_indexes([entry])) == 1


@pytest.mark.parametrize("bad_hash", ["0" * 63, "0" * 65, "A" * 64, "g" * 64, "", 12345, None, b"0" * 64])
def test_malformed_hash_rejected(bad_hash: Any) -> None:
    profile = _parse([{"profile_id": "ok", "manufacturer": "A", "models": ["M"],
                       "coordinates": _coordinates(detector_side_length=40)}])[0]
    entry = IndexedProfile(profile=profile, source_kind="memory", revision=None, profile_hash=bad_hash)
    with pytest.raises(EquipmentProfileError) as excinfo:
        build_profile_indexes([entry])
    assert excinfo.value.code is ProfileErrorCode.INVALID_TYPE


def test_stale_hash_fails_closed() -> None:
    """A well-formed but wrong hash means the context disagrees with the content."""
    entry = _indexed("stale", {"coordinates": _coordinates(detector_side_length=40)})
    last = entry.profile_hash[-1]
    flipped = entry.profile_hash[:-1] + ("0" if last != "0" else "1")
    bad = IndexedProfile(
        profile=entry.profile, source_kind=entry.source_kind, revision=None, profile_hash=flipped
    )
    with pytest.raises(EquipmentProfileError) as excinfo:
        build_profile_indexes([bad])
    assert excinfo.value.code is ProfileErrorCode.CONFLICTING_PROFILE_METADATA
    text = str(excinfo.value) + repr(excinfo.value)
    assert "Acme" not in text
    assert flipped not in text
    assert excinfo.value.__cause__ is None


# ---------------------------------------------------------------------------
# Hand-built profile structure gates
# ---------------------------------------------------------------------------


_MANUAL_MALFORMED_CASES: tuple[tuple[dict[str, Any], ProfileErrorCode], ...] = (
    ({"models": ["ManualScope"]}, ProfileErrorCode.INVALID_TYPE),
    ({"models": ("ManualScope", 7)}, ProfileErrorCode.INVALID_TYPE),
    ({"manufacturer": None}, ProfileErrorCode.INVALID_TYPE),
    ({"profile_id": 123}, ProfileErrorCode.INVALID_TYPE),
    ({"manufacturer_aliases": ["Ok", 5]}, ProfileErrorCode.INVALID_TYPE),
    ({"model_aliases": (("OnlyAlias",),)}, ProfileErrorCode.INVALID_TYPE),
    ({"model_aliases": ((1, "ManualScope"),)}, ProfileErrorCode.INVALID_TYPE),
    ({"model_aliases": ["OkAlias"]}, ProfileErrorCode.INVALID_TYPE),
    ({"coordinates": {"detector_side_length": 40.0}}, ProfileErrorCode.INVALID_TYPE),
    ({"coordinates": Coordinates(detector_side_length=10**400)}, ProfileErrorCode.INVALID_NUMBER),
    ({"coordinates": Coordinates(detector_side_length=True)}, ProfileErrorCode.INVALID_NUMBER),
    ({"coordinates": Coordinates(swap_lateral_longitudinal=1)},  # type: ignore[arg-type]
     ProfileErrorCode.INVALID_TYPE),
    ({"provenance": {"source": "x"}}, ProfileErrorCode.INVALID_TYPE),
    ({"promote_coordinate_wildcard": "yes"}, ProfileErrorCode.INVALID_TYPE),
    ({"transmission": ("not-a-row",)}, ProfileErrorCode.INVALID_TYPE),
)


@pytest.mark.parametrize(("fields", "code"), _MANUAL_MALFORMED_CASES)
def test_manual_malformed_profiles_rejected(fields: dict[str, Any], code: ProfileErrorCode) -> None:
    entries = [_manual_entry(fields)]
    with pytest.raises(EquipmentProfileError) as excinfo:
        build_profile_indexes(entries)
    assert excinfo.value.code is code


def test_manual_mutable_transmission_rejected() -> None:
    """A list holding a valid row is still rejected: transmission must be a tuple."""
    tx_profile = _parse([{"profile_id": "tx-base", "manufacturer": "Acme", "models": ["TxBase"],
                          "transmission": [_transmission_row(device_model="TxBase")]}])[0]
    real_row = tx_profile.transmission[0]
    entries = [_manual_entry({"coordinates": None, "models": ("TxBase",), "transmission": [real_row]})]
    with pytest.raises(EquipmentProfileError) as excinfo:
        build_profile_indexes(entries)
    assert excinfo.value.code is ProfileErrorCode.INVALID_TYPE


def test_manual_unresolvable_alias_target_rejected() -> None:
    """A well-typed but dangling alias target fails with the boundary's usual code on re-parse."""
    entries = [_manual_entry({"model_aliases": (("OkAlias", "Missing"),)})]
    with pytest.raises(EquipmentProfileError) as excinfo:
        build_profile_indexes(entries)
    assert excinfo.value.code is ProfileErrorCode.ALIAS_TARGET_MISMATCH


def test_manual_empty_domain_rejected() -> None:
    """A well-typed profile with neither domain fails with the boundary's usual code on re-parse."""
    entries = [_manual_entry({"coordinates": None})]
    with pytest.raises(EquipmentProfileError) as excinfo:
        build_profile_indexes(entries)
    assert excinfo.value.code is ProfileErrorCode.EMPTY_DOMAIN


# ---------------------------------------------------------------------------
# Conflicts fail closed before publishing
# ---------------------------------------------------------------------------


def test_duplicate_coordinate_claims_fail_closed() -> None:
    first = _indexed("first", {"coordinates": _coordinates(detector_side_length=40)})
    second = _indexed("second", {"coordinates": _coordinates(detector_side_length=50)})
    with pytest.raises(EquipmentProfileError) as excinfo:
        build_profile_indexes([first, second])
    assert excinfo.value.code is ProfileErrorCode.DUPLICATE_COORDINATE_CLAIM


def test_duplicate_claims_fail_even_when_identical() -> None:
    first = _indexed("first", {"coordinates": _coordinates(detector_side_length=40)})
    second = _indexed("second", {"coordinates": _coordinates(detector_side_length=40)})
    with pytest.raises(EquipmentProfileError) as excinfo:
        build_profile_indexes([first, second])
    assert excinfo.value.code is ProfileErrorCode.DUPLICATE_COORDINATE_CLAIM


def test_duplicate_profile_ids_fail_closed() -> None:
    first = _indexed("same-id", {"coordinates": _coordinates(detector_side_length=40)})
    second = _indexed("same-id", {"coordinates": _coordinates(swap_lateral_longitudinal=True)})
    with pytest.raises(EquipmentProfileError) as excinfo:
        build_profile_indexes([first, second])
    assert excinfo.value.code is ProfileErrorCode.DUPLICATE_PROFILE_ID


def test_alias_collisions_fail_closed() -> None:
    first = _indexed(
        "first",
        {"models": ["ModelA"], "model_aliases": ["Shared"], "coordinates": _coordinates(detector_side_length=40)},
    )
    second = _indexed(
        "second",
        {"models": ["ModelB"], "model_aliases": {"Shared": "ModelB"},
         "coordinates": _coordinates(detector_side_length=40)},
    )
    with pytest.raises(EquipmentProfileError) as excinfo:
        build_profile_indexes([first, second])
    assert excinfo.value.code is ProfileErrorCode.DUPLICATE_COORDINATE_CLAIM


def test_wildcard_collisions_fail_closed() -> None:
    first = _indexed(
        "wild-a",
        {"models": ["*"], "coordinates": _coordinates(translation_offset={"z": -1.0})},
    )
    second = _indexed(
        "wild-b",
        {"models": ["*"], "coordinates": _coordinates(translation_offset={"z": -2.0})},
    )
    with pytest.raises(EquipmentProfileError) as excinfo:
        build_profile_indexes([first, second])
    assert excinfo.value.code is ProfileErrorCode.DUPLICATE_COORDINATE_CLAIM


def test_duplicate_transmission_keys_fail_closed() -> None:
    first = _indexed("first", {"transmission": [_transmission_row()]})
    second = _indexed("second", {"transmission": [_transmission_row(device_model="DemoScope 2000")]})
    with pytest.raises(EquipmentProfileError) as excinfo:
        build_profile_indexes([first, second])
    assert excinfo.value.code is ProfileErrorCode.DUPLICATE_TRANSMISSION_KEY


def test_conflict_errors_carry_no_user_data() -> None:
    first = _indexed("first", {"coordinates": _coordinates(detector_side_length=40)})
    second = _indexed("second", {"coordinates": _coordinates(detector_side_length=40)})
    with pytest.raises(EquipmentProfileError) as excinfo:
        build_profile_indexes([first, second])
    text = str(excinfo.value) + repr(excinfo.value)
    assert "Acme" not in text
    assert "DemoScope" not in text
    assert excinfo.value.__cause__ is None


def test_conflict_diagnostic_follows_the_lead_entry_only() -> None:
    """The conflict content is order-independent; only the diagnostic source kind follows the lead entry."""
    mem = _indexed("dup-a", {"coordinates": _coordinates(detector_side_length=40)}, source_kind="memory")
    store = _indexed(
        "dup-b", {"coordinates": _coordinates(detector_side_length=40)}, source_kind="store", revision=3
    )
    with pytest.raises(EquipmentProfileError) as first:
        build_profile_indexes([mem, store])
    with pytest.raises(EquipmentProfileError) as second:
        build_profile_indexes([store, mem])
    assert first.value.code is second.value.code is ProfileErrorCode.DUPLICATE_COORDINATE_CLAIM
    assert first.value.source_kind == "memory"
    assert second.value.source_kind == "store"


# ---------------------------------------------------------------------------
# Determinism, immutability, and lookup cost
# ---------------------------------------------------------------------------


def test_every_permutation_compiles_to_identical_content() -> None:
    """Full compiled equality — claims, node groups, and profiles — for every source order."""
    entries = _example_entries()
    expected = build_profile_indexes(entries)
    for order in itertools.permutations(entries):
        assert build_profile_indexes(list(order)) == expected


def test_inputs_and_results_are_immutable() -> None:
    from dataclasses import FrozenInstanceError

    entries = _example_entries()
    indexes = build_profile_indexes(entries)

    with pytest.raises(FrozenInstanceError):
        indexes.coordinates.keys = ()  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        entries[0].revision = 5  # type: ignore[misc]
    assert indexes.coordinates.lookup_exact("Acme Imaging", "DemoScope 2000") is not None


def test_event_lookup_never_touches_profiles() -> None:
    """Lookups bisect the sorted key tables, so they resolve identically with no profiles attached."""
    indexes = build_profile_indexes(_example_entries())
    bare_coordinates = replace(indexes.coordinates, profiles=())
    bare_transmission = replace(indexes.transmission, profiles=())

    assert list(bare_coordinates.keys) == sorted(bare_coordinates.keys)
    assert list(bare_transmission.keys) == sorted(bare_transmission.keys)

    claim = bare_coordinates.lookup_exact("Acme Imaging", "DemoScope 2000")
    assert claim == indexes.coordinates.lookup_exact("Acme Imaging", "DemoScope 2000")
    assert bare_coordinates.lookup_wildcard("Acme Imaging") == indexes.coordinates.lookup_wildcard(
        "Acme Imaging"
    )
    assert bare_coordinates.lookup_exact("No Such Maker", "No Such Model") is None

    nodes = bare_transmission.nodes_for("DemoScope 2000", "Single Plane")
    assert nodes == indexes.transmission.nodes_for("DemoScope 2000", "Single Plane")
    assert len(nodes) == 3
    assert bare_transmission.nodes_for("No Such Model", "Single Plane") == ()


def test_empty_index_is_valid() -> None:
    indexes = build_profile_indexes([])
    assert len(indexes) == 0
    assert indexes.coordinates.lookup_exact("Acme Imaging", "DemoScope 2000") is None
    assert indexes.transmission.nodes_for("DemoScope 2000", "Single Plane") == ()


# ---------------------------------------------------------------------------
# Value-free reprs
# ---------------------------------------------------------------------------


def test_all_public_reprs_are_value_free() -> None:
    """Every public repr is probed with sentinel identity, provenance, and row text."""
    profile = _parse(
        [{
            "profile_id": "sentinel-zz",
            "manufacturer": "Sentinel Maker ZZ",
            "models": ["Sentinel Model ZZ"],
            "provenance": {"source": "Sentinel Source ZZ", "notes": "Sentinel Notes ZZ"},
            "coordinates": _coordinates(detector_side_length=40),
            "transmission": [
                _transmission_row(
                    device_model="Sentinel Model ZZ",
                    source="Sentinel RowSource ZZ",
                    comment="Sentinel Comment ZZ",
                )
            ],
        }]
    )[0]
    entry = IndexedProfile(
        profile=profile, source_kind="memory", revision=None, profile_hash=profile_hash(profile)
    )
    indexes = build_profile_indexes([entry])
    claim = indexes.coordinates.lookup_exact("Sentinel Maker ZZ", "Sentinel Model ZZ")
    assert claim is not None
    nodes = indexes.transmission.nodes_for("Sentinel Model ZZ", "Single Plane")
    assert len(nodes) == 1

    text = (
        repr(entry)
        + repr(indexes)
        + repr(indexes.coordinates)
        + repr(claim)
        + repr(indexes.transmission)
        + repr(nodes[0])
    )
    for sentinel in (
        "sentinel-zz",
        "Sentinel Maker ZZ",
        "Sentinel Model ZZ",
        "Sentinel Source ZZ",
        "Sentinel Notes ZZ",
        "Sentinel RowSource ZZ",
        "Sentinel Comment ZZ",
        "Single Plane",
    ):
        assert sentinel not in text, sentinel


@pytest.mark.parametrize("field,count", [("models", 33), ("manufacturer_aliases", 17), ("model_aliases", 17), ("transmission", 2001)])
def test_hand_built_collections_rejected_before_serialization(field: str, count: int, monkeypatch: pytest.MonkeyPatch) -> None:
    from dataclasses import replace

    import guiskindose.equipment_profiles.indexes as module

    entry = _example_entries()[0]
    items = tuple(("alias", "model") for _ in range(count)) if field == "model_aliases" else ("oversized",) * count
    malformed = replace(entry, profile=replace(entry.profile, **{field: items}))

    def must_not_serialize(*args: object) -> None:
        pytest.fail("oversized collection reached serialization")

    monkeypatch.setattr(module, "canonical_profile_dict", must_not_serialize)
    with pytest.raises(EquipmentProfileError):
        build_profile_indexes([malformed])


def test_hand_built_duplicate_alias_pair_cannot_disappear() -> None:
    from dataclasses import replace

    entry = _example_entries()[0]
    pair = ("duplicate-alias", entry.profile.models[0])
    malformed = replace(entry, profile=replace(entry.profile, model_aliases=(pair, pair)))
    with pytest.raises(EquipmentProfileError) as caught:
        build_profile_indexes([malformed])
    assert caught.value.code is ProfileErrorCode.DUPLICATE_JSON_KEY
