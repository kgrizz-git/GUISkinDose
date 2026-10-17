"""Tests for settings-JSON equipment-profile source requests (inert helper).

Covers the exact request grammar (absent/empty/files/store), canonical
parity against direct assembly, relative/CWD/absolute path semantics,
pre-I/O shape and bound validation, ID/sheet typing, capability/conflict
gates, no-publish on failure, and no path leakage into errors or
provenance. Profile files and store databases are generated per test under
``tmp_path``; no fixture binary is tracked.
"""

from __future__ import annotations

import dataclasses
import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from guiskindose.equipment_profiles import (
    FileSource,
    ProfileStore,
    assemble_session,
    parse_memory_document,
)
from guiskindose.equipment_profiles.errors import EquipmentProfileError, ProfileErrorCode
from guiskindose.settings_equipment_profiles import equipment_session_from_config
from tests.unittests.test_equipment_captured_input import (
    _philips_coordinates,
    _siemens_coordinates,
)


def _siemens_doc() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "profiles": [
            {
                "profile_id": "p-siemens",
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
                "profile_id": "p-philips",
                "manufacturer": "Philips",
                "models": ["Allura Clarity"],
                "coordinates": _philips_coordinates(),
            }
        ],
    }


def _json_file(tmp_path: Path, name: str, doc: dict[str, Any]) -> str:
    path = tmp_path / name
    path.write_text(json.dumps(doc), encoding="utf-8")
    return str(path)


def _csv_file(tmp_path: Path, name: str) -> str:
    import csv
    import io

    from guiskindose.equipment_profiles import FLAT_COLUMNS

    columns = list(FLAT_COLUMNS)
    head = [""] * len(columns)
    head[0] = "profile"
    head[1] = "p-siemens"
    head[columns.index("manufacturer")] = "Siemens"
    head[columns.index("models")] = "AXIOM-Artis"
    rows = [head]
    leaves = [
        ("translation_offset.x", "5.0"),
        ("translation_offset.y", "-3.5"),
        ("translation_offset.z", "0.0"),
        ("translation_direction.x", "-"),
        ("translation_direction.y", "+"),
        ("translation_direction.z", "+"),
        ("rotation_direction.Ap1", "-"),
        ("rotation_direction.Ap2", "+"),
        ("rotation_direction.Ap3", "+"),
        ("rotation_direction.At1", "+"),
        ("rotation_direction.At2", "-"),
        ("rotation_direction.At3", "+"),
        ("swap_lateral_longitudinal", "false"),
        ("field_size_mode", "CFA"),
        ("detector_side_length", "30"),
    ]
    for field, value in leaves:
        row = [""] * len(columns)
        row[0] = "coordinate"
        row[1] = "p-siemens"
        row[columns.index("field")] = field
        row[columns.index("value")] = value
        rows.append(row)
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(columns)
    writer.writerows(rows)
    path = tmp_path / name
    path.write_text(buffer.getvalue(), encoding="utf-8")
    return str(path)


def _seed_store(path: Path, profiles: list[Any], *, enabled: list[str]) -> Path:
    store = ProfileStore.open(path)
    try:
        for profile in profiles:
            store.save_new_revision(profile)
        for profile_id in enabled:
            record = next(r for r in store.list_records() if r.profile_id == profile_id)
            store.set_enabled(profile_id, True, expected_current_revision=record.current_revision)
    finally:
        store.close()
    return path


def _code(excinfo: pytest.ExceptionInfo[EquipmentProfileError]) -> ProfileErrorCode:
    return excinfo.value.code


