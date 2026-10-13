"""Tests for CLI custom equipment-profile file inputs.

Profile files are generated per test (JSON written directly; CSV/TSV via the
csv module; XLSX via openpyxl under ``tmp_path``) so no tracked binary is
committed. Dose runs go through the real ``cli()`` entry point with
``capsys``-captured stdout/stderr and are compared against the equivalent
Python session runs. Covers flag spelling/defaults, DICOM full/partial
parity, tabular CFA/ASD parity, disjoint repeats with order-independent
hashes and outputs, four-format profile parity, named/indexed sheet
selection, unsupported/conflict/malformed/missing/unknown-sheet failures
with zero exam reads and private stderr, pre-bound session refusal, GUI
refusal without UI or profile I/O, and session-aware preview smoke. No
tracked binaries are used.
"""

from __future__ import annotations

import csv
import io
import json
import sys
from pathlib import Path
from typing import Any

import pytest

from guiskindose import get_path_to_example_rdsr_files, load_settings_example_json
from guiskindose.__main__ import cli
from guiskindose.cli_equipment_profiles import (
    GUI_EQUIPMENT_PROFILES_MESSAGE,
    bind_equipment_session,
    equipment_profile_args_present,
    equipment_session_from_args,
)
from guiskindose.equipment_profiles import (
    FLAT_COLUMNS,
    FileSource,
    assemble_session,
)
from guiskindose.main import analyze_multiple_input_files, main
from guiskindose.privacy import UserFacingInputError
from guiskindose.settings import PyskindoseSettings
from tests.unittests.test_equipment_captured_input import (
    _GENERIC_HEADER,
    _GENERIC_PHILIPS_ROW,
    _GENERIC_SIEMENS_ROW,
    _dose_settings,
    _philips_coordinates,
    _siemens_coordinates,
    _snapshot_norm,
)

_SIEMENS_DICOM = get_path_to_example_rdsr_files() / "siemens_axiom_artis.dcm"

_COLUMNS: tuple[str, ...] = tuple(FLAT_COLUMNS)
_WIDTH = len(_COLUMNS)


def _siemens_profile_doc() -> dict[str, Any]:
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


def _philips_profile_doc() -> dict[str, Any]:
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


def _leaf_rows(coordinates: dict[str, Any], profile_id: str) -> list[list[str]]:
    rows: list[list[str]] = []
    for field in (
        "translation_offset.x",
        "translation_offset.y",
        "translation_offset.z",
        "translation_direction.x",
        "translation_direction.y",
        "translation_direction.z",
        "rotation_direction.Ap1",
        "rotation_direction.Ap2",
        "rotation_direction.Ap3",
        "rotation_direction.At1",
        "rotation_direction.At2",
        "rotation_direction.At3",
        "swap_lateral_longitudinal",
        "field_size_mode",
        "detector_side_length",
    ):
        row = [""] * _WIDTH
        row[0] = "coordinate"
        row[1] = profile_id
        row[_COLUMNS.index("field")] = field
        node: Any = coordinates
        for part in field.split("."):
            node = node[part]
        row[_COLUMNS.index("value")] = (
            str(node).lower() if isinstance(node, bool) else str(node)
        )
        rows.append(row)
    return rows


def _profile_table(
    profile_id: str, manufacturer: str, model: str, coordinates: dict[str, Any]
) -> list[list[str]]:
    head = [""] * _WIDTH
    head[0] = "profile"
    head[1] = profile_id
    head[_COLUMNS.index("manufacturer")] = manufacturer
    head[_COLUMNS.index("models")] = model
    return [head, *_leaf_rows(coordinates, profile_id)]


def _write_csv(path: Path, rows: list[list[str]]) -> Path:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(list(_COLUMNS))
    writer.writerows(rows)
    path.write_text(buffer.getvalue(), encoding="utf-8")
    return path


def _write_tsv(path: Path, rows: list[list[str]]) -> Path:
    lines = ["\t".join(list(_COLUMNS))]
    lines.extend("\t".join(row) for row in rows)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _write_xlsx(path: Path, sheets: list[tuple[str, list[str], list[list[str]]]]) -> Path:
    from openpyxl import Workbook

    workbook = Workbook()
    first = True
    for title, header, rows in sheets:
        sheet = workbook.active if first else workbook.create_sheet()
        first = False
        assert sheet is not None
        sheet.title = title
        sheet.append(list(header))
        for row in rows:
            sheet.append(list(row))
    workbook.save(path)
    return path


def _siemens_table() -> list[list[str]]:
    return _profile_table("p-siemens", "Siemens", "AXIOM-Artis", _siemens_coordinates())


