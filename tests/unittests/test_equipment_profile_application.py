"""Tests for the first Python API coordinate slice: custom sessions end to end.

A bound session resolves during raw normalization (DICOM plus raw-shaped
tabular), applies all 15 effective leaves before geometry calculation, and
reports the per-exam match, notice, and session hashes in dict/JSON results.
Already-normalized inputs refuse closed. No GUI, CLI-flag, or export-catalog
wiring is exercised.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from guiskindose import PyskindoseSettings, load_settings_example_json
from guiskindose.equipment_profiles import (
    EquipmentProfileError,
    ProfileErrorCode,
    ProfileStore,
    assemble_session,
    parse_memory_document,
)
from guiskindose.main import analyze_data, analyze_input_file, analyze_multiple_input_files

_DICOM = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "guiskindose"
    / "example_data"
    / "RDSR"
    / "siemens_axiom_artis.dcm"
)
_PHILIPS_DICOM = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "guiskindose"
    / "example_data"
    / "RDSR"
    / "philips_allura_clarity_u104.dcm"
)
_FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "tabular_inputs"

_RAW_HEADER = (
    "Manufacturer,ManufacturerModelName,IrradiationEventType,AcquisitionPlane,"
    "DistanceSourcetoDetector_mm,DistanceSourcetoIsocenter_mm,"
    "TableLongitudinalPosition_mm,TableLateralPosition_mm,TableHeightPosition_mm,CollimatedFieldArea_m2,"
    "XRayFilterMaterial,XRayFilterThicknessMinimum_mm,XRayFilterThicknessMaximum_mm,"
    "PositionerPrimaryAngle_deg,PositionerSecondaryAngle_deg,KVP_kV,DoseRP_Gy"
)
_RAW_ROW = (
    "{maker},{model},Fluoroscopy,Single Plane,1198,785,37.8,40.6,294.1,0.01,"
    "Copper or Copper compound,0.6,0.6,-0.1,-1.1,{kvp},{dose}"
)

_LEAF_PATHS = (
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
)


def _settings(**overrides: Any):
    base = load_settings_example_json()
    base["mode"] = "calculate_dose"
    base["phantom"]["model"] = "cylinder"
    base["plot"]["plot_dosemap"] = False
    base["plot"]["notebook_mode"] = False
    base.update(overrides)
    return PyskindoseSettings(settings=base, output_format="dict")


def _raw_profile(pid, maker="Siemens", model="AXIOM-Artis", **overrides):
    base = {
        "profile_id": pid,
        "manufacturer": maker,
        "models": [model],
        "coordinates": {"detector_side_length": 40.0},
    }
    base.update(overrides)
    return base


def _session_for(*profiles, **kwargs):
    return assemble_session(documents=[{"schema_version": 1, "profiles": list(profiles)}], **kwargs)


def _settings_with(*profiles):
    settings = _settings()
    settings.equipment_profile_session = _session_for(*profiles)
    return settings


def _full_coordinates():
    return {
        "translation_offset": {"x": 5.0, "y": 0.0, "z": -1.0},
        "translation_direction": {"x": "+", "y": "+", "z": "+"},
        "rotation_direction": {"Ap1": "+", "Ap2": "-", "Ap3": "+", "At1": "+", "At2": "+", "At3": "+"},
        "swap_lateral_longitudinal": False,
        "field_size_mode": "CFA",
        "detector_side_length": 40.0,
    }


def _raw_csv(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def _single_event_csv(maker="Siemens", model="AXIOM-Artis", kvp=77.0, dose=0.00003):
    return _RAW_HEADER + "\n" + _RAW_ROW.format(maker=maker, model=model, kvp=kvp, dose=dose) + "\n"


def _match(output: dict) -> dict:
    assert output["equipment_profile_match"] is not None
    return output["equipment_profile_match"]


# ---------------------------------------------------------------------------
# Raw DICOM: partial and full custom profiles
# ---------------------------------------------------------------------------


def test_dicom_partial_custom_applies_offset_and_inherits() -> None:
    session_profile = _raw_profile(
        "siemens-tweak",
        coordinates={
            "translation_offset": {"x": 5.0, "y": 0.0, "z": 0.0},
            "translation_direction": {"x": "+", "y": "+", "z": "+"},
            "rotation_direction": {"Ap1": "+", "Ap2": "+", "Ap3": "+", "At1": "+", "At2": "+", "At3": "+"},
            "swap_lateral_longitudinal": False,
            "field_size_mode": "CFA",
            "detector_side_length": 40.0,
        },
    )
    # Drop one leaf so the profile is partial: detector size inherits bundled exact.
    del session_profile["coordinates"]["detector_side_length"]
    settings = _settings_with(session_profile)
    output = analyze_input_file(str(_DICOM), settings=settings)
    match = _match(output)
    assert (match["profile_id"], match["source"], match["level"]) == ("siemens-tweak", "custom", "exact")
    assert match["affected_event_count"] == 21
    assert {leaf["field"] for leaf in match["fields"]} == set(_LEAF_PATHS)
    by_field = {leaf["field"]: leaf for leaf in match["fields"]}
    assert by_field["translation_offset.x"]["value"] == 5.0
    assert by_field["translation_offset.x"]["inherited"] is False
    assert by_field["detector_side_length"]["value"] == 40.0
    assert by_field["detector_side_length"]["inherited"] is True
    assert by_field["detector_side_length"]["source"] == "bundled"
    assert match["notice"]["kind"] == "partial"
    assert settings.equipment_profile_session is not None
    assert match["active_set_hash"] == settings.equipment_profile_session.active_set_hash
    # Geometry carries the custom offset: +5 cm on every event versus bundled.
    plain = analyze_input_file(str(_DICOM), settings=_settings())
    assert plain.get("equipment_profile_match") is None
    assert len(output["events"]["kerma"]) == len(plain["events"]["kerma"]) == 21
    assert output["psd"] != plain["psd"]


def test_dicom_full_custom_is_complete_and_exact() -> None:
    settings = _settings_with(_raw_profile("siemens-full", coordinates=_full_coordinates()))
    output = analyze_input_file(str(_DICOM), settings=settings)
    match = _match(output)
    assert match["notice"]["kind"] == "complete"
    assert match["notice"]["entries"] == []
    assert all(leaf["inherited"] is False for leaf in match["fields"])
    by_field = {leaf["field"]: leaf for leaf in match["fields"]}
    assert by_field["rotation_direction.Ap2"]["value"] == "-"
    assert by_field["swap_lateral_longitudinal"]["value"] is False
    assert by_field["translation_offset.x"]["value"] == 5.0
    assert match["matched_input_key"] == {"manufacturer": "siemens", "model": "axiom artis"}


def test_dicom_results_identical_across_json_output() -> None:
    from guiskindose.main import analyze_input_file as run

    profile = _raw_profile("siemens-full", coordinates=_full_coordinates())
    dict_output = run(str(_DICOM), settings=_settings_with(profile))
    json_output = json.loads(
        run(str(_DICOM), settings=_settings_with(_raw_profile("siemens-full", coordinates=_full_coordinates())), output_format="json")
    )
    assert dict_output["equipment_profile_match"] == json_output["equipment_profile_match"]
    assert dict_output["psd"] == json_output["psd"]


# ---------------------------------------------------------------------------
# Zero/False preservation and swap semantics
# ---------------------------------------------------------------------------


def test_zero_offset_applies_instead_of_inheriting(tmp_path: Path) -> None:
    # Philips bundled offset x is -0.3; an explicit 0.0 must win over inheritance.
    settings = _settings_with(
        _raw_profile(
            "philips-zero",
            maker="Philips",
            model="Allura Clarity",
            coordinates={"translation_offset": {"x": 0.0}},
        )
    )
    output = analyze_input_file(str(_PHILIPS_DICOM), settings=settings)
    match = _match(output)
    assert match["profile_id"] == "philips-zero"
    assert match["fields"][0]["value"] == 0.0
    assert match["fields"][0]["inherited"] is False
    from guiskindose.helpers.read_and_normalize_rdsr_data import read_and_normalise_rdsr_data

    plain_data = read_and_normalise_rdsr_data(rdsr_filepath=str(_PHILIPS_DICOM), settings=_settings())
    custom_data = read_and_normalise_rdsr_data(rdsr_filepath=str(_PHILIPS_DICOM), settings=settings)
    # Explicit 0.0 wins over the bundled -0.3 on every event.
    assert (((custom_data["Tx"] - plain_data["Tx"]).abs() - 0.3).abs().max() < 1e-9)


def test_explicit_false_swap_disables_ge_swap(tmp_path: Path) -> None:
    text = _RAW_HEADER + "\n" + _RAW_ROW.format(
        maker="GE Healthcare", model="Unknown GE Model", kvp=77.0, dose=0.00003
    ) + "\n"
    path = _raw_csv(tmp_path, "ge.csv", text)
    settings = _settings_with(
        _raw_profile(
            "ge-noswap",
            maker="GE Healthcare",
            model="Unknown GE Model",
            coordinates={"swap_lateral_longitudinal": False},
        )
    )
    output = analyze_input_file(str(path), settings=settings, input_schema="generic_rdsr_like")
    match = _match(output)
    assert (match["source"], match["profile_id"]) == ("custom", "ge-noswap")
    assert match["notice"]["kind"] == "partial"
    assert match["affected_event_count"] == 1


def test_ge_swap_geometry_differs_with_explicit_false(tmp_path: Path) -> None:
    text = _RAW_HEADER + "\n" + _RAW_ROW.format(
        maker="GE Healthcare", model="Unknown GE Model", kvp=77.0, dose=0.00003
    ) + "\n"
    path = _raw_csv(tmp_path, "ge.csv", text)
    from guiskindose.input_adapters.registry import read_and_normalize_input

    plain_settings = _settings()
    plain = read_and_normalize_input(path, input_schema="generic_rdsr_like", settings=plain_settings)
    assert plain_settings.normalization_settings.swap_lateral_longitudinal is True
    assert plain.normalized_data["Tx"].iloc[0] == pytest.approx(4.06)
    custom_settings = _settings_with(
        _raw_profile(
            "ge-noswap",
            maker="GE Healthcare",
            model="Unknown GE Model",
            coordinates={"swap_lateral_longitudinal": False},
        )
    )
    custom = read_and_normalize_input(path, input_schema="generic_rdsr_like", settings=custom_settings)
    assert custom_settings.normalization_settings.swap_lateral_longitudinal is False
    assert custom.normalized_data["Tx"].iloc[0] == pytest.approx(3.78)
    assert custom.normalized_data["Tz"].iloc[0] == pytest.approx(4.06)


# ---------------------------------------------------------------------------
# Filtering, fallback, and source parity
# ---------------------------------------------------------------------------


def test_zero_dose_incomplete_event_dropped_and_counted(tmp_path: Path) -> None:
    rows = [
        _RAW_ROW.format(maker="Siemens", model="AXIOM-Artis", kvp=77.0, dose=0.00003),
        _RAW_ROW.format(maker="Siemens", model="AXIOM-Artis", kvp="", dose=0.0),
    ]
    path = _raw_csv(tmp_path, "events.csv", _RAW_HEADER + "\n" + "\n".join(rows) + "\n")
    settings = _settings_with(_raw_profile("siemens-tweak", coordinates={"detector_side_length": 30.0}))
    output = analyze_input_file(str(path), settings=settings, input_schema="generic_rdsr_like")
    match = _match(output)
    assert match["affected_event_count"] == 1
    assert len(output["events"]["kerma"]) == 1


def test_unknown_identity_falls_back_to_default(tmp_path: Path) -> None:
    path = _raw_csv(
        tmp_path, "unknown.csv", _single_event_csv(maker="NoSuch", model="NoSuch")
    )
    settings = _settings_with(_raw_profile("siemens-tweak", coordinates={"detector_side_length": 30.0}))
    output = analyze_input_file(str(path), settings=settings, input_schema="generic_rdsr_like")
    match = _match(output)
    assert (match["source"], match["level"]) == ("default", "default")
    assert match["notice"]["kind"] == "complete"
    assert match["matched_input_key"] == {"manufacturer": "nosuch", "model": "nosuch"}
    plain = analyze_input_file(str(path), settings=_settings(), input_schema="generic_rdsr_like")
    assert plain.get("equipment_profile_match") is None
    assert output["psd"] == plain["psd"]


def test_store_file_memory_parity(tmp_path: Path) -> None:
    raw = _raw_profile("parity", maker="Acme Imaging", model="Scope P", coordinates={"detector_side_length": 30.0})
    path = tmp_path / "parity.json"
    path.write_text(json.dumps({"schema_version": 1, "profiles": [raw]}), encoding="utf-8")
    store = ProfileStore.open(tmp_path / "parity.sqlite3")
    try:
        (profile,) = parse_memory_document({"schema_version": 1, "profiles": [raw]}).profiles
        store.save_new_revision(profile)
        snapshot = store.selected_snapshot(["parity"])
    finally:
        store.close()
    from guiskindose.equipment_profiles import FileSource

    file_session = assemble_session(files=[FileSource(str(path))])
    memory_session = assemble_session(documents=[{"schema_version": 1, "profiles": [raw]}])
    store_session = assemble_session(snapshots=[snapshot])
    results = []
    for session in (file_session, memory_session, store_session):
        settings = _settings()
        settings.equipment_profile_session = session
        csv_path = _raw_csv(
            tmp_path, f"parity-{session.provenance.sources[0].kind}.csv",
            _single_event_csv(maker="Acme Imaging", model="Scope P"),
        )
        output = analyze_input_file(str(csv_path), settings=settings, input_schema="generic_rdsr_like")
        results.append(output)
    psds = [output["psd"] for output in results]
    assert psds[0] == psds[1] == psds[2]
    kinds = [output["equipment_profile_match"]["source_kind"] for output in results]
    assert kinds == ["json", "memory", "store"]
    assert [output["equipment_profile_match"]["profile_id"] for output in results] == ["parity"] * 3
    assert [output["equipment_profile_match"]["revision"] for output in results] == [None, None, 1]


# ---------------------------------------------------------------------------
# Notices, hashes, reuse, and refusal paths
# ---------------------------------------------------------------------------


def test_match_carries_hashes_and_session_context() -> None:
    from guiskindose.equipment_profiles import profile_hash

    settings = _settings_with(_raw_profile("siemens-full", coordinates=_full_coordinates()))
    output = analyze_input_file(str(_DICOM), settings=settings)
    match = _match(output)
    session = settings.equipment_profile_session
    assert session is not None
    assert match["active_set_hash"] == session.active_set_hash
    assert match["profile_hash"] == profile_hash(session.profiles[0])
    assert match["revision"] is None
    assert match["session"]["total_profiles"] == 1
    assert match["session"]["sources"][0]["kind"] == "memory"
    assert "text" in match["notice"]
    assert isinstance(match["notice"]["text"], str)


def test_settings_reuse_across_identities_has_no_stale_state() -> None:
    import tempfile

    settings = _settings_with(_raw_profile("siemens-tweak", coordinates={"detector_side_length": 30.0}))
    first = analyze_input_file(str(_DICOM), settings=settings)
    assert _match(first)["profile_id"] == "siemens-tweak"
    assert settings.normalization_settings.input_manufacturer == "Siemens"
    with tempfile.TemporaryDirectory() as tmp:
        other = Path(tmp) / "other.csv"
        other.write_text(_single_event_csv(maker="NoSuch", model="NoSuch"), encoding="utf-8")
        second = analyze_input_file(str(other), settings=settings, input_schema="generic_rdsr_like")
    assert _match(second)["source"] == "default"
    assert settings.normalization_settings.input_manufacturer == "NoSuch"
    assert settings.normalization_settings.matched_manufacturer == "Default"
    third = analyze_input_file(str(_DICOM), settings=settings)
    assert _match(third)["profile_id"] == "siemens-tweak"
    assert settings.normalization_settings.input_manufacturer == "Siemens"
    assert settings.normalization_settings.matched_manufacturer == "Siemens"


def test_unsupported_session_fails_before_any_load(tmp_path: Path) -> None:
    document = {
        "schema_version": 1,
        "profiles": [_raw_profile("wild", models=["*"], coordinates={"detector_side_length": 40.0})],
    }
    with pytest.raises(EquipmentProfileError) as excinfo:
        assemble_session(documents=[document])
    assert excinfo.value.code is ProfileErrorCode.UNSUPPORTED_PROFILE_CAPABILITY
    # A normal run afterwards is unaffected.
    output = analyze_input_file(str(_DICOM), settings=_settings())
    assert output.get("equipment_profile_match") is None


def test_mixed_manufacturer_raw_input_fails_and_settings_stay_usable(tmp_path: Path) -> None:
    rows = [
        _RAW_ROW.format(maker="Siemens", model="AXIOM-Artis", kvp=77.0, dose=0.00003),
        _RAW_ROW.format(maker="Philips", model="Allura Clarity", kvp=77.0, dose=0.00003),
    ]
    path = _raw_csv(tmp_path, "mixed.csv", _RAW_HEADER + "\n" + "\n".join(rows) + "\n")
    settings = _settings_with(_raw_profile("siemens-tweak", coordinates={"detector_side_length": 30.0}))
    from guiskindose.rdsr_input_checks import RdsrInputError

    with pytest.raises(RdsrInputError):
        analyze_input_file(str(path), settings=settings, input_schema="generic_rdsr_like")
    output = analyze_input_file(str(_DICOM), settings=settings)
    assert _match(output)["profile_id"] == "siemens-tweak"


def test_normalized_schema_with_session_is_refused(tmp_path: Path) -> None:
    header = (
        "model,DSD,DSI,DID,DSIRP,acquisition_type,acquisition_plane,Tx,Ty,Tz,At1,At2,At3,"
        "filter_thickness_Cu,filter_thickness_Al,Ap1,Ap2,Ap3,DSL,FS_lat,FS_long,kVp,K_IRP"
    )
    row = "AXIOM-Artis,119.8,78.5,41.3,63.5,Fluoroscopy,Single Plane,3.78,29.41,4.06,0,0,0,0.6,0.0,-0.1,-1.1,0,40,10,10,77,0.03"
    path = _raw_csv(tmp_path, "norm.csv", header + "\n" + row + "\n")
    settings = _settings_with(_raw_profile("siemens-tweak", coordinates={"detector_side_length": 30.0}))
    with pytest.raises(ValueError, match="pre-transformed geometry"):
        analyze_input_file(str(path), settings=settings, input_schema="normalized")


def test_preparsed_json_with_session_is_refused() -> None:
    preparsed = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "guiskindose"
        / "example_data"
        / "RDSR"
        / "beam_collimations.json"
    )
    settings = _settings_with(_raw_profile("siemens-tweak", coordinates={"detector_side_length": 30.0}))
    with pytest.raises(ValueError, match="raw DICOM"):
        analyze_input_file(str(preparsed), settings=settings)


def test_direct_analyze_data_with_session_and_no_record_fails() -> None:
    from guiskindose.helpers.read_and_normalize_rdsr_data import read_and_normalise_rdsr_data

    plain_settings = _settings()
    data_norm = read_and_normalise_rdsr_data(rdsr_filepath=str(_DICOM), settings=plain_settings)
    settings = _settings_with(_raw_profile("siemens-tweak", coordinates={"detector_side_length": 30.0}))
    with pytest.raises(ValueError, match=r"no.*resolved raw provenance"):
        analyze_data(normalized_data=data_norm, settings=settings)
    empty_settings = _settings()
    empty_settings.equipment_profile_session = assemble_session()
    output = analyze_data(normalized_data=data_norm, settings=empty_settings)
    assert isinstance(output, dict)
    assert output.get("equipment_profile_match") is None


def test_no_session_golden_parity_and_absent_match() -> None:
    output = analyze_input_file(str(_DICOM), settings=_settings())
    assert output.get("equipment_profile_match") is None
    assert output["psd"] == pytest.approx(1.1773, abs=1e-3)


def test_session_survives_settings_serialization_round_trip() -> None:
    settings = _settings_with(_raw_profile("siemens-tweak", coordinates={"detector_side_length": 30.0}))
    serialized = settings.to_settings_dict()
    assert "equipment_profile_session" not in serialized
    assert "equipment_profile_session" not in settings.to_json()
    rebuilt = PyskindoseSettings(settings=serialized, output_format="dict")
    assert rebuilt.equipment_profile_session is None


def test_mistyped_session_attribute_fails_closed() -> None:
    settings = _settings()
    settings.equipment_profile_session = "not-a-session"  # type: ignore[assignment]
    with pytest.raises(ValueError, match="EquipmentProfileSession"):
        analyze_input_file(str(_DICOM), settings=settings)


def test_settings_constructor_validates_session_type() -> None:
    base = load_settings_example_json()
    with pytest.raises(ValueError, match="EquipmentProfileSession"):
        PyskindoseSettings(settings=base, output_format="dict", equipment_profile_session="nope")  # type: ignore[arg-type]


def test_multi_exam_per_exam_records_and_preserved_totals(tmp_path: Path) -> None:
    first = _raw_csv(tmp_path, "ex1.csv", _single_event_csv(maker="Siemens", model="AXIOM-Artis"))
    second = _raw_csv(tmp_path, "ex2.csv", _single_event_csv(maker="NoSuch", model="NoSuch"))
    settings = _settings_with(
        _raw_profile("siemens-tweak", coordinates={"detector_side_length": 30.0})
    )
    result = analyze_multiple_input_files(
        [first, second], settings=settings, input_schema="generic_rdsr_like"
    )
    payload = result.to_dict()
    assert [exam["equipment_profile_match"]["profile_id"] for exam in payload["exams"]] == [
        "siemens-tweak",
        "bundled-default-default",
    ]
    assert [exam["equipment_profile_match"]["source"] for exam in payload["exams"]] == ["custom", "default"]
    singles = [
        analyze_input_file(str(path), settings=_settings_with(
            _raw_profile("siemens-tweak", coordinates={"detector_side_length": 30.0})
        ), input_schema="generic_rdsr_like")["psd"]
        for path in (first, second)
    ]
    assert [exam["output"]["psd"] for exam in payload["exams"]] == singles
    assert payload["total_events"] == 2
    assert [exam["event_count"] for exam in payload["exams"]] == [1, 1]


def test_output_hides_notes_paths_and_station_identifiers(tmp_path: Path) -> None:
    secret_path = tmp_path / "secret_clinic_notes.json"
    secret_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "profiles": [
                    _raw_profile(
                        "sneaky",
                        maker="Siemens",
                        model="AXIOM-Artis",
                        coordinates={"detector_side_length": 30.0},
                        provenance={"source": "Dr Quiet", "notes": "Confidential ward note"},
                    )
                ],
            }
        ),
        encoding="utf-8",
    )
    from guiskindose.equipment_profiles import FileSource

    settings = _settings()
    settings.equipment_profile_session = assemble_session(files=[FileSource(str(secret_path))])
    output = analyze_input_file(str(_DICOM), settings=settings)
    text = json.dumps(output)
    for sentinel in ("secret_clinic", "Dr Quiet", "Confidential ward note", "StationName", "Serial"):
        assert sentinel not in text, sentinel


def test_radimetrics_raw_path_resolves_custom() -> None:
    path = _FIXTURES / "radimetrics_events.csv"
    settings = _settings_with(
        _raw_profile("radimetrics-tweak", coordinates={"translation_offset": {"x": 2.0}})
    )
    output = analyze_input_file(str(path), settings=settings, input_schema="radimetrics")
    match = _match(output)
    assert (match["source"], match["profile_id"]) == ("custom", "radimetrics-tweak")
    assert match["affected_event_count"] == 5
    assert match["matched_input_key"] == {"manufacturer": "siemens", "model": "axiom artis"}


def test_dosetrack_raw_path_resolves_custom() -> None:
    path = _FIXTURES / "dosetrack_events.csv"
    settings = _settings_with(
        _raw_profile("dosetrack-tweak", coordinates={"translation_offset": {"x": 2.0}})
    )
    output = analyze_input_file(str(path), settings=settings, input_schema="dosetrack")
    match = _match(output)
    assert (match["source"], match["profile_id"]) == ("custom", "dosetrack-tweak")
    assert match["affected_event_count"] == len(output["events"]["kerma"])


# ---------------------------------------------------------------------------
# Field-size mode ordering: effective custom mode governs validation
# ---------------------------------------------------------------------------


def _philips_cfa_csv(tmp_path: Path) -> Path:
    # Philips selects bundled ASD, but the file carries CFA and no shutters.
    text = _RAW_HEADER + "\n" + _RAW_ROW.format(
        maker="Philips", model="Allura Clarity", kvp=60.0, dose=0.00003
    ) + "\n"
    return _raw_csv(tmp_path, "philips.csv", text)


def test_custom_cfa_over_bundled_asd_passes_without_shutters(tmp_path: Path) -> None:
    path = _philips_cfa_csv(tmp_path)
    settings = _settings_with(
        _raw_profile(
            "philips-cfa",
            maker="Philips",
            model="Allura Clarity",
            coordinates={"field_size_mode": "CFA", "detector_side_length": 40.0},
        )
    )
    output = analyze_input_file(str(path), settings=settings, input_schema="generic_rdsr_like")
    match = _match(output)
    assert (match["source"], match["profile_id"]) == ("custom", "philips-cfa")
    assert match["notice"]["kind"] == "partial"
    by_field = {leaf["field"]: leaf for leaf in match["fields"]}
    assert by_field["field_size_mode"]["value"] == "CFA"
    assert by_field["field_size_mode"]["inherited"] is False


def test_custom_asd_over_bundled_cfa_requires_shutters(tmp_path: Path) -> None:
    from guiskindose.rdsr_input_checks import RdsrInputError

    path = _raw_csv(
        tmp_path, "siemens.csv", _single_event_csv(maker="Siemens", model="AXIOM-Artis")
    )
    settings = _settings_with(
        _raw_profile(
            "siemens-asd",
            coordinates={"field_size_mode": "ASD", "detector_side_length": 40.0},
        )
    )
    with pytest.raises(RdsrInputError) as excinfo:
        analyze_input_file(str(path), settings=settings, input_schema="generic_rdsr_like")
    assert "hutter" in str(excinfo.value)


def test_failed_normalization_publishes_no_record() -> None:
    import pandas as pd

    from guiskindose.rdsr_normalizer import rdsr_normalizer_with_source_rows

    frame = pd.DataFrame(
        {
            "Manufacturer": ["Siemens"],
            "ManufacturerModelName": ["AXIOM-Artis"],
            "DistanceSourcetoDetector_mm": [1000.0],
            "FinalDistanceSourcetoDetector_mm": [1000.0],
            "DistanceSourcetoIsocenter_mm": [700.0],
            "IrradiationEventType": ["Fluoroscopy"],
            "AcquisitionPlane": ["Single Plane"],
            "TableLongitudinalPosition_mm": [100.0],
            "TableHeightPosition_mm": [200.0],
            "TableLateralPosition_mm": [300.0],
            "XRayFilterMaterial": [["Copper or Copper compound", "Aluminum or Aluminum compound"]],
            "XRayFilterThicknessMinimum_mm": [[0.1, 1.0]],
            "XRayFilterThicknessMaximum_mm": [[0.1, 1.0]],
            "PositionerPrimaryAngle_deg": [10.0],
            "PositionerSecondaryAngle_deg": [20.0],
            "CollimatedFieldArea_m2": [0.01],
            "KVP_kV": [80.0],
            "DoseRP_Gy": [0.5],
        }
    )
    settings = _settings_with(
        _raw_profile(
            "siemens-asd",
            coordinates={"field_size_mode": "ASD", "detector_side_length": 40.0},
        )
    )
    from guiskindose.rdsr_input_checks import RdsrInputError

    published: list = []
    with pytest.raises(RdsrInputError):
        rdsr_normalizer_with_source_rows(frame, settings, equipment_receipt_out=published)
    assert published == []


# ---------------------------------------------------------------------------
# Empty retained frames fail safely under a session
# ---------------------------------------------------------------------------


def test_empty_retained_frame_fails_safely(tmp_path: Path) -> None:
    import pandas as pd

    from guiskindose.equipment_resolution import finalize_session_application

    settings = _settings_with(_raw_profile("siemens-tweak", coordinates={"detector_side_length": 30.0}))
    empty = pd.DataFrame(
        {"Manufacturer": pd.Series(dtype=object), "ManufacturerModelName": pd.Series(dtype=object)}
    )
    with pytest.raises(ValueError, match="retained"):
        finalize_session_application(data_parsed=empty, settings=settings, applied=True)


# ---------------------------------------------------------------------------
# Receipt binding: wrong session, changed frame, forged records
# ---------------------------------------------------------------------------


def _dicom_receipt(maker="Siemens", model="AXIOM-Artis"):
    from guiskindose.helpers.read_and_normalize_rdsr_data import read_and_normalise_rdsr_data

    settings = _settings_with(_raw_profile("siemens-tweak", coordinates={"detector_side_length": 30.0}))
    published: list = []
    frame = read_and_normalise_rdsr_data(
        rdsr_filepath=str(_DICOM), settings=settings, equipment_receipt_out=published
    )
    assert len(published) == 1
    return settings, frame, published[0]


def test_wrong_session_receipt_rejected() -> None:
    _, frame_a, receipt_a = _dicom_receipt()
    settings_b = _settings_with(_raw_profile("other-tweak", coordinates={"detector_side_length": 31.0}))
    with pytest.raises(ValueError, match="different session"):
        analyze_data(normalized_data=frame_a, settings=settings_b, equipment_receipt=receipt_a)


def test_changed_frame_rejected() -> None:
    settings, frame, receipt = _dicom_receipt()
    with pytest.raises(ValueError, match="event count"):
        analyze_data(normalized_data=frame.iloc[:20], settings=settings, equipment_receipt=receipt)


def test_changed_identity_rejected() -> None:
    from guiskindose.helpers.read_and_normalize_rdsr_data import read_and_normalise_rdsr_data

    settings, _, receipt = _dicom_receipt()
    philips_frame = read_and_normalise_rdsr_data(
        rdsr_filepath=str(_PHILIPS_DICOM), settings=_settings()
    )
    with pytest.raises(ValueError, match="identity"):
        analyze_data(normalized_data=philips_frame, settings=settings, equipment_receipt=receipt)


def test_forged_record_fields_rejected() -> None:
    import dataclasses

    settings, frame, receipt = _dicom_receipt()
    forged_record = dataclasses.replace(receipt.resolution.record, fields="junk")
    forged = dataclasses.replace(
        receipt, resolution=dataclasses.replace(receipt.resolution, record=forged_record)
    )
    with pytest.raises(ValueError, match="15 leaves"):
        analyze_data(normalized_data=frame, settings=settings, equipment_receipt=forged)


def test_forged_notice_rejected() -> None:
    import dataclasses

    settings, frame, receipt = _dicom_receipt()
    forged = dataclasses.replace(
        receipt, resolution=dataclasses.replace(receipt.resolution, notice="junk")
    )
    with pytest.raises(ValueError, match="invalid notice"):
        analyze_data(normalized_data=frame, settings=settings, equipment_receipt=forged)


def test_stale_norm_settings_detected() -> None:
    settings, frame, receipt = _dicom_receipt()
    settings.normalization_settings.trans_offset.x = 999.0
    with pytest.raises(ValueError, match="no longer match"):
        analyze_data(normalized_data=frame, settings=settings, equipment_receipt=receipt)


def test_resolve_twice_yields_identical_receipts() -> None:
    from guiskindose.helpers.read_and_normalize_rdsr_data import read_and_normalise_rdsr_data

    settings = _settings_with(_raw_profile("siemens-tweak", coordinates={"detector_side_length": 30.0}))
    first_out: list = []
    read_and_normalise_rdsr_data(rdsr_filepath=str(_DICOM), settings=settings, equipment_receipt_out=first_out)
    second_out: list = []
    read_and_normalise_rdsr_data(rdsr_filepath=str(_DICOM), settings=settings, equipment_receipt_out=second_out)
    assert first_out == second_out


def test_multi_atomic_preflight_before_any_calculation(tmp_path: Path) -> None:
    from guiskindose.input_adapters.registry import read_and_normalize_input
    from guiskindose.main import analyze_multiple_exams

    settings = _settings_with(_raw_profile("siemens-tweak", coordinates={"detector_side_length": 30.0}))
    good_path = _raw_csv(tmp_path, "good.csv", _single_event_csv(maker="Siemens", model="AXIOM-Artis"))
    good = read_and_normalize_input(good_path, input_schema="generic_rdsr_like", settings=settings)
    assert not isinstance(good, list)
    plain_settings = _settings()
    bad_path = _raw_csv(tmp_path, "bad.csv", _single_event_csv(maker="Siemens", model="AXIOM-Artis"))
    bad = read_and_normalize_input(bad_path, input_schema="generic_rdsr_like", settings=plain_settings)
    assert not isinstance(bad, list)
    with pytest.raises(ValueError, match="Exam 2"):
        analyze_multiple_exams([good, bad], settings)


# ---------------------------------------------------------------------------
# Per-exam restore: distinct full profiles must not leak across exams
# ---------------------------------------------------------------------------


def _siemens_full():
    return _raw_profile(
        "siemens-full",
        coordinates={
            "translation_offset": {"x": 5.0, "y": 1.0, "z": -1.0},
            "translation_direction": {"x": "+", "y": "-", "z": "+"},
            "rotation_direction": {"Ap1": "-", "Ap2": "+", "Ap3": "+", "At1": "+", "At2": "-", "At3": "+"},
            "swap_lateral_longitudinal": False,
            "field_size_mode": "CFA",
            "detector_side_length": 30.0,
        },
    )


def _philips_full():
    return _raw_profile(
        "philips-full",
        maker="Philips",
        model="Allura Clarity",
        coordinates={
            "translation_offset": {"x": -2.0, "y": 3.0, "z": 4.0},
            "translation_direction": {"x": "-", "y": "+", "z": "+"},
            "rotation_direction": {"Ap1": "+", "Ap2": "-", "Ap3": "+", "At1": "+", "At2": "+", "At3": "-"},
            "swap_lateral_longitudinal": True,
            "field_size_mode": "ASD",
            "detector_side_length": 25.0,
        },
    )


def _two_custom_session():
    return _session_for(_siemens_full(), _philips_full())


def test_multi_distinct_full_profiles_match_separate_runs() -> None:
    from guiskindose.main import analyze_multiple_input_files

    session = _two_custom_session()
    first_settings = _settings()
    first_settings.equipment_profile_session = session
    second_settings = _settings()
    second_settings.equipment_profile_session = session
    solo_siemens = analyze_input_file(str(_DICOM), settings=first_settings)
    solo_philips = analyze_input_file(str(_PHILIPS_DICOM), settings=second_settings)
    multi_settings = _settings()
    multi_settings.equipment_profile_session = session
    result = analyze_multiple_input_files([_DICOM, _PHILIPS_DICOM], settings=multi_settings)
    payload = result.to_dict()
    assert [exam["equipment_profile_match"]["profile_id"] for exam in payload["exams"]] == [
        "siemens-full",
        "philips-full",
    ]
    assert [exam["equipment_profile_match"]["source"] for exam in payload["exams"]] == ["custom", "custom"]
    for exam, solo in zip(payload["exams"], (solo_siemens, solo_philips), strict=True):
        assert exam["output"]["psd"] == solo["psd"]
        assert exam["output"]["events"]["kerma"] == solo["events"]["kerma"]
        assert exam["equipment_profile_match"] == solo["equipment_profile_match"]
        assert exam["output"]["dose_map"] == solo["dose_map"]


def test_multi_exam_restores_effective_settings_per_exam() -> None:
    import sys

    from guiskindose.main import analyze_multiple_input_files

    session = _two_custom_session()
    settings = _settings()
    settings.equipment_profile_session = session
    seen = {}
    analyze_module = sys.modules["guiskindose.analyze_data"]
    real_calculate = analyze_module.calculate_dose

    def spy(*, normalized_data, settings, table, pad, exam_id):
        norm = settings.normalization_settings
        seen[exam_id] = (
            norm.trans_offset.x,
            norm.trans_offset.y,
            norm.swap_lateral_longitudinal,
            norm.field_size_mode,
            norm.detector_side_length,
            norm.rot_dir.Ap2,
            norm.matched_manufacturer,
            norm.matched_model,
        )
        return real_calculate(
            normalized_data=normalized_data, settings=settings, table=table, pad=pad, exam_id=exam_id
        )

    monkeypatch = pytest.MonkeyPatch()
    try:
        monkeypatch.setattr(analyze_module, "calculate_dose", spy)
        analyze_multiple_input_files([_DICOM, _PHILIPS_DICOM], settings=settings)
    finally:
        monkeypatch.undo()
    assert seen["Exam 1"] == (5.0, 1.0, False, "CFA", 30.0, 1, "Siemens", "AXIOM-Artis")
    assert seen["Exam 2"] == (-2.0, 3.0, True, "ASD", 25.0, -1, "Philips", "Allura Clarity")


def test_norm_summary_refreshes_with_custom_values() -> None:
    settings = _settings_with(_raw_profile("siemens-swap", coordinates={"swap_lateral_longitudinal": True}))
    analyze_input_file(str(_DICOM), settings=settings)
    summary = settings.normalization_settings.attrs_str
    assert "swap_lateral_longitudinal : True" in summary
    assert "Siemens" in summary
    plain_settings = _settings()
    analyze_input_file(str(_DICOM), settings=plain_settings)
    assert "swap_lateral_longitudinal : False" in plain_settings.normalization_settings.attrs_str


def test_restore_direct_bridge_overwrites_both_directions() -> None:
    from guiskindose.equipment_resolution import restore_receipt_to_settings
    from guiskindose.helpers.read_and_normalize_rdsr_data import read_and_normalise_rdsr_data

    session = _two_custom_session()
    first_settings = _settings()
    first_settings.equipment_profile_session = session
    first_out: list = []
    read_and_normalise_rdsr_data(
        rdsr_filepath=str(_DICOM), settings=first_settings, equipment_receipt_out=first_out
    )
    second_settings = _settings()
    second_settings.equipment_profile_session = session
    second_out: list = []
    read_and_normalise_rdsr_data(
        rdsr_filepath=str(_PHILIPS_DICOM), settings=second_settings, equipment_receipt_out=second_out
    )
    receipt_a, receipt_b = first_out[0], second_out[0]
    fresh = _settings()
    norm = fresh.normalization_settings
    restore_receipt_to_settings(receipt_b, norm)
    assert (norm.trans_offset.x, norm.swap_lateral_longitudinal, norm.detector_side_length) == (-2.0, True, 25.0)
    assert (norm.matched_manufacturer, norm.matched_model) == ("Philips", "Allura Clarity")
    restore_receipt_to_settings(receipt_a, norm)
    assert (norm.trans_offset.x, norm.swap_lateral_longitudinal, norm.detector_side_length) == (5.0, False, 30.0)
    assert (norm.matched_manufacturer, norm.matched_model) == ("Siemens", "AXIOM-Artis")



def test_changed_geometry_with_same_identity_and_count_rejected() -> None:
    settings, frame, receipt = _dicom_receipt()
    changed = frame.copy()
    changed["Tx"] = changed["Tx"] + 1.0
    with pytest.raises(ValueError, match="geometry"):
        analyze_data(normalized_data=changed, settings=settings, equipment_receipt=receipt)


def test_well_typed_forged_notice_text_rejected() -> None:
    from dataclasses import replace

    settings, frame, receipt = _dicom_receipt()
    notice = replace(receipt.resolution.notice, text="Synthetic forbidden notice payload")
    forged = replace(receipt, resolution=replace(receipt.resolution, notice=notice))
    with pytest.raises(ValueError, match="resolved session content"):
        analyze_data(normalized_data=frame, settings=settings, equipment_receipt=forged)


def test_receipt_not_published_on_geometry_failure(monkeypatch) -> None:
    import importlib

    import pydicom

    from guiskindose.rdsr_parser import rdsr_parser

    normalizer = importlib.import_module("guiskindose.rdsr_normalizer")
    parsed = rdsr_parser(pydicom.dcmread(_DICOM))
    settings = _settings_with(_raw_profile("siemens-tweak", coordinates={"detector_side_length": 30.0}))
    published: list = []

    def fail_geometry(**kwargs):
        raise ValueError("Synthetic geometry failure")

    monkeypatch.setattr(normalizer, "_normalize_beam_parameters", fail_geometry)
    with pytest.raises(ValueError, match="Synthetic geometry failure"):
        normalizer.rdsr_normalizer(parsed, settings, equipment_receipt_out=published)
    assert published == []


def test_dicom_post_normalization_kvp_filter_rebinds_receipt(monkeypatch) -> None:
    import importlib

    helper = importlib.import_module("guiskindose.helpers.read_and_normalize_rdsr_data")
    settings, frame, receipt = _dicom_receipt()
    settings.remove_invalid_rows = True
    changed = frame.copy()
    changed.loc[changed.index[0], "kVp"] = 0.0

    def normalized_snapshot(data_parsed, settings, *, equipment_receipt_out):
        equipment_receipt_out.append(receipt)
        return changed

    monkeypatch.setattr(helper, "rdsr_normalizer", normalized_snapshot)
    published: list = []
    retained = helper.read_and_normalise_rdsr_data(str(_DICOM), settings, equipment_receipt_out=published)
    assert len(retained) == len(frame) - 1
    assert published[0].event_count == len(retained)
    assert published[0].resolution.record.affected_event_count == len(retained)
    from guiskindose.equipment_resolution import validate_application_receipt

    validate_application_receipt(receipt=published[0], frame=retained, settings=settings)



@pytest.mark.parametrize("field,value", [
    ("translation_offset.x", False),
    ("translation_offset.x", float("nan")),
    ("translation_direction.x", "invalid"),
    ("rotation_direction.Ap1", 1.0),
    ("swap_lateral_longitudinal", 1.0),
    ("field_size_mode", "invalid"),
    ("detector_side_length", True),
])
def test_forged_leaf_scalars_fail_closed(field, value) -> None:
    from dataclasses import replace

    settings, frame, receipt = _dicom_receipt()
    fields = tuple(replace(leaf, value=value) if leaf.field == field else leaf for leaf in receipt.resolution.record.fields)
    record = replace(receipt.resolution.record, fields=fields)
    forged = replace(receipt, resolution=replace(receipt.resolution, record=record))
    with pytest.raises(ValueError, match="invalid leaf value"):
        analyze_data(normalized_data=frame, settings=settings, equipment_receipt=forged)