def _named_workbook(tmp_path: Path, name: str, title: str) -> str:
    pytest.importorskip("openpyxl")
    from openpyxl import Workbook

    from guiskindose.equipment_profiles import FLAT_COLUMNS

    columns = list(FLAT_COLUMNS)
    workbook = Workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet.title = title
    sheet.append(columns)
    head = [""] * len(columns)
    head[0] = "profile"
    head[1] = "p-siemens"
    head[columns.index("manufacturer")] = "Siemens"
    head[columns.index("models")] = "AXIOM-Artis"
    sheet.append(head)
    for field, value in [
        ("translation_offset.x", "5.0"),
        ("translation_offset.y", "-3.5"),
        ("translation_offset.z", "0.0"),
        ("translation_direction.x", "-"),
        ("translation_direction.y", "+"),
        ("translation_direction.z", "+"),
        ("rotation_direction.Ap1", "-"),
        ("rotation_direction.Ap2", "+"),
        ("rotation_direction.Ap3", "+"),
        ("rotation_direction.At1", "+"),
        ("rotation_direction.At2", "-"),
        ("rotation_direction.At3", "+"),
        ("swap_lateral_longitudinal", "false"),
        ("field_size_mode", "CFA"),
        ("detector_side_length", "30"),
    ]:
        row = [""] * len(columns)
        row[0] = "coordinate"
        row[1] = "p-siemens"
        row[columns.index("field")] = field
        row[columns.index("value")] = value
        sheet.append(row)
    path = tmp_path / name
    workbook.save(path)
    return str(path)


# ---------------------------------------------------------------------------
# Absent, empty, and positive parity
# ---------------------------------------------------------------------------


def test_absent_config_returns_none(tmp_path: Path) -> None:
    assert equipment_session_from_config(None) is None
    assert equipment_session_from_config(None, tmp_path) is None


def test_explicit_empty_assembles_empty_session() -> None:
    empty = equipment_session_from_config({})
    assert empty is not None
    assert len(empty.profiles) == 0
    assert equipment_session_from_config({"files": []}) is not None


def test_files_parity_vs_direct(tmp_path: Path) -> None:
    siemens = _json_file(tmp_path, "siemens.json", _siemens_doc())
    config = {"files": [{"path": siemens}]}
    actual = equipment_session_from_config(config)
    expected = assemble_session(files=[FileSource(siemens)])
    assert actual is not None
    assert actual.active_set_hash == expected.active_set_hash
    assert [p.profile_id for p in actual.profiles] == ["p-siemens"]


def test_csv_config_parity_vs_direct(tmp_path: Path) -> None:
    profile = _csv_file(tmp_path, "siemens.csv")
    config = {"files": [{"path": profile, "format": "csv"}]}
    actual = equipment_session_from_config(config)
    expected = assemble_session(files=[FileSource(profile)])
    assert actual is not None
    assert actual.active_set_hash == expected.active_set_hash


def test_sheet_name_and_index_parity(tmp_path: Path) -> None:
    workbook = _named_workbook(tmp_path, "profiles.xlsx", "Target")
    named = equipment_session_from_config({"files": [{"path": workbook, "sheet": "Target"}]})
    indexed = equipment_session_from_config({"files": [{"path": workbook, "sheet": 0}]})
    direct = assemble_session(files=[FileSource(workbook, sheet=0)])
    assert named is not None
    assert indexed is not None
    assert named.active_set_hash == indexed.active_set_hash
    assert indexed.active_set_hash == direct.active_set_hash


def test_store_composition_parity(tmp_path: Path) -> None:
    philips = _json_file(tmp_path, "philips.json", _philips_doc())
    db = _seed_store(
        tmp_path / "profiles.sqlite3",
        [parse_memory_document(_siemens_doc()).profiles[0]],
        enabled=["p-siemens"],
    )
    config = {"files": [{"path": philips}], "store": {"path": str(db)}}
    actual = equipment_session_from_config(config)
    reader = ProfileStore.open_read_only(db)
    try:
        snapshot = reader.selected_snapshot()
    finally:
        reader.close()
    expected = assemble_session(files=[FileSource(philips)], snapshots=[snapshot])
    assert actual is not None
    assert actual.active_set_hash == expected.active_set_hash
    assert sorted(p.profile_id for p in actual.profiles) == ["p-philips", "p-siemens"]