def _settings_file(tmp_path: Path) -> Path:
    config = load_settings_example_json()
    config["mode"] = "calculate_dose"
    path = tmp_path / "settings.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    return path


def _stdout_json(capsys: pytest.CaptureFixture[str]) -> Any:
    out = capsys.readouterr().out
    return json.loads(out[out.index("{"):])

# ---------------------------------------------------------------------------
# Flag spelling, defaults, and GUI guard
# ---------------------------------------------------------------------------


def test_flag_spelling_and_defaults() -> None:
    from guiskindose.cli_args import get_argument_parser

    args = get_argument_parser([])
    assert args.equipment_profile is None
    assert args.equipment_profile_sheet is None
    assert not equipment_profile_args_present(args)
    repeated = get_argument_parser(
        ["--equipment-profile", "a.json", "--equipment-profile", "b.csv"]
    )
    assert repeated.equipment_profile == ["a.json", "b.csv"]
    assert equipment_profile_args_present(repeated)
    sheet_only = get_argument_parser(["--equipment-profile-sheet", "1"])
    assert sheet_only.equipment_profile_sheet == "1"
    assert equipment_profile_args_present(sheet_only)


def test_gui_rejects_profile_flags_before_ui_or_io(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    gui_app = pytest.importorskip("guiskindose.gui.app")
    called: list[bool] = []
    sentinel = str(tmp_path / "SENTINEL_MISSING_PROFILE_zzz.json")

    def _no_ui(**kwargs: Any) -> None:
        called.append(True)

    monkeypatch.setattr(gui_app, "run_gui", _no_ui)
    monkeypatch.setattr(
        sys, "argv", ["guiskindose", "--mode", "gui", "--equipment-profile", sentinel]
    )
    with pytest.raises(SystemExit) as excinfo:
        cli()
    assert excinfo.value.code == 1
    err = capsys.readouterr().err
    assert GUI_EQUIPMENT_PROFILES_MESSAGE in err
    assert "SENTINEL_MISSING_PROFILE_zzz" not in err
    assert called == []
    monkeypatch.setattr(
        sys,
        "argv",
        ["guiskindose", "--mode", "gui", "--equipment-profile-sheet", "Profiles"],
    )
    with pytest.raises(SystemExit) as excinfo:
        cli()
    assert excinfo.value.code == 1
    assert GUI_EQUIPMENT_PROFILES_MESSAGE in capsys.readouterr().err
    assert called == []


# ---------------------------------------------------------------------------
# Dose parity: CLI file sessions vs equivalent Python sessions
# ---------------------------------------------------------------------------


def _dose_argv(
    settings_path: Path, exam: Path, profiles: list[Path], extra: list[str] | None = None
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
    for profile in profiles:
        argv.extend(["--equipment-profile", str(profile)])
    if extra:
        argv.extend(extra)
    return argv


def test_dicom_full_parity(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    profile = tmp_path / "siemens.json"
    profile.write_text(json.dumps(_siemens_profile_doc()), encoding="utf-8")
    settings_path = _settings_file(tmp_path)
    monkeypatch.setattr(sys, "argv", _dose_argv(settings_path, _SIEMENS_DICOM, [profile]))
    cli()
    payload = _stdout_json(capsys)
    config = json.loads(settings_path.read_text(encoding="utf-8"))
    session = assemble_session(files=[FileSource(str(profile))])
    expected: Any = main(
        file_path=str(_SIEMENS_DICOM),
        settings=PyskindoseSettings(
            settings=config, output_format="dict", equipment_profile_session=session
        ),
    )
    assert payload["psd"] == expected["psd"]
    assert payload["equipment_profile_match"] == expected["equipment_profile_match"]
    assert payload["dose_map"] == json.loads(json.dumps(expected["dose_map"]))


def test_dicom_partial_parity(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    doc = {
        "schema_version": 1,
        "profiles": [
            {
                "profile_id": "p-partial",
                "manufacturer": "Siemens",
                "models": ["AXIOM-Artis"],
                "coordinates": {"translation_offset": {"z": 1.5}},
            }
        ],
    }
    profile = tmp_path / "partial.json"
    profile.write_text(json.dumps(doc), encoding="utf-8")
    settings_path = _settings_file(tmp_path)
    monkeypatch.setattr(sys, "argv", _dose_argv(settings_path, _SIEMENS_DICOM, [profile]))
    cli()
    payload = _stdout_json(capsys)
    config = json.loads(settings_path.read_text(encoding="utf-8"))
    session = assemble_session(files=[FileSource(str(profile))])
    expected: Any = main(
        file_path=str(_SIEMENS_DICOM),
        settings=PyskindoseSettings(
            settings=config, output_format="dict", equipment_profile_session=session
        ),
    )
    assert payload["equipment_profile_match"]["profile_id"] == "p-partial"
    assert payload["psd"] == expected["psd"]
    assert payload["equipment_profile_match"] == expected["equipment_profile_match"]


def test_tabular_cfa_asd_parity(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    profile = tmp_path / "both.json"
    profile.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "profiles": _siemens_profile_doc()["profiles"]
                + _philips_profile_doc()["profiles"],
            }
        ),
        encoding="utf-8",
    )
    siemens_exam = tmp_path / "siemens.csv"
    siemens_exam.write_text(_GENERIC_HEADER + "\n" + _GENERIC_SIEMENS_ROW + "\n", encoding="utf-8")
    philips_cells = list(csv.reader(io.StringIO(_GENERIC_HEADER + "\n" + _GENERIC_PHILIPS_ROW + "\n")))
    philips_exam = tmp_path / "philips.xlsx"
    _write_xlsx(philips_exam, [("Events", philips_cells[0], philips_cells[1:])])
    settings_path = _settings_file(tmp_path)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "guiskindose",
            "--settings",
            str(settings_path),
            "--file-path",
            str(siemens_exam),
            str(philips_exam),
            "--output-format",
            "json",
            "--input-schema",
            "generic_rdsr_like",
            "--equipment-profile",
            str(profile),
        ],
    )
    cli()
    payload = _stdout_json(capsys)
    config = json.loads(settings_path.read_text(encoding="utf-8"))
    session = assemble_session(files=[FileSource(str(profile))])
    expected = analyze_multiple_input_files(
        [siemens_exam, philips_exam],
        settings=PyskindoseSettings(
            settings=config, output_format="json", equipment_profile_session=session
        ),
        input_schema="generic_rdsr_like",
    ).to_dict()
    assert payload["aggregate_psd"] == expected["aggregate_psd"]
    assert payload["total_events"] == expected["total_events"]
    assert [exam["equipment_profile_match"] for exam in payload["exams"]] == [
        exam["equipment_profile_match"] for exam in expected["exams"]
    ]


