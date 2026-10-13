"""Unit tests for the local user profile store repository.

All databases live under ``tmp_path``; the real default user database is never touched. Tests cover creation
and versioning, enable/disable/delete, optimistic-concurrency races between two handles, rollback on failed
writes, snapshot stability and determinism, cross-enabled conflict validation, corruption and version
rejection without mutating the file, value-free diagnostics, and every documented bound.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from guiskindose.equipment_profiles import (
    MAX_PROFILES,
    EquipmentProfileError,
    Profile,
    ProfileErrorCode,
    ProfileStore,
    canonical_profile_dict,
    default_store_path,
    parse_json_bytes,
    parse_memory_document,
    profile_hash,
)
from guiskindose.equipment_profiles.store_types import (
    SelectedRevision,
    StoredRecord,
    StoredRevision,
    StoreSnapshot,
    store_source_hash,
)

_EXAMPLE_PATH = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "guiskindose"
    / "example_data"
    / "equipment_profiles"
    / "equipment_profile_example.json"
)


def _code(excinfo: pytest.ExceptionInfo[EquipmentProfileError]) -> ProfileErrorCode:
    return excinfo.value.code


def _example_profiles() -> tuple[Profile, ...]:
    return parse_json_bytes(_EXAMPLE_PATH.read_bytes()).profiles


def _open(path: Path) -> ProfileStore:
    return ProfileStore.open(path / "profiles.sqlite3")


def _coordinate_profile(profile_id: str = "demo-partial") -> Profile:
    return parse_memory_document(
        {
            "schema_version": 1,
            "profiles": [
                {
                    "profile_id": profile_id,
                    "manufacturer": "Acme Imaging",
                    "models": ["DemoScope 2000"],
                    "coordinates": {"detector_side_length": 40},
                }
            ],
        }
    ).profiles[0]


# ---------------------------------------------------------------------------
# Lifecycle and basic CRUD
# ---------------------------------------------------------------------------


def test_create_save_read_and_list_round_trip(tmp_path: Path) -> None:
    store = _open(tmp_path)
    saved = [store.save_new_revision(profile) for profile in _example_profiles()]

    assert [record.profile_id for record in saved] == [
        "demo-scope-2000",
        "demo-scope-wildcard",
        "demo-biplane-rows",
    ]
    assert all(record.current_revision == 1 and record.enabled is False for record in saved)

    for profile in _example_profiles():
        stored = store.read_revision(profile.profile_id)
        assert isinstance(stored, StoredRevision)
        assert stored.revision == 1
        assert stored.profile_hash == profile_hash(profile)
        assert canonical_profile_dict(stored.profile) == canonical_profile_dict(profile)

    listed = store.list_records()
    assert isinstance(listed[0], StoredRecord)
    assert [record.profile_id for record in listed] == sorted(record.profile_id for record in listed)


def test_new_revisions_version_and_keep_enablement(tmp_path: Path) -> None:
    store = _open(tmp_path)
    store.save_new_revision(_coordinate_profile())
    store.set_enabled("demo-partial", True)

    second = store.save_new_revision(_coordinate_profile(), expected_current_revision=1)
    assert second.current_revision == 2
    assert second.enabled is True
    assert second.generation == 3

    assert store.read_revision("demo-partial", 1).revision == 1
    assert store.read_revision("demo-partial", 2).revision == 2
    assert store.read_revision("demo-partial").revision == 2


def test_enable_disable_delete(tmp_path: Path) -> None:
    store = _open(tmp_path)
    store.save_new_revision(_coordinate_profile())

    assert store.set_enabled("demo-partial", True).enabled is True
    assert store.set_enabled("demo-partial", False).enabled is False

    store.delete_record("demo-partial")
    with pytest.raises(EquipmentProfileError) as excinfo:
        store.read_revision("demo-partial")
    assert _code(excinfo) is ProfileErrorCode.STORE_NOT_FOUND
    assert store.list_records() == ()
    assert store.selected_snapshot().profiles == ()


def test_missing_ids_fail_closed(tmp_path: Path) -> None:
    store = _open(tmp_path)
    with pytest.raises(EquipmentProfileError) as excinfo:
        store.read_revision("no-such-profile")
    assert _code(excinfo) is ProfileErrorCode.STORE_NOT_FOUND

    with pytest.raises(EquipmentProfileError) as excinfo:
        store.set_enabled("no-such-profile", True)
    assert _code(excinfo) is ProfileErrorCode.STORE_NOT_FOUND

    with pytest.raises(EquipmentProfileError) as excinfo:
        store.delete_record("no-such-profile")
    assert _code(excinfo) is ProfileErrorCode.STORE_NOT_FOUND

    store.save_new_revision(_coordinate_profile())
    with pytest.raises(EquipmentProfileError) as excinfo:
        store.read_revision("demo-partial", 99)
    assert _code(excinfo) is ProfileErrorCode.STORE_NOT_FOUND


def test_uninitialized_handle_is_unavailable(tmp_path: Path) -> None:
    store = ProfileStore(tmp_path / "never-initialized.sqlite3")
    with pytest.raises(EquipmentProfileError) as excinfo:
        store.list_records()
    assert _code(excinfo) is ProfileErrorCode.STORE_UNAVAILABLE
    assert not (tmp_path / "never-initialized.sqlite3").exists()


def test_empty_enabled_store_yields_a_valid_empty_snapshot(tmp_path: Path) -> None:
    store = _open(tmp_path)
    store.save_new_revision(_coordinate_profile())

    snapshot = store.selected_snapshot()
    assert isinstance(snapshot, StoreSnapshot)
    assert snapshot.profiles == ()
    assert snapshot.selected == ()
    assert snapshot.logical_rows == 0
    assert snapshot.source_kind == "store"
    assert len(snapshot.source_hash) == 64


def test_saving_starts_disabled_and_unsupported_capabilities_persist_without_activation(
    tmp_path: Path,
) -> None:
    """Aliases, wildcards, and transmission rows may be stored; the store never activates or applies them."""
    store = _open(tmp_path)
    for profile in _example_profiles():
        record = store.save_new_revision(profile)
        assert record.enabled is False

    wildcard = store.read_revision("demo-scope-wildcard")
    assert wildcard.profile.models == ("*",)
    assert len(store.read_revision("demo-scope-2000").profile.transmission) == 3

    store.set_enabled("demo-scope-wildcard", True)
    snapshot = store.selected_snapshot()
    assert [profile.profile_id for profile in snapshot.profiles] == ["demo-scope-wildcard"]


# ---------------------------------------------------------------------------
# Optimistic concurrency and rollback
# ---------------------------------------------------------------------------


def test_save_revision_cas_race_between_two_handles(tmp_path: Path) -> None:
    first = _open(tmp_path)
    second = _open(tmp_path)
    first.save_new_revision(_coordinate_profile())

    updated = second.save_new_revision(_coordinate_profile(), expected_current_revision=1)
    assert updated.current_revision == 2
    stale = _coordinate_profile()
    with pytest.raises(EquipmentProfileError) as excinfo:
        first.save_new_revision(stale, expected_current_revision=1)
    assert _code(excinfo) is ProfileErrorCode.STORE_CONFLICT

    revisions = {record.current_revision for record in first.list_records()}
    assert revisions == {2}


def test_save_on_existing_record_requires_expected_revision(tmp_path: Path) -> None:
    """Updating without ``expected_current_revision`` fails even when the caller is not stale."""
    store = _open(tmp_path)
    store.save_new_revision(_coordinate_profile())

    update = _coordinate_profile()
    with pytest.raises(EquipmentProfileError) as excinfo:
        store.save_new_revision(update)
    assert _code(excinfo) is ProfileErrorCode.STORE_CONFLICT

    record = store.save_new_revision(_coordinate_profile(), expected_current_revision=1)
    assert record.current_revision == 2
    assert record.generation == 2


def test_generation_advances_on_every_mutation_and_survives_recreate(tmp_path: Path) -> None:
    """Delete/recreate continues generation and revision monotonically: no ABA reuse."""
    store = _open(tmp_path)
    first = store.save_new_revision(_coordinate_profile())
    assert (first.generation, first.current_revision) == (1, 1)

    enabled = store.set_enabled("demo-partial", True)
    assert enabled.generation == 2
    assert enabled.current_revision == 1

    store.delete_record("demo-partial", expected_current_revision=1)
    recreated = store.save_new_revision(_coordinate_profile())
    assert recreated.generation == 3
    assert recreated.current_revision == 2
    assert recreated.enabled is False

    with pytest.raises(EquipmentProfileError) as excinfo:
        store.set_enabled("demo-partial", True, expected_current_revision=1)
    assert _code(excinfo) is ProfileErrorCode.STORE_CONFLICT


def test_enable_cas_race_between_two_handles(tmp_path: Path) -> None:
    first = _open(tmp_path)
    second = _open(tmp_path)
    first.save_new_revision(_coordinate_profile())

    second.save_new_revision(_coordinate_profile(), expected_current_revision=1)
    with pytest.raises(EquipmentProfileError) as excinfo:
        first.set_enabled("demo-partial", True, expected_current_revision=1)
    assert _code(excinfo) is ProfileErrorCode.STORE_CONFLICT
    assert first.list_records()[0].enabled is False


def test_failed_save_leaves_no_partial_state(tmp_path: Path) -> None:
    store = _open(tmp_path)
    store.save_new_revision(_coordinate_profile())

    bad = Profile(
        profile_id="demo-partial",
        manufacturer="Acme Imaging",
        models=("DemoScope 2000",),
        coordinates=None,
        transmission=(),
    )
    # A hand-built profile with no domain content cannot round-trip.
    with pytest.raises(EquipmentProfileError):
        store.save_new_revision(bad)

    assert store.read_revision("demo-partial").revision == 1
    assert len(store.list_records()) == 1


def test_delete_cas_and_missing_revision_arguments(tmp_path: Path) -> None:
    store = _open(tmp_path)
    store.save_new_revision(_coordinate_profile())
    store.save_new_revision(_coordinate_profile(), expected_current_revision=1)

    for bad in (True, 0, -1, "2"):
        with pytest.raises(EquipmentProfileError) as excinfo:
            store.delete_record("demo-partial", expected_current_revision=bad)  # type: ignore[arg-type]
        assert _code(excinfo) is ProfileErrorCode.VALUE_OUT_OF_RANGE

    with pytest.raises(EquipmentProfileError) as excinfo:
        store.delete_record("demo-partial", expected_current_revision=1)
    assert _code(excinfo) is ProfileErrorCode.STORE_CONFLICT

    store.delete_record("demo-partial", expected_current_revision=2)
    with pytest.raises(EquipmentProfileError) as excinfo:
        store.read_revision("demo-partial")
    assert _code(excinfo) is ProfileErrorCode.STORE_NOT_FOUND


# ---------------------------------------------------------------------------
# Snapshots
# ---------------------------------------------------------------------------


def test_snapshot_is_stable_after_later_edits(tmp_path: Path) -> None:
    store = _open(tmp_path)
    store.save_new_revision(_coordinate_profile())
    store.set_enabled("demo-partial", True)
    snapshot = store.selected_snapshot()

    store.save_new_revision(_coordinate_profile(), expected_current_revision=1)
    store.set_enabled("demo-partial", False)

    assert len(snapshot.profiles) == 1
    assert snapshot.selected[0].revision == 1
    assert snapshot.logical_rows == 2
    fresh = store.selected_snapshot()
    assert fresh.profiles == ()
    assert fresh.source_hash != snapshot.source_hash


def test_source_hash_tracks_selection_and_revisions_but_not_content_hashes(tmp_path: Path) -> None:
    store = _open(tmp_path)
    first = _example_profiles()[0]
    second = parse_memory_document(
        {
            "schema_version": 1,
            "profiles": [
                {
                    "profile_id": "other-partial",
                    "manufacturer": "Acme Imaging",
                    "models": ["Other Model"],
                    "coordinates": {"detector_side_length": 40},
                }
            ],
        }
    ).profiles[0]
    store.save_new_revision(first)
    store.save_new_revision(second)
    store.set_enabled("demo-scope-2000", True)
    store.set_enabled("other-partial", True)
    assert store.list_records()[0].generation >= 1

    both = store.selected_snapshot()
    only_first = store.selected_snapshot(["demo-scope-2000"])
    assert both.source_hash != only_first.source_hash
    assert {item.profile_id for item in both.selected} == {"demo-scope-2000", "other-partial"}

    store.save_new_revision(first, expected_current_revision=1)
    reselected = store.selected_snapshot(["demo-scope-2000"])
    assert reselected.source_hash != only_first.source_hash
    assert profile_hash(first) == profile_hash(reselected.profiles[0])

    reopened = ProfileStore.open(tmp_path / "profiles.sqlite3")
    assert reopened.selected_snapshot().source_hash == store.selected_snapshot().source_hash


def test_file_to_store_to_canonical_json_reload_keeps_hashes(tmp_path: Path) -> None:
    from guiskindose.equipment_profiles import parse_json_bytes

    store = _open(tmp_path)
    for profile in _example_profiles():
        store.save_new_revision(profile)
    snapshot = store.selected_snapshot([profile.profile_id for profile in _example_profiles()])

    reloaded = parse_json_bytes(
        json.dumps(
            {"schema_version": 1, "profiles": [profile.canonical_dict() for profile in snapshot.profiles]}
        ).encode("utf-8")
    )
    assert {profile.profile_id: profile_hash(profile) for profile in reloaded.profiles} == {
        profile.profile_id: profile_hash(profile) for profile in _example_profiles()
    }


def test_explicit_conflicting_selection_fails_closed(tmp_path: Path) -> None:
    store = _open(tmp_path)
    first = _coordinate_profile("a")
    second = _coordinate_profile("b")
    store.save_new_revision(first)
    store.save_new_revision(second)

    with pytest.raises(EquipmentProfileError) as excinfo:
        store.selected_snapshot(["a", "b"])
    assert _code(excinfo) is ProfileErrorCode.DUPLICATE_COORDINATE_CLAIM


def test_enable_runs_conflict_validation_atomically(tmp_path: Path) -> None:
    store = _open(tmp_path)
    store.save_new_revision(_coordinate_profile("a"))
    store.save_new_revision(_coordinate_profile("b"))
    store.set_enabled("a", True)

    with pytest.raises(EquipmentProfileError) as excinfo:
        store.set_enabled("b", True)
    assert _code(excinfo) is ProfileErrorCode.DUPLICATE_COORDINATE_CLAIM

    records = {record.profile_id: record.enabled for record in store.list_records()}
    assert records == {"a": True, "b": False}


def test_conflicts_across_enabled_transmission_keys(tmp_path: Path) -> None:
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

    def _tx_profile(profile_id: str) -> Profile:
        return parse_memory_document(
            {
                "schema_version": 1,
                "profiles": [
                    {
                        "profile_id": profile_id,
                        "manufacturer": "Acme Imaging",
                        "models": ["DemoScope 2000"],
                        "transmission": [dict(row)],
                    }
                ],
            }
        ).profiles[0]

    store = _open(tmp_path)
    store.save_new_revision(_tx_profile("tx-a"))
    store.save_new_revision(_tx_profile("tx-b"))
    store.set_enabled("tx-a", True)

    with pytest.raises(EquipmentProfileError) as excinfo:
        store.set_enabled("tx-b", True)
    assert _code(excinfo) is ProfileErrorCode.DUPLICATE_TRANSMISSION_KEY


def test_distinct_coordinate_and_transmission_profiles_enable_together(tmp_path: Path) -> None:
    store = _open(tmp_path)
    store.save_new_revision(_coordinate_profile("coord"))
    row_profile = parse_memory_document(
        {
            "schema_version": 1,
            "profiles": [
                {
                    "profile_id": "tx",
                    "manufacturer": "Acme Imaging",
                    "models": ["Other Model"],
                    "transmission": [
                        {
                            "device_model": "Other Model",
                            "acquisition_plane": "Single Plane",
                            "kvp_kv": 80,
                            "filtration_added_mmcu": 0.0,
                            "filtration_added_mmal": 0,
                            "k_patient_support": 0.71,
                            "evidence_status": "estimated",
                        }
                    ],
                }
            ],
        }
    ).profiles[0]
    store.save_new_revision(row_profile)
    store.set_enabled("coord", True)
    store.set_enabled("tx", True)

    snapshot = store.selected_snapshot()
    assert len(snapshot.profiles) == 2


# ---------------------------------------------------------------------------
# Corruption, versions, and foreign databases
# ---------------------------------------------------------------------------


def _file_bytes(path: Path) -> bytes:
    return path.read_bytes()


def test_rejected_databases_are_left_byte_identical(tmp_path: Path) -> None:
    target = tmp_path / "profiles.sqlite3"

    foreign = sqlite3.connect(str(target))
    foreign.execute("CREATE TABLE other_stuff(id INTEGER PRIMARY KEY)")
    foreign.commit()
    foreign.close()
    before = _file_bytes(target)
    with pytest.raises(EquipmentProfileError) as excinfo:
        ProfileStore.open(target)
    assert _code(excinfo) is ProfileErrorCode.STORE_CORRUPTION
    assert _file_bytes(target) == before

    future = sqlite3.connect(str(target))
    future.execute("PRAGMA user_version = 99")
    future.commit()
    future.close()
    before = _file_bytes(target)
    with pytest.raises(EquipmentProfileError) as excinfo:
        ProfileStore.open(target)
    assert _code(excinfo) is ProfileErrorCode.UNSUPPORTED_STORE_VERSION
    assert _file_bytes(target) == before

    target.write_bytes(b"this is not a sqlite database at all")
    with pytest.raises(EquipmentProfileError) as excinfo:
        ProfileStore.open(target)
    assert _code(excinfo) is ProfileErrorCode.STORE_CORRUPTION


def test_corrupt_schema_missing_table_is_rejected_without_mutation(tmp_path: Path) -> None:
    store = _open(tmp_path)
    store.save_new_revision(_coordinate_profile())
    target = tmp_path / "profiles.sqlite3"
    before = _file_bytes(target)

    raw = sqlite3.connect(str(target))
    raw.execute("DROP TABLE profile_revisions")
    raw.commit()
    raw.close()
    tampered = _file_bytes(target)
    assert tampered != before  # our own DROP changed the file, as expected

    with pytest.raises(EquipmentProfileError) as excinfo:
        ProfileStore.open(target)
    assert _code(excinfo) is ProfileErrorCode.STORE_CORRUPTION
    assert _file_bytes(target) == tampered  # the rejected open changed nothing further


def test_corrupt_schema_version_metadata_is_rejected(tmp_path: Path) -> None:
    store = _open(tmp_path)
    store.save_new_revision(_coordinate_profile())
    target = tmp_path / "profiles.sqlite3"

    raw = sqlite3.connect(str(target))
    raw.execute("UPDATE store_meta SET value = '7' WHERE key = 'store_schema_version'")
    raw.commit()
    raw.close()

    with pytest.raises(EquipmentProfileError) as excinfo:
        ProfileStore.open(target)
    assert _code(excinfo) is ProfileErrorCode.STORE_CORRUPTION


def test_tampered_payload_and_hash_are_rejected_on_read(tmp_path: Path) -> None:
    store = _open(tmp_path)
    store.save_new_revision(_coordinate_profile())
    target = tmp_path / "profiles.sqlite3"

    raw = sqlite3.connect(str(target))
    raw.execute("UPDATE profile_revisions SET payload_json = '{\"schema_version\": 1, \"other\": true}'")
    raw.commit()
    raw.close()
    with pytest.raises(EquipmentProfileError) as excinfo:
        store.read_revision("demo-partial")
    # Either the precise structural code or the corruption code is a closed rejection.
    assert _code(excinfo) in (
        ProfileErrorCode.UNKNOWN_FIELD,
        ProfileErrorCode.STORE_CORRUPTION,
    )
    assert excinfo.value.source_kind == "store"

    raw = sqlite3.connect(str(target))
    raw.execute("UPDATE profile_revisions SET payload_json = 'not json', profile_hash = '0' * 64")
    raw.commit()
    raw.close()
    with pytest.raises(EquipmentProfileError) as excinfo:
        store.read_revision("demo-partial")
    assert _code(excinfo) is ProfileErrorCode.STORE_CORRUPTION


def test_tampered_hash_with_valid_payload_is_rejected(tmp_path: Path) -> None:
    store = _open(tmp_path)
    store.save_new_revision(_coordinate_profile())
    target = tmp_path / "profiles.sqlite3"

    raw = sqlite3.connect(str(target))
    raw.execute("UPDATE profile_revisions SET profile_hash = 'f' * 64")
    raw.commit()
    raw.close()

    with pytest.raises(EquipmentProfileError) as excinfo:
        store.read_revision("demo-partial")
    assert _code(excinfo) is ProfileErrorCode.STORE_CORRUPTION


def test_opening_a_directory_is_unavailable(tmp_path: Path) -> None:
    target = tmp_path / "a-directory"
    target.mkdir()
    with pytest.raises(EquipmentProfileError) as excinfo:
        ProfileStore.open(target)
    assert _code(excinfo) is ProfileErrorCode.STORE_UNAVAILABLE


# ---------------------------------------------------------------------------
# Bounds
# ---------------------------------------------------------------------------


def test_selection_and_listing_bounds(tmp_path: Path) -> None:
    store = _open(tmp_path)
    store.save_new_revision(_coordinate_profile())

    with pytest.raises(EquipmentProfileError) as excinfo:
        store.selected_snapshot([f"p{i}" for i in range(MAX_PROFILES + 1)])
    assert _code(excinfo) is ProfileErrorCode.PROFILE_LIMIT_EXCEEDED

    with pytest.raises(EquipmentProfileError) as excinfo:
        store.list_records(limit=65)
    assert _code(excinfo) is ProfileErrorCode.VALUE_OUT_OF_RANGE

    for bad_limit, bad_offset in ((-1, 0), (1, -1), (True, 0), (1, True)):
        with pytest.raises(EquipmentProfileError) as excinfo:
            store.list_records(limit=bad_limit, offset=bad_offset)
        assert _code(excinfo) is ProfileErrorCode.VALUE_OUT_OF_RANGE

    assert store.list_records(limit=0) == ()
    assert [record.profile_id for record in store.list_records(limit=1, offset=0)] == ["demo-partial"]
    assert store.list_records(limit=1, offset=1) == ()

    with pytest.raises(EquipmentProfileError) as excinfo:
        store.selected_snapshot([123])  # type: ignore[list-item]
    assert _code(excinfo) is ProfileErrorCode.INVALID_PROFILE_ID

    with pytest.raises(EquipmentProfileError) as excinfo:
        store.selected_snapshot("demo-partial")  # type: ignore[arg-type]
    assert _code(excinfo) is ProfileErrorCode.INVALID_TYPE


def test_global_record_and_revision_caps(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import guiskindose.equipment_profiles.store_schema as store_module

    monkeypatch.setattr(store_module, "MAX_STORE_RECORDS", 1)
    monkeypatch.setattr(store_module, "MAX_REVISIONS_PER_PROFILE", 2)
    store = _open(tmp_path)
    store.save_new_revision(_coordinate_profile())
    store.save_new_revision(_coordinate_profile(), expected_current_revision=1)

    other = _coordinate_profile("other")
    with pytest.raises(EquipmentProfileError) as excinfo:
        store.save_new_revision(other)
    assert _code(excinfo) is ProfileErrorCode.STORE_LIMIT_EXCEEDED

    retry = _coordinate_profile()
    with pytest.raises(EquipmentProfileError) as excinfo:
        store.save_new_revision(retry, expected_current_revision=2)
    assert _code(excinfo) is ProfileErrorCode.STORE_LIMIT_EXCEEDED


def test_snapshot_aggregate_row_ceiling(tmp_path: Path) -> None:
    store = _open(tmp_path)
    rows = [
        {
            "device_model": "M",
            "acquisition_plane": "Single Plane",
            "kvp_kv": 80,
            "filtration_added_mmcu": float(index % 50),
            "filtration_added_mmal": 0,
            "k_patient_support": 0.7,
            "evidence_status": "estimated",
        }
        for index in range(200)
    ]
    names: list[str] = []
    for index in range(60):
        document = parse_memory_document(
            {
                "schema_version": 1,
                "profiles": [
                    {
                        "profile_id": f"p{index}",
                        "manufacturer": "A",
                        "models": [f"M{index}"],
                        "coordinates": {"detector_side_length": 40},
                        "transmission": [{**row, "device_model": f"M{index}"} for row in rows],
                    }
                ],
            }
        )
        profile = document.profiles[0]
        store.save_new_revision(profile)
        names.append(profile.profile_id)
    assert len(names) == 60
    with pytest.raises(EquipmentProfileError) as excinfo:
        store.selected_snapshot(names)
    assert _code(excinfo) is ProfileErrorCode.ROW_LIMIT_EXCEEDED


# ---------------------------------------------------------------------------
# Privacy and diagnostics
# ---------------------------------------------------------------------------


def test_paths_notes_and_causes_never_appear_in_diagnostics(tmp_path: Path) -> None:
    store = _open(tmp_path)
    profile = parse_memory_document(
        {
            "schema_version": 1,
            "profiles": [
                {
                    "profile_id": "secret-id-1",
                    "manufacturer": "Acme Imaging",
                    "models": ["DemoScope 2000"],
                    "provenance": {"source": "SENSITIVE-SOURCE", "notes": "SENSITIVE-NOTES"},
                    "coordinates": {"detector_side_length": 40},
                }
            ],
        }
    ).profiles[0]
    store.save_new_revision(profile)

    with pytest.raises(EquipmentProfileError) as excinfo:
        store.read_revision("missing-id")
    text = str(excinfo.value) + repr(excinfo.value)
    assert "missing-id" not in text
    assert "secret-id-1" not in text
    assert "SENSITIVE-SOURCE" not in text
    assert "SENSITIVE-NOTES" not in text
    assert str(tmp_path) not in text
    assert excinfo.value.__cause__ is None

    stored = store.read_revision("secret-id-1")
    assert "SENSITIVE-SOURCE" not in repr(stored)
    assert "SENSITIVE-NOTES" not in repr(stored)
    listed = store.list_records()[0]
    assert "secret-id-1" in repr(listed)


def test_provenance_is_retained_privately_but_hashed(tmp_path: Path) -> None:
    store = _open(tmp_path)
    profile = parse_memory_document(
        {
            "schema_version": 1,
            "profiles": [
                {
                    "profile_id": "p",
                    "manufacturer": "A",
                    "models": ["M"],
                    "provenance": {"source": "kept", "notes": "kept-too"},
                    "coordinates": {"detector_side_length": 40},
                }
            ],
        }
    ).profiles[0]
    store.save_new_revision(profile)
    stored = store.read_revision("p")

    assert stored.profile.provenance is not None
    assert stored.profile.provenance.source == "kept"
    assert stored.profile_hash == profile_hash(profile)


# ---------------------------------------------------------------------------
# Paths and defaults
# ---------------------------------------------------------------------------


def test_default_store_path_computes_without_touching_the_filesystem(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(Path, "home", classmethod(lambda _cls: tmp_path))
    path = default_store_path()

    assert path == tmp_path / ".guiskindose" / "equipment_profiles.sqlite3"
    assert not path.exists()
    assert not (tmp_path / ".guiskindose").exists()


def test_initialize_creates_parents_but_paths_never_serialize(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "deep" / "profiles.sqlite3"
    store = ProfileStore.open(target)
    snapshot = store.selected_snapshot()

    assert target.exists()
    assert "nested" not in snapshot.source_hash
    store.close()


def test_selected_revisions_are_deterministic_and_store_scoped(tmp_path: Path) -> None:
    first = _open(tmp_path)
    first.save_new_revision(_coordinate_profile())
    first.set_enabled("demo-partial", True)

    again = ProfileStore.open(tmp_path / "profiles.sqlite3")
    assert again.selected_snapshot().source_hash == first.selected_snapshot().source_hash

    other = ProfileStore.open(tmp_path / "other.sqlite3")
    other.save_new_revision(_coordinate_profile())
    other.set_enabled("demo-partial", True)
    assert other.selected_snapshot().source_hash != first.selected_snapshot().source_hash


def test_store_source_hash_wrapper_shape() -> None:

    selected = (
        SelectedRevision(profile_id="b", revision=2, profile_hash="h" * 64),
        SelectedRevision(profile_id="a", revision=1, profile_hash="0" * 64),
    )
    digest = store_source_hash("store-1", selected)
    assert digest == store_source_hash("store-1", tuple(reversed(selected)))
    assert digest != store_source_hash("store-2", selected)


# ---------------------------------------------------------------------------
# Regression tests for reviewed commit-blocking defects
# ---------------------------------------------------------------------------


def test_idempotent_enable_is_allowed(tmp_path: Path) -> None:
    """Enabling an already-enabled record succeeds without a duplicate-claim failure."""
    store = _open(tmp_path)
    store.save_new_revision(_coordinate_profile())
    first = store.set_enabled("demo-partial", True)
    second = store.set_enabled("demo-partial", True)

    assert second.enabled is True
    assert second.current_revision == first.current_revision
    assert second.generation == first.generation + 1


def test_conflicting_enabled_update_rolls_back_atomically(tmp_path: Path) -> None:
    """Saving a revision that would break the enabled set fails and changes nothing."""
    store = _open(tmp_path)
    other = parse_memory_document(
        {
            "schema_version": 1,
            "profiles": [
                {
                    "profile_id": "c",
                    "manufacturer": "Acme Imaging",
                    "models": ["Other Model"],
                    "coordinates": {"detector_side_length": 40},
                }
            ],
        }
    ).profiles[0]
    store.save_new_revision(_coordinate_profile("a"))
    store.save_new_revision(other)
    store.set_enabled("a", True)
    store.set_enabled("c", True)

    clash = parse_memory_document(
        {
            "schema_version": 1,
            "profiles": [
                {
                    "profile_id": "c",
                    "manufacturer": "Acme Imaging",
                    "models": ["DemoScope 2000"],
                    "coordinates": {"translation_offset": {"x": 1.0}},
                }
            ],
        }
    ).profiles[0]

    before = store.read_revision("c")
    with pytest.raises(EquipmentProfileError) as excinfo:
        store.save_new_revision(clash, expected_current_revision=1)
    assert _code(excinfo) is ProfileErrorCode.DUPLICATE_COORDINATE_CLAIM

    after = store.read_revision("c")
    assert (after.revision, after.profile_hash) == (before.revision, before.profile_hash)
    records = {record.profile_id: record.enabled for record in store.list_records()}
    assert records == {"a": True, "c": True}


def test_injected_failure_rolls_back_and_keeps_the_handle_usable(tmp_path: Path) -> None:
    """An unexpected exception inside a write rolls back, closes safely, and normalizes closed."""
    import guiskindose.equipment_profiles.store_writes as store_module

    store = _open(tmp_path)
    store.save_new_revision(_coordinate_profile("a"))
    store.save_new_revision(_coordinate_profile("b"))
    store.set_enabled("a", True)

    original = store_module.validate_profile_set

    def _boom(profiles: object, *, source_kind: str) -> None:
        raise RuntimeError("injected")

    store_module.validate_profile_set = _boom  # type: ignore[assignment]
    try:
        with pytest.raises(EquipmentProfileError) as excinfo:
            store.set_enabled("b", True)
        assert _code(excinfo) is ProfileErrorCode.STORE_CORRUPTION
        assert excinfo.value.__cause__ is None
    finally:
        store_module.validate_profile_set = original

    # The failed enable left no partial state: the handle closed itself safely, and a fresh handle sees
    # the pre-failure state and can keep writing.
    with pytest.raises(EquipmentProfileError) as excinfo:
        store.list_records()
    assert _code(excinfo) is ProfileErrorCode.STORE_UNAVAILABLE
    other = ProfileStore.open(tmp_path / "profiles.sqlite3")
    records = {record.profile_id: record.enabled for record in other.list_records()}
    assert records == {"a": True, "b": False}
    other.save_new_revision(_coordinate_profile("a"), expected_current_revision=1)
    assert other.read_revision("a").revision == 2


def test_injected_failure_inside_a_read_rolls_back(tmp_path: Path) -> None:
    import guiskindose.equipment_profiles.store_reads as store_module

    store = _open(tmp_path)
    store.save_new_revision(_coordinate_profile())
    store.set_enabled("demo-partial", True)

    original = store_module.validate_profile_set

    def _boom(profiles: object, *, source_kind: str) -> None:
        raise ValueError("injected-read")

    store_module.validate_profile_set = _boom  # type: ignore[assignment]
    try:
        with pytest.raises(EquipmentProfileError) as excinfo:
            store.selected_snapshot()
        assert _code(excinfo) is ProfileErrorCode.STORE_CORRUPTION
    finally:
        store_module.validate_profile_set = original

    # The failed read closed the handle safely; a fresh handle sees intact data.
    with pytest.raises(EquipmentProfileError) as excinfo:
        store.list_records()
    assert _code(excinfo) is ProfileErrorCode.STORE_UNAVAILABLE
    reopened = ProfileStore.open(tmp_path / "profiles.sqlite3")
    assert reopened.selected_snapshot().logical_rows == 2


def test_oversized_payload_is_rejected_before_it_is_fetched(tmp_path: Path) -> None:
    store = _open(tmp_path)
    store.save_new_revision(_coordinate_profile())
    target = tmp_path / "profiles.sqlite3"

    raw = sqlite3.connect(str(target))
    raw.execute(
        "UPDATE profile_revisions SET payload_json = ?",
        ("x" * (8 * 1024 * 1024 + 1),),
    )
    raw.commit()
    raw.close()

    with pytest.raises(EquipmentProfileError) as excinfo:
        store.read_revision("demo-partial")
    assert _code(excinfo) is ProfileErrorCode.STORE_CORRUPTION


def test_non_text_payload_storage_is_rejected(tmp_path: Path) -> None:
    store = _open(tmp_path)
    store.save_new_revision(_coordinate_profile())
    target = tmp_path / "profiles.sqlite3"

    raw = sqlite3.connect(str(target))
    raw.execute("UPDATE profile_revisions SET payload_json = ?", (b"\x00\x01binary",))
    raw.commit()
    raw.close()

    with pytest.raises(EquipmentProfileError) as excinfo:
        store.read_revision("demo-partial")
    assert _code(excinfo) is ProfileErrorCode.STORE_CORRUPTION


def test_deep_or_cyclic_payload_is_rejected(tmp_path: Path) -> None:
    store = _open(tmp_path)
    store.save_new_revision(_coordinate_profile())
    target = tmp_path / "profiles.sqlite3"

    deep: dict[str, object] = {}
    current: dict[str, object] = deep
    for _ in range(40):
        nested: dict[str, object] = {}
        current["child"] = nested
        current = nested
    raw = sqlite3.connect(str(target))
    raw.execute("UPDATE profile_revisions SET payload_json = ?", (json.dumps(deep),))
    raw.commit()
    raw.close()

    # The nesting budget is enforced, then normalized: a stored payload that fails anywhere means the
    # database cannot be trusted.
    with pytest.raises(EquipmentProfileError) as excinfo:
        store.read_revision("demo-partial")
    assert _code(excinfo) is ProfileErrorCode.STORE_CORRUPTION
    assert excinfo.value.source_kind == "store"
    assert excinfo.value.__cause__ is None


def test_corrupt_unicode_payload_is_rejected(tmp_path: Path) -> None:
    store = _open(tmp_path)
    store.save_new_revision(_coordinate_profile())
    target = tmp_path / "profiles.sqlite3"

    stored = store.read_revision("demo-partial")
    import json as _json

    text = _json.dumps(stored.profile.canonical_dict(), ensure_ascii=True)
    # Splice a lone-surrogate escape into stored ASCII text: encodable for SQLite, undecodable as UTF-8.
    text = text.replace("Acme Imaging", "Acme \\ud800 Imaging", 1)
    raw = sqlite3.connect(str(target))
    raw.execute("UPDATE profile_revisions SET payload_json = ?", (text,))
    raw.commit()
    raw.close()

    # The undecodable payload normalizes to a closed corruption error, never a raw codec message.
    with pytest.raises(EquipmentProfileError) as excinfo:
        store.read_revision("demo-partial")
    assert _code(excinfo) is ProfileErrorCode.STORE_CORRUPTION
    assert excinfo.value.source_kind == "store"
    assert excinfo.value.__cause__ is None


def test_stored_row_count_mismatch_is_rejected(tmp_path: Path) -> None:
    store = _open(tmp_path)
    store.save_new_revision(_coordinate_profile())
    target = tmp_path / "profiles.sqlite3"

    raw = sqlite3.connect(str(target))
    raw.execute("UPDATE profile_revisions SET logical_rows = 999999")
    raw.commit()
    raw.close()

    # The stored count disagrees with the verified payload, so the read fails closed even though the
    # content hash still matches.
    with pytest.raises(EquipmentProfileError) as excinfo:
        store.read_revision("demo-partial")
    assert _code(excinfo) is ProfileErrorCode.STORE_CORRUPTION

    # A *smaller* tampered count fails the same way: the aggregate pre-check would pass it, but the
    # post-parse recheck compares against the actual canonical payload.
    raw = sqlite3.connect(str(target))
    raw.execute("UPDATE profile_revisions SET logical_rows = 1")
    raw.commit()
    raw.close()

    with pytest.raises(EquipmentProfileError) as excinfo:
        store.read_revision("demo-partial")
    assert _code(excinfo) is ProfileErrorCode.STORE_CORRUPTION


def test_list_verifies_every_listed_payload(tmp_path: Path) -> None:
    store = _open(tmp_path)
    store.save_new_revision(_coordinate_profile("a"))
    store.save_new_revision(_coordinate_profile("b"))
    target = tmp_path / "profiles.sqlite3"

    raw = sqlite3.connect(str(target))
    raw.execute("UPDATE profile_revisions SET profile_hash = ? WHERE profile_id = 'b'", ("0" * 64,))
    raw.commit()
    raw.close()

    with pytest.raises(EquipmentProfileError) as excinfo:
        store.list_records()
    assert _code(excinfo) is ProfileErrorCode.STORE_CORRUPTION


def test_corrupt_record_metadata_types_are_rejected(tmp_path: Path) -> None:
    store = _open(tmp_path)
    store.save_new_revision(_coordinate_profile())
    target = tmp_path / "profiles.sqlite3"

    raw = sqlite3.connect(str(target))
    raw.execute("UPDATE profile_records SET current_revision = 'not-an-int' WHERE profile_id = 'demo-partial'")
    raw.commit()
    raw.close()

    with pytest.raises(EquipmentProfileError) as excinfo:
        store.list_records()
    assert _code(excinfo) is ProfileErrorCode.STORE_CORRUPTION
    assert "not-an-int" not in str(excinfo.value)


def test_non_hex_store_id_is_rejected(tmp_path: Path) -> None:
    store = _open(tmp_path)
    store.save_new_revision(_coordinate_profile())
    target = tmp_path / "profiles.sqlite3"

    raw = sqlite3.connect(str(target))
    raw.execute("UPDATE store_meta SET value = 'not-hex!!' WHERE key = 'store_id'")
    raw.commit()
    raw.close()

    with pytest.raises(EquipmentProfileError) as excinfo:
        store.selected_snapshot()
    assert _code(excinfo) is ProfileErrorCode.STORE_CORRUPTION


def test_schema_rejects_missing_keys_triggers_and_views(tmp_path: Path) -> None:
    from guiskindose.equipment_profiles import store_schema

    assert set(store_schema.schema_statements()) != set()
    store = _open(tmp_path)
    store.save_new_revision(_coordinate_profile())
    target = tmp_path / "profiles.sqlite3"

    raw = sqlite3.connect(str(target))
    raw.execute("CREATE TRIGGER sneak AFTER INSERT ON profile_records BEGIN SELECT 1; END")
    raw.commit()
    raw.close()
    with pytest.raises(EquipmentProfileError) as excinfo:
        ProfileStore.open(target)
    assert _code(excinfo) is ProfileErrorCode.STORE_CORRUPTION
    raw = sqlite3.connect(str(target))
    raw.execute("DROP TRIGGER sneak")
    raw.commit()
    raw.close()
    reopened = ProfileStore.open(target)
    records = reopened.list_records()
    reopened.close()
    assert records


def test_schema_rejects_dropped_primary_key(tmp_path: Path) -> None:
    store = _open(tmp_path)
    store.save_new_revision(_coordinate_profile())
    target = tmp_path / "profiles.sqlite3"

    raw = sqlite3.connect(str(target))
    # Rebuild profile_records without its primary key: a PK-less table with the same columns.
    raw.execute("ALTER TABLE profile_records RENAME TO profile_records_old")
    raw.execute(
        "CREATE TABLE profile_records(profile_id TEXT, enabled INTEGER, current_revision INTEGER, "
        "generation INTEGER, updated_utc TEXT)"
    )
    raw.execute(
        "INSERT INTO profile_records SELECT profile_id, enabled, current_revision, generation, updated_utc "
        "FROM profile_records_old"
    )
    raw.execute("DROP TABLE profile_records_old")
    raw.commit()
    raw.close()

    with pytest.raises(EquipmentProfileError) as excinfo:
        ProfileStore.open(target)
    assert _code(excinfo) is ProfileErrorCode.STORE_CORRUPTION


def test_duplicate_selection_ids_are_rejected(tmp_path: Path) -> None:
    store = _open(tmp_path)
    store.save_new_revision(_coordinate_profile())

    with pytest.raises(EquipmentProfileError) as excinfo:
        store.selected_snapshot(["demo-partial", "demo-partial"])
    assert _code(excinfo) is ProfileErrorCode.DUPLICATE_PROFILE_ID


def test_huge_offset_and_revision_are_rejected_before_binding(tmp_path: Path) -> None:
    store = _open(tmp_path)
    store.save_new_revision(_coordinate_profile())

    with pytest.raises(EquipmentProfileError) as excinfo:
        store.list_records(limit=10, offset=10**400)
    assert _code(excinfo) is ProfileErrorCode.VALUE_OUT_OF_RANGE
    assert excinfo.value.__cause__ is None

    with pytest.raises(EquipmentProfileError) as excinfo:
        store.read_revision("demo-partial", 10**400)  # type: ignore[arg-type]
    assert _code(excinfo) is ProfileErrorCode.VALUE_OUT_OF_RANGE


def test_nul_path_is_rejected_without_value_error(tmp_path: Path) -> None:
    with pytest.raises(EquipmentProfileError) as excinfo:
        ProfileStore.open(str(tmp_path / "x.sqlite3") + "\x00evil")
    assert _code(excinfo) is ProfileErrorCode.INVALID_TYPE
    assert excinfo.value.__cause__ is None


def test_non_profile_save_candidates_are_rejected(tmp_path: Path) -> None:
    store = _open(tmp_path)

    with pytest.raises(EquipmentProfileError) as excinfo:
        store.save_new_revision({"profile_id": "x"})  # type: ignore[arg-type]
    assert _code(excinfo) is ProfileErrorCode.INVALID_TYPE
    assert store.list_records() == ()


def test_hand_built_wrong_typed_values_are_rejected_before_serialization(tmp_path: Path) -> None:
    from guiskindose.equipment_profiles.models import Coordinates

    store = _open(tmp_path)

    bool_as_number = Profile(
        profile_id="demo-partial",
        manufacturer="Acme Imaging",
        models=("DemoScope 2000",),
        coordinates=Coordinates(detector_side_length=True),  # type: ignore[arg-type]
    )
    with pytest.raises(EquipmentProfileError) as excinfo:
        store.save_new_revision(bool_as_number)
    assert _code(excinfo) is ProfileErrorCode.INVALID_NUMBER

    number_as_bool = Profile(
        profile_id="demo-partial",
        manufacturer="Acme Imaging",
        models=("DemoScope 2000",),
        coordinates=Coordinates(swap_lateral_longitudinal=1),  # type: ignore[arg-type]
    )
    with pytest.raises(EquipmentProfileError) as excinfo:
        store.save_new_revision(number_as_bool)
    assert _code(excinfo) is ProfileErrorCode.INVALID_TYPE

    huge = Profile(
        profile_id="demo-partial",
        manufacturer="Acme Imaging",
        models=("DemoScope 2000",),
        coordinates=Coordinates(detector_side_length=10**400),
    )
    with pytest.raises(EquipmentProfileError) as excinfo:
        store.save_new_revision(huge)
    assert _code(excinfo) is ProfileErrorCode.INVALID_NUMBER
    assert store.list_records() == ()


# ---------------------------------------------------------------------------
# Regression tests for the review-fix round
# ---------------------------------------------------------------------------


def test_tampered_smaller_row_count_fails_on_list_snapshot_and_enable(tmp_path: Path) -> None:
    """A stored count smaller than the actual payload fails on every read path, not just direct reads."""
    store = _open(tmp_path)
    store.save_new_revision(_coordinate_profile())
    store.set_enabled("demo-partial", True)
    target = tmp_path / "profiles.sqlite3"

    raw = sqlite3.connect(str(target))
    raw.execute("UPDATE profile_revisions SET logical_rows = 1")
    raw.commit()
    raw.close()

    with pytest.raises(EquipmentProfileError) as excinfo:
        store.list_records()
    assert _code(excinfo) is ProfileErrorCode.STORE_CORRUPTION

    with pytest.raises(EquipmentProfileError) as excinfo:
        store.selected_snapshot()
    assert _code(excinfo) is ProfileErrorCode.STORE_CORRUPTION

    other = ProfileStore.open(target)
    with pytest.raises(EquipmentProfileError) as excinfo:
        other.set_enabled("demo-partial", False)
    assert _code(excinfo) is ProfileErrorCode.STORE_CORRUPTION


def test_multibyte_payload_byte_bound_applies_before_materialization(tmp_path: Path) -> None:
    """A payload whose character count fits but whose byte size does not is rejected before parsing."""
    store = _open(tmp_path)
    store.save_new_revision(_coordinate_profile())
    target = tmp_path / "profiles.sqlite3"

    stored = store.read_revision("demo-partial")
    import json as _json

    text = _json.dumps(stored.profile.canonical_dict(), ensure_ascii=True)
    # Pad with multibyte characters: char count stays modest while UTF-8 bytes explode.
    padding = "é" * (4 * 1024 * 1024)
    evil = text[:-1] + ', "comment": "' + padding + '"}'
    assert len(evil) < 8 * 1024 * 1024
    assert len(evil.encode("utf-8")) > 8 * 1024 * 1024
    raw = sqlite3.connect(str(target))
    raw.execute("UPDATE profile_revisions SET payload_json = ?", (evil,))
    raw.commit()
    raw.close()

    with pytest.raises(EquipmentProfileError) as excinfo:
        store.read_revision("demo-partial")
    assert _code(excinfo) is ProfileErrorCode.STORE_CORRUPTION


def test_stale_expected_generation_fails_on_enable_and_delete(tmp_path: Path) -> None:
    store = _open(tmp_path)
    store.save_new_revision(_coordinate_profile())
    first = store.set_enabled("demo-partial", True)
    assert first.generation == 2

    other = ProfileStore.open(tmp_path / "profiles.sqlite3")
    other.set_enabled("demo-partial", False)
    assert other.list_records()[0].generation == 3

    with pytest.raises(EquipmentProfileError) as excinfo:
        store.set_enabled("demo-partial", True, expected_generation=2)
    assert _code(excinfo) is ProfileErrorCode.STORE_CONFLICT

    with pytest.raises(EquipmentProfileError) as excinfo:
        store.delete_record("demo-partial", expected_generation=2)
    assert _code(excinfo) is ProfileErrorCode.STORE_CONFLICT

    # The record is untouched and still disabled at generation 3.
    record = other.list_records()[0]
    assert (record.enabled, record.generation, record.current_revision) == (False, 3, 1)


def test_nested_transaction_rejection_rolls_back_the_outer_work(tmp_path: Path) -> None:
    """A nested call refused inside outer work must roll back everything the outer work did."""

    def _nested(connection: sqlite3.Connection) -> None:
        store = ProfileStore.__new__(ProfileStore)
        store._connection = connection
        store.list_records()

    store = _open(tmp_path)
    store.save_new_revision(_coordinate_profile("keep"))
    before = store.list_records()

    def _outer(connection: sqlite3.Connection) -> None:
        connection.execute(
            "INSERT INTO profile_tombstones(profile_id, generation, next_revision) VALUES (?, 1, 1)",
            ("outer-junk",),
        )
        _nested(connection)

    with pytest.raises(EquipmentProfileError) as excinfo:
        store._write(_outer)
    assert _code(excinfo) is ProfileErrorCode.STORE_UNAVAILABLE

    # The outer INSERT was rolled back with the refused nesting: no junk tombstone remains.
    assert [record.profile_id for record in store.list_records()] == [record.profile_id for record in before]
    raw = sqlite3.connect(str(tmp_path / "profiles.sqlite3"))
    assert raw.execute("SELECT COUNT(*) FROM profile_tombstones").fetchone() == (0,)
    raw.close()


def test_missing_enabled_revision_pointer_fails_closed(tmp_path: Path) -> None:
    """An enabled record whose current revision row is absent fails; it is never silently omitted."""
    store = _open(tmp_path)
    first = parse_memory_document(
        {
            "schema_version": 1,
            "profiles": [
                {
                    "profile_id": "a",
                    "manufacturer": "Acme Imaging",
                    "models": ["ModelA"],
                    "coordinates": {"detector_side_length": 40},
                }
            ],
        }
    ).profiles[0]
    second = parse_memory_document(
        {
            "schema_version": 1,
            "profiles": [
                {
                    "profile_id": "b",
                    "manufacturer": "Acme Imaging",
                    "models": ["ModelB"],
                    "coordinates": {"detector_side_length": 40},
                }
            ],
        }
    ).profiles[0]
    store.save_new_revision(first)
    store.save_new_revision(second)
    store.set_enabled("a", True)
    store.set_enabled("b", True)

    raw = sqlite3.connect(str(tmp_path / "profiles.sqlite3"))
    raw.execute("DELETE FROM profile_revisions WHERE profile_id = 'b' AND revision = 1")
    raw.commit()
    raw.close()

    with pytest.raises(EquipmentProfileError) as excinfo:
        store.selected_snapshot()
    assert _code(excinfo) is ProfileErrorCode.STORE_CORRUPTION

    with pytest.raises(EquipmentProfileError) as excinfo:
        store.list_records()
    assert _code(excinfo) is ProfileErrorCode.STORE_CORRUPTION


def test_dropped_check_constraint_is_rejected_without_mutation(tmp_path: Path) -> None:
    """Rebuilding a table without its CHECK constraints fails schema verification."""
    store = _open(tmp_path)
    store.save_new_revision(_coordinate_profile())
    target = tmp_path / "profiles.sqlite3"
    before = target.read_bytes()

    raw = sqlite3.connect(str(target))
    raw.execute("ALTER TABLE profile_records RENAME TO profile_records_old")
    raw.execute(
        "CREATE TABLE profile_records(profile_id TEXT PRIMARY KEY NOT NULL, enabled INTEGER NOT NULL, "
        "current_revision INTEGER NOT NULL, generation INTEGER NOT NULL, updated_utc TEXT NOT NULL)"
    )
    raw.execute(
        "INSERT INTO profile_records SELECT profile_id, enabled, current_revision, generation, updated_utc "
        "FROM profile_records_old"
    )
    raw.execute("DROP TABLE profile_records_old")
    raw.commit()
    raw.close()
    tampered = target.read_bytes()
    assert tampered != before

    with pytest.raises(EquipmentProfileError) as excinfo:
        ProfileStore.open(target)
    assert _code(excinfo) is ProfileErrorCode.STORE_CORRUPTION
    assert target.read_bytes() == tampered


def test_non_utc_timestamp_is_rejected(tmp_path: Path) -> None:
    store = _open(tmp_path)
    store.save_new_revision(_coordinate_profile())
    target = tmp_path / "profiles.sqlite3"

    raw = sqlite3.connect(str(target))
    raw.execute("UPDATE profile_records SET updated_utc = '2026-10-11T05:00:00+05:00'")
    raw.commit()
    raw.close()

    with pytest.raises(EquipmentProfileError) as excinfo:
        store.list_records()
    assert _code(excinfo) is ProfileErrorCode.STORE_CORRUPTION

    raw = sqlite3.connect(str(target))
    raw.execute("UPDATE profile_revisions SET created_utc = '2026-10-11T05:00:00'")
    raw.commit()
    raw.close()

    with pytest.raises(EquipmentProfileError) as excinfo:
        store.read_revision("demo-partial")
    assert _code(excinfo) is ProfileErrorCode.STORE_CORRUPTION


def test_oversized_tombstone_identities_are_rejected(tmp_path: Path) -> None:
    """Cycling through fresh IDs cannot grow tombstones without bound; growth fails closed."""
    import guiskindose.equipment_profiles.store_schema as store_schema

    store = _open(tmp_path)
    store.save_new_revision(_coordinate_profile("victim"))
    target = tmp_path / "profiles.sqlite3"
    raw = sqlite3.connect(str(target))
    raw.executemany(
        "INSERT INTO profile_tombstones(profile_id, generation, next_revision) VALUES (?, 2, 2)",
        [(f"tomb-{index:04d}",) for index in range(store_schema.MAX_STORED_IDENTITIES - 1)],
    )
    raw.commit()
    raw.close()

    # 1 live record + 1023 tombstones: one more brand-new ID would exceed the bound.
    newcomer = _coordinate_profile("brand-new")
    with pytest.raises(EquipmentProfileError) as excinfo:
        store.save_new_revision(newcomer)
    assert _code(excinfo) is ProfileErrorCode.STORE_LIMIT_EXCEEDED

    # Deleting still works: it removes one record for every tombstone it adds, so the total is unchanged.
    store.delete_record("victim")
    assert store.list_records() == ()

    # Recreating a tombstoned ID consumes its tombstone first, so it fits and continues monotonically.
    recreated = store.save_new_revision(_coordinate_profile("victim"))
    assert (recreated.generation, recreated.current_revision) == (2, 2)

    # But a genuinely new ID still exceeds the bound.
    another = _coordinate_profile("brand-new")
    with pytest.raises(EquipmentProfileError) as excinfo:
        store.save_new_revision(another)
    assert _code(excinfo) is ProfileErrorCode.STORE_LIMIT_EXCEEDED


def test_matching_expected_generation_succeeds(tmp_path: Path) -> None:
    """A correct generation expectation allows the mutation and advances the generation."""
    store = _open(tmp_path)
    store.save_new_revision(_coordinate_profile())
    first = store.set_enabled("demo-partial", True)
    assert first.generation == 2

    second = store.set_enabled("demo-partial", False, expected_generation=2)
    assert (second.enabled, second.generation) == (False, 3)

    store.delete_record("demo-partial", expected_generation=3)
    with pytest.raises(EquipmentProfileError) as excinfo:
        store.read_revision("demo-partial")
    assert _code(excinfo) is ProfileErrorCode.STORE_NOT_FOUND


def test_malformed_stored_payload_normalizes_to_corruption(tmp_path: Path) -> None:
    """Valid JSON with the wrong shape in a payload fails as corruption, not a structural code."""
    store = _open(tmp_path)
    store.save_new_revision(_coordinate_profile())
    target = tmp_path / "profiles.sqlite3"

    raw = sqlite3.connect(str(target))
    raw.execute("UPDATE profile_revisions SET payload_json = ?", ('{"unexpected": "shape"}',))
    raw.commit()
    raw.close()

    with pytest.raises(EquipmentProfileError) as excinfo:
        store.read_revision("demo-partial")
    assert _code(excinfo) is ProfileErrorCode.STORE_CORRUPTION
    assert excinfo.value.__cause__ is None


def test_extra_metadata_key_is_rejected_without_mutation(tmp_path: Path) -> None:
    store = _open(tmp_path)
    store.save_new_revision(_coordinate_profile())
    target = tmp_path / "profiles.sqlite3"
    before = target.read_bytes()

    raw = sqlite3.connect(str(target))
    raw.execute("INSERT INTO store_meta(key, value) VALUES ('extra_key', 'extra_value')")
    raw.commit()
    raw.close()
    tampered = target.read_bytes()
    assert tampered != before

    with pytest.raises(EquipmentProfileError) as excinfo:
        ProfileStore.open(target)
    assert _code(excinfo) is ProfileErrorCode.STORE_CORRUPTION
    assert target.read_bytes() == tampered


def test_foreign_key_orphan_is_rejected_on_next_transaction(tmp_path: Path) -> None:
    """Deleting a record row directly leaves orphan revisions; the next operation fails closed."""
    store = _open(tmp_path)
    store.save_new_revision(_coordinate_profile())
    target = tmp_path / "profiles.sqlite3"

    raw = sqlite3.connect(str(target))
    raw.execute("PRAGMA foreign_keys = OFF")
    raw.execute("DELETE FROM profile_records WHERE profile_id = 'demo-partial'")
    raw.commit()
    raw.close()

    with pytest.raises(EquipmentProfileError) as excinfo:
        store.list_records()
    assert _code(excinfo) is ProfileErrorCode.STORE_CORRUPTION
