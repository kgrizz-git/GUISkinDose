"""Tests for frozen multi-source equipment-profile session assembly and resolution.

Covers: exact file-bytes source hashes, JSON/CSV equality, file mutation after
load, memory determinism, store revision/hash provenance with save/delete
after snapshot, multi-kind conflicts in both orders, bounds before copying,
capability-gate publication rollback, empty sessions, per-exam store context,
repr/provenance privacy, SPEC §8 path handling, XLSX sheet selection, and
per-exam resolution without recompiling. No application wiring is exercised.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from guiskindose.equipment_profiles import (
    EquipmentProfileError,
    ExamCoordinateIdentity,
    FileSource,
    ProfileErrorCode,
    ProfileStore,
    active_set_hash,
    assemble_session,
    bundled_coordinate_set,
    parse_memory_document,
    prepare_bundled_context,
    profile_hash,
    resolve_with_prepared,
    source_bytes_hash,
)

EXAMPLES = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "guiskindose"
    / "example_data"
    / "equipment_profiles"
)

_FLAT_HEADER = (
    "record_type,profile_id,manufacturer,models,manufacturer_aliases,model_aliases,"
    "source,notes,field,value,device_model,acquisition_plane,kvp_kv,"
    "filtration_added_mmcu,filtration_added_mmal,k_patient_support,evidence_status,date,comment"
)


def _raw(pid, maker="Acme Imaging", model="DemoScope 2000", **overrides):
    base = {
        "profile_id": pid,
        "manufacturer": maker,
        "models": [model],
        "coordinates": {"detector_side_length": 40.0},
    }
    base.update(overrides)
    return base


def _doc(*profiles):
    return {"schema_version": 1, "profiles": list(profiles)}


def _json_file(tmp_path: Path, name: str, *profiles) -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(_doc(*profiles)), encoding="utf-8")
    return path


def _csv_text(pid, maker="Acme Imaging", model="Scope C"):
    profile_row = ["profile", pid, maker, model] + [""] * 15
    coord_row = ["coordinate", pid] + [""] * 6 + ["detector_side_length", "40.0"] + [""] * 9
    return _FLAT_HEADER + "\n" + ",".join(profile_row) + "\n" + ",".join(coord_row) + "\n"


def _tsv_text(pid, maker="Acme Imaging", model="Scope T"):
    return _csv_text(pid, maker, model).replace(",", "\t")


def _xlsx_file(tmp_path: Path, name: str, sheets: list[tuple[str, str, str]]) -> Path:
    """Write a workbook with one profile per sheet: (profile_id, maker, model)."""
    openpyxl = pytest.importorskip("openpyxl")
    from openpyxl import Workbook

    del openpyxl
    workbook = Workbook()
    for index, (pid, maker, model) in enumerate(sheets):
        sheet = workbook.active if index == 0 else workbook.create_sheet()
        assert sheet is not None
        sheet.append(_FLAT_HEADER.split(","))
        sheet.append(["profile", pid, maker, model] + [None] * 15)
        sheet.append(
            ["coordinate", pid] + [None] * 6 + ["detector_side_length", 40.0] + [None] * 9
        )
    path = tmp_path / name
    workbook.save(path)
    return path


def _bundled():
    return bundled_coordinate_set(
        json.loads((Path(__file__).resolve().parents[2] / "src" / "guiskindose" / "normalization_settings.json").read_bytes())[
            "normalization_settings"
        ]
    )


def _store_with(tmp_path: Path, *profiles):
    store = ProfileStore.open(tmp_path / "profiles.sqlite3")
    parsed = parse_memory_document(_doc(*profiles)).profiles
    for profile in parsed:
        store.save_new_revision(profile)
    return store


def _identity(maker="Acme Imaging", model="Scope A", events=3):
    return ExamCoordinateIdentity(manufacturer=maker, model=model, event_count=events)


# ---------------------------------------------------------------------------
# File sources: hashes, equality, and post-load immutability
# ---------------------------------------------------------------------------


def test_file_bytes_hash_is_exact(tmp_path: Path) -> None:
    path = _json_file(tmp_path, "a.json", _raw("ex-a", model="Scope A"))
    session = assemble_session(files=[FileSource(str(path))])
    (source,) = session.provenance.sources
    assert (source.kind, source.format) == ("file", "json")
    assert source.source_hash == source_bytes_hash(path.read_bytes())
    assert source.profile_ids == ("ex-a",)
    assert (source.profile_count, source.logical_rows) == (1, 2)


def test_json_csv_equality_same_profiles_different_bytes(tmp_path: Path) -> None:
    from guiskindose.equipment_profiles import parse_csv_bytes, parse_json_bytes

    json_path = EXAMPLES / "equipment_profile_example.json"
    csv_path = EXAMPLES / "equipment_profile_example.csv"
    json_profiles = parse_json_bytes(json_path.read_bytes()).profiles
    csv_profiles = parse_csv_bytes(csv_path.read_bytes()).profiles
    assert [profile_hash(p) for p in json_profiles] == [profile_hash(p) for p in csv_profiles]
    assert active_set_hash(json_profiles) == active_set_hash(csv_profiles)


def test_file_mutation_after_assembly_cannot_alter_session(tmp_path: Path) -> None:
    path = _json_file(tmp_path, "a.json", _raw("ex-a", model="Scope A"))
    session = assemble_session(files=[FileSource(str(path))])
    before = (session.profiles, session.active_set_hash)
    path.write_text(json.dumps(_doc(_raw("ex-a", model="Scope CHANGED"))), encoding="utf-8")
    current_state = (session.profiles, session.active_set_hash)
    assert current_state == before
    resolved = session.resolve(_identity(), _bundled())
    assert resolved.record.profile_id == "ex-a"
    fresh = assemble_session(files=[FileSource(str(path))])
    assert fresh.active_set_hash != session.active_set_hash


def test_csv_tsv_xlsx_file_kinds_recorded(tmp_path: Path) -> None:
    csv_path = tmp_path / "c.csv"
    csv_path.write_text(_csv_text("ex-c", model="Scope C"), encoding="utf-8")
    tsv_path = tmp_path / "t.tsv"
    tsv_path.write_text(_tsv_text("ex-t", model="Scope T"), encoding="utf-8")
    xlsx_path = _xlsx_file(tmp_path, "x.xlsx", [("ex-x", "Acme Imaging", "Scope X")])
    session = assemble_session(
        files=[FileSource(str(csv_path)), FileSource(str(tsv_path)), FileSource(str(xlsx_path))]
    )
    assert [source.format for source in session.provenance.sources] == ["csv", "tsv", "xlsx"]
    assert [source.profile_ids for source in session.provenance.sources] == [
        ("ex-c",),
        ("ex-t",),
        ("ex-x",),
    ]
    resolved = session.resolve(_identity(model="Scope X"), _bundled())
    assert (resolved.record.source, resolved.record.profile_id) == ("custom", "ex-x")


def test_xlsx_sheet_selection_uses_integer_semantics(tmp_path: Path) -> None:
    path = _xlsx_file(
        tmp_path, "two.xlsx", [("ex-x0", "Acme Imaging", "Scope X0"), ("ex-x1", "Acme Imaging", "Scope X1")]
    )
    first = assemble_session(files=[FileSource(str(path), sheet=0)])
    assert first.provenance.sources[0].profile_ids == ("ex-x0",)
    second = assemble_session(files=[FileSource(str(path), sheet=1)])
    assert second.provenance.sources[0].profile_ids == ("ex-x1",)
    defaulted = assemble_session(files=[FileSource(str(path))])
    assert defaulted.provenance.sources[0].profile_ids == ("ex-x0",)


# ---------------------------------------------------------------------------
# Memory documents and determinism
# ---------------------------------------------------------------------------


def test_memory_documents_assemble_deterministically() -> None:
    first = assemble_session(
        documents=[_doc(_raw("ex-a", model="Scope A")), _doc(_raw("ex-b", model="Scope B"))]
    )
    second = assemble_session(
        documents=[_doc(_raw("ex-a", model="Scope A")), _doc(_raw("ex-b", model="Scope B"))]
    )
    assert first == second
    assert [p.profile_id for p in first.profiles] == ["ex-a", "ex-b"]
    assert all(source.kind == "memory" for source in first.provenance.sources)
    assert all(source.source_hash is None for source in first.provenance.sources)
    assert (first.provenance.total_profiles, first.provenance.total_rows) == (2, 4)
    assert first.provenance.active_set_hash == first.active_set_hash


# ---------------------------------------------------------------------------
# Store snapshots: revision context and post-snapshot stability
# ---------------------------------------------------------------------------


def test_store_snapshot_carries_revision_and_hash_context(tmp_path: Path) -> None:
    store = _store_with(tmp_path, _raw("ex-s", model="Scope S"))
    try:
        snapshot = store.selected_snapshot(["ex-s"])
        session = assemble_session(snapshots=[snapshot])
        (source,) = session.provenance.sources
        assert (source.kind, source.format) == ("store", None)
        assert source.source_hash == snapshot.source_hash
        assert source.revisions == (("ex-s", 1),)
        resolved = session.resolve(_identity(model="Scope S"), _bundled())
        assert (resolved.record.source, resolved.record.profile_id) == ("custom", "ex-s")
        assert (resolved.record.source_kind, resolved.record.revision) == ("store", 1)
        leaf = resolved.record.leaf("detector_side_length")
        assert leaf is not None
        assert (leaf.source_kind, leaf.revision) == ("store", 1)
    finally:
        store.close()


def test_store_save_after_snapshot_leaves_old_session_stable(tmp_path: Path) -> None:
    store = _store_with(tmp_path, _raw("ex-s", model="Scope S"))
    try:
        old = assemble_session(snapshots=[store.selected_snapshot(["ex-s"])])
        profile = parse_memory_document(_doc(_raw("ex-s", model="Scope S2"))).profiles[0]
        store.save_new_revision(profile, expected_current_revision=1)
        assert old.profiles[0].models == ("Scope S",)
        assert old.resolve(_identity(model="Scope S"), _bundled()).record.profile_id == "ex-s"
        new = assemble_session(snapshots=[store.selected_snapshot(["ex-s"])])
        assert new.profiles[0].models == ("Scope S2",)
        assert new.provenance.sources[0].revisions == (("ex-s", 2),)
    finally:
        store.close()


def test_store_delete_after_snapshot_old_stable_new_fails(tmp_path: Path) -> None:
    store = _store_with(tmp_path, _raw("ex-s", model="Scope S"))
    try:
        old = assemble_session(snapshots=[store.selected_snapshot(["ex-s"])])
        store.delete_record("ex-s")
        assert old.resolve(_identity(model="Scope S"), _bundled()).record.profile_id == "ex-s"
        try:
            refreshed = store.selected_snapshot(["ex-s"])
        except EquipmentProfileError as exc:
            assert exc.code is ProfileErrorCode.STORE_NOT_FOUND
            refreshed = None
        assert refreshed is None
    finally:
        store.close()


# ---------------------------------------------------------------------------
# Cross-kind conflicts, bounds, and the capability gate
# ---------------------------------------------------------------------------


def test_duplicate_ids_across_kinds_fail_in_both_orders(tmp_path: Path) -> None:
    path = _json_file(tmp_path, "a.json", _raw("dupe", model="Scope A"))
    first = _doc(_raw("dupe", model="Scope B"))
    source = FileSource(str(path))
    with pytest.raises(EquipmentProfileError) as memory_first:
        assemble_session(files=[source], documents=[first])
    with pytest.raises(EquipmentProfileError) as file_order_only:
        assemble_session(documents=[first], files=[source])
    assert memory_first.value.code is ProfileErrorCode.DUPLICATE_PROFILE_ID
    assert file_order_only.value.code is ProfileErrorCode.DUPLICATE_PROFILE_ID


def test_duplicate_claim_file_and_store_fails(tmp_path: Path) -> None:
    path = _json_file(tmp_path, "a.json", _raw("ex-a", model="Scope A"))
    store = _store_with(tmp_path, _raw("ex-b", model="Scope A"))
    try:
        snapshot = store.selected_snapshot(["ex-b"])
        source = FileSource(str(path))
        with pytest.raises(EquipmentProfileError) as excinfo:
            assemble_session(files=[source], snapshots=[snapshot])
        assert excinfo.value.code is ProfileErrorCode.DUPLICATE_COORDINATE_CLAIM
    finally:
        store.close()


def test_profile_cap_checked_before_copying(tmp_path: Path) -> None:
    documents = [
        _doc(_raw(f"ex-{index:02d}", maker=f"Maker {index}", model=f"Scope {index}")) for index in range(63)
    ]
    path = _json_file(
        tmp_path,
        "more.json",
        _raw("ex-63", maker="Maker 63", model="Scope 63"),
        _raw("ex-64", maker="Maker 64", model="Scope 64"),
    )
    source = FileSource(str(path))
    with pytest.raises(EquipmentProfileError) as excinfo:
        assemble_session(files=[source], documents=documents)
    assert excinfo.value.code is ProfileErrorCode.PROFILE_LIMIT_EXCEEDED


def test_row_cap_checked_before_copying() -> None:
    def rows():
        return [
            {
                "device_model": "Scope R",
                "acquisition_plane": "Single Plane",
                "kvp_kv": float((slot % 200) + 1),
                "filtration_added_mmcu": float(slot // 200) * 0.5,
                "filtration_added_mmal": 0.0,
                "k_patient_support": 0.5,
                "evidence_status": "estimated",
            }
            for slot in range(2000)
        ]

    documents = [
        _doc(
            {
                "profile_id": f"rows-{index}",
                "manufacturer": "Acme Imaging",
                "models": ["Scope R"],
                "transmission": [
                    {**row, "filtration_added_mmal": float(index)} for row in rows()
                ],
            }
        )
        for index in range(6)
    ]
    with pytest.raises(EquipmentProfileError) as excinfo:
        assemble_session(documents=documents)
    assert excinfo.value.code is ProfileErrorCode.ROW_LIMIT_EXCEEDED


def test_capability_gate_blocks_session_and_leaves_old_session_usable() -> None:
    good = assemble_session(documents=[_doc(_raw("ex-a", model="Scope A"))])
    gated = _doc(_raw("wild", models=["*"], coordinates={"detector_side_length": 40.0}))
    with pytest.raises(EquipmentProfileError) as excinfo:
        assemble_session(documents=[gated])
    assert excinfo.value.code is ProfileErrorCode.UNSUPPORTED_PROFILE_CAPABILITY
    assert excinfo.value.capability == "model_wildcard"
    assert good.resolve(_identity(), _bundled()).record.profile_id == "ex-a"


def test_empty_selection_is_a_valid_empty_session() -> None:
    session = assemble_session()
    assert len(session.profiles) == 0
    assert session.provenance.sources == ()
    assert (session.provenance.total_profiles, session.provenance.total_rows) == (0, 0)
    resolved = session.resolve(_identity(maker="Siemens", model="AXIOM-Artis"), _bundled())
    assert (resolved.record.source, resolved.record.level) == ("bundled", "exact")


# ---------------------------------------------------------------------------
# Request validation, paths, and privacy
# ---------------------------------------------------------------------------


def test_unsupported_suffix_fails_without_path(tmp_path: Path) -> None:
    path = tmp_path / "secret_clinic_export.txt"
    path.write_text("profile_id\n", encoding="utf-8")
    source = FileSource(str(path))
    with pytest.raises(EquipmentProfileError) as excinfo:
        assemble_session(files=[source])
    assert excinfo.value.code is ProfileErrorCode.UNSUPPORTED_SOURCE_SUFFIX
    assert "secret_clinic" not in str(excinfo.value)
    assert "secret_clinic" not in repr(excinfo.value)


def test_missing_file_is_value_free(tmp_path: Path) -> None:
    source = FileSource(str(tmp_path / "absent.json"))
    with pytest.raises(EquipmentProfileError) as excinfo:
        assemble_session(files=[source])
    assert excinfo.value.code is ProfileErrorCode.UNREADABLE_SOURCE


@pytest.mark.parametrize(
    ("source", "code"),
    [
        ("not-a-request", ProfileErrorCode.INVALID_TYPE),
        (FileSource(path=123), ProfileErrorCode.INVALID_TYPE),  # type: ignore[arg-type]
        (FileSource(path="a.json", format="bogus"), ProfileErrorCode.INVALID_ENUM),
        (FileSource(path="a.json", sheet="1"), ProfileErrorCode.INVALID_TYPE),
        (FileSource(path="a.json", sheet=-1), ProfileErrorCode.VALUE_OUT_OF_RANGE),
        (FileSource(path="a.csv", sheet=0), ProfileErrorCode.INVALID_TYPE),
    ],
)
def test_malformed_file_requests_rejected(source, code, tmp_path: Path) -> None:
    target = tmp_path / "a.json"
    target.write_text(json.dumps(_doc(_raw("ex-a", model="Scope A"))), encoding="utf-8")
    with pytest.raises(EquipmentProfileError) as excinfo:
        assemble_session(files=[source])
    assert excinfo.value.code is code


def test_malformed_top_level_inputs_rejected() -> None:
    with pytest.raises(EquipmentProfileError) as excinfo:
        assemble_session(documents="not-a-sequence")
    assert excinfo.value.code is ProfileErrorCode.INVALID_TYPE
    with pytest.raises(EquipmentProfileError) as excinfo:
        assemble_session(snapshots=["not-a-snapshot"])  # type: ignore[list-item]
    assert excinfo.value.code is ProfileErrorCode.INVALID_TYPE
    with pytest.raises(EquipmentProfileError) as excinfo:
        assemble_session(settings_base_dir=123)  # type: ignore[arg-type]
    assert excinfo.value.code is ProfileErrorCode.INVALID_TYPE


def test_relative_paths_resolve_cwd_or_base_dir(tmp_path: Path, monkeypatch) -> None:
    path = _json_file(tmp_path, "rel.json", _raw("ex-a", model="Scope A"))
    monkeypatch.chdir(tmp_path)
    via_cwd = assemble_session(files=[FileSource("rel.json")])
    assert [p.profile_id for p in via_cwd.profiles] == ["ex-a"]
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    missing = FileSource("rel.json")
    with pytest.raises(EquipmentProfileError):
        assemble_session(files=[missing])
    via_base = assemble_session(files=[FileSource("rel.json")], settings_base_dir=tmp_path)
    assert [p.profile_id for p in via_base.profiles] == ["ex-a"]
    assert path.name not in str(via_base.provenance)


def test_absolute_paths_ignore_base_dir(tmp_path: Path) -> None:
    path = _json_file(tmp_path, "abs.json", _raw("ex-a", model="Scope A"))
    other = tmp_path / "other"
    other.mkdir()
    session = assemble_session(files=[FileSource(str(path))], settings_base_dir=other)
    assert [p.profile_id for p in session.profiles] == ["ex-a"]


def test_repr_and_provenance_hide_paths_and_notes(tmp_path: Path) -> None:
    secret = tmp_path / "secret_clinic_notes.json"
    secret.write_text(
        json.dumps(
            _doc(
                _raw(
                    "ex-a",
                    model="Scope A",
                    provenance={"source": "Dr Quiet", "notes": "Confidential ward note"},
                )
            )
        ),
        encoding="utf-8",
    )
    session = assemble_session(files=[FileSource(str(secret))])
    text = repr(session) + repr(session.provenance) + repr(session.provenance.sources[0])
    text += repr(FileSource(str(secret)))
    for sentinel in ("secret_clinic", "Dr Quiet", "Confidential ward note", ".json"):
        assert sentinel not in text, sentinel
    assert "profiles=1" in repr(session)


def test_resolve_rejects_bad_bundled_type() -> None:
    session = assemble_session(documents=[_doc(_raw("ex-a", model="Scope A"))])
    identity = _identity()
    with pytest.raises(EquipmentProfileError) as excinfo:
        session.resolve(identity, "not-a-bundled-set")  # type: ignore[arg-type]
    assert excinfo.value.code is ProfileErrorCode.INVALID_TYPE


def test_resolve_accepts_prepared_bundled_without_preparation(monkeypatch) -> None:
    import guiskindose.equipment_profiles.preparation as preparation_module

    session = assemble_session(documents=[_doc(_raw("ex-a", model="Scope A"))])
    prepared = prepare_bundled_context(_bundled())
    calls = []

    def _boom(*args, **kwargs):
        calls.append(1)
        raise AssertionError("recompiled during per-exam resolution")

    monkeypatch.setattr(preparation_module, "build_profile_indexes", _boom)
    monkeypatch.setattr(preparation_module, "check_initial_capabilities", _boom)
    first = session.resolve(_identity(), prepared)
    second = session.resolve(_identity(), prepared)
    assert calls == []
    assert first == second
    assert first.record.profile_id == "ex-a"


def test_resolve_with_prepared_matches_direct_resolution() -> None:
    session = assemble_session(documents=[_doc(_raw("ex-a", model="Scope A"))])
    identity = _identity()
    bundled = _bundled()
    direct = session.resolve(identity, bundled)
    prepared = resolve_with_prepared(
        identity=identity, custom=session.prepared, bundled=prepare_bundled_context(bundled)
    )
    assert prepared == direct


# ---------------------------------------------------------------------------
# Request bounds: declared lengths, lying lengths, aggregate cap, short-circuit
# ---------------------------------------------------------------------------


def test_declared_source_oversize_fails_before_any_read(tmp_path: Path) -> None:
    """65 file requests fail on the declared count without touching the filesystem."""
    missing = [FileSource(str(tmp_path / f"absent-{index}.json")) for index in range(65)]
    with pytest.raises(EquipmentProfileError) as excinfo:
        assemble_session(files=missing)
    assert excinfo.value.code is ProfileErrorCode.PROFILE_LIMIT_EXCEEDED


def test_lying_request_length_cannot_force_unbounded_copy() -> None:
    """A sequence under-reporting its length is still capped by bounded iteration."""
    from collections.abc import Sequence

    requests = [FileSource(f"absent-{index}.json") for index in range(70)]

    class _Lying(Sequence):
        def __len__(self) -> int:
            return 1

        def __getitem__(self, index):
            if isinstance(index, slice):
                return requests[index]
            return requests[index]

    lying = _Lying()  # type: ignore[arg-type]
    with pytest.raises(EquipmentProfileError) as excinfo:
        assemble_session(files=lying)
    assert excinfo.value.code is ProfileErrorCode.PROFILE_LIMIT_EXCEEDED


def test_empty_snapshots_cannot_inflate_sources_unbounded() -> None:
    """Empty snapshots carry provenance but no profiles; 65 still exceed the source cap."""
    from guiskindose.equipment_profiles import StoreSnapshot, store_source_hash

    store_id = "ab" * 16
    empties = [
        StoreSnapshot(
            store_id=store_id,
            source_kind="store",
            selected=(),
            profiles=(),
            source_hash=store_source_hash(store_id, ()),
            logical_rows=0,
        )
        for _ in range(65)
    ]
    with pytest.raises(EquipmentProfileError) as excinfo:
        assemble_session(snapshots=empties)
    assert excinfo.value.code is ProfileErrorCode.PROFILE_LIMIT_EXCEEDED


def test_single_empty_snapshot_assembles_but_validates_wrapper() -> None:
    from guiskindose.equipment_profiles import StoreSnapshot, store_source_hash

    store_id = "ab" * 16
    valid = StoreSnapshot(
        store_id=store_id,
        source_kind="store",
        selected=(),
        profiles=(),
        source_hash=store_source_hash(store_id, ()),
        logical_rows=0,
    )
    session = assemble_session(snapshots=[valid])
    assert len(session.profiles) == 0
    assert session.provenance.sources[0].profile_count == 0
    tampered = StoreSnapshot(
        store_id=store_id,
        source_kind="store",
        selected=(),
        profiles=(),
        source_hash="0" * 64,
        logical_rows=0,
    )
    with pytest.raises(EquipmentProfileError) as excinfo:
        assemble_session(snapshots=[tampered])
    assert excinfo.value.code is ProfileErrorCode.CONFLICTING_PROFILE_METADATA


def test_profile_ceiling_short_circuits_before_next_read(tmp_path: Path) -> None:
    """After the 65th profile the third file is never opened (it does not exist)."""
    full = _json_file(
        tmp_path,
        "full.json",
        *[_raw(f"ex-{index:02d}", maker=f"Maker {index}", model=f"Scope {index}") for index in range(64)],
    )
    extra = _json_file(tmp_path, "extra.json", _raw("ex-64", maker="Maker 64", model="Scope 64"))
    missing = tmp_path / "absent.json"
    sources = [FileSource(str(full)), FileSource(str(extra)), FileSource(str(missing))]
    with pytest.raises(EquipmentProfileError) as excinfo:
        assemble_session(files=sources)
    assert excinfo.value.code is ProfileErrorCode.PROFILE_LIMIT_EXCEEDED


# ---------------------------------------------------------------------------
# Snapshot revalidation: tampered metadata fails closed
# ---------------------------------------------------------------------------


def _snapshot_parts(tmp_path: Path, *profiles, store_id="cd" * 16):

    store = ProfileStore.open(tmp_path / "tamper.sqlite3")
    try:
        parsed = parse_memory_document(_doc(*profiles)).profiles
        for profile in parsed:
            store.save_new_revision(profile)
        snapshot = store.selected_snapshot([profile.profile_id for profile in parsed])
        return store, snapshot
    except Exception:
        store.close()
        raise


def test_snapshot_selected_hash_tampering_fails(tmp_path: Path) -> None:
    import dataclasses

    store, snapshot = _snapshot_parts(tmp_path, _raw("ex-s", model="Scope S"))
    try:
        selected = snapshot.selected[0]
        tampered_selected = dataclasses.replace(selected, profile_hash="1" * 64)
        tampered = dataclasses.replace(snapshot, selected=(tampered_selected,))
        with pytest.raises(EquipmentProfileError) as excinfo:
            assemble_session(snapshots=[tampered])
        assert excinfo.value.code is ProfileErrorCode.CONFLICTING_PROFILE_METADATA
    finally:
        store.close()


def test_snapshot_source_hash_sentinel_rejected(tmp_path: Path) -> None:
    import dataclasses

    store, snapshot = _snapshot_parts(tmp_path, _raw("ex-s", model="Scope S"))
    try:
        tampered = dataclasses.replace(snapshot, source_hash="patient/site/path")
        with pytest.raises(EquipmentProfileError) as excinfo:
            assemble_session(snapshots=[tampered])
        assert excinfo.value.code is ProfileErrorCode.INVALID_TYPE
        assert "patient" not in str(excinfo.value)
    finally:
        store.close()


def test_snapshot_wrong_lengths_rejected(tmp_path: Path) -> None:
    import dataclasses

    store, snapshot = _snapshot_parts(tmp_path, _raw("ex-s", model="Scope S"))
    try:
        short_hash = dataclasses.replace(snapshot, source_hash="0" * 63)
        with pytest.raises(EquipmentProfileError) as excinfo:
            assemble_session(snapshots=[short_hash])
        assert excinfo.value.code is ProfileErrorCode.INVALID_TYPE
        bad_store = dataclasses.replace(snapshot, store_id="not-hex")
        with pytest.raises(EquipmentProfileError) as excinfo:
            assemble_session(snapshots=[bad_store])
        assert excinfo.value.code is ProfileErrorCode.INVALID_TYPE
    finally:
        store.close()


def test_snapshot_inconsistent_rows_rejected(tmp_path: Path) -> None:
    import dataclasses

    store, snapshot = _snapshot_parts(tmp_path, _raw("ex-s", model="Scope S"))
    try:
        tampered = dataclasses.replace(snapshot, logical_rows=999)
        with pytest.raises(EquipmentProfileError) as excinfo:
            assemble_session(snapshots=[tampered])
        assert excinfo.value.code is ProfileErrorCode.CONFLICTING_PROFILE_METADATA
    finally:
        store.close()


def test_snapshot_list_shapes_rejected(tmp_path: Path) -> None:
    import dataclasses

    store, snapshot = _snapshot_parts(tmp_path, _raw("ex-s", model="Scope S"))
    try:
        listed = dataclasses.replace(
            snapshot, selected=list(snapshot.selected), profiles=list(snapshot.profiles)
        )
        with pytest.raises(EquipmentProfileError) as excinfo:
            assemble_session(snapshots=[listed])
        assert excinfo.value.code is ProfileErrorCode.INVALID_TYPE
    finally:
        store.close()


def test_snapshot_mutable_profile_cannot_enter_session(tmp_path: Path) -> None:
    import dataclasses
    from dataclasses import replace

    store, snapshot = _snapshot_parts(tmp_path, _raw("ex-s", model="Scope S"))
    try:
        mutable = replace(snapshot.profiles[0], models=["Scope S"])
        listed_hash = snapshot.source_hash
        tampered = dataclasses.replace(snapshot, profiles=(mutable,))
        with pytest.raises(EquipmentProfileError) as excinfo:
            assemble_session(snapshots=[tampered])
        assert excinfo.value.code is ProfileErrorCode.INVALID_TYPE
        assert listed_hash == snapshot.source_hash
    finally:
        store.close()


@pytest.mark.parametrize("bad_revision", [0, -2, True, 2**63])
def test_snapshot_bad_revisions_rejected(tmp_path: Path, bad_revision) -> None:
    import dataclasses

    store, snapshot = _snapshot_parts(tmp_path, _raw("ex-s", model="Scope S"))
    try:
        selected = snapshot.selected[0]
        tampered_selected = dataclasses.replace(selected, revision=bad_revision)
        tampered = dataclasses.replace(snapshot, selected=(tampered_selected,))
        with pytest.raises(EquipmentProfileError) as excinfo:
            assemble_session(snapshots=[tampered])
        assert excinfo.value.code is ProfileErrorCode.VALUE_OUT_OF_RANGE
    finally:
        store.close()


# ---------------------------------------------------------------------------
# Path boundary: hostile pathlikes, NUL, and sentinel-free request reprs
# ---------------------------------------------------------------------------


class _BytesPath:
    """os.PathLike returning bytes: rejected without leaking."""

    def __fspath__(self):
        return b"/tmp/evil.json"


class _RaisingPath:
    """os.PathLike raising from __fspath__: collapsed to a closed error."""

    def __init__(self, error):
        self._error = error

    def __fspath__(self):
        raise self._error("hostile message with /tmp/secret leaking text")


class _StrPath:
    """Well-behaved custom path type carrying a real file."""

    def __init__(self, text):
        self._text = text

    def __fspath__(self):
        return self._text


def test_bytes_pathlike_rejected_closed(tmp_path: Path) -> None:
    source = FileSource(_BytesPath())  # type: ignore[arg-type]
    with pytest.raises(EquipmentProfileError) as excinfo:
        assemble_session(files=[source])
    assert excinfo.value.code is ProfileErrorCode.INVALID_TYPE
    assert "evil" not in str(excinfo.value)


@pytest.mark.parametrize("error", [ValueError, OSError, RuntimeError])
def test_raising_pathlike_collapsed_closed(tmp_path: Path, error) -> None:
    source = FileSource(_RaisingPath(error))
    with pytest.raises(EquipmentProfileError) as excinfo:
        assemble_session(files=[source])
    assert excinfo.value.code is ProfileErrorCode.INVALID_TYPE
    assert "hostile" not in str(excinfo.value)
    assert "secret" not in str(excinfo.value)


def test_nul_path_fails_as_unreadable(tmp_path: Path) -> None:
    source = FileSource(str(tmp_path / "\0evil.json"))
    with pytest.raises(EquipmentProfileError) as excinfo:
        assemble_session(files=[source])
    assert excinfo.value.code is ProfileErrorCode.UNREADABLE_SOURCE


def test_custom_str_pathlike_resolves(tmp_path: Path) -> None:
    path = _json_file(tmp_path, "ok.json", _raw("ex-a", model="Scope A"))
    session = assemble_session(files=[FileSource(_StrPath(str(path)))])
    assert [p.profile_id for p in session.profiles] == ["ex-a"]


def test_request_repr_shows_validated_values_only() -> None:
    assert repr(FileSource("a.json", format="json", sheet=0)) == "FileSource(format='json', sheet=0)"
    assert repr(FileSource("a.json", format="evil-sentinel", sheet=10**30)) == (
        "FileSource(format=None, sheet=1000000000000000000000000000000)"
    )
    assert "evil-sentinel" not in repr(FileSource("a.json", format="evil-sentinel"))


# ---------------------------------------------------------------------------
# Canonical ordering: reordered inputs assemble equal sessions
# ---------------------------------------------------------------------------


def test_reordered_inputs_assemble_equal_sessions(tmp_path: Path) -> None:
    first = _json_file(tmp_path, "b.json", _raw("ex-b", model="Scope B"))
    second = _json_file(tmp_path, "a.json", _raw("ex-a", model="Scope A"))
    memory = _doc(_raw("ex-m", maker="Maker M", model="Scope M"))
    forward = assemble_session(files=[FileSource(str(first)), FileSource(str(second))], documents=[memory])
    backward = assemble_session(documents=[memory], files=[FileSource(str(second)), FileSource(str(first))])
    assert forward == backward
    assert [p.profile_id for p in forward.profiles] == ["ex-a", "ex-b", "ex-m"]
    assert [s.kind for s in forward.provenance.sources] == ["file", "file", "memory"]
    assert forward.provenance == backward.provenance


def test_mixed_kind_reorder_preserves_hashes_and_revisions(tmp_path: Path) -> None:
    path = _json_file(tmp_path, "a.json", _raw("ex-a", model="Scope A"))
    store = _store_with(tmp_path, _raw("ex-s", model="Scope S"))
    try:
        memory = _doc(_raw("ex-m", maker="Maker M", model="Scope M"))
        first = assemble_session(
            files=[FileSource(str(path))],
            documents=[memory],
            snapshots=[store.selected_snapshot(["ex-s"])],
        )
        second = assemble_session(
            snapshots=[store.selected_snapshot(["ex-s"])],
            documents=[memory],
            files=[FileSource(str(path))],
        )
        assert first == second
        kinds = [source.kind for source in first.provenance.sources]
        assert kinds == ["file", "memory", "store"]
        store_source = first.provenance.sources[2]
        assert store_source.revisions == (("ex-s", 1),)
        assert store_source.source_hash == store.selected_snapshot(["ex-s"]).source_hash
    finally:
        store.close()


def test_snapshot_malformed_coordinate_payload_fails_before_hashing(tmp_path: Path) -> None:
    from dataclasses import replace

    store, snapshot = _snapshot_parts(tmp_path, _raw("ex-s", model="Scope S"))
    try:
        malformed = replace(snapshot.profiles[0], coordinates={"site-sentinel": "private"})
        tampered = replace(snapshot, profiles=(malformed,))
        requests = [tampered]
        with pytest.raises(EquipmentProfileError) as caught:
            assemble_session(snapshots=requests)
        assert caught.value.code is ProfileErrorCode.INVALID_TYPE
        assert "site-sentinel" not in str(caught.value)
    finally:
        store.close()


def test_prepared_context_rejects_duplicate_entry_tuple() -> None:
    from dataclasses import replace

    session = assemble_session(documents=[_doc(_raw("ex-a"))])
    duplicate = (session.prepared.entries[0], session.prepared.entries[0])
    with pytest.raises(EquipmentProfileError) as caught:
        replace(session.prepared, entries=duplicate)
    assert caught.value.code is ProfileErrorCode.DUPLICATE_PROFILE_ID


def test_prepared_context_rejects_disconnected_index_profiles() -> None:
    from dataclasses import replace

    session = assemble_session(documents=[_doc(_raw("ex-a"))])
    disconnected = replace(session.custom, profiles=())
    with pytest.raises(EquipmentProfileError) as caught:
        replace(session.prepared, index=disconnected)
    assert caught.value.code is ProfileErrorCode.INVALID_TYPE