def test_store_ids_and_enabled_semantics(tmp_path: Path) -> None:
    db = _seed_store(
        tmp_path / "profiles.sqlite3",
        [
            parse_memory_document(_siemens_doc()).profiles[0],
            parse_memory_document(_philips_doc()).profiles[0],
        ],
        enabled=["p-philips"],
    )
    wide = equipment_session_from_config({"store": {"path": str(db)}})
    assert wide is not None
    assert [p.profile_id for p in wide.profiles] == ["p-philips"]
    narrow = equipment_session_from_config({"store": {"path": str(db), "ids": ["p-siemens"]}})
    assert narrow is not None
    assert [p.profile_id for p in narrow.profiles] == ["p-siemens"]


# ---------------------------------------------------------------------------
# Path semantics: explicit base dir, CWD, absolute
# ---------------------------------------------------------------------------


def test_relative_base_dir_and_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    subdir = tmp_path / "conf"
    subdir.mkdir()
    profile = _json_file(subdir, "siemens.json", _siemens_doc())
    config = {"files": [{"path": "siemens.json"}]}
    based = equipment_session_from_config(config, subdir)
    assert based is not None
    assert [p.profile_id for p in based.profiles] == ["p-siemens"]
    monkeypatch.chdir(subdir)
    local = equipment_session_from_config(config)
    assert local is not None
    assert local.active_set_hash == based.active_set_hash
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    with pytest.raises(EquipmentProfileError) as excinfo:
        equipment_session_from_config(config, elsewhere)
    assert _code(excinfo) is ProfileErrorCode.UNREADABLE_SOURCE
    assert profile not in str(excinfo.value)


def test_absolute_paths_ignore_base(tmp_path: Path) -> None:
    profile = _json_file(tmp_path, "siemens.json", _siemens_doc())
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    config = {"files": [{"path": profile}]}
    actual = equipment_session_from_config(config, elsewhere)
    assert actual is not None
    assert [p.profile_id for p in actual.profiles] == ["p-siemens"]


# ---------------------------------------------------------------------------
# Pre-I/O shape matrix (pure mappings; nothing is read)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("config", "code"),
    [
        ([], ProfileErrorCode.INVALID_TYPE),
        ("block", ProfileErrorCode.INVALID_TYPE),
        (42, ProfileErrorCode.INVALID_TYPE),
        ({"files": [], "bogus": 1}, ProfileErrorCode.UNKNOWN_FIELD),
        ({"files": "s.json"}, ProfileErrorCode.INVALID_TYPE),
        ({"files": [{"path": "s.json"}, "nope"]}, ProfileErrorCode.INVALID_TYPE),
        ({"files": [{"path": "s.json", "nope": 1}]}, ProfileErrorCode.UNKNOWN_FIELD),
        ({"files": [{}]}, ProfileErrorCode.MISSING_REQUIRED_FIELD),
        ({"files": [{"path": 7}]}, ProfileErrorCode.INVALID_TYPE),
        ({"files": [{"path": "s.json", "format": "yaml"}]}, ProfileErrorCode.INVALID_ENUM),
        ({"files": [{"path": "s.json", "sheet": True}]}, ProfileErrorCode.VALUE_OUT_OF_RANGE),
        ({"files": [{"path": "s.json", "sheet": 1.5}]}, ProfileErrorCode.VALUE_OUT_OF_RANGE),
        ({"files": [{"path": "s.json", "sheet": -1}]}, ProfileErrorCode.VALUE_OUT_OF_RANGE),
        ({"files": [{"path": "s.json", "sheet": ""}]}, ProfileErrorCode.VALUE_OUT_OF_RANGE),
        ({"files": [{"path": "s.csv", "sheet": 0}]}, ProfileErrorCode.INVALID_TYPE),
        ({"store": "db"}, ProfileErrorCode.INVALID_TYPE),
        ({"store": {"path": "db", "nope": 1}}, ProfileErrorCode.UNKNOWN_FIELD),
        ({"store": {}}, ProfileErrorCode.MISSING_REQUIRED_FIELD),
        ({"store": {"path": "db", "ids": "p-siemens"}}, ProfileErrorCode.INVALID_TYPE),
        ({"store": {"path": "db", "ids": [7]}}, ProfileErrorCode.INVALID_PROFILE_ID),
        ({"store": {"path": "db", "ids": ["p-siemens", "p-siemens"]}}, ProfileErrorCode.DUPLICATE_PROFILE_ID),
    ],
)
def test_request_shapes_fail_before_io(config: Any, code: ProfileErrorCode) -> None:
    with pytest.raises(EquipmentProfileError) as excinfo:
        equipment_session_from_config(config)
    assert _code(excinfo) is code