def test_repeats_disjoint_order_parity(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    siemens_profile = tmp_path / "siemens.json"
    siemens_profile.write_text(json.dumps(_siemens_profile_doc()), encoding="utf-8")
    philips_profile = tmp_path / "philips.json"
    philips_profile.write_text(json.dumps(_philips_profile_doc()), encoding="utf-8")
    settings_path = _settings_file(tmp_path)
    monkeypatch.setattr(
        sys,
        "argv",
        _dose_argv(settings_path, _SIEMENS_DICOM, [siemens_profile, philips_profile]),
    )
    cli()
    forward = _stdout_json(capsys)
    monkeypatch.setattr(
        sys,
        "argv",
        _dose_argv(settings_path, _SIEMENS_DICOM, [philips_profile, siemens_profile]),
    )
    cli()
    reversed_run = _stdout_json(capsys)
    assert forward["psd"] == reversed_run["psd"]
    assert forward["equipment_profile_match"] == reversed_run["equipment_profile_match"]
    assert (
        assemble_session(files=[FileSource(str(siemens_profile)), FileSource(str(philips_profile))]).active_set_hash
        == assemble_session(
            files=[FileSource(str(philips_profile)), FileSource(str(siemens_profile))]
        ).active_set_hash
    )


# ---------------------------------------------------------------------------
# Profile-source formats and sheet selection
# ---------------------------------------------------------------------------


def _match_core(match: Any) -> Any:
    """Dose-relevant match content without source provenance."""
    return (
        match["profile_id"],
        match["level"],
        match["notice"],
        sorted((field["field"], field["value"]) for field in match["fields"]),
    )


def test_profile_format_parity(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    table = _siemens_table()
    json_path = tmp_path / "profile.json"
    json_path.write_text(json.dumps(_siemens_profile_doc()), encoding="utf-8")
    csv_path = _write_csv(tmp_path / "profile.csv", table)
    tsv_path = _write_tsv(tmp_path / "profile.tsv", table)
    xlsx_path = _write_xlsx(tmp_path / "profile.xlsx", [("Profiles", list(_COLUMNS), table)])
    hashes = {
        assemble_session(files=[FileSource(str(path))]).active_set_hash for path in (
            json_path, csv_path, tsv_path, xlsx_path,
        )
    }
    assert len(hashes) == 1
    settings_path = _settings_file(tmp_path)
    monkeypatch.setattr(sys, "argv", _dose_argv(settings_path, _SIEMENS_DICOM, [csv_path]))
    cli()
    csv_run = _stdout_json(capsys)
    monkeypatch.setattr(sys, "argv", _dose_argv(settings_path, _SIEMENS_DICOM, [xlsx_path]))
    cli()
    xlsx_run = _stdout_json(capsys)
    assert csv_run["psd"] == xlsx_run["psd"]
    assert _match_core(csv_run["equipment_profile_match"]) == _match_core(
        xlsx_run["equipment_profile_match"]
    )


def _argv_namespace(paths: Any, sheet: Any = None) -> Any:
    """Minimal argparse namespace carrying only the profile flags (values untouched)."""
    import argparse

    return argparse.Namespace(equipment_profile=paths, equipment_profile_sheet=sheet)


# ---------------------------------------------------------------------------
# Closed failures: zero exam reads, private stderr, non-zero exit
# ---------------------------------------------------------------------------


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


def test_cli_missing_profile_zero_reads_private_stderr(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    sentinel = str(tmp_path / "SENTINEL_MISSING_PROFILE_zzz.json")
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
            sentinel,
        ],
    )
    with pytest.raises(SystemExit) as excinfo:
        cli()
    assert excinfo.value.code == 1
    err = capsys.readouterr().err
    assert "unreadable_source" in err
    assert "SENTINEL_MISSING_PROFILE_zzz" not in err
    assert probes == {"load": [], "dcmread": []}


def test_cli_malformed_profile_notes_not_printed(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    doc = _siemens_profile_doc()
    doc["profiles"][0]["provenance"] = {"source": "test", "notes": "SENTINEL_NOTE_PHRASE"}
    doc["profiles"][0]["coordinates"]["translation_offset"]["x"] = "bogus"
    profile = tmp_path / "malformed.json"
    profile.write_text(json.dumps(doc), encoding="utf-8")
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
            str(profile),
        ],
    )
    with pytest.raises(SystemExit) as excinfo:
        cli()
    assert excinfo.value.code == 1
    err = capsys.readouterr().err
    assert "SENTINEL_NOTE_PHRASE" not in err
    assert str(profile) not in err
    assert probes == {"load": [], "dcmread": []}


