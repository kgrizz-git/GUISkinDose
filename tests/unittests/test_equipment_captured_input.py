"""Tests for single-file captured input through the public API.

Captures flow from real raw loads (Siemens/Philips DICOM, generic CSV/TSV/XLSX
with shutters); replay and calculation go exclusively through the public
``analyze_input_file`` and ``main`` entry points with a capture — never
through internal loaders. Covers DICOM full/partial/default and Philips ASD
parity, generic CFA/ASD tabular parity across formats, direct ``main``
parity and tabular refusal, matching import options with genuine post-options
receipts, non-tabular import-options refusal, offline replay, caller purity
and output-format preservation, malformed/forged/session conflicts with zero
source reads, normalized/preparsed-JSON/multi-study/plot-setup refusals, and
unchanged no-capture behavior. No tracked binary fixtures are used.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from guiskindose import get_path_to_example_rdsr_files, load_settings_example_json
from guiskindose.equipment_profiles import FileSource, assemble_session
from guiskindose.equipment_profiles.capture import (
    CODE_EQUIPMENT_GEOMETRY_MISMATCH,
    CODE_INVALID_EQUIPMENT_CAPTURE,
    CaptureError,
)
from guiskindose.input_adapters.import_options import TabularImportOptions
from guiskindose.main import analyze_input_file, main
from guiskindose.settings import PyskindoseSettings

_SIEMENS_DICOM = get_path_to_example_rdsr_files() / "siemens_axiom_artis.dcm"
_PHILIPS_DICOM = get_path_to_example_rdsr_files() / "philips_allura_clarity_u104.dcm"

_GENERIC_HEADER = (
    "Manufacturer,ManufacturerModelName,IrradiationEventType,AcquisitionPlane,"
    "DistanceSourcetoDetector_mm,DistanceSourcetoIsocenter_mm,"
    "TableLongitudinalPosition_mm,TableLateralPosition_mm,TableHeightPosition_mm,"
    "CollimatedFieldArea_m2,XRayFilterMaterial,XRayFilterThicknessMinimum_mm,"
    "XRayFilterThicknessMaximum_mm,PositionerPrimaryAngle_deg,PositionerSecondaryAngle_deg,"
    "KVP_kV,DoseRP_Gy,LeftShutter_mm,RightShutter_mm,TopShutter_mm,BottomShutter_mm"
)
_GENERIC_SIEMENS_ROW = (
    "Siemens,AXIOM-Artis,Fluoroscopy,Single Plane,1198,785,37.8,40.6,294.1,0.01,"
    "Copper or Copper compound,0.6,0.6,-0.1,-1.1,77.0,0.00003,,,"
)
_GENERIC_PHILIPS_ROW = (
    "Philips,Allura Clarity,Fluoroscopy,Single Plane,1198,785,37.8,40.6,294.1,0.01,"
    "Copper or Copper compound,0.6,0.6,-0.1,-1.1,77.0,0.00003,130.0,130.0,163.5,163.5"
)


def _siemens_coordinates() -> dict[str, Any]:
    return {
        "translation_offset": {"x": 5.0, "y": -3.5, "z": 0.0},
        "translation_direction": {"x": "-", "y": "+", "z": "+"},
        "rotation_direction": {
            "Ap1": "-",
            "Ap2": "+",
            "Ap3": "+",
            "At1": "+",
            "At2": "-",
            "At3": "+",
        },
        "swap_lateral_longitudinal": False,
        "field_size_mode": "CFA",
        "detector_side_length": 30.0,
    }


def _philips_coordinates() -> dict[str, Any]:
    return {
        "translation_offset": {"x": 1.0, "y": 2.0, "z": 3.0},
        "translation_direction": {"x": "+", "y": "+", "z": "+"},
        "rotation_direction": {
            "Ap1": "+",
            "Ap2": "-",
            "Ap3": "+",
            "At1": "+",
            "At2": "+",
            "At3": "-",
        },
        "swap_lateral_longitudinal": True,
        "field_size_mode": "ASD",
        "detector_side_length": 25.0,
    }


def _siemens_doc(profile_id: str = "p-siemens") -> dict[str, Any]:
    return {
        "schema_version": 1,
        "profiles": [
            {
                "profile_id": profile_id,
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


def _dose_settings(session: Any = None) -> PyskindoseSettings:
    config = load_settings_example_json()
    config["mode"] = "calculate_dose"
    if session is None:
        return PyskindoseSettings(settings=config, output_format="dict")
    return PyskindoseSettings(
        settings=config, output_format="dict", equipment_profile_session=session
    )


def _write(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def _live_capture_dicom(dicom: Path, session: Any) -> tuple[Any, Any]:
    """Real DICOM load plus validated capture (no calculation)."""
    from guiskindose.equipment_capture import capture_from_receipt
    from guiskindose.helpers.read_and_normalize_rdsr_data import read_and_normalise_rdsr_data

    settings = _dose_settings(session)
    out: list[Any] = []
    frame = read_and_normalise_rdsr_data(str(dicom), settings, equipment_receipt_out=out)
    assert len(out) == 1
    receipt = out[0]
    context = capture_from_receipt(receipt=receipt, frame=frame, settings=settings)
    return context, frame


def _snapshot_norm(norm: Any) -> dict[str, Any]:
    return {
        "offset": (norm.trans_offset.x, norm.trans_offset.y, norm.trans_offset.z),
        "trans_dir": (norm.trans_dir.x, norm.trans_dir.y, norm.trans_dir.z),
        "rot_dir": (
            norm.rot_dir.Ap1,
            norm.rot_dir.Ap2,
            norm.rot_dir.Ap3,
            norm.rot_dir.At1,
            norm.rot_dir.At2,
            norm.rot_dir.At3,
        ),
        "mode": norm.field_size_mode,
        "size": norm.detector_side_length,
        "swap": norm.swap_lateral_longitudinal,
        "input": (norm.input_manufacturer, norm.input_model),
        "matched": (norm.matched_manufacturer, norm.matched_model),
        "method": norm.normalization_method,
        "summary": norm.attrs_str,
    }


def _code(excinfo: pytest.ExceptionInfo[CaptureError]) -> str:
    return excinfo.value.code


# ---------------------------------------------------------------------------
# DICOM parity through the public API
# ---------------------------------------------------------------------------


def test_siemens_dicom_full_parity() -> None:
    session = assemble_session(documents=[_siemens_doc()])
    dicom_str = str(_SIEMENS_DICOM)
    live_output = analyze_input_file(dicom_str, settings=_dose_settings(session))
    context, _ = _live_capture_dicom(_SIEMENS_DICOM, session)
    actual: Any = analyze_input_file(dicom_str, settings=_dose_settings(), equipment_capture_context=context)
    assert actual["psd"] == live_output["psd"]
    assert actual["dose_map"] == live_output["dose_map"]
    assert actual["equipment_profile_match"] == live_output["equipment_profile_match"]


def test_philips_dicom_asd_parity() -> None:
    session = assemble_session(documents=[_philips_doc()])
    dicom_str = str(_PHILIPS_DICOM)
    live_output = analyze_input_file(dicom_str, settings=_dose_settings(session))
    context, _ = _live_capture_dicom(_PHILIPS_DICOM, session)
    assert context.source == "custom"
    actual: Any = analyze_input_file(dicom_str, settings=_dose_settings(), equipment_capture_context=context)
    assert actual["psd"] == live_output["psd"]
    assert actual["dose_map"] == live_output["dose_map"]
    assert actual["equipment_profile_match"] == live_output["equipment_profile_match"]


def test_dicom_partial_and_default_parity() -> None:
    partial_doc = {
        "schema_version": 1,
        "profiles": [
            {
                "profile_id": "p-partial",
                "manufacturer": "Siemens",
                "models": ["AXIOM-Artis"],
                "coordinates": {"detector_side_length": 30.0},
            }
        ],
    }
    partial_session = assemble_session(documents=[partial_doc])
    dicom_str = str(_SIEMENS_DICOM)
    partial_live = analyze_input_file(dicom_str, settings=_dose_settings(partial_session))
    partial_context, _ = _live_capture_dicom(_SIEMENS_DICOM, partial_session)
    assert partial_context.notice_kind == "partial"
    partial_actual: Any = analyze_input_file(
        dicom_str, settings=_dose_settings(), equipment_capture_context=partial_context
    )
    assert partial_actual["psd"] == partial_live["psd"]
    assert partial_actual["equipment_profile_match"] == partial_live["equipment_profile_match"]


def test_main_dicom_parity() -> None:
    session = assemble_session(documents=[_siemens_doc()])
    dicom_str = str(_SIEMENS_DICOM)
    live_output = analyze_input_file(dicom_str, settings=_dose_settings(session))
    context, _ = _live_capture_dicom(_SIEMENS_DICOM, session)
    actual: Any = main(dicom_str, settings=_dose_settings(), equipment_capture_context=context)
    assert actual["psd"] == live_output["psd"]
    assert actual["dose_map"] == live_output["dose_map"]
    assert actual["equipment_profile_match"] == live_output["equipment_profile_match"]


def test_main_tabular_refusal(tmp_path: Path, monkeypatch: Any) -> None:
    import guiskindose.input_adapters.tabular_loader as loader_module

    session = assemble_session(documents=[_siemens_doc()])
    csv_path = _write(tmp_path, "events.csv", _GENERIC_HEADER + "\n" + _GENERIC_SIEMENS_ROW + "\n")
    context, _, _ = _live_capture_csv(csv_path, session)
    real_load = loader_module.load
    reads: list[str] = []

    def _spy_load(path: Any, *args: Any, **kwargs: Any) -> Any:
        reads.append(str(path))
        return real_load(path, *args, **kwargs)

    monkeypatch.setattr(loader_module, "load", _spy_load)
    csv_str = str(csv_path)
    settings = _dose_settings()
    with pytest.raises(CaptureError) as excinfo:
        main(csv_str, settings=settings, equipment_capture_context=context)
    assert _code(excinfo) == CODE_INVALID_EQUIPMENT_CAPTURE
    assert reads == []


# ---------------------------------------------------------------------------
# Tabular parity across formats, modes, and options
# ---------------------------------------------------------------------------


def test_generic_csv_tsv_xlsx_parity(tmp_path: Path) -> None:
    import openpyxl
    import pandas as pd

    session = assemble_session(documents=[_siemens_doc()])
    csv_path = _write(tmp_path, "events.csv", _GENERIC_HEADER + "\n" + _GENERIC_SIEMENS_ROW + "\n")
    raw_frame = pd.read_csv(csv_path, dtype=str)
    tsv_path = tmp_path / "events.tsv"
    raw_frame.to_csv(tsv_path, sep="\t", index=False)
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet.append(list(raw_frame.columns))
    for row in raw_frame.itertuples(index=False, name=None):
        sheet.append(list(row))
    xlsx_path = tmp_path / "events.xlsx"
    workbook.save(xlsx_path)
    live_output = analyze_input_file(
        str(csv_path), settings=_dose_settings(session), input_schema="generic_rdsr_like"
    )
    context, frame, _ = _live_capture_csv(csv_path, session)
    actual: Any = None
    for candidate in (csv_path, tsv_path, xlsx_path):
        candidate_str = str(candidate)
        actual = analyze_input_file(
            candidate_str, settings=_dose_settings(), input_schema="generic_rdsr_like",
            equipment_capture_context=context,
        )
        assert actual["psd"] == live_output["psd"]
        assert actual["dose_map"] == live_output["dose_map"]
    assert actual["equipment_profile_match"] == live_output["equipment_profile_match"]
    assert frame is not None


def _live_capture_csv(path: Path, session: Any) -> tuple[Any, Any, PyskindoseSettings]:
    """Real raw CSV load plus validated capture and its settings (no calculation)."""
    from guiskindose.equipment_capture import capture_from_receipt
    from guiskindose.input_adapters.registry import read_and_normalize_input

    settings = _dose_settings(session)
    result = read_and_normalize_input(path, input_schema="generic_rdsr_like", settings=settings)
    assert not isinstance(result, list)
    assert result.equipment_receipt is not None
    receipt = result.equipment_receipt
    context = capture_from_receipt(receipt=receipt, frame=result.normalized_data, settings=settings)
    return context, result.normalized_data, settings


@pytest.mark.parametrize(
    "options",
    [
        TabularImportOptions(swap_lat_lon=True),
        TabularImportOptions(flip_ap1=True),
        TabularImportOptions(swap_lat_lon=True, flip_ap2=True),
    ],
    ids=["swapped", "flipped", "both"],
)
def test_matching_import_options_parity(tmp_path: Path, options: Any) -> None:
    session = assemble_session(documents=[_siemens_doc()])
    path = _write(tmp_path, "events.csv", _GENERIC_HEADER + "\n" + _GENERIC_SIEMENS_ROW + "\n")
    path_str = str(path)
    live_settings = _dose_settings(session)
    live_output = analyze_input_file(
        path_str, settings=live_settings, input_schema="generic_rdsr_like", import_options=options
    )
    context, _, _ = _live_capture_options(path, session, options)
    actual: Any = analyze_input_file(
        path_str, settings=_dose_settings(), input_schema="generic_rdsr_like",
        import_options=options, equipment_capture_context=context,
    )
    assert actual["psd"] == live_output["psd"]
    assert actual["dose_map"] == live_output["dose_map"]
    assert actual["equipment_profile_match"] == live_output["equipment_profile_match"]
    divergent = TabularImportOptions()
    divergent_settings = _dose_settings()
    with pytest.raises(CaptureError) as excinfo:
        analyze_input_file(
            path_str, settings=divergent_settings, input_schema="generic_rdsr_like",
            import_options=divergent, equipment_capture_context=context,
        )
    assert _code(excinfo) == CODE_EQUIPMENT_GEOMETRY_MISMATCH


def test_import_options_non_tabular_refusal(monkeypatch: Any) -> None:
    session = assemble_session(documents=[_siemens_doc()])
    dicom_str = str(_SIEMENS_DICOM)
    context, _ = _live_capture_dicom(_SIEMENS_DICOM, session)
    options = TabularImportOptions(swap_lat_lon=True)
    settings = _dose_settings()
    reads: list[bool] = []

    def reject_read(*args: Any, **kwargs: Any) -> Any:
        reads.append(True)
        raise AssertionError("unexpected source read")

    monkeypatch.setattr("guiskindose.helpers.read_and_normalize_rdsr_data.pydicom.dcmread", reject_read)
    with pytest.raises(CaptureError) as excinfo:
        analyze_input_file(
            dicom_str, settings=settings, import_options=options,
            equipment_capture_context=context,
        )
    assert _code(excinfo) == CODE_INVALID_EQUIPMENT_CAPTURE
    assert reads == []


def _live_capture_options(path: Path, session: Any, options: Any) -> tuple[Any, Any, Any]:
    """Live CSV load with import options plus a capture over the final frame."""
    from guiskindose.equipment_capture import capture_from_receipt
    from guiskindose.input_adapters.registry import read_and_normalize_input

    settings = _dose_settings(session)
    result = read_and_normalize_input(
        path, input_schema="generic_rdsr_like", settings=settings, import_options=options
    )
    assert not isinstance(result, list)
    assert result.equipment_receipt is not None
    receipt = result.equipment_receipt
    context = capture_from_receipt(receipt=receipt, frame=result.normalized_data, settings=settings)
    return context, result.normalized_data, settings


# ---------------------------------------------------------------------------
# Offline, purity, conflicts, and refusals through the public API
# ---------------------------------------------------------------------------


def test_offline_profiles_deleted_bundles_broken(monkeypatch: Any, tmp_path: Path) -> None:
    import json

    from guiskindose.equipment_capture import capture_to_json
    from guiskindose.equipment_profiles.capture_codec import capture_from_json
    from guiskindose.settings import normalization_settings as normalization_module

    doc = _siemens_doc()
    profile_path = tmp_path / "profiles.json"
    profile_path.write_text(json.dumps(doc), encoding="utf-8")
    session = assemble_session(files=[FileSource(profile_path)])
    csv_path = _write(tmp_path, "events.csv", _GENERIC_HEADER + "\n" + _GENERIC_SIEMENS_ROW + "\n")
    csv_str = str(csv_path)
    live_output = analyze_input_file(str(csv_path), settings=_dose_settings(session), input_schema="generic_rdsr_like")
    context, _, _ = _live_capture_csv(csv_path, session)
    parsed = capture_from_json(capture_to_json(context))
    profile_path.unlink()

    def _raise_selection(self: Any, data_parsed: Any) -> Any:
        raise AssertionError("bundled selection consulted during replay")

    def _raise_resolve(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("live resolver consulted during replay")

    monkeypatch.setattr(
        normalization_module.NormalizationSettings, "update_used_settings", _raise_selection
    )
    monkeypatch.setattr(
        "guiskindose.equipment_resolution.resolve_exam_coordinates", _raise_resolve
    )
    actual: Any = analyze_input_file(
        csv_str, settings=_dose_settings(), input_schema="generic_rdsr_like",
        equipment_capture_context=parsed,
    )
    assert actual["psd"] == live_output["psd"]
    assert actual["equipment_profile_match"] == live_output["equipment_profile_match"]


def test_caller_settings_preserved(tmp_path: Path) -> None:
    session = assemble_session(documents=[_siemens_doc()])
    path = _write(tmp_path, "events.csv", _GENERIC_HEADER + "\n" + _GENERIC_SIEMENS_ROW + "\n")
    path_str = str(path)
    context, _, _ = _live_capture_csv(path, session)
    fresh = _dose_settings()
    before = _snapshot_norm(fresh.normalization_settings)
    actual: Any = analyze_input_file(
        path_str, settings=fresh, input_schema="generic_rdsr_like", equipment_capture_context=context
    )
    assert actual["psd"] > 0.0
    assert _snapshot_norm(fresh.normalization_settings) == before


def test_caller_output_format_preserved(tmp_path: Path) -> None:
    session = assemble_session(documents=[_siemens_doc()])
    path = _write(tmp_path, "events.csv", _GENERIC_HEADER + "\n" + _GENERIC_SIEMENS_ROW + "\n")
    path_str = str(path)
    context, _, _ = _live_capture_csv(path, session)
    config = load_settings_example_json()
    config["mode"] = "calculate_dose"
    fresh = PyskindoseSettings(settings=config, output_format="json")
    actual: Any = analyze_input_file(
        path_str, settings=fresh, input_schema="generic_rdsr_like", output_format="dict",
        equipment_capture_context=context,
    )
    assert isinstance(actual, dict)
    assert fresh.output_format == "json"


def test_malformed_and_session_conflicts_pre_io(monkeypatch: Any, tmp_path: Path) -> None:
    import copy as _copy

    import guiskindose.helpers.read_and_normalize_rdsr_data as dicom_helper
    import guiskindose.input_adapters.tabular_loader as loader_module

    session = assemble_session(documents=[_siemens_doc()])
    path = _write(tmp_path, "events.csv", _GENERIC_HEADER + "\n" + _GENERIC_SIEMENS_ROW + "\n")
    context, _, _ = _live_capture_csv(path, session)
    forged = _copy.copy(context)
    object.__setattr__(forged, "event_count", "bad")
    real_load = loader_module.load
    reads: list[str] = []

    def _spy_load(path: Any, *args: Any, **kwargs: Any) -> Any:
        reads.append(str(path))
        return real_load(path, *args, **kwargs)

    monkeypatch.setattr(loader_module, "load", _spy_load)
    real_read = dicom_helper.pydicom.dcmread
    dicom_reads: list[str] = []

    def _spy_read(path: Any, *args: Any, **kwargs: Any) -> Any:
        dicom_reads.append(str(path))
        return real_read(path, *args, **kwargs)

    monkeypatch.setattr(dicom_helper.pydicom, "dcmread", _spy_read)
    fresh = _dose_settings()
    path_str = str(path)
    with pytest.raises(CaptureError) as excinfo:
        analyze_input_file(
            path_str, settings=fresh, input_schema="generic_rdsr_like", equipment_capture_context=forged
        )
    assert _code(excinfo) == CODE_INVALID_EQUIPMENT_CAPTURE
    assert reads == []
    session_settings = _dose_settings(session)
    with pytest.raises(CaptureError) as excinfo:
        analyze_input_file(
            path_str, settings=session_settings, input_schema="generic_rdsr_like",
            equipment_capture_context=context,
        )
    assert _code(excinfo) == CODE_INVALID_EQUIPMENT_CAPTURE
    assert reads == []
    assert dicom_reads == []


def test_unsupported_inputs_refused(tmp_path: Path) -> None:
    session = assemble_session(documents=[_siemens_doc()])
    csv_path = _write(tmp_path, "events.csv", _GENERIC_HEADER + "\n" + _GENERIC_SIEMENS_ROW + "\n")
    context, _, _ = _live_capture_csv(csv_path, session)
    norm_path = _write(
        tmp_path,
        "norm.csv",
        "manufacturer,model,DSD,DSI,DID,DSIRP,acquisition_type,acquisition_plane,"
        "Tx,Ty,Tz,At1,At2,At3,filter_thickness_Cu,filter_thickness_Al,"
        "Ap1,Ap2,Ap3,DSL,FS_lat,FS_long,kVp,K_IRP\n"
        "Siemens,AXIOM-Artis,119.8,78.5,41.3,5.0,Fluoroscopy,Single Plane,"
        "0,0,0,0,0,0,0.6,0.1,0,0,0,30,10,10,77,0.00003\n",
    )
    norm_str = str(norm_path)
    fresh = _dose_settings()
    with pytest.raises(CaptureError) as excinfo:
        analyze_input_file(
            norm_str, settings=fresh, input_schema="normalized", equipment_capture_context=context
        )
    assert _code(excinfo) == CODE_INVALID_EQUIPMENT_CAPTURE
    multi_path = _write(
        tmp_path,
        "multi.csv",
        "manufacturer,model,DSD,DSI,DID,DSIRP,acquisition_type,acquisition_plane,study_id,"
        "Tx,Ty,Tz,At1,At2,At3,filter_thickness_Cu,filter_thickness_Al,"
        "Ap1,Ap2,Ap3,DSL,FS_lat,FS_long,kVp,K_IRP\n"
        "Siemens,AXIOM-Artis,119.8,78.5,41.3,5.0,Fluoroscopy,Single Plane,S1,"
        "0,0,0,0,0,0,0.6,0.1,0,0,0,30,10,10,77,0.00003\n"
        "Siemens,AXIOM-Artis,119.8,78.5,41.3,5.0,Fluoroscopy,Single Plane,S2,"
        "0,0,0,0,0,0,0.6,0.1,0,0,0,30,10,10,77,0.00003\n",
    )
    multi_str = str(multi_path)
    with pytest.raises(CaptureError) as excinfo:
        analyze_input_file(
            multi_str, settings=fresh, input_schema="normalized", equipment_capture_context=context
        )
    assert _code(excinfo) == CODE_INVALID_EQUIPMENT_CAPTURE
    json_path = tmp_path / "missing.json"
    json_str = str(json_path)
    with pytest.raises(CaptureError) as excinfo:
        analyze_input_file(json_str, settings=fresh, equipment_capture_context=context)
    assert _code(excinfo) == CODE_INVALID_EQUIPMENT_CAPTURE


def test_plot_setup_refusal(tmp_path: Path) -> None:
    session = assemble_session(documents=[_siemens_doc()])
    csv_path = _write(tmp_path, "events.csv", _GENERIC_HEADER + "\n" + _GENERIC_SIEMENS_ROW + "\n")
    context, _, _ = _live_capture_csv(csv_path, session)
    config = load_settings_example_json()
    config["mode"] = "plot_setup"
    plot_settings = PyskindoseSettings(settings=config, output_format="dict")
    csv_str = str(csv_path)
    with pytest.raises(CaptureError) as excinfo:
        analyze_input_file(
            csv_str, settings=plot_settings, input_schema="generic_rdsr_like",
            equipment_capture_context=context,
        )
    assert _code(excinfo) == CODE_INVALID_EQUIPMENT_CAPTURE


def test_no_capture_behavior_unchanged(tmp_path: Path) -> None:
    path = _write(tmp_path, "events.csv", _GENERIC_HEADER + "\n" + _GENERIC_SIEMENS_ROW + "\n")
    path_str = str(path)
    actual: Any = analyze_input_file(path_str, settings=_dose_settings(), input_schema="generic_rdsr_like")
    assert "equipment_profile_match" not in actual
    assert actual["psd"] > 0.0


def test_self_returning_settings_copy_rejected() -> None:
    from guiskindose.equipment_captured_input import shielded_settings_for_capture

    class SharedSettings(PyskindoseSettings):
        def __deepcopy__(self, memo: Any) -> Any:
            return self

    settings = SharedSettings(settings=load_settings_example_json(), output_format="json")
    before = settings.to_settings_dict()
    with pytest.raises(CaptureError) as caught:
        shielded_settings_for_capture(settings)
    assert caught.value.code == CODE_INVALID_EQUIPMENT_CAPTURE
    assert settings.to_settings_dict() == before
    assert settings.output_format == "json"


@pytest.mark.parametrize("malformed", [False, True])
def test_dicom_read_failure_is_private(tmp_path: Path, malformed: bool) -> None:
    session = assemble_session(documents=[_siemens_doc()])
    context, _ = _live_capture_dicom(_SIEMENS_DICOM, session)
    source = tmp_path / "PRIVATE-SENTINEL.dcm"
    if malformed:
        source.write_text("not a DICOM", encoding="utf-8")
    settings = _dose_settings()
    before = settings.to_settings_dict()
    with pytest.raises(CaptureError) as caught:
        analyze_input_file(str(source), settings=settings, equipment_capture_context=context)
    assert caught.value.code == CODE_INVALID_EQUIPMENT_CAPTURE
    assert "PRIVATE-SENTINEL" not in str(caught.value)
    assert caught.value.__suppress_context__
    assert settings.to_settings_dict() == before
