"""Tests for CLI existing-store selection composed with profile files.

Store databases are built per test with the writable API under ``tmp_path``
and opened read-only through the new factory or CLI flags; no fixture binary
is tracked. Covers the read-only connection contract (no creation, no
writes, coded failures), ID selection semantics (enabled vs explicit,
current revisions), file/store composition parity against frozen Python
snapshots, closed failures with zero exam reads and private stderr, caller
preservation, and the four-flag GUI guard.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

import pytest

from guiskindose import get_path_to_example_rdsr_files, load_settings_example_json
from guiskindose.__main__ import cli
from guiskindose.cli_equipment_profiles import (
    GUI_EQUIPMENT_PROFILES_MESSAGE,
    equipment_session_from_args,
)
from guiskindose.equipment_profiles import (
    FileSource,
    ProfileStore,
    assemble_session,
    parse_memory_document,
)
from guiskindose.equipment_profiles.errors import EquipmentProfileError, ProfileErrorCode
from guiskindose.main import main
from guiskindose.privacy import UserFacingInputError
from guiskindose.settings import PyskindoseSettings
from tests.unittests.test_cli_equipment_profiles import (
    _settings_file,
    _stdout_json,
)
from tests.unittests.test_equipment_captured_input import (
    _GENERIC_HEADER,
    _GENERIC_SIEMENS_ROW,
    _philips_coordinates,
    _siemens_coordinates,
    _snapshot_norm,
)

_SIEMENS_DICOM = get_path_to_example_rdsr_files() / "siemens_axiom_artis.dcm"


def _siemens_profile(profile_id: str = "p-siemens", offset_x: float = 5.0) -> Any:
    import copy

    coordinates = copy.deepcopy(_siemens_coordinates())
    coordinates["translation_offset"]["x"] = offset_x
    return parse_memory_document(
        {
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
    ).profiles[0]


def _philips_profile(profile_id: str = "p-philips") -> Any:
    return parse_memory_document(
        {
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
    ).profiles[0]


def _seed_store(path: Path, profiles: list[Any], *, enabled: list[str] | None = None) -> Path:
    """Build a populated store with the writable API; all records disabled unless listed."""
    store = ProfileStore.open(path)
    try:
        for profile in profiles:
            store.save_new_revision(profile)
        for profile_id in enabled or []:
            record = next(r for r in store.list_records() if r.profile_id == profile_id)
            store.set_enabled(profile_id, True, expected_current_revision=record.current_revision)
    finally:
        store.close()
    return path


def _store_argv(
    settings_path: Path,
    exam: Path,
    profiles: list[Path] | None = None,
    store: Path | None = None,
    ids: list[str] | None = None,
) -> list[str]:
    argv = [
        "guiskindose",
        "--settings",
        str(settings_path),
        "--file-path",
        str(exam),
        "--output-format",
        "json",
    ]
    for profile in profiles or []:
        argv.extend(["--equipment-profile", str(profile)])
    if store is not None:
        argv.extend(["--equipment-profile-store", str(store)])
    for profile_id in ids or []:
        argv.extend(["--equipment-profile-id", profile_id])
    return argv


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _spy_exam_reads(monkeypatch: pytest.MonkeyPatch) -> dict[str, list[str]]:
    """Record-delegate spies over the real exam loaders (not aliases)."""
    import guiskindose.helpers.read_and_normalize_rdsr_data as dicom_helper
    import guiskindose.input_adapters.registry as registry_module

    probes: dict[str, list[str]] = {"load": [], "dcmread": []}
    real_load = registry_module.load

    def _spy_load(path: Any, *args: Any, **kwargs: Any) -> Any:
        probes["load"].append(str(path))
        return real_load(path, *args, **kwargs)

    monkeypatch.setattr(registry_module, "load", _spy_load)
    real_read = dicom_helper.pydicom.dcmread

    def _spy_read(path: Any, *args: Any, **kwargs: Any) -> Any:
        probes["dcmread"].append(str(path))
        return real_read(path, *args, **kwargs)

    monkeypatch.setattr(dicom_helper.pydicom, "dcmread", _spy_read)
    return probes


# ---------------------------------------------------------------------------
# Read-only factory contract
# ---------------------------------------------------------------------------


def test_read_only_open_reads_and_leaves_bytes_untouched(tmp_path: Path) -> None:
    db = _seed_store(
        tmp_path / "profiles.sqlite3",
        [_siemens_profile(), _philips_profile()],
        enabled=["p-siemens", "p-philips"],
    )
    before = _sha256(db)
    store = ProfileStore.open_read_only(db)
    try:
        assert [(r.profile_id, r.current_revision) for r in store.list_records()] == [
            ("p-philips", 1),
            ("p-siemens", 1),
        ]
        snapshot = store.selected_snapshot()
        assert sorted(p.profile_id for p in snapshot.profiles) == ["p-philips", "p-siemens"]
    finally:
        store.close()
    assert _sha256(db) == before


def test_read_only_missing_and_parent_untouched(tmp_path: Path) -> None:
    missing = tmp_path / "SENTINEL_ABSENT_DB_zzz.sqlite3"
    with pytest.raises(EquipmentProfileError) as excinfo:
        ProfileStore.open_read_only(missing)
    assert excinfo.value.code is ProfileErrorCode.STORE_UNAVAILABLE
    assert not missing.exists()
    nested = tmp_path / "no_such_dir" / "deep.sqlite3"
    with pytest.raises(EquipmentProfileError) as excinfo:
        ProfileStore.open_read_only(nested)
    assert excinfo.value.code is ProfileErrorCode.STORE_UNAVAILABLE
    assert not (tmp_path / "no_such_dir").exists()


def test_read_only_empty_foreign_unversioned_future(tmp_path: Path) -> None:
    empty = tmp_path / "empty.sqlite3"
    empty.write_bytes(b"")
    with pytest.raises(EquipmentProfileError) as excinfo:
        ProfileStore.open_read_only(empty)
    assert excinfo.value.code is ProfileErrorCode.STORE_CORRUPTION
    assert empty.stat().st_size == 0
    foreign = tmp_path / "foreign.sqlite3"
    foreign.write_text("not a database", encoding="utf-8")
    with pytest.raises(EquipmentProfileError) as excinfo:
        ProfileStore.open_read_only(foreign)
    assert excinfo.value.code is ProfileErrorCode.STORE_CORRUPTION
    assert foreign.read_text(encoding="utf-8") == "not a database"
    unversioned = tmp_path / "unversioned.sqlite3"
    connection = sqlite3.connect(str(unversioned))
    connection.execute("CREATE TABLE stray(id INTEGER PRIMARY KEY)")
    connection.commit()
    connection.close()
    with pytest.raises(EquipmentProfileError) as excinfo:
        ProfileStore.open_read_only(unversioned)
    assert excinfo.value.code is ProfileErrorCode.STORE_CORRUPTION
    future = tmp_path / "future.sqlite3"
    connection = sqlite3.connect(str(future))
    connection.execute("PRAGMA user_version = 99")
    connection.commit()
    connection.close()
    with pytest.raises(EquipmentProfileError) as excinfo:
        ProfileStore.open_read_only(future)
    assert excinfo.value.code is ProfileErrorCode.UNSUPPORTED_STORE_VERSION


def test_read_only_mutations_fail_coded_bytes_unchanged(tmp_path: Path) -> None:
    db = _seed_store(tmp_path / "profiles.sqlite3", [_siemens_profile()], enabled=["p-siemens"])
    before = _sha256(db)
    store = ProfileStore.open_read_only(db)
    try:
        candidate = _philips_profile()
        with pytest.raises(EquipmentProfileError) as excinfo:
            store.save_new_revision(candidate)
        assert excinfo.value.code is ProfileErrorCode.STORE_UNAVAILABLE
        with pytest.raises(EquipmentProfileError) as excinfo:
            store.set_enabled("p-siemens", False)
        assert excinfo.value.code is ProfileErrorCode.STORE_UNAVAILABLE
        with pytest.raises(EquipmentProfileError) as excinfo:
            store.delete_record("p-siemens")
        assert excinfo.value.code is ProfileErrorCode.STORE_UNAVAILABLE
    finally:
        store.close()
    assert _sha256(db) == before
    writable = ProfileStore.open(db)
    try:
        writable.set_enabled("p-siemens", False)
        assert writable.list_records()[0].enabled is False
    finally:
        writable.close()


def test_read_only_uri_special_chars(tmp_path: Path) -> None:
    awkward = tmp_path / "my prof#1%3F.db"
    db = _seed_store(awkward, [_siemens_profile()], enabled=["p-siemens"])
    nested = tmp_path / "ünicode dir" / "sp ace # %3F.db"
    nested.parent.mkdir()
    db.replace(nested)
    store = ProfileStore.open_read_only(nested)
    try:
        assert [r.profile_id for r in store.list_records()] == ["p-siemens"]
    finally:
        store.close()


def test_read_only_sees_committed_data(tmp_path: Path) -> None:
    db = _seed_store(
        tmp_path / "profiles.sqlite3",
        [_siemens_profile(), _philips_profile()],
        enabled=["p-siemens", "p-philips"],
    )
    live = ProfileStore.open(db)
    try:
        live_hashes = sorted(
            (r.profile_id, r.current_revision) for r in live.list_records()
        )
        live_snapshot = live.selected_snapshot().source_hash
    finally:
        live.close()
    store = ProfileStore.open_read_only(db)
    try:
        assert sorted((r.profile_id, r.current_revision) for r in store.list_records()) == live_hashes
        assert store.selected_snapshot().source_hash == live_snapshot
    finally:
        store.close()


# ---------------------------------------------------------------------------
# CLI composition: store snapshots plus files
# ---------------------------------------------------------------------------


def test_store_enabled_parity_and_hash(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    db = _seed_store(
        tmp_path / "profiles.sqlite3",
        [_siemens_profile(), _philips_profile()],
        enabled=["p-siemens", "p-philips"],
    )
    settings_path = _settings_file(tmp_path)
    monkeypatch.setattr(sys, "argv", _store_argv(settings_path, _SIEMENS_DICOM, store=db))
    cli()
    payload = _stdout_json(capsys)
    frozen = ProfileStore.open_read_only(db)
    try:
        snapshot = frozen.selected_snapshot()
    finally:
        frozen.close()
    config = json.loads(settings_path.read_text(encoding="utf-8"))
    session = assemble_session(snapshots=[snapshot])
    expected: Any = main(
        file_path=str(_SIEMENS_DICOM),
        settings=PyskindoseSettings(
            settings=config, output_format="dict", equipment_profile_session=session
        ),
    )
    assert payload["equipment_profile_match"]["profile_id"] == "p-siemens"
    assert payload["psd"] == expected["psd"]
    assert payload["equipment_profile_match"] == expected["equipment_profile_match"]
    assert payload["dose_map"] == json.loads(json.dumps(expected["dose_map"]))


def test_explicit_id_ignores_disabled(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    db = _seed_store(tmp_path / "profiles.sqlite3", [_siemens_profile()], enabled=[])
    settings_path = _settings_file(tmp_path)
    monkeypatch.setattr(sys, "argv", _store_argv(settings_path, _SIEMENS_DICOM, store=db))
    cli()
    baseline = _stdout_json(capsys)
    assert "equipment_profile_match" not in baseline
    config = json.loads(settings_path.read_text(encoding="utf-8"))
    plain: Any = main(
        file_path=str(_SIEMENS_DICOM),
        settings=PyskindoseSettings(settings=config, output_format="dict"),
    )
    assert baseline["psd"] == plain["psd"]
    monkeypatch.setattr(
        sys, "argv", _store_argv(settings_path, _SIEMENS_DICOM, store=db, ids=["p-siemens"])
    )
    cli()
    selected = _stdout_json(capsys)
    assert selected["equipment_profile_match"]["profile_id"] == "p-siemens"
    assert selected["psd"] != baseline["psd"]
    frozen = ProfileStore.open_read_only(db)
    try:
        snapshot = frozen.selected_snapshot(["p-siemens"])
    finally:
        frozen.close()
    session = assemble_session(snapshots=[snapshot])
    expected: Any = main(
        file_path=str(_SIEMENS_DICOM),
        settings=PyskindoseSettings(
            settings=config, output_format="dict", equipment_profile_session=session
        ),
    )
    assert selected["psd"] == expected["psd"]
    assert selected["equipment_profile_match"] == expected["equipment_profile_match"]


def test_current_revision_selected(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    db = tmp_path / "profiles.sqlite3"
    writer = ProfileStore.open(db)
    try:
        writer.save_new_revision(_siemens_profile())
        writer.save_new_revision(_siemens_profile(offset_x=9.0), expected_current_revision=1)
    finally:
        writer.close()
    reader = ProfileStore.open_read_only(db)
    try:
        assert reader.list_records()[0].current_revision == 2
        current = reader.selected_snapshot(["p-siemens"])
    finally:
        reader.close()
    settings_path = _settings_file(tmp_path)
    monkeypatch.setattr(
        sys, "argv", _store_argv(settings_path, _SIEMENS_DICOM, store=db, ids=["p-siemens"])
    )
    cli()
    payload = _stdout_json(capsys)
    session = assemble_session(snapshots=[current])
    config = json.loads(settings_path.read_text(encoding="utf-8"))
    expected: Any = main(
        file_path=str(_SIEMENS_DICOM),
        settings=PyskindoseSettings(
            settings=config, output_format="dict", equipment_profile_session=session
        ),
    )
    assert payload["psd"] == expected["psd"]
    assert payload["equipment_profile_match"] == expected["equipment_profile_match"]


def test_store_file_order_and_composition(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    db = _seed_store(tmp_path / "profiles.sqlite3", [_siemens_profile()], enabled=["p-siemens"])
    philips_file = tmp_path / "philips.json"
    philips_file.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "profiles": [
                    {
                        "profile_id": "p-philips",
                        "manufacturer": "Philips",
                        "models": ["Allura Clarity"],
                        "coordinates": _philips_coordinates(),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    settings_path = _settings_file(tmp_path)
    monkeypatch.setattr(
        sys, "argv", _store_argv(settings_path, _SIEMENS_DICOM, profiles=[philips_file], store=db)
    )
    cli()
    file_then_store = _stdout_json(capsys)
    store = ProfileStore.open_read_only(db)
    try:
        snapshot = store.selected_snapshot()
    finally:
        store.close()
    session = assemble_session(files=[FileSource(str(philips_file))], snapshots=[snapshot])
    config = json.loads(settings_path.read_text(encoding="utf-8"))
    expected: Any = main(
        file_path=str(_SIEMENS_DICOM),
        settings=PyskindoseSettings(
            settings=config, output_format="dict", equipment_profile_session=session
        ),
    )
    assert file_then_store["psd"] == expected["psd"]
    assert file_then_store["equipment_profile_match"] == expected["equipment_profile_match"]
    assert file_then_store["equipment_profile_match"]["active_set_hash"] == session.active_set_hash


def test_store_file_conflict_closed(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    db = _seed_store(tmp_path / "profiles.sqlite3", [_siemens_profile()], enabled=["p-siemens"])
    rival = tmp_path / "rival.json"
    rival.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "profiles": [
                    {
                        "profile_id": "p-rival",
                        "manufacturer": "Siemens",
                        "models": ["AXIOM-Artis"],
                        "coordinates": dict(_siemens_coordinates(), translation_offset={"x": 9.0, "y": -3.5, "z": 0.0}),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    exam = tmp_path / "events.csv"
    exam.write_text(_GENERIC_HEADER + "\n" + _GENERIC_SIEMENS_ROW + "\n", encoding="utf-8")
    probes = _spy_exam_reads(monkeypatch)
    settings_path = _settings_file(tmp_path)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "guiskindose",
            "--settings",
            str(settings_path),
            "--file-path",
            str(exam),
            "--input-schema",
            "generic_rdsr_like",
            "--equipment-profile",
            str(rival),
            "--equipment-profile-store",
            str(db),
        ],
    )
    with pytest.raises(SystemExit) as excinfo:
        cli()
    assert excinfo.value.code == 1
    err = capsys.readouterr().err
    assert "duplicate_coordinate_claim" in err
    assert "p-rival" not in err
    assert str(db) not in err
    assert probes == {"load": [], "dcmread": []}


def test_store_unsupported_capability_closed(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    from guiskindose.equipment_profiles import parse_memory_document

    doc = {
        "schema_version": 1,
        "profiles": [
            {
                "profile_id": "p-trans",
                "manufacturer": "Siemens",
                "models": ["AXIOM-Artis"],
                "transmission": [
                    {
                        "device_model": "AXIOM-Artis",
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
    db = tmp_path / "profiles.sqlite3"
    writer = ProfileStore.open(db)
    try:
        writer.save_new_revision(parse_memory_document(doc).profiles[0])
    finally:
        writer.close()
    exam = tmp_path / "events.csv"
    exam.write_text(_GENERIC_HEADER + "\n" + _GENERIC_SIEMENS_ROW + "\n", encoding="utf-8")
    probes = _spy_exam_reads(monkeypatch)
    settings_path = _settings_file(tmp_path)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "guiskindose",
            "--settings",
            str(settings_path),
            "--file-path",
            str(exam),
            "--input-schema",
            "generic_rdsr_like",
            "--equipment-profile-store",
            str(db),
            "--equipment-profile-id",
            "p-trans",
        ],
    )
    with pytest.raises(SystemExit) as excinfo:
        cli()
    assert excinfo.value.code == 1
    err = capsys.readouterr().err
    assert "unsupported_profile_capability" in err
    assert "p-trans" not in err
    assert str(db) not in err
    assert probes == {"load": [], "dcmread": []}


def _store_namespace(store: Any, ids: Any) -> Any:
    """Minimal argparse namespace carrying only store selectors."""
    import argparse

    return argparse.Namespace(
        equipment_profile=None,
        equipment_profile_sheet=None,
        equipment_profile_store=store,
        equipment_profile_id=ids,
    )


def test_id_bounds_types_dup_pre_io(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    db = _seed_store(tmp_path / "profiles.sqlite3", [_siemens_profile()], enabled=["p-siemens"])
    real_connect = sqlite3.connect
    connects: list[str] = []

    def _spy_connect(*args: Any, **kwargs: Any) -> Any:
        connects.append(str(args[0]) if args else "")
        return real_connect(*args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", _spy_connect)
    request_0 = _store_namespace(store=db, ids=[f"p-{index}" for index in range(65)])
    with pytest.raises(UserFacingInputError):
        equipment_session_from_args(request_0)
    request_1 = _store_namespace(store=db, ids=[123])
    with pytest.raises(UserFacingInputError):
        equipment_session_from_args(request_1)
    request_2 = _store_namespace(store=db, ids=["p-siemens", "p-siemens"])
    with pytest.raises(UserFacingInputError):
        equipment_session_from_args(request_2)
    request_3 = _store_namespace(store=None, ids=["p-siemens"])
    with pytest.raises(UserFacingInputError):
        equipment_session_from_args(request_3)
    assert connects == []


def test_store_missing_corrupt_future_cli(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    exam = tmp_path / "events.csv"
    exam.write_text(_GENERIC_HEADER + "\n" + _GENERIC_SIEMENS_ROW + "\n", encoding="utf-8")
    settings_path = _settings_file(tmp_path)
    corrupt = tmp_path / "SENTINEL_CORRUPT_DB_zzz.sqlite3"
    corrupt.write_text("not a database", encoding="utf-8")
    future = tmp_path / "future.sqlite3"
    connection = sqlite3.connect(str(future))
    connection.execute("PRAGMA user_version = 99")
    connection.commit()
    connection.close()
    probes = _spy_exam_reads(monkeypatch)
    for candidate in (tmp_path / "SENTINEL_ABSENT_DB_zzz.sqlite3", corrupt, future):
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "guiskindose",
                "--settings",
                str(settings_path),
                "--file-path",
                str(exam),
                "--input-schema",
                "generic_rdsr_like",
                "--equipment-profile-store",
                str(candidate),
            ],
        )
        with pytest.raises(SystemExit) as excinfo:
            cli()
        assert excinfo.value.code == 1
        err = capsys.readouterr().err
        assert "SENTINEL" not in err
        assert str(candidate) not in err
    assert probes == {"load": [], "dcmread": []}


def test_caller_preserved_and_gui_store(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    import argparse

    from guiskindose.main import prepare_cli_settings

    config = load_settings_example_json()
    config["mode"] = "calculate_dose"
    fresh = PyskindoseSettings(settings=config, output_format="dict")
    before_norm = _snapshot_norm(fresh.normalization_settings)
    missing = tmp_path / "SENTINEL_ABSENT_DB_zzz.sqlite3"
    namespace = argparse.Namespace(
        settings=fresh,
        output_format="json",
        plane_code_map="1:Single Plane",
        kerma_meter_correction=True,
        equipment_profile=None,
        equipment_profile_sheet=None,
        equipment_profile_store=str(missing),
        equipment_profile_id=None,
    )
    with pytest.raises(UserFacingInputError) as excinfo:
        prepare_cli_settings(namespace)
    assert "SENTINEL_ABSENT_DB_zzz" not in str(excinfo.value)
    assert fresh.output_format == "dict"
    assert fresh.equipment_profile_session is None
    assert _snapshot_norm(fresh.normalization_settings) == before_norm
    gui_app = pytest.importorskip("guiskindose.gui.app")
    called: list[bool] = []

    def _no_ui(**kwargs: Any) -> None:
        called.append(True)

    monkeypatch.setattr(gui_app, "run_gui", _no_ui)
    for argv in (
        ["guiskindose", "--mode", "gui", "--equipment-profile-store", str(missing)],
        ["guiskindose", "--mode", "gui", "--equipment-profile-id", "p-siemens"],
    ):
        monkeypatch.setattr(sys, "argv", argv)
        with pytest.raises(SystemExit) as excinfo:
            cli()
        assert excinfo.value.code == 1
        err = capsys.readouterr().err
        assert GUI_EQUIPMENT_PROFILES_MESSAGE in err
        assert "SENTINEL" not in err
    assert called == []


# ---------------------------------------------------------------------------
# Read-only lifetime hardening
# ---------------------------------------------------------------------------


class _HostilePath:
    """os.PathLike whose hook raises raw (never a real path)."""

    def __fspath__(self) -> str:
        raise RuntimeError("PRIVATE SENTINEL")


def test_hostile_path_hook_closed(tmp_path: Path) -> None:
    hostile: Any = _HostilePath()
    with pytest.raises(EquipmentProfileError) as excinfo:
        ProfileStore.open_read_only(hostile)
    assert excinfo.value.code is ProfileErrorCode.INVALID_TYPE
    assert "SENTINEL" not in str(excinfo.value)
    request = _store_namespace(store=hostile, ids=None)
    with pytest.raises(UserFacingInputError) as excinfo:
        equipment_session_from_args(request)
    assert "SENTINEL" not in str(excinfo.value)


def test_read_only_initialize_refused_without_filesystem(tmp_path: Path) -> None:
    db = _seed_store(tmp_path / "profiles.sqlite3", [_siemens_profile()], enabled=["p-siemens"])
    store = ProfileStore.open_read_only(db)
    store.close()
    db.unlink()
    with pytest.raises(EquipmentProfileError) as excinfo:
        store.initialize()
    assert excinfo.value.code is ProfileErrorCode.STORE_UNAVAILABLE
    assert not db.exists()


def test_read_only_writes_run_no_statements(tmp_path: Path) -> None:
    db = _seed_store(tmp_path / "profiles.sqlite3", [_siemens_profile()], enabled=["p-siemens"])
    store = ProfileStore.open_read_only(db)
    try:
        traced: list[str] = []
        # White-box read of the live connection: the trace callback is the
        # only precise probe that no statement (BEGIN included) executes.
        assert store._connection is not None
        store._connection.set_trace_callback(traced.append)
        candidate = _philips_profile()
        with pytest.raises(EquipmentProfileError) as excinfo:
            store.save_new_revision(candidate)
        assert excinfo.value.code is ProfileErrorCode.STORE_UNAVAILABLE
        assert traced == []
    finally:
        store.close()


def test_open_read_only_verify_failure_cleanup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import guiskindose.equipment_profiles.profile_store as store_module

    db = _seed_store(tmp_path / "profiles.sqlite3", [_siemens_profile()], enabled=["p-siemens"])
    before = _sha256(db)

    def _boom(connection: Any) -> None:
        raise RuntimeError("PRIVATE SENTINEL")

    monkeypatch.setattr(store_module, "verify_schema", _boom)
    with pytest.raises(EquipmentProfileError) as excinfo:
        ProfileStore.open_read_only(db)
    assert excinfo.value.code is ProfileErrorCode.STORE_CORRUPTION
    assert "SENTINEL" not in str(excinfo.value)
    monkeypatch.undo()
    assert _sha256(db) == before
    reopened = ProfileStore.open_read_only(db)
    try:
        assert [r.profile_id for r in reopened.list_records()] == ["p-siemens"]
    finally:
        reopened.close()


def test_open_read_only_cancellation_preserved(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import guiskindose.equipment_profiles.profile_store as store_module

    db = _seed_store(tmp_path / "profiles.sqlite3", [_siemens_profile()], enabled=["p-siemens"])

    def _cancel(connection: Any) -> None:
        raise KeyboardInterrupt()

    monkeypatch.setattr(store_module, "verify_schema", _cancel)
    with pytest.raises(KeyboardInterrupt):
        ProfileStore.open_read_only(db)
    monkeypatch.undo()
    reopened = ProfileStore.open_read_only(db)
    try:
        assert [r.profile_id for r in reopened.list_records()] == ["p-siemens"]
    finally:
        reopened.close()