def test_cli_conflict_and_capability_closed(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    first_doc = _siemens_profile_doc()
    second_doc = _siemens_profile_doc()
    second_doc["profiles"][0]["profile_id"] = "p-siemens-b"
    second_doc["profiles"][0]["coordinates"]["translation_offset"]["x"] = 9.0
    first = tmp_path / "a.json"
    first.write_text(json.dumps(first_doc), encoding="utf-8")
    second = tmp_path / "b.json"
    second.write_text(json.dumps(second_doc), encoding="utf-8")
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
    trans = tmp_path / "trans.json"
    trans.write_text(json.dumps(transmission_doc), encoding="utf-8")
    exam = tmp_path / "events.csv"
    exam.write_text(_GENERIC_HEADER + "\n" + _GENERIC_SIEMENS_ROW + "\n", encoding="utf-8")
    settings_path = _settings_file(tmp_path)
    probes = _spy_exam_reads(monkeypatch)
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
            str(first),
            "--equipment-profile",
            str(second),
        ],
    )
    with pytest.raises(SystemExit) as excinfo:
        cli()
    assert excinfo.value.code == 1
    err = capsys.readouterr().err
    assert "duplicate_coordinate_claim" in err
    assert "p-siemens-b" not in err
    assert probes == {"load": [], "dcmread": []}
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
            str(trans),
        ],
    )
    with pytest.raises(SystemExit) as excinfo:
        cli()
    assert excinfo.value.code == 1
    assert "unsupported_profile_capability" in capsys.readouterr().err


def test_bind_refuses_silent_replace() -> None:
    session = assemble_session(documents=[_siemens_profile_doc()])
    settings = _dose_settings(session)
    before = dict(settings.__dict__)
    replacement = assemble_session(documents=[_philips_profile_doc()])
    with pytest.raises(UserFacingInputError):
        bind_equipment_session(settings, replacement)
    assert settings.equipment_profile_session is not replacement
    assert settings.equipment_profile_session is session
    assert settings.__dict__ == before


