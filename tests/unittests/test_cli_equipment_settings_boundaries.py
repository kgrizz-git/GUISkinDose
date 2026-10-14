"""Ordering and entry-point regressions for CLI settings profile sources."""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path
from typing import Any

import pytest

from guiskindose import load_settings_example_json
from guiskindose.__main__ import cli
from guiskindose.equipment_profiles import FileSource, ProfileStore, assemble_session, parse_memory_document
from guiskindose.main import analyze_multiple_input_files, prepare_cli_settings
from guiskindose.privacy import UserFacingInputError
from guiskindose.settings import PyskindoseSettings
from tests.unittests.test_cli_equipment_profiles import _stdout_json
from tests.unittests.test_cli_equipment_settings import (
    _profile_file,
    _settings_with_block,
    _siemens_doc,
    _spy_exam_reads,
    _write_text,
)
from tests.unittests.test_equipment_captured_input import (
    _GENERIC_HEADER,
    _GENERIC_SIEMENS_ROW,
    _dose_settings,
)

# ---------------------------------------------------------------------------
# Validation-before-construction ordering
# ---------------------------------------------------------------------------


def _never_construct(settings: Any = None) -> Any:
    raise AssertionError("construction ran before validation")


def test_invalid_block_before_construction(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import guiskindose.cli_settings as cli_settings_module

    monkeypatch.setattr(
        cli_settings_module, "parse_settings_to_settings_class", _never_construct
    )
    bad_block = {"files": [{"path": str(tmp_path / "siemens.json")}, {"path": 7}]}
    namespace = argparse.Namespace(
        settings={"mode": "calculate_dose", "equipment_profiles": bad_block},
        output_format=None,
        plane_code_map=None,
        equipment_profile=None,
        equipment_profile_sheet=None,
        equipment_profile_store=None,
        equipment_profile_id=None,
    )
    with pytest.raises(UserFacingInputError) as excinfo:
        prepare_cli_settings(namespace)
    assert "invalid_type" in str(excinfo.value)


def test_combined_cap_before_construction(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import guiskindose.cli_settings as cli_settings_module

    monkeypatch.setattr(
        cli_settings_module, "parse_settings_to_settings_class", _never_construct
    )
    cli_paths = [str(tmp_path / f"missing-{index}.json") for index in range(64)]
    config = {"mode": "calculate_dose", "equipment_profiles": {"files": [{"path": "one-more.json"}]}}
    namespace = argparse.Namespace(
        settings=config,
        output_format=None,
        plane_code_map=None,
        equipment_profile=cli_paths,
        equipment_profile_sheet=None,
        equipment_profile_store=None,
        equipment_profile_id=None,
    )
    with pytest.raises(UserFacingInputError) as excinfo:
        prepare_cli_settings(namespace)
    assert "profile_limit_exceeded" in str(excinfo.value)


def test_prebound_refusal_before_parsing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    session = assemble_session(documents=[_siemens_doc()])
    settings = _dose_settings(session)
    before_format = settings.output_format
    probes = _spy_exam_reads(monkeypatch)
    namespace = argparse.Namespace(
        settings=settings,
        output_format="json",
        plane_code_map=None,
        equipment_profile=[123],
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


def test_cli_bounds_convert_closed() -> None:
    from guiskindose.cli_equipment_profiles import equipment_session_from_args

    namespace = argparse.Namespace(
        equipment_profile=[f"e{index}.json" for index in range(65)],
        equipment_profile_sheet=None,
        equipment_profile_store=None,
        equipment_profile_id=None,
    )
    with pytest.raises(UserFacingInputError) as excinfo:
        equipment_session_from_args(namespace)
    assert "profile_limit_exceeded" in str(excinfo.value)


def test_cli_bad_format_before_store_open(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from guiskindose.cli_equipment_profiles import equipment_session_from_args
    from guiskindose.equipment_profiles import parse_memory_document

    db = tmp_path / "profiles.sqlite3"
    writer = ProfileStore.open(db)
    try:
        writer.save_new_revision(parse_memory_document(_siemens_doc()).profiles[0])
        writer.set_enabled("p-siemens", True)
    finally:
        writer.close()
    real_connect = sqlite3.connect
    connects: list[str] = []

    def _spy_connect(*args: Any, **kwargs: Any) -> Any:
        connects.append(str(args[0]) if args else "")
        return real_connect(*args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", _spy_connect)
    namespace = argparse.Namespace(
        equipment_profile=["SENTINEL_BAD_zzz.yaml"],
        equipment_profile_sheet=None,
        equipment_profile_store=str(db),
        equipment_profile_id=None,
    )
    with pytest.raises(UserFacingInputError) as excinfo:
        equipment_session_from_args(namespace)
    assert "unsupported_source_suffix" in str(excinfo.value)
    assert "SENTINEL_BAD_zzz" not in str(excinfo.value)
    assert connects == []


def test_sheet_range_before_store_open(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from guiskindose.cli_equipment_profiles import equipment_session_from_args
    from guiskindose.equipment_profiles import parse_memory_document
    from guiskindose.equipment_profiles.errors import EquipmentProfileError, ProfileErrorCode
    from guiskindose.settings_equipment_profiles import equipment_session_from_config

    db = tmp_path / "profiles.sqlite3"
    writer = ProfileStore.open(db)
    try:
        writer.save_new_revision(parse_memory_document(_siemens_doc()).profiles[0])
        writer.set_enabled("p-siemens", True)
    finally:
        writer.close()
    real_connect = sqlite3.connect
    connects: list[str] = []

    def _spy_connect(*args: Any, **kwargs: Any) -> Any:
        connects.append(str(args[0]) if args else "")
        return real_connect(*args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", _spy_connect)
    for bad_sheet in (16, 10**30):
        namespace = argparse.Namespace(
            equipment_profile=["SENTINEL_PROFILE_zzz.xlsx"],
            equipment_profile_sheet=bad_sheet,
            equipment_profile_store=str(db),
            equipment_profile_id=None,
        )
        with pytest.raises(UserFacingInputError) as excinfo:
            equipment_session_from_args(namespace)
        assert "SENTINEL_PROFILE_zzz" not in str(excinfo.value)
    assert connects == []
    with pytest.raises(EquipmentProfileError) as excinfo:
        equipment_session_from_config({"files": [{"path": "SENTINEL_X_zzz.xlsx", "sheet": 10**30}]})
    assert excinfo.value.code is ProfileErrorCode.VALUE_OUT_OF_RANGE
    assert "SENTINEL_X_zzz" not in str(excinfo.value)


def test_hostile_settings_path_closed(tmp_path: Path) -> None:
    profile = _profile_file(tmp_path, "siemens.json", _siemens_doc())

    class _HostilePath(type(tmp_path)):
        @property
        def parent(self) -> Path:
            raise RuntimeError("PRIVATE SENTINEL")

    namespace = argparse.Namespace(
        settings=_HostilePath(str(tmp_path / "settings.json")),
        output_format=None,
        plane_code_map=None,
        equipment_profile=[str(profile)],
        equipment_profile_sheet=None,
        equipment_profile_store=None,
        equipment_profile_id=None,
    )
    with pytest.raises(UserFacingInputError) as excinfo:
        prepare_cli_settings(namespace)
    assert "SENTINEL" not in str(excinfo.value)


# ---------------------------------------------------------------------------
# Positive preview/multi and GUI unicode guard
# ---------------------------------------------------------------------------


def test_preview_positive_with_config(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    exam = _write_text(tmp_path / "events.csv", _GENERIC_HEADER + "\n" + _GENERIC_SIEMENS_ROW + "\n")
    profile = _profile_file(tmp_path, "siemens.json", _siemens_doc())
    settings_path = _settings_with_block(tmp_path, "settings.json", {"files": [{"path": str(profile)}]})
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
            "--input-preview-only",
        ],
    )
    cli()
    assert "events" in capsys.readouterr().out.lower()


def test_multi_positive_with_config(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    siemens_exam = _write_text(
        tmp_path / "siemens.csv", _GENERIC_HEADER + "\n" + _GENERIC_SIEMENS_ROW + "\n"
    )
    second_exam = _write_text(
        tmp_path / "siemens2.csv", _GENERIC_HEADER + "\n" + _GENERIC_SIEMENS_ROW + "\n"
    )
    profile = _profile_file(tmp_path, "siemens.json", _siemens_doc())
    settings_path = _settings_with_block(tmp_path, "settings.json", {"files": [{"path": str(profile)}]})
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "guiskindose",
            "--settings",
            str(settings_path),
            "--file-path",
            str(siemens_exam),
            str(second_exam),
            "--output-format",
            "json",
            "--input-schema",
            "generic_rdsr_like",
        ],
    )
    cli()
    payload = _stdout_json(capsys)
    session = assemble_session(files=[FileSource(str(profile))])
    expected_config = load_settings_example_json()
    expected_config["mode"] = "calculate_dose"
    expected = analyze_multiple_input_files(
        [siemens_exam, second_exam],
        settings=PyskindoseSettings(
            settings=expected_config,
            output_format="dict",
            equipment_profile_session=session,
        ),
        input_schema="generic_rdsr_like",
    ).to_dict()
    assert payload["aggregate_psd"] == expected["aggregate_psd"]
    assert payload["exams"][0]["equipment_profile_match"]["profile_id"] == "p-siemens"


def test_gui_invalid_utf8_proceeds(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    gui_app = pytest.importorskip("guiskindose.gui.app")
    called: list[bool] = []

    def _no_ui(**kwargs: Any) -> None:
        called.append(True)

    monkeypatch.setattr(gui_app, "run_gui", _no_ui)
    settings_path = tmp_path / "settings.json"
    settings_path.write_bytes(b'{"mode": "calculate_dose", "oops": "\xff\xfe"}')
    monkeypatch.setattr(sys, "argv", ["guiskindose", "--mode", "gui", "--settings", str(settings_path)])
    cli()
    assert called == [True]


@pytest.mark.parametrize("path", ["", "bad\x00store", "bad\ud800store"])
def test_cli_store_path_rejected_before_settings_or_source_io(
    monkeypatch: pytest.MonkeyPatch, path: str
) -> None:
    import guiskindose.cli_settings as cli_settings_module
    from tests.unittests.test_settings_equipment_profiles import _assert_no_profile_io, _spy_profile_io

    probes = _spy_profile_io(monkeypatch)
    monkeypatch.setattr(cli_settings_module, "parse_settings_to_settings_class", _never_construct)
    namespace = argparse.Namespace(settings={}, equipment_profile_store=path)
    with pytest.raises(UserFacingInputError) as excinfo:
        prepare_cli_settings(namespace)
    assert "invalid_type" in str(excinfo.value)
    _assert_no_profile_io(probes)


@pytest.mark.parametrize("raw", [
    '{"equipment_profiles": {}, "equipment_profiles": null}',
    '{"equipment_profiles": {"files": [], "files": []}}',
])
def test_duplicate_profile_settings_keys_fail_before_construction(
    monkeypatch: pytest.MonkeyPatch, raw: str
) -> None:
    import guiskindose.cli_settings as cli_settings_module

    monkeypatch.setattr(cli_settings_module, "parse_settings_to_settings_class", _never_construct)
    namespace = argparse.Namespace(settings=raw)
    with pytest.raises(UserFacingInputError) as excinfo:
        prepare_cli_settings(namespace)
    assert str(excinfo.value) == "Equipment profile settings are not valid."


def test_two_store_sides_assemble_once(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import guiskindose.settings_equipment_profiles as source_module
    from tests.unittests.test_cli_equipment_settings import _philips_doc, _seed_store

    first = _seed_store(tmp_path / "one.db", [parse_memory_document(_siemens_doc()).profiles[0]], enabled=["p-siemens"])
    second = _seed_store(tmp_path / "two.db", [parse_memory_document(_philips_doc()).profiles[0]], enabled=["p-philips"])
    config = load_settings_example_json()
    config["equipment_profiles"] = {"store": {"path": str(second)}}
    namespace = argparse.Namespace(settings=config, equipment_profile_store=str(first))
    real_assemble = source_module.assemble_session
    calls: list[tuple[int, int]] = []

    def assemble_spy(**kwargs: Any) -> Any:
        calls.append((len(kwargs["files"]), len(kwargs["snapshots"])))
        return real_assemble(**kwargs)

    monkeypatch.setattr(source_module, "assemble_session", assemble_spy)
    settings = prepare_cli_settings(namespace)
    assert calls == [(0, 2)]
    session = settings.equipment_profile_session
    assert session is not None
    assert [profile.profile_id for profile in session.profiles] == ["p-philips", "p-siemens"]
