"""Tests for direct settings source-block support (constructor + initialize).

Covers dict/JSON/file-base/absolute/store compositions with geometry, PSD,
match, and serialization parity against existing sessions; closed refusal
for block+session conflicts and malformed blocks (never through the legacy
fallback); caller mapping purity; and capability gates. Profile files and
store databases are generated per test under ``tmp_path``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from guiskindose import get_path_to_example_rdsr_files, load_settings_example_json
from guiskindose.equipment_profiles import (
    FileSource,
    ProfileStore,
    assemble_session,
    parse_memory_document,
)
from guiskindose.equipment_profiles.errors import EquipmentProfileError, ProfileErrorCode
from guiskindose.main import main
from guiskindose.settings import PyskindoseSettings, initialize_settings
from tests.unittests.test_equipment_captured_input import (
    _philips_coordinates,
    _siemens_coordinates,
)

_SIEMENS_DICOM = get_path_to_example_rdsr_files() / "siemens_axiom_artis.dcm"


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


def _profile_file(tmp_path: Path, name: str, doc: dict[str, Any]) -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(doc), encoding="utf-8")
    return path


def _base_config() -> dict[str, Any]:
    config = load_settings_example_json()
    config["mode"] = "calculate_dose"
    return config


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


# ---------------------------------------------------------------------------
# Positive parity: dict, JSON, base-relative, absolute, store
# ---------------------------------------------------------------------------


def test_dict_block_assembles_and_calculates(tmp_path: Path) -> None:
    profile = _profile_file(tmp_path, "siemens.json", _siemens_doc())
    config = _base_config()
    config["equipment_profiles"] = {"files": [{"path": str(profile)}]}
    settings = PyskindoseSettings(settings=config, output_format="dict")
    assert settings.equipment_profile_session is not None
    output: Any = main(file_path=str(_SIEMENS_DICOM), settings=settings)
    assert output["equipment_profile_match"]["profile_id"] == "p-siemens"
    expected = assemble_session(files=[FileSource(str(profile))])
    assert output["equipment_profile_match"]["active_set_hash"] == expected.active_set_hash
    assert "equipment_profiles" not in settings.to_settings_dict()
    assert "equipment_profiles" not in settings.to_json()


def test_json_str_block_with_base_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _profile_file(tmp_path, "siemens.json", _siemens_doc())
    config = _base_config()
    config["equipment_profiles"] = {"files": [{"path": "siemens.json"}]}
    monkeypatch.chdir(tmp_path)
    settings = PyskindoseSettings(settings=json.dumps(config), output_format="dict")
    assert settings.equipment_profile_session is not None
    output: Any = main(file_path=str(_SIEMENS_DICOM), settings=settings)
    assert output["equipment_profile_match"]["profile_id"] == "p-siemens"


def test_file_base_relative_and_absolute(tmp_path: Path) -> None:
    conf_dir = tmp_path / "conf"
    conf_dir.mkdir()
    profile = _profile_file(conf_dir, "siemens.json", _siemens_doc())

    def _configured(block: Any) -> dict[str, Any]:
        config = load_settings_example_json()
        config["mode"] = "calculate_dose"
        config["equipment_profiles"] = block
        return config

    relative = PyskindoseSettings(
        settings=_configured({"files": [{"path": "siemens.json"}]}),
        output_format="dict",
        settings_base_dir=conf_dir,
    )
    relative_session = relative.equipment_profile_session
    assert relative_session is not None
    assert [p.profile_id for p in relative_session.profiles] == ["p-siemens"]
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    absolute = PyskindoseSettings(
        settings=_configured({"files": [{"path": str(profile)}]}),
        output_format="dict",
        settings_base_dir=elsewhere,
    )
    absolute_session = absolute.equipment_profile_session
    assert absolute_session is not None
    assert absolute_session.active_set_hash == relative_session.active_set_hash


def test_store_block_enabled_and_ids(tmp_path: Path) -> None:
    db = _seed_store(
        tmp_path / "profiles.sqlite3",
        [parse_memory_document(_siemens_doc()).profiles[0]],
        enabled=[],
    )
    config = _base_config()
    config["equipment_profiles"] = {"store": {"path": str(db)}}
    baseline = PyskindoseSettings(settings=config, output_format="dict")
    baseline_session = baseline.equipment_profile_session
    assert baseline_session is not None
    assert len(baseline_session.profiles) == 0
    config["equipment_profiles"] = {"store": {"path": str(db), "ids": ["p-siemens"]}}
    selected = PyskindoseSettings(settings=config, output_format="dict")
    selected_session = selected.equipment_profile_session
    assert selected_session is not None
    assert [p.profile_id for p in selected_session.profiles] == ["p-siemens"]
    output: Any = main(file_path=str(_SIEMENS_DICOM), settings=selected)
    assert output["equipment_profile_match"]["profile_id"] == "p-siemens"


# ---------------------------------------------------------------------------
# Closed refusals and fallback immunity
# ---------------------------------------------------------------------------


def test_block_plus_session_refuses_before_io(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import guiskindose.equipment_profiles.session as session_module

    profile = _profile_file(tmp_path, "siemens.json", _siemens_doc())
    session = assemble_session(files=[FileSource(str(profile))])
    config = _base_config()
    config["equipment_profiles"] = {"files": [{"path": str(profile)}]}
    reads: list[str] = []
    real_parse = session_module.parse_json_file

    def _spy_parse(path: Any, *args: Any, **kwargs: Any) -> Any:
        reads.append(str(path))
        return real_parse(path, *args, **kwargs)

    monkeypatch.setattr(session_module, "parse_json_file", _spy_parse)
    real_mkdir: Any = Path.mkdir

    def _spy_mkdir(self: Any, *args: Any, **kwargs: Any) -> Any:
        reads.append(f"mkdir:{self}")
        return real_mkdir(self, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", _spy_mkdir)
    with pytest.raises(EquipmentProfileError) as excinfo:
        PyskindoseSettings(settings=config, equipment_profile_session=session)
    assert _code(excinfo) is ProfileErrorCode.INVALID_TYPE
    empty_config = _base_config()
    empty_config["equipment_profiles"] = {}
    with pytest.raises(EquipmentProfileError) as excinfo:
        PyskindoseSettings(settings=empty_config, equipment_profile_session=session)
    assert _code(excinfo) is ProfileErrorCode.INVALID_TYPE
    assert reads == []


def test_wrong_session_type_refuses_unchanged() -> None:
    config = _base_config()
    bogus: Any = "nope"
    with pytest.raises(ValueError) as excinfo:
        PyskindoseSettings(settings=config, equipment_profile_session=bogus)
    assert str(excinfo.value) == "equipment_profile_session must be an EquipmentProfileSession or None."


def test_source_bearing_mistype_closed(tmp_path: Path) -> None:
    profile = _profile_file(tmp_path, "siemens.json", _siemens_doc())
    config = _base_config()
    config["equipment_profiles"] = {"files": [{"path": str(profile)}]}
    bogus: Any = "nope"
    with pytest.raises(EquipmentProfileError) as excinfo:
        PyskindoseSettings(settings=config, equipment_profile_session=bogus)
    assert _code(excinfo) is ProfileErrorCode.INVALID_TYPE


def test_invalid_block_never_falls_back(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import guiskindose.settings.pyskindose_settings as settings_module

    profile = _profile_file(tmp_path, "siemens.json", _siemens_doc())
    bad = {"mode": "calculate_dose", "equipment_profiles": {"files": [{"path": str(profile)}, {"path": 7}]}}
    mkdir_calls: list[str] = []
    real_mkdir = Path.mkdir

    def _spy_mkdir(self: Any, *args: Any, **kwargs: Any) -> Any:
        mkdir_calls.append(str(self))
        return real_mkdir(self, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", _spy_mkdir)
    real_output_path = settings_module.PyskindoseSettings._initialize_output_path

    def _spy_output_path(*args: Any, **kwargs: Any) -> Any:
        mkdir_calls.append("output-path")
        return real_output_path(*args, **kwargs)

    monkeypatch.setattr(
        settings_module.PyskindoseSettings,
        "_initialize_output_path",
        staticmethod(_spy_output_path),
    )
    with pytest.raises(EquipmentProfileError) as excinfo:
        PyskindoseSettings(settings=bad)
    assert _code(excinfo) is ProfileErrorCode.INVALID_TYPE
    from guiskindose.helpers.parse_settings_to_settings_class import parse_settings_to_settings_class

    with pytest.raises(EquipmentProfileError) as excinfo:
        parse_settings_to_settings_class(settings=bad)
    assert _code(excinfo) is ProfileErrorCode.INVALID_TYPE
    assert mkdir_calls == []


def test_malformed_json_still_value_error() -> None:
    with pytest.raises(ValueError):
        PyskindoseSettings(settings="{not json")


def test_duplicate_json_keys_fail_closed(tmp_path: Path) -> None:
    profile = _profile_file(tmp_path, "siemens.json", _siemens_doc())
    config = _base_config()
    config["equipment_profiles"] = {"files": [{"path": str(profile)}]}
    duped = json.dumps(config).replace('"mode": "calculate_dose"', '"mode": "x", "mode": "y"')
    with pytest.raises(EquipmentProfileError) as excinfo:
        PyskindoseSettings(settings=duped)
    assert _code(excinfo) is ProfileErrorCode.DUPLICATE_JSON_KEY


def test_source_cap_closed(tmp_path: Path) -> None:
    many = {"mode": "calculate_dose", "equipment_profiles": {"files": [{"path": f"e{i}.json"} for i in range(65)]}}
    with pytest.raises(EquipmentProfileError) as excinfo:
        PyskindoseSettings(settings=many)
    assert _code(excinfo) is ProfileErrorCode.PROFILE_LIMIT_EXCEEDED


def test_prebound_object_stable() -> None:
    session = assemble_session(documents=[_siemens_doc()])
    config = _base_config()
    bound = PyskindoseSettings(settings=config, equipment_profile_session=session)
    assert initialize_settings(bound) is bound
    assert initialize_settings(bound, settings_base_dir="/tmp") is bound
    assert bound.equipment_profile_session is session


def test_caller_dict_purity(tmp_path: Path) -> None:
    profile = _profile_file(tmp_path, "siemens.json", _siemens_doc())
    config = _base_config()
    config["equipment_profiles"] = {"files": [{"path": str(profile)}]}
    before = json.loads(json.dumps(config))
    settings = PyskindoseSettings(settings=config, output_format="dict")
    assert settings.equipment_profile_session is not None
    assert config == before


def test_constructor_parity_full_dose(tmp_path: Path) -> None:
    profile = _profile_file(tmp_path, "siemens.json", _siemens_doc())
    config = _base_config()
    config["equipment_profiles"] = {"files": [{"path": str(profile)}]}
    via_config = PyskindoseSettings(settings=config, output_format="dict")
    out_config: Any = main(file_path=str(_SIEMENS_DICOM), settings=via_config)
    session = assemble_session(files=[FileSource(str(profile))])
    plain_config = _base_config()
    via_explicit = PyskindoseSettings(
        settings=plain_config, output_format="dict", equipment_profile_session=session
    )
    out_explicit: Any = main(file_path=str(_SIEMENS_DICOM), settings=via_explicit)
    assert out_config["psd"] == out_explicit["psd"]
    assert out_config["dose_map"] == out_explicit["dose_map"]
    assert out_config["equipment_profile_match"] == out_explicit["equipment_profile_match"]


def test_initialize_settings_file_store_different_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from guiskindose.equipment_profiles import parse_memory_document

    conf_dir = tmp_path / "conf"
    conf_dir.mkdir()
    _profile_file(conf_dir, "siemens.json", _siemens_doc())
    db = _seed_store(
        conf_dir / "profiles.sqlite3",
        [parse_memory_document(_philips_doc()).profiles[0]],
        enabled=["p-philips"],
    )
    config = _base_config()
    config["equipment_profiles"] = {
        "files": [{"path": "siemens.json"}],
        "store": {"path": "profiles.sqlite3"},
    }
    work_dir = tmp_path / "work"
    work_dir.mkdir()
    monkeypatch.chdir(work_dir)
    settings = initialize_settings(config, settings_base_dir=conf_dir)
    assert settings.equipment_profile_session is not None
    assert sorted(p.profile_id for p in settings.equipment_profile_session.profiles) == [
        "p-philips",
        "p-siemens",
    ]
    settings.output_format = "dict"
    output: Any = main(file_path=str(_SIEMENS_DICOM), settings=settings)
    assert output["equipment_profile_match"]["profile_id"] == "p-siemens"
    assert db.exists()


def test_alias_capability_remains_gated(tmp_path: Path) -> None:
    aliased = _siemens_doc()
    aliased["profiles"][0]["model_aliases"] = ["AXIOMArtis"]
    alias_path = _profile_file(tmp_path, "SENTINEL_ALIAS_zzz.json", aliased)
    alias_config = {"mode": "calculate_dose", "equipment_profiles": {"files": [{"path": str(alias_path)}]}}
    with pytest.raises(EquipmentProfileError) as excinfo:
        PyskindoseSettings(settings=alias_config)
    assert _code(excinfo) is ProfileErrorCode.UNSUPPORTED_PROFILE_CAPABILITY
    assert "SENTINEL_ALIAS_zzz" not in str(excinfo.value)


def test_cli_single_assemble_no_duplicate_read(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    import sys

    import guiskindose.equipment_profiles.session as session_module

    profile = _profile_file(tmp_path, "siemens.json", _siemens_doc())
    config = _base_config()
    config["equipment_profiles"] = {"files": [{"path": str(profile)}]}
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(json.dumps(config), encoding="utf-8")
    reads: list[str] = []
    real_parse = session_module.parse_json_file

    def _spy_parse(path: Any, *args: Any, **kwargs: Any) -> Any:
        reads.append(str(path))
        return real_parse(path, *args, **kwargs)

    monkeypatch.setattr(session_module, "parse_json_file", _spy_parse)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "guiskindose",
            "--settings",
            str(settings_path),
            "--file-path",
            str(_SIEMENS_DICOM),
            "--output-format",
            "json",
        ],
    )
    from guiskindose.__main__ import cli

    cli()
    assert reads == [str(profile)]


def test_absent_and_empty_source_blocks() -> None:
    no_block = PyskindoseSettings(_base_config(), output_format="dict")
    assert no_block.equipment_profile_session is None
    config = _base_config()
    config["equipment_profiles"] = None
    explicit = assemble_session()
    absent = PyskindoseSettings(config, output_format="dict", equipment_profile_session=explicit)
    assert absent.equipment_profile_session is explicit
    config["equipment_profiles"] = {}
    empty = PyskindoseSettings(config, output_format="dict")
    session = empty.equipment_profile_session
    assert session is not None
    assert session.profiles == ()