def test_preview_with_session_smoke(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    profile = tmp_path / "siemens.json"
    profile.write_text(json.dumps(_siemens_profile_doc()), encoding="utf-8")
    exam = tmp_path / "events.csv"
    exam.write_text(_GENERIC_HEADER + "\n" + _GENERIC_SIEMENS_ROW + "\n", encoding="utf-8")
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
            "--input-preview-only",
            "--equipment-profile",
            str(profile),
        ],
    )
    cli()
    assert "events" in capsys.readouterr().out.lower()


def test_relative_profile_path_resolves_cwd(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    profile = tmp_path / "siemens.json"
    profile.write_text(json.dumps(_siemens_profile_doc()), encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    session = equipment_session_from_args(_argv_namespace([Path("siemens.json")]))
    assert session is not None
    assert [source.profile_ids for source in session.provenance.sources] == [("p-siemens",)]


# ---------------------------------------------------------------------------
# Request-shape bounds, strict selectors, and staging
# ---------------------------------------------------------------------------


def test_non_list_paths_and_oversize_fail_before_io(tmp_path: Path) -> None:
    profile = tmp_path / "siemens.json"
    profile.write_text(json.dumps(_siemens_profile_doc()), encoding="utf-8")
    for bad in (
        (str(profile) for _ in range(1)),
        str(profile),
        {"p": str(profile)},
        [123],
        [None],
        [b"bytes-path"],
    ):
        raised_argument_2 = _argv_namespace(bad)
        with pytest.raises(UserFacingInputError) as excinfo:
            equipment_session_from_args(raised_argument_2)
        assert str(profile) not in str(excinfo.value)
    many = [str(profile)] * 65
    raised_argument_1 = _argv_namespace(many)
    with pytest.raises(UserFacingInputError) as excinfo:
        equipment_session_from_args(raised_argument_1)
    assert "profile_limit_exceeded" in str(excinfo.value)


def test_strict_selector_rejects_bool_and_negative() -> None:
    for bad in (True, 1.5, "-1", "", "   "):
        raised_argument_3 = _argv_namespace([], sheet=bad)
        with pytest.raises(UserFacingInputError):
            equipment_session_from_args(raised_argument_3)


def test_prebound_refusal_precedes_profile_io(tmp_path: Path) -> None:
    session = assemble_session(documents=[_siemens_profile_doc()])
    settings = _dose_settings(session)
    missing = tmp_path / "SENTINEL_ABSENT_PROFILE_zzz.json"
    namespace = _argv_namespace_full(
        settings, [missing], output_format="json", plane_map="1:Single Plane", kerma=True
    )
    from guiskindose.main import prepare_cli_settings

    with pytest.raises(UserFacingInputError) as excinfo:
        prepare_cli_settings(namespace)
    assert str(excinfo.value) == "Equipment profile session is already configured."
    assert "SENTINEL_ABSENT_PROFILE_zzz" not in str(excinfo.value)
    assert settings.equipment_profile_session is session
    assert settings.output_format == "dict"


def _argv_namespace_full(
    settings: Any,
    profiles: list[Path],
    *,
    output_format: str | None = None,
    plane_map: str | None = None,
    kerma: bool = False,
    sheet: Any = None,
) -> Any:
    """argparse namespace with mutating flags for prepare-level staging tests."""
    import argparse

    return argparse.Namespace(
        settings=settings,
        output_format=output_format,
        plane_code_map=plane_map,
        kerma_meter_correction=kerma,
        equipment_profile=[str(path) for path in profiles],
        equipment_profile_sheet=sheet,
    )


def test_failed_candidate_leaves_caller_settings_intact(tmp_path: Path) -> None:
    from guiskindose.main import prepare_cli_settings

    config = load_settings_example_json()
    config["mode"] = "calculate_dose"
    fresh = PyskindoseSettings(settings=config, output_format="dict")
    before_norm = _snapshot_norm(fresh.normalization_settings)
    before_format = fresh.output_format
    before_map = fresh.dosetrack_plane_code_map
    before_kerma = fresh.kerma_meter_correction.enable
    missing = tmp_path / "SENTINEL_ABSENT_PROFILE_zzz.json"
    namespace = _argv_namespace_full(
        fresh,
        [missing],
        output_format="json",
        plane_map="1:Single Plane",
        kerma=True,
    )
    with pytest.raises(UserFacingInputError) as excinfo:
        prepare_cli_settings(namespace)
    assert "SENTINEL_ABSENT_PROFILE_zzz" not in str(excinfo.value)
    assert fresh.output_format == before_format
    assert fresh.dosetrack_plane_code_map == before_map
    assert fresh.kerma_meter_correction.enable is before_kerma
    assert fresh.equipment_profile_session is None
    assert _snapshot_norm(fresh.normalization_settings) == before_norm
