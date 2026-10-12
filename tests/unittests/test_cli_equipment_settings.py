"""Tests for headless CLI settings-JSON source wiring and CLI+config composition.

Settings files, profile files, and store databases are generated per test
under ``tmp_path``; no fixture binary is tracked. Covers settings-file base
resolution from another working directory, inline JSON/dict configs,
CLI+config disjoint hash/dose parity, cross-side conflicts, malformed-side
failures with zero I/O, the combined source cap, ID semantics through
wiring, output serialization purity, pre-bound refusal, staging, preview/
export/multi failure atomicity, the JSON-decode fallback, and the GUI
config guard. No tracked binaries are used.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

import pytest

from guiskindose import get_path_to_example_rdsr_files, load_settings_example_json
from guiskindose.__main__ import cli
from guiskindose.equipment_profiles import (
    FileSource,
    ProfileStore,
    assemble_session,
    parse_memory_document,
)
from guiskindose.main import main, prepare_cli_settings
from guiskindose.privacy import UserFacingInputError
from guiskindose.settings import PyskindoseSettings
from tests.unittests.test_cli_equipment_profiles import _settings_file, _stdout_json
from tests.unittests.test_equipment_captured_input import (
    _GENERIC_HEADER,
    _GENERIC_SIEMENS_ROW,
    _dose_settings,
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


def _write_text(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def _profile_file(tmp_path: Path, name: str, doc: dict[str, Any]) -> Path:
    return _write_text(tmp_path / name, json.dumps(doc))


def _settings_with_block(tmp_path: Path, name: str, block: Any) -> Path:
    config = load_settings_example_json()
    config["mode"] = "calculate_dose"
    config["equipment_profiles"] = block
    return _write_text(tmp_path / name, json.dumps(config))


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


def _code(excinfo: pytest.ExceptionInfo[BaseException]) -> str:
    return str(getattr(excinfo.value, "code", ""))


# ---------------------------------------------------------------------------
# Config file base resolution and inline configs
# ---------------------------------------------------------------------------


def test_config_file_relative_base_different_cwd(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    conf_dir = tmp_path / "conf"
    conf_dir.mkdir()
    profile = _profile_file(conf_dir, "siemens.json", _siemens_doc())
    db = _seed_store(
        conf_dir / "profiles.sqlite3",
        [parse_memory_document(_philips_doc()).profiles[0]],
        enabled=["p-philips"],
    )
    settings_path = _settings_with_block(
        conf_dir,
        "settings.json",
        {"files": [{"path": "siemens.json"}], "store": {"path": "profiles.sqlite3"}},
    )
    work_dir = tmp_path / "work"
    work_dir.mkdir()
    monkeypatch.chdir(work_dir)
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
    cli()
    payload = _stdout_json(capsys)
    assert payload["equipment_profile_match"]["profile_id"] == "p-siemens"
    snapshot_source = ProfileStore.open_read_only(db)
    try:
        snapshot = snapshot_source.selected_snapshot()
    finally:
        snapshot_source.close()
    expected = assemble_session(files=[FileSource(str(profile))], snapshots=[snapshot])
    assert payload["equipment_profile_match"]["active_set_hash"] == expected.active_set_hash


def test_inline_json_and_dict_configs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # NOTE: argparse coerces --settings to Path, so inline JSON reaches
    # prepare only programmatically (mirroring test_cli_kerma_meter); the
    # file-based CLI path is covered by test_config_file_relative_base_*.
    _profile_file(tmp_path, "siemens.json", _siemens_doc())
    config = load_settings_example_json()
    config["mode"] = "calculate_dose"
    config["equipment_profiles"] = {"files": [{"path": "siemens.json"}]}
    monkeypatch.chdir(tmp_path)
    json_namespace = argparse.Namespace(
        settings=json.dumps(config),
        output_format="json",
        plane_code_map=None,
        equipment_profile=None,
        equipment_profile_sheet=None,
        equipment_profile_store=None,
        equipment_profile_id=None,
    )
    json_settings = prepare_cli_settings(json_namespace)
    assert json_settings.equipment_profile_session is not None
    json_output: Any = main(file_path=str(_SIEMENS_DICOM), settings=json_settings)
    assert json.loads(json_output)["equipment_profile_match"]["profile_id"] == "p-siemens"
    dict_namespace = argparse.Namespace(
        settings=dict(config),
        output_format="dict",
        plane_code_map=None,
        equipment_profile=None,
        equipment_profile_sheet=None,
        equipment_profile_store=None,
        equipment_profile_id=None,
    )
    dict_settings = prepare_cli_settings(dict_namespace)
    assert dict_settings.equipment_profile_session is not None
    assert "equipment_profiles" in config
    dict_output: Any = main(file_path=str(_SIEMENS_DICOM), settings=dict_settings)
    assert dict_output["psd"] == json.loads(json_output)["psd"]


# ---------------------------------------------------------------------------
# CLI+config composition
# ---------------------------------------------------------------------------


def test_cli_config_disjoint_hash_dose_parity(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    cli_profile = _profile_file(tmp_path, "philips.json", _philips_doc())
    conf_dir = tmp_path / "conf"
    conf_dir.mkdir()
    conf_profile = _profile_file(conf_dir, "siemens.json", _siemens_doc())
    settings_path = _settings_with_block(
        conf_dir, "settings.json", {"files": [{"path": "siemens.json"}]}
    )
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
            "--equipment-profile",
            str(cli_profile),
        ],
    )
    cli()
    payload = _stdout_json(capsys)
    expected_session = assemble_session(
        files=[FileSource(str(cli_profile)), FileSource(str(conf_profile))]
    )
    assert payload["equipment_profile_match"]["active_set_hash"] == expected_session.active_set_hash
    config = json.loads(settings_path.read_text(encoding="utf-8"))
    del config["equipment_profiles"]
    expected_output: Any = main(
        file_path=str(_SIEMENS_DICOM),
        settings=PyskindoseSettings(
            settings=config,
            output_format="dict",
            equipment_profile_session=expected_session,
        ),
    )
    assert payload["psd"] == expected_output["psd"]
    assert payload["equipment_profile_match"] == expected_output["equipment_profile_match"]


def test_duplicate_conflicts_across_sides(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    profile = _profile_file(tmp_path, "siemens.json", _siemens_doc())
    rival_doc = _siemens_doc()
    rival_doc["profiles"][0]["profile_id"] = "p-rival"
    rival_doc["profiles"][0]["coordinates"]["translation_offset"]["x"] = 9.0
    conf_dir = tmp_path / "conf"
    conf_dir.mkdir()
    _profile_file(conf_dir, "rival.json", rival_doc)
    settings_path = _settings_with_block(conf_dir, "settings.json", {"files": [{"path": "rival.json"}]})
    probes = _spy_exam_reads(monkeypatch)
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
            "--equipment-profile",
            str(profile),
        ],
    )
    with pytest.raises(SystemExit) as excinfo:
        cli()
    assert excinfo.value.code == 1
    err = capsys.readouterr().err
    assert "duplicate_coordinate_claim" in err
    assert "p-rival" not in err
    assert probes == {"load": [], "dcmread": []}
    same_both = _settings_with_block(conf_dir, "same.json", {"files": [{"path": str(profile)}]})
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "guiskindose",
            "--settings",
            str(same_both),
            "--file-path",
            str(_SIEMENS_DICOM),
            "--output-format",
            "json",
            "--equipment-profile",
            str(profile),
        ],
    )
    with pytest.raises(SystemExit) as excinfo:
        cli()
    assert excinfo.value.code == 1
    assert "duplicate_profile_id" in capsys.readouterr().err


def test_malformed_late_side_zero_io(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    _profile_file(tmp_path, "siemens.json", _siemens_doc())
    settings_path = _settings_with_block(
        tmp_path, "settings.json", {"files": [{"path": str(tmp_path / "siemens.json")}, {"path": 7}]}
    )
    probes = _spy_exam_reads(monkeypatch)
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
    with pytest.raises(SystemExit) as excinfo:
        cli()
    assert excinfo.value.code == 1
    assert "invalid_type" in capsys.readouterr().err
    assert probes == {"load": [], "dcmread": []}
    namespace = argparse.Namespace(
        settings=_settings_file(tmp_path),
        output_format=None,
        plane_code_map=None,
        equipment_profile=[123],
        equipment_profile_sheet=None,
        equipment_profile_store=None,
        equipment_profile_id=None,
    )
    with pytest.raises(UserFacingInputError) as excinfo:
        prepare_cli_settings(namespace)
    assert "must be explicit paths" in str(excinfo.value)
    shape_namespace = argparse.Namespace(
        settings=_settings_file(tmp_path),
        output_format=None,
        plane_code_map=None,
        equipment_profile=(path for path in ["siemens.json"]),
        equipment_profile_sheet=None,
        equipment_profile_store=None,
        equipment_profile_id=None,
    )
    with pytest.raises(UserFacingInputError) as excinfo:
        prepare_cli_settings(shape_namespace)
    assert "must be a list of explicit paths" in str(excinfo.value)


def test_combined_cap_before_io(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    import guiskindose.cli_settings as cli_settings_module

    real_connect = sqlite3.connect
    connects: list[str] = []

    def _spy_connect(*args: Any, **kwargs: Any) -> Any:
        connects.append(str(args[0]) if args else "")
        return real_connect(*args, **kwargs)

    def _boom_construction(settings: Any = None) -> Any:
        raise AssertionError("construction ran before validation")

    monkeypatch.setattr(sqlite3, "connect", _spy_connect)
    monkeypatch.setattr(cli_settings_module, "parse_settings_to_settings_class", _boom_construction)
    probes = _spy_exam_reads(monkeypatch)
    cli_paths = [str(tmp_path / f"missing-{index}.json") for index in range(64)]
    settings_path = _settings_with_block(
        tmp_path, "settings.json", {"files": [{"path": "one-more.json"}]}
    )
    argv = [
        "guiskindose",
        "--settings",
        str(settings_path),
        "--file-path",
        str(_SIEMENS_DICOM),
        "--output-format",
        "json",
    ]
    for path in cli_paths:
        argv.extend(["--equipment-profile", path])
    monkeypatch.setattr(sys, "argv", argv)
    with pytest.raises(SystemExit) as excinfo:
        cli()
    assert excinfo.value.code == 1
    assert "profile_limit_exceeded" in capsys.readouterr().err
    assert probes == {"load": [], "dcmread": []}
    assert connects == []


def test_disabled_ids_current_rev_through_wiring(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    from guiskindose.equipment_profiles import parse_memory_document

    siemens_v1 = parse_memory_document(_siemens_doc()).profiles[0]
    v2_doc = _siemens_doc()
    v2_doc["profiles"][0]["coordinates"]["translation_offset"]["x"] = 9.0
    siemens_v2 = parse_memory_document(v2_doc).profiles[0]
    db = tmp_path / "profiles.sqlite3"
    writer = ProfileStore.open(db)
    try:
        writer.save_new_revision(siemens_v1)
        writer.save_new_revision(siemens_v2, expected_current_revision=1)
        writer.set_enabled("p-siemens", False, expected_current_revision=2)
    finally:
        writer.close()
    settings_path = _settings_with_block(
        tmp_path, "settings.json", {"store": {"path": str(db), "ids": ["p-siemens"]}}
    )
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
    cli()
    payload = _stdout_json(capsys)
    assert payload["equipment_profile_match"]["profile_id"] == "p-siemens"
    reader = ProfileStore.open_read_only(db)
    try:
        assert reader.list_records()[0].current_revision == 2
        snapshot = reader.selected_snapshot(["p-siemens"])
    finally:
        reader.close()
    session = assemble_session(snapshots=[snapshot])
    config = json.loads(settings_path.read_text(encoding="utf-8"))
    del config["equipment_profiles"]
    expected_output: Any = main(
        file_path=str(_SIEMENS_DICOM),
        settings=PyskindoseSettings(
            settings=config, output_format="dict", equipment_profile_session=session
        ),
    )
    assert payload["psd"] == expected_output["psd"]


# ---------------------------------------------------------------------------
# Purity, pre-bound refusal, staging, fallback
# ---------------------------------------------------------------------------


def test_output_serialization_purity(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    profile = _profile_file(tmp_path, "siemens.json", _siemens_doc())
    config = load_settings_example_json()
    config["mode"] = "calculate_dose"
    config["equipment_profiles"] = {"files": [{"path": str(profile)}]}
    config_path = _write_text(tmp_path / "settings.json", json.dumps(config))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "guiskindose",
            "--settings",
            str(config_path),
            "--file-path",
            str(_SIEMENS_DICOM),
            "--output-format",
            "json",
        ],
    )
    cli()
    out = capsys.readouterr().out
    assert "equipment_profiles" not in out
    assert str(profile) not in out
    namespace = argparse.Namespace(
        settings=dict(config),
        output_format=None,
        plane_code_map=None,
        equipment_profile=None,
        equipment_profile_sheet=None,
        equipment_profile_store=None,
        equipment_profile_id=None,
    )
    settings = prepare_cli_settings(namespace)
    assert "equipment_profiles" not in settings.to_settings_dict()
    assert namespace.settings["equipment_profiles"] == {"files": [{"path": str(profile)}]}


def test_prebound_refusal(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    session = assemble_session(documents=[_siemens_doc()])
    settings = _dose_settings(session)
    before_format = settings.output_format
    profile = _profile_file(tmp_path, "siemens.json", _siemens_doc())
    probes = _spy_exam_reads(monkeypatch)
    namespace = argparse.Namespace(
        settings=settings,
        output_format="json",
        plane_code_map=None,
        equipment_profile=[str(profile)],
        equipment_profile_sheet=None,
        equipment_profile_store=None,
        equipment_profile_id=None,
    )
    with pytest.raises(UserFacingInputError) as excinfo:
        prepare_cli_settings(namespace)
    assert str(excinfo.value) == "Equipment profile session is already configured."
    assert settings.equipment_profile_session is not None
    assert settings.output_format == before_format
    assert probes == {"load": [], "dcmread": []}


def test_staged_copy_config_only(tmp_path: Path) -> None:
    config = load_settings_example_json()
    config["mode"] = "calculate_dose"
    missing = tmp_path / "SENTINEL_ABSENT_PROFILE_zzz.json"
    config["equipment_profiles"] = {"files": [{"path": str(missing)}]}
    before = json.loads(json.dumps(config))
    namespace = argparse.Namespace(
        settings=config,
        output_format="json",
        plane_code_map="1:Single Plane",
        kerma_meter_correction=True,
        equipment_profile=None,
        equipment_profile_sheet=None,
        equipment_profile_store=None,
        equipment_profile_id=None,
    )
    with pytest.raises(UserFacingInputError) as excinfo:
        prepare_cli_settings(namespace)
    assert "SENTINEL_ABSENT_PROFILE_zzz" not in str(excinfo.value)
    assert config == before


def test_json_decode_fallback_unchanged() -> None:
    namespace = argparse.Namespace(
        settings="{not json",
        output_format=None,
        plane_code_map=None,
        equipment_profile=None,
        equipment_profile_sheet=None,
        equipment_profile_store=None,
        equipment_profile_id=None,
    )
    settings = prepare_cli_settings(namespace)
    assert settings.equipment_profile_session is None


# ---------------------------------------------------------------------------
# Preview, export, multi, and GUI config guard
# ---------------------------------------------------------------------------


def test_preview_export_multi_fail_before_read(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    exam = _write_text(tmp_path / "events.csv", _GENERIC_HEADER + "\n" + _GENERIC_SIEMENS_ROW + "\n")
    bad_block = {"files": [{"path": str(exam)}, {"path": 7}]}
    settings_path = _settings_with_block(tmp_path, "settings.json", bad_block)
    probes = _spy_exam_reads(monkeypatch)
    preview_argv = [
        "guiskindose",
        "--settings",
        str(settings_path),
        "--file-path",
        str(exam),
        "--input-schema",
        "generic_rdsr_like",
        "--input-preview-only",
    ]
    monkeypatch.setattr(sys, "argv", preview_argv)
    with pytest.raises(SystemExit) as excinfo:
        cli()
    assert excinfo.value.code == 1
    multi_argv = [
        "guiskindose",
        "--settings",
        str(settings_path),
        "--file-path",
        str(exam),
        str(_SIEMENS_DICOM),
        "--output-format",
        "json",
    ]
    monkeypatch.setattr(sys, "argv", multi_argv)
    with pytest.raises(SystemExit) as excinfo:
        cli()
    assert excinfo.value.code == 1
    export_path = tmp_path / "report.xlsx"
    export_argv = [
        "guiskindose",
        "--settings",
        str(settings_path),
        "--file-path",
        str(exam),
        "--export-format",
        "xlsx",
        "--export-path",
        str(export_path),
    ]
    monkeypatch.setattr(sys, "argv", export_argv)
    with pytest.raises(SystemExit) as excinfo:
        cli()
    assert excinfo.value.code == 1
    assert not export_path.exists()
    assert probes == {"load": [], "dcmread": []}


def test_gui_config_refusal(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    from guiskindose.cli_settings import (
        GUI_SETTINGS_EQUIPMENT_PROFILES_MESSAGE,
        settings_equipment_block_present,
    )

    gui_app = pytest.importorskip("guiskindose.gui.app")
    called: list[bool] = []

    def _no_ui(**kwargs: Any) -> None:
        called.append(True)

    monkeypatch.setattr(gui_app, "run_gui", _no_ui)
    missing_profile = tmp_path / "SENTINEL_ABSENT_PROFILE_zzz.json"
    settings_path = _settings_with_block(
        tmp_path, "settings.json", {"files": [{"path": str(missing_profile)}]}
    )
    plain_config = load_settings_example_json()
    plain_config["mode"] = "calculate_dose"
    plain_path = _write_text(tmp_path / "plain.json", json.dumps(plain_config))
    monkeypatch.setattr(sys, "argv", ["guiskindose", "--mode", "gui", "--settings", str(settings_path)])
    with pytest.raises(SystemExit) as excinfo:
        cli()
    assert excinfo.value.code == 1
    err = capsys.readouterr().err
    assert GUI_SETTINGS_EQUIPMENT_PROFILES_MESSAGE in err
    assert "SENTINEL_ABSENT_PROFILE_zzz" not in err
    inline_namespace = argparse.Namespace(
        settings=json.dumps({"mode": "calculate_dose", "equipment_profiles": {"files": []}})
    )
    assert settings_equipment_block_present(inline_namespace) is True
    plain_namespace = argparse.Namespace(settings=str(plain_path))
    assert settings_equipment_block_present(plain_namespace) is False
    missing_namespace = argparse.Namespace(settings=str(tmp_path / "absent.json"))
    assert settings_equipment_block_present(missing_namespace) is False
    monkeypatch.setattr(sys, "argv", ["guiskindose", "--mode", "gui", "--settings", str(plain_path)])
    cli()
    assert called == [True]
    monkeypatch.setattr(
        sys, "argv", ["guiskindose", "--mode", "gui", "--settings", str(tmp_path / "absent.json")]
    )
    cli()
    assert called == [True, True]


def test_absent_both_legacy_and_explicit_empty(tmp_path: Path) -> None:
    plain_path = _settings_file(tmp_path)
    plain_namespace = argparse.Namespace(
        settings=str(plain_path),
        output_format=None,
        plane_code_map=None,
        equipment_profile=None,
        equipment_profile_sheet=None,
        equipment_profile_store=None,
        equipment_profile_id=None,
    )
    plain_settings = prepare_cli_settings(plain_namespace)
    assert plain_settings.equipment_profile_session is None
    empty_path = _settings_with_block(tmp_path, "empty.json", {})
    empty_namespace = argparse.Namespace(
        settings=str(empty_path),
        output_format=None,
        plane_code_map=None,
        equipment_profile=None,
        equipment_profile_sheet=None,
        equipment_profile_store=None,
        equipment_profile_id=None,
    )
    empty_settings = prepare_cli_settings(empty_namespace)
    assert empty_settings.equipment_profile_session is not None
    assert len(empty_settings.equipment_profile_session.profiles) == 0