def test_bounds_fail_before_io(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    real_connect = sqlite3.connect
    connects: list[str] = []

    def _spy_connect(*args: Any, **kwargs: Any) -> Any:
        connects.append(str(args[0]) if args else "")
        return real_connect(*args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", _spy_connect)
    many_files = {"files": [{"path": f"e{index}.json"} for index in range(65)]}
    with pytest.raises(EquipmentProfileError) as excinfo:
        equipment_session_from_config(many_files)
    assert _code(excinfo) is ProfileErrorCode.PROFILE_LIMIT_EXCEEDED
    many_mixed = {
        "files": [{"path": f"e{index}.json"} for index in range(64)],
        "store": {"path": str(tmp_path / "absent.sqlite3")},
    }
    with pytest.raises(EquipmentProfileError) as excinfo:
        equipment_session_from_config(many_mixed)
    assert _code(excinfo) is ProfileErrorCode.PROFILE_LIMIT_EXCEEDED
    many_ids = {"store": {"path": str(tmp_path / "absent.sqlite3"), "ids": [f"p-{index}" for index in range(65)]}}
    with pytest.raises(EquipmentProfileError) as excinfo:
        equipment_session_from_config(many_ids)
    assert _code(excinfo) is ProfileErrorCode.PROFILE_LIMIT_EXCEEDED
    assert connects == []


# ---------------------------------------------------------------------------
# Gates, conflicts, and privacy
# ---------------------------------------------------------------------------


def test_alias_and_transmission_gated(tmp_path: Path) -> None:
    aliased = _siemens_doc()
    aliased["profiles"][0]["model_aliases"] = ["AXIOMArtis"]
    alias_path = _json_file(tmp_path, "SENTINEL_ALIAS_SOURCE_zzz.json", aliased)
    with pytest.raises(EquipmentProfileError) as excinfo:
        equipment_session_from_config({"files": [{"path": alias_path}]})
    assert _code(excinfo) is ProfileErrorCode.UNSUPPORTED_PROFILE_CAPABILITY
    assert "SENTINEL_ALIAS_SOURCE_zzz" not in str(excinfo.value)
    transmission_doc = {
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
    trans_path = _json_file(tmp_path, "trans.json", transmission_doc)
    with pytest.raises(EquipmentProfileError) as excinfo:
        equipment_session_from_config({"files": [{"path": trans_path}]})
    assert _code(excinfo) is ProfileErrorCode.UNSUPPORTED_PROFILE_CAPABILITY


def test_conflict_publishes_nothing(tmp_path: Path) -> None:
    first = _json_file(tmp_path, "SENTINEL_FIRST_zzz.json", _siemens_doc())
    rival_doc = _siemens_doc()
    rival_doc["profiles"][0]["profile_id"] = "p-rival"
    rival_doc["profiles"][0]["coordinates"]["translation_offset"]["x"] = 9.0
    second = _json_file(tmp_path, "second.json", rival_doc)
    with pytest.raises(EquipmentProfileError) as excinfo:
        equipment_session_from_config({"files": [{"path": first}, {"path": second}]})
    assert _code(excinfo) is ProfileErrorCode.DUPLICATE_COORDINATE_CLAIM
    assert "SENTINEL_FIRST_zzz" not in str(excinfo.value)
    assert "p-rival" not in str(excinfo.value)


def test_malformed_late_request_zero_io(tmp_path: Path) -> None:
    missing = str(tmp_path / "SENTINEL_ABSENT_PROFILE_zzz.json")
    malformed = {"files": [{"path": missing}, {"path": 7}]}
    with pytest.raises(EquipmentProfileError) as excinfo:
        equipment_session_from_config(malformed)
    assert _code(excinfo) is ProfileErrorCode.INVALID_TYPE
    assert "SENTINEL_ABSENT_PROFILE_zzz" not in str(excinfo.value)
    store_malformed = {
        "store": {"path": str(tmp_path / "absent.sqlite3"), "ids": ["p-ok", "p-ok"]},
    }
    with pytest.raises(EquipmentProfileError) as excinfo:
        equipment_session_from_config(store_malformed)
    assert _code(excinfo) is ProfileErrorCode.DUPLICATE_PROFILE_ID


def test_provenance_carries_no_paths(tmp_path: Path) -> None:
    profile = _json_file(tmp_path, "SENTINEL_PROVENANCE_zzz.json", _siemens_doc())
    session = equipment_session_from_config({"files": [{"path": profile}]})
    assert session is not None
    assert "SENTINEL_PROVENANCE_zzz" not in repr(session.provenance)
    assert "SENTINEL_PROVENANCE_zzz" not in repr(session)


# ---------------------------------------------------------------------------
# Base/path policy, pre-I/O format and sheet gates
# ---------------------------------------------------------------------------


def _spy_profile_io(monkeypatch: pytest.MonkeyPatch) -> dict[str, list[str]]:
    """Record-delegate spies over store opens and session adapter readers."""
    import guiskindose.equipment_profiles.session as session_module
    from guiskindose.equipment_profiles import ProfileStore

    probes: dict[str, list[str]] = {
        "open_read_only": [],
        "parse_json_file": [],
        "parse_csv_file": [],
        "parse_tsv_file": [],
        "parse_xlsx_file": [],
    }
    real_open = ProfileStore.open_read_only

    def _spy_open(path: Any) -> Any:
        probes["open_read_only"].append(str(path))
        return real_open(path)

    monkeypatch.setattr(ProfileStore, "open_read_only", _spy_open)
    for name in ("parse_json_file", "parse_csv_file", "parse_tsv_file", "parse_xlsx_file"):
        real_parse = getattr(session_module, name)

        def _spy_parse(path: Any, *args: Any, _real: Any = real_parse, _name: str = name, **kwargs: Any) -> Any:
            probes[_name].append(str(path))
            return _real(path, *args, **kwargs)

        monkeypatch.setattr(session_module, name, _spy_parse)
    return probes


def _assert_no_profile_io(probes: dict[str, list[str]]) -> None:
    assert probes == {
        "open_read_only": [],
        "parse_json_file": [],
        "parse_csv_file": [],
        "parse_tsv_file": [],
        "parse_xlsx_file": [],
    }


def test_store_path_resolves_base(tmp_path: Path) -> None:
    from guiskindose.equipment_profiles import parse_memory_document

    base = tmp_path / "conf"
    base.mkdir()
    db = base / "profiles.sqlite3"
    writer = ProfileStore.open(db)
    try:
        writer.save_new_revision(parse_memory_document(_siemens_doc()).profiles[0])
        writer.set_enabled("p-siemens", True)
    finally:
        writer.close()
    config = {"store": {"path": "profiles.sqlite3"}}
    session = equipment_session_from_config(config, base)
    assert session is not None
    assert [p.profile_id for p in session.profiles] == ["p-siemens"]
    _json_file(base, "philips.json", _philips_doc())
    mixed = equipment_session_from_config(
        {"files": [{"path": "philips.json"}], "store": {"path": "profiles.sqlite3"}}, base
    )
    assert mixed is not None
    assert sorted(p.profile_id for p in mixed.profiles) == ["p-philips", "p-siemens"]
    absolute = equipment_session_from_config({"store": {"path": str(db)}}, tmp_path / "elsewhere")
    assert absolute is not None
    assert [p.profile_id for p in absolute.profiles] == ["p-siemens"]


def test_base_validation_closed(tmp_path: Path) -> None:
    import os

    profile = _json_file(tmp_path, "siemens.json", _siemens_doc())
    good = {"files": [{"path": profile}]}

    class _HostileBase(os.PathLike):
        def __fspath__(self) -> str:
            raise RuntimeError("PRIVATE SENTINEL")

    bad_bases: list[Any] = [
        123,
        b"bytes-base",
        "base\x00dir",
        "base\ud800dir",
        _HostileBase(),
    ]
    for bad in bad_bases:
        with pytest.raises(EquipmentProfileError) as excinfo:
            equipment_session_from_config(good, bad)
        assert _code(excinfo) is ProfileErrorCode.INVALID_TYPE
        assert "SENTINEL" not in str(excinfo.value)


def test_empty_and_surrogate_paths_refused() -> None:
    for bad in ("", "a\ud800b.json"):
        with pytest.raises(EquipmentProfileError) as excinfo:
            equipment_session_from_config({"files": [{"path": bad}]})
        assert _code(excinfo) is ProfileErrorCode.INVALID_TYPE
        encoded = str(excinfo.value).encode("ascii")
        assert isinstance(encoded, bytes)
    with pytest.raises(EquipmentProfileError) as excinfo:
        equipment_session_from_config({"store": {"path": ""}})
    assert _code(excinfo) is ProfileErrorCode.INVALID_TYPE


def test_unsupported_format_and_sheet_range_pre_io(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from guiskindose.equipment_profiles import parse_memory_document

    db = tmp_path / "profiles.sqlite3"
    writer = ProfileStore.open(db)
    try:
        writer.save_new_revision(parse_memory_document(_siemens_doc()).profiles[0])
        writer.set_enabled("p-siemens", True)
    finally:
        writer.close()
    probes = _spy_profile_io(monkeypatch)
    bad_suffix = {"files": [{"path": "SENTINEL_BAD_zzz.yaml"}], "store": {"path": str(db)}}
    with pytest.raises(EquipmentProfileError) as excinfo:
        equipment_session_from_config(bad_suffix)
    assert _code(excinfo) is ProfileErrorCode.UNSUPPORTED_SOURCE_SUFFIX
    assert "SENTINEL_BAD_zzz" not in str(excinfo.value)
    workbook = _named_workbook(tmp_path, "profiles.xlsx", "Target")
    for bad_sheet in (16, 10**30):
        ranged = {"files": [{"path": workbook, "sheet": bad_sheet}], "store": {"path": str(db)}}
        with pytest.raises(EquipmentProfileError) as excinfo:
            equipment_session_from_config(ranged)
        assert _code(excinfo) is ProfileErrorCode.VALUE_OUT_OF_RANGE
    _assert_no_profile_io(probes)
    with pytest.raises(EquipmentProfileError) as excinfo:
        equipment_session_from_config({"files": [{"path": workbook, "sheet": 15}]})
    assert _code(excinfo) is ProfileErrorCode.UNKNOWN_SHEET


def test_exact_keys_and_key_count(tmp_path: Path) -> None:
    profile = _json_file(tmp_path, "siemens.json", _siemens_doc())

    class _EvilKey(str):
        __hash__ = str.__hash__

        def __eq__(self, other: object) -> bool:
            raise AssertionError("key equality must never run")

    evil_config = {_EvilKey("files"): [{"path": profile}]}
    with pytest.raises(EquipmentProfileError) as excinfo:
        equipment_session_from_config(evil_config)
    assert _code(excinfo) is ProfileErrorCode.INVALID_TYPE
    with pytest.raises(EquipmentProfileError) as excinfo:
        equipment_session_from_config({"files": [], "a": 1, "b": 2, "c": 3})
    assert _code(excinfo) is ProfileErrorCode.UNKNOWN_FIELD
    entry: dict[Any, Any] = {"path": profile, "format": "json", "sheet": 0, "extra": 1}
    with pytest.raises(EquipmentProfileError) as excinfo:
        equipment_session_from_config({"files": [entry]})
    assert _code(excinfo) is ProfileErrorCode.UNKNOWN_FIELD


def test_shape_refusals_touch_nothing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _json_file(tmp_path, "siemens.json", _siemens_doc())
    db = tmp_path / "profiles.sqlite3"
    probes = _spy_profile_io(monkeypatch)
    malformed = {"files": [{"path": str(tmp_path / "absent.json")}, {"path": 7}]}
    with pytest.raises(EquipmentProfileError) as excinfo:
        equipment_session_from_config(malformed)
    assert _code(excinfo) is ProfileErrorCode.INVALID_TYPE
    store_malformed = {"store": {"path": str(db), "ids": ["p-ok", 7]}}
    with pytest.raises(EquipmentProfileError) as excinfo:
        equipment_session_from_config(store_malformed)
    assert _code(excinfo) is ProfileErrorCode.INVALID_PROFILE_ID
    over = {
        "files": [{"path": f"e{index}.json"} for index in range(64)],
        "store": {"path": str(db)},
    }
    with pytest.raises(EquipmentProfileError) as excinfo:
        equipment_session_from_config(over)
    assert _code(excinfo) is ProfileErrorCode.PROFILE_LIMIT_EXCEEDED
    _assert_no_profile_io(probes)


def test_validated_request_seam() -> None:
    from guiskindose.settings_equipment_profiles import _parse_request

    request = _parse_request(
        {"files": [{"path": "siemens.json"}], "store": {"path": "db.sqlite3", "ids": ["p-siemens"]}},
        None,
    )
    assert repr(request) == "ValidatedRequest(files=1, store=True)"
    assert "siemens.json" not in repr(request)
    assert "p-siemens" not in repr(request)
    assert "db.sqlite3" not in repr(request)
    bare = _parse_request({"files": [{"path": "siemens.json"}]}, None)
    assert repr(bare) == "ValidatedRequest(files=1, store=False)"
    assignment_target: Any = request
    with pytest.raises(dataclasses.FrozenInstanceError):
        assignment_target.files = ()


class _RaisingString(str):
    __hash__ = str.__hash__

    def __eq__(self, other: object) -> bool:
        raise RuntimeError("PRIVATE KEY SENTINEL")

    def encode(self, *args: Any, **kwargs: Any) -> bytes:
        raise RuntimeError("PRIVATE BASE SENTINEL")


def test_store_keys_validate_before_lookup(monkeypatch: pytest.MonkeyPatch) -> None:
    probes = _spy_profile_io(monkeypatch)
    request = {"store": {_RaisingString("ids"): ["p-one"], "path": "db.sqlite3"}}
    with pytest.raises(EquipmentProfileError) as excinfo:
        equipment_session_from_config(request)
    assert excinfo.value.code is ProfileErrorCode.INVALID_TYPE
    assert "SENTINEL" not in str(excinfo.value)
    _assert_no_profile_io(probes)


def test_base_string_subclass_rejected_without_hooks(monkeypatch: pytest.MonkeyPatch) -> None:
    probes = _spy_profile_io(monkeypatch)
    base = _RaisingString("base")
    with pytest.raises(EquipmentProfileError) as excinfo:
        equipment_session_from_config({}, base)
    assert excinfo.value.code is ProfileErrorCode.INVALID_TYPE
    assert "SENTINEL" not in str(excinfo.value)
    _assert_no_profile_io(probes)


@pytest.mark.parametrize("sheet", ["name\x00suffix", "name\ud800suffix"])
def test_sheet_unicode_validation_precedes_store_open(
    monkeypatch: pytest.MonkeyPatch, sheet: str
) -> None:
    probes = _spy_profile_io(monkeypatch)
    request = {"files": [{"path": "p.xlsx", "sheet": sheet}], "store": {"path": "db.sqlite3"}}
    with pytest.raises(EquipmentProfileError) as excinfo:
        equipment_session_from_config(request)
    assert excinfo.value.code is ProfileErrorCode.VALUE_OUT_OF_RANGE
    _assert_no_profile_io(probes)


def test_store_ids_require_exact_strings(monkeypatch: pytest.MonkeyPatch) -> None:
    probes = _spy_profile_io(monkeypatch)
    request = {"store": {"path": "db.sqlite3", "ids": [_RaisingString("p-one"), "p-one"]}}
    with pytest.raises(EquipmentProfileError) as excinfo:
        equipment_session_from_config(request)
    assert excinfo.value.code is ProfileErrorCode.INVALID_PROFILE_ID
    _assert_no_profile_io(probes)
