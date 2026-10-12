"""Tests for raw tabular replay from captured authorities.

Captures flow from real raw tabular loads (generic, Radimetrics, DoseTrack)
through the capture producer; replay re-reads the same raw source with no
live session. Covers CSV/TSV/in-memory-XLSX canonical-frame equivalence,
CFA parity plus ASD enforcement, partial/default/missing-identity recipes,
zero/False recipes, matching and divergent import options, dropped-row
retention counts, explicit/auto normalized refusal, malformed-capture pre-I/O
rejection with zero file reads, session and settings conflicts, offline
replay with bundled selection and resolution forcibly broken, geometry and
identity tampering, caller purity, and PSD/dose-map/match parity through
``analyze_data``. Fixtures are synthetic single-row files under ``tmp_path``
shaped after the tracked adapter fixtures. No tracked binary fixtures.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from guiskindose import load_settings_example_json
from guiskindose.equipment_profiles import FileSource, assemble_session
from guiskindose.equipment_profiles.capture import (
    CODE_EQUIPMENT_GEOMETRY_MISMATCH,
    CODE_INVALID_EQUIPMENT_CAPTURE,
    CaptureError,
)
from guiskindose.input_adapters.import_options import TabularImportOptions
from guiskindose.input_adapters.registry import read_and_normalize_input
from guiskindose.main import analyze_data, analyze_input_file
from guiskindose.settings import PyskindoseSettings

_GENERIC_HEADER = (
    "Manufacturer,ManufacturerModelName,IrradiationEventType,AcquisitionPlane,"
    "DistanceSourcetoDetector_mm,DistanceSourcetoIsocenter_mm,"
    "TableLongitudinalPosition_mm,TableLateralPosition_mm,TableHeightPosition_mm,"
    "CollimatedFieldArea_m2,XRayFilterMaterial,XRayFilterThicknessMinimum_mm,"
    "XRayFilterThicknessMaximum_mm,PositionerPrimaryAngle_deg,PositionerSecondaryAngle_deg,"
    "KVP_kV,DoseRP_Gy"
)
_GENERIC_ROW = (
    "Siemens,AXIOM-Artis,Fluoroscopy,Single Plane,1198,785,37.8,40.6,294.1,0.01,"
    "Copper or Copper compound,0.6,0.6,-0.1,-1.1,77.0,0.00003"
)

_RADIMETRICS_HEADER = (
    "Manufacturer,Device,Acquisition Plane Code (RF),Date Performed,"
    "Irradiation Event Type (RF),Acquisition Protocol (RF),DAP (Total) Gy-cm2,"
    "Reference Point Dose (Total) mGy,Primary Angle (RF) [°],Secondary Angle (RF) [°],"
    "Collimated Field Area (RF) [cm²],Xray Filter Material Codes (RF),"
    "Xray Filter Min Thicknesses,Xray Filter Max Thicknesses,kVp kV,mA (RF),"
    "Pulse Width (RF),mAs mAs,Source To Detector Distance (RF) [mm],"
    "Source To Isocenter Distance (RF) [mm],Table Longitudinal Position [mm],"
    "Table Lateral Position [mm],Table Height Position [mm]"
)
_RADIMETRICS_ROW = (
    "Siemens,AXIOM-Artis,Single Plane,2026-06-01,Fluoroscopy,FL - High Con.,"
    "7.4e-07,0.030,-0.1,-1.1,1054.4149,Copper or Copper compound,0.6,0.6,77.0,"
    "48.0,31.0,1.488,1198.0,785.0,37.8,40.6,294.1"
)

_DOSETRACK_HEADER = (
    "Equipment Name,Plane Code,Study Date,Acquisition Type,Acquisition Protocol Name,"
    "Air Kerma (mGy),DAP (Gy*cm2),Tube Voltage Peak (kV),Tube Current (uA),mAs (mAs),"
    "Positioner Primary Angle (deg),Positioner Secondary Angle (deg),"
    "Collimated Field Area (m2),Filter Type,Filter Material,Filter Thickness,"
    "Pulse Rate (pulse/s),Pulse Width (ms),Focal Spot Size (mm),"
    "Distance Source to Detector (mm),Distance Source To Isocenter (mm),"
    "Table Longitudinal Position (mm),Table Lateral Position (mm),"
    "Table Height Position (mm),Target Region"
)
_DOSETRACK_ROW = (
    "AXIOM-Artis,113622,2026-06-01,Fluoroscopy,FL - Standard,15.0,0.540,70,100000,2.5,"
    "0.0,0.0,0.01000,Copper,Cu,0.1,15.0,80.0,0.3,1000.0,750.0,0.0,0.0,290.0,Pelvis"
)

_NORMALIZED_HEADER = (
    "manufacturer,model,DSD,DSI,DID,DSIRP,acquisition_type,acquisition_plane,"
    "Tx,Ty,Tz,At1,At2,At3,filter_thickness_Cu,filter_thickness_Al,"
    "Ap1,Ap2,Ap3,DSL,FS_lat,FS_long,kVp,K_IRP"
)
_NORMALIZED_ROW = (
    "Siemens,AXIOM-Artis,119.8,78.5,41.3,5.0,Fluoroscopy,Single Plane,"
    "0,0,0,0,0,0,0.6,0.1,0,0,0,30,10,10,77,0.00003"
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


def _siemens_doc(profile_id: str = "t-siemens") -> dict[str, Any]:
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


def _live_capture(path: Path, schema: str, session: Any) -> tuple[Any, Any, PyskindoseSettings]:
    """Real raw tabular load plus validated capture (no calculation)."""
    from guiskindose.equipment_capture import capture_from_receipt

    settings = _dose_settings(session)
    result = read_and_normalize_input(path, input_schema=schema, settings=settings)
    assert not isinstance(result, list)
    assert result.equipment_receipt is not None
    receipt = result.equipment_receipt
    context = capture_from_receipt(receipt=receipt, frame=result.normalized_data, settings=settings)
    return context, result.normalized_data, settings


def _replay(path: Path, schema: str, context: Any) -> tuple[Any, Any]:
    """Replay one raw file with a capture on fresh settings."""
    fresh = _dose_settings()
    result = read_and_normalize_input(
        path, input_schema=schema, settings=fresh, equipment_capture_context=context
    )
    assert not isinstance(result, list)
    return result, fresh


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
# Per-schema replay parity
# ---------------------------------------------------------------------------


def test_generic_csv_replay_parity(tmp_path: Path) -> None:
    session = assemble_session(documents=[_siemens_doc()])
    path = _write(tmp_path, "events.csv", _GENERIC_HEADER + "\n" + _GENERIC_ROW + "\n")
    live_output = analyze_input_file(str(path), settings=_dose_settings(session), input_schema="generic_rdsr_like")
    context, frame, _ = _live_capture(path, "generic_rdsr_like", session)
    result, fresh = _replay(path, "generic_rdsr_like", context)
    assert result.equipment_receipt is None
    assert result.normalized_data.equals(frame)
    actual: Any = analyze_data(result.normalized_data, fresh, equipment_capture_context=context)
    assert actual["psd"] == live_output["psd"]
    assert actual["dose_map"] == live_output["dose_map"]
    assert actual["equipment_profile_match"] == live_output["equipment_profile_match"]


def test_radimetrics_csv_replay_parity(tmp_path: Path) -> None:
    session = assemble_session(documents=[_siemens_doc()])
    path = _write(tmp_path, "rad.csv", _RADIMETRICS_HEADER + "\n" + _RADIMETRICS_ROW + "\n")
    live_output = analyze_input_file(str(path), settings=_dose_settings(session), input_schema="radimetrics")
    context, frame, _ = _live_capture(path, "radimetrics", session)
    result, fresh = _replay(path, "radimetrics", context)
    assert result.equipment_receipt is None
    assert result.normalized_data.equals(frame)
    actual: Any = analyze_data(result.normalized_data, fresh, equipment_capture_context=context)
    assert actual["psd"] == live_output["psd"]
    assert actual["dose_map"] == live_output["dose_map"]
    assert actual["equipment_profile_match"] == live_output["equipment_profile_match"]


def test_dosetrack_csv_replay_parity(tmp_path: Path) -> None:
    session = assemble_session(documents=[_siemens_doc()])
    path = _write(tmp_path, "dose.csv", _DOSETRACK_HEADER + "\n" + _DOSETRACK_ROW + "\n")
    live_output = analyze_input_file(str(path), settings=_dose_settings(session), input_schema="dosetrack")
    context, frame, _ = _live_capture(path, "dosetrack", session)
    result, fresh = _replay(path, "dosetrack", context)
    assert result.equipment_receipt is None
    assert result.normalized_data.equals(frame)
    actual: Any = analyze_data(result.normalized_data, fresh, equipment_capture_context=context)
    assert actual["psd"] == live_output["psd"]
    assert actual["dose_map"] == live_output["dose_map"]
    assert actual["equipment_profile_match"] == live_output["equipment_profile_match"]


def test_tsv_xlsx_same_canonical_frame(tmp_path: Path) -> None:
    session = assemble_session(documents=[_siemens_doc()])
    csv_path = _write(tmp_path, "events.csv", _GENERIC_HEADER + "\n" + _GENERIC_ROW + "\n")
    tsv_path = _write(tmp_path, "events.tsv", _GENERIC_HEADER.replace(",", "\t") + "\n" + _GENERIC_ROW.replace(",", "\t") + "\n")
    xlsx_path = _write_xlsx(tmp_path, "events.xlsx")
    context, frame, _ = _live_capture(csv_path, "generic_rdsr_like", session)
    tsv_result, _ = _replay_typed(tsv_path, "generic_rdsr_like", context)
    xlsx_result, _ = _replay_typed(xlsx_path, "generic_rdsr_like", context)
    assert tsv_result.normalized_data.equals(frame)
    assert xlsx_result.normalized_data.equals(frame)
    assert tsv_result.equipment_receipt is None
    assert xlsx_result.equipment_receipt is None


def _write_xlsx(tmp_path: Path, name: str) -> Path:
    """Build an in-memory XLSX workbook (never a tracked fixture)."""
    import openpyxl

    workbook = openpyxl.Workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet.append(_GENERIC_HEADER.split(","))
    sheet.append(_GENERIC_ROW.split(","))
    path = tmp_path / name
    workbook.save(path)
    return path


def _replay_typed(path: Path, schema: str, context: Any) -> tuple[Any, Any]:
    fresh = _dose_settings()
    result = read_and_normalize_input(
        path, input_schema=schema, settings=fresh, equipment_capture_context=context
    )
    assert not isinstance(result, list)
    return result, fresh


def test_partial_and_default_replay(tmp_path: Path) -> None:
    partial_doc = {
        "schema_version": 1,
        "profiles": [
            {
                "profile_id": "t-partial",
                "manufacturer": "Siemens",
                "models": ["AXIOM-Artis"],
                "coordinates": {"detector_side_length": 30.0},
            }
        ],
    }
    partial_session = assemble_session(documents=[partial_doc])
    path = _write(tmp_path, "events.csv", _GENERIC_HEADER + "\n" + _GENERIC_ROW + "\n")
    partial_live = analyze_input_file(str(path), settings=_dose_settings(partial_session), input_schema="generic_rdsr_like")
    partial_context, _, _ = _live_capture(path, "generic_rdsr_like", partial_session)
    assert partial_context.notice_kind == "partial"
    partial_result, partial_fresh = _replay(path, "generic_rdsr_like", partial_context)
    partial_actual: Any = analyze_data(
        partial_result.normalized_data, partial_fresh, equipment_capture_context=partial_context
    )
    assert partial_actual["psd"] == partial_live["psd"]
    assert partial_actual["equipment_profile_match"] == partial_live["equipment_profile_match"]
    blank_row = _GENERIC_ROW.replace("Siemens,AXIOM-Artis", ",", 1)
    blank_path = _write(tmp_path, "blank.csv", _GENERIC_HEADER + "\n" + blank_row + "\n")
    default_session = assemble_session(documents=[_siemens_doc()])
    default_live = analyze_input_file(
        str(blank_path), settings=_dose_settings(default_session), input_schema="generic_rdsr_like"
    )
    assert default_live["equipment_profile_match"]["source"] == "default"
    default_context, default_frame, _ = _live_capture(blank_path, "generic_rdsr_like", default_session)
    default_result, default_fresh = _replay(blank_path, "generic_rdsr_like", default_context)
    assert default_result.normalized_data.equals(default_frame)
    default_actual: Any = analyze_data(
        default_result.normalized_data, default_fresh, equipment_capture_context=default_context
    )
    assert default_actual["psd"] == default_live["psd"]
    assert default_actual["equipment_profile_match"] == default_live["equipment_profile_match"]


def test_asd_mode_enforced_on_shutterless_tabular(tmp_path: Path) -> None:
    # Tabular schemas carry no shutter columns, so a genuine ASD recipe fails
    # closed at concept enforcement. The ASD capture below is produced by the
    # real Philips DICOM loader (no mutated or rehashed content); only the
    # replay input is tabular, with Philips identity but no shutters.
    from guiskindose.helpers.read_and_normalize_rdsr_data import read_and_normalise_rdsr_data

    philips_doc = {
        "schema_version": 1,
        "profiles": [
            {
                "profile_id": "t-asd",
                "manufacturer": "Philips",
                "models": ["Allura Clarity"],
                "coordinates": {
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
                },
            }
        ],
    }
    philips_dicom = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "guiskindose"
        / "example_data"
        / "RDSR"
        / "philips_allura_clarity_u104.dcm"
    )
    philips_session = assemble_session(documents=[philips_doc])
    philips_settings = _dose_settings(philips_session)
    out: list[Any] = []
    philips_frame = read_and_normalise_rdsr_data(
        str(philips_dicom), philips_settings, equipment_receipt_out=out
    )
    assert len(out) == 1
    from guiskindose.equipment_capture import capture_from_receipt

    asd_context = capture_from_receipt(
        receipt=out[0], frame=philips_frame, settings=philips_settings
    )
    assert asd_context.source == "custom"
    philips_row = _GENERIC_ROW.replace("Siemens,AXIOM-Artis", "Philips,Allura Clarity", 1)
    path = _write(tmp_path, "philips.csv", _GENERIC_HEADER + "\n" + philips_row + "\n")
    fresh = _dose_settings()
    with pytest.raises(CaptureError) as excinfo:
        read_and_normalize_input(
            path, input_schema="generic_rdsr_like", settings=fresh, equipment_capture_context=asd_context
        )
    assert _code(excinfo) == CODE_INVALID_EQUIPMENT_CAPTURE


# ---------------------------------------------------------------------------
# Import options and dropped rows
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "options",
    [
        TabularImportOptions(swap_lat_lon=True),
        TabularImportOptions(flip_ap1=True),
        TabularImportOptions(swap_lat_lon=True, flip_ap2=True),
    ],
    ids=["swapped", "flipped", "both"],
)
def test_matching_import_options_accept_divergent_reject(tmp_path: Path, options: Any) -> None:
    from guiskindose.equipment_capture import capture_from_receipt, capture_to_mapping

    session = assemble_session(documents=[_siemens_doc()])
    path = _write(tmp_path, "events.csv", _GENERIC_HEADER + "\n" + _GENERIC_ROW + "\n")
    live_settings = _dose_settings(session)
    live_output = analyze_input_file(
        str(path), settings=live_settings, input_schema="generic_rdsr_like", import_options=options
    )
    live_result = read_and_normalize_input(
        path, input_schema="generic_rdsr_like", settings=live_settings, import_options=options
    )
    assert not isinstance(live_result, list)
    assert live_result.equipment_receipt is not None
    context = capture_from_receipt(
        receipt=live_result.equipment_receipt, frame=live_result.normalized_data, settings=live_settings
    )
    fresh = _dose_settings()
    replayed = read_and_normalize_input(
        path,
        input_schema="generic_rdsr_like",
        settings=fresh,
        import_options=options,
        equipment_capture_context=context,
    )
    assert not isinstance(replayed, list)
    assert replayed.normalized_data.equals(live_result.normalized_data)
    actual: Any = analyze_data(replayed.normalized_data, fresh, equipment_capture_context=context)
    assert actual["psd"] == live_output["psd"]
    assert actual["dose_map"] == live_output["dose_map"]
    assert actual["equipment_profile_match"] == live_output["equipment_profile_match"]
    assert actual["equipment_profile_match"] == capture_to_mapping(context)["match"]
    divergent = TabularImportOptions()
    divergent_settings = _dose_settings()
    with pytest.raises(CaptureError) as excinfo:
        read_and_normalize_input(
            path,
            input_schema="generic_rdsr_like",
            settings=divergent_settings,
            import_options=divergent,
            equipment_capture_context=context,
        )
    assert _code(excinfo) == CODE_EQUIPMENT_GEOMETRY_MISMATCH


def test_dropped_source_row_retention_counts(tmp_path: Path) -> None:
    bad_row = _GENERIC_ROW.replace("0.00003", "0.0").replace("0.01,", ",", 1)
    text = _GENERIC_HEADER + "\n" + _GENERIC_ROW + "\n" + bad_row + "\n"
    path = _write(tmp_path, "dropped.csv", text)
    session = assemble_session(documents=[_siemens_doc()])
    settings = _dose_settings(session)
    result = read_and_normalize_input(path, input_schema="generic_rdsr_like", settings=settings)
    assert not isinstance(result, list)
    assert len(result.normalized_data) == 1
    assert result.equipment_receipt is not None
    from guiskindose.equipment_capture import capture_from_receipt

    context = capture_from_receipt(
        receipt=result.equipment_receipt, frame=result.normalized_data, settings=settings
    )
    assert context.event_count == 1
    fresh = _dose_settings()
    replayed = read_and_normalize_input(
        path, input_schema="generic_rdsr_like", settings=fresh, equipment_capture_context=context
    )
    assert not isinstance(replayed, list)
    assert len(replayed.normalized_data) == 1
    assert replayed.normalized_data.equals(result.normalized_data)


# ---------------------------------------------------------------------------
# Refusals: normalized, malformed, session, settings
# ---------------------------------------------------------------------------


def test_explicit_and_auto_normalized_refusal(tmp_path: Path) -> None:
    session = assemble_session(documents=[_siemens_doc()])
    csv_path = _write(tmp_path, "events.csv", _GENERIC_HEADER + "\n" + _GENERIC_ROW + "\n")
    context, _, _ = _live_capture(csv_path, "generic_rdsr_like", session)
    norm_path = _write(tmp_path, "norm.csv", _NORMALIZED_HEADER + "\n" + _NORMALIZED_ROW + "\n")
    fresh = _dose_settings()
    with pytest.raises(CaptureError) as excinfo:
        read_and_normalize_input(
            norm_path, input_schema="normalized", settings=fresh, equipment_capture_context=context
        )
    assert _code(excinfo) == CODE_INVALID_EQUIPMENT_CAPTURE
    with pytest.raises(CaptureError) as excinfo:
        read_and_normalize_input(
            norm_path, input_schema="auto", settings=fresh, equipment_capture_context=context
        )
    assert _code(excinfo) == CODE_INVALID_EQUIPMENT_CAPTURE


def test_malformed_capture_reads_zero_sources(monkeypatch: Any, tmp_path: Path) -> None:
    import copy as _copy

    import guiskindose.input_adapters.tabular_loader as loader_module

    session = assemble_session(documents=[_siemens_doc()])
    path = _write(tmp_path, "events.csv", _GENERIC_HEADER + "\n" + _GENERIC_ROW + "\n")
    context, _, _ = _live_capture(path, "generic_rdsr_like", session)
    forged = _copy.copy(context)
    object.__setattr__(forged, "event_count", "bad")
    real_load = loader_module.load
    reads: list[str] = []

    def _spy(path: Any, *args: Any, **kwargs: Any) -> Any:
        reads.append(str(path))
        return real_load(path, *args, **kwargs)

    monkeypatch.setattr(loader_module, "load", _spy)
    fresh = _dose_settings()
    with pytest.raises(CaptureError) as excinfo:
        read_and_normalize_input(
            path, input_schema="generic_rdsr_like", settings=fresh, equipment_capture_context=forged
        )
    assert _code(excinfo) == CODE_INVALID_EQUIPMENT_CAPTURE
    assert reads == []


def test_session_conflict_and_missing_settings(tmp_path: Path) -> None:
    session = assemble_session(documents=[_siemens_doc()])
    path = _write(tmp_path, "events.csv", _GENERIC_HEADER + "\n" + _GENERIC_ROW + "\n")
    context, _, _ = _live_capture(path, "generic_rdsr_like", session)
    missing = tmp_path / "missing.csv"
    live_settings = _dose_settings(session)
    with pytest.raises(CaptureError) as excinfo:
        read_and_normalize_input(
            missing, input_schema="generic_rdsr_like", settings=live_settings,
            equipment_capture_context=context,
        )
    assert _code(excinfo) == CODE_INVALID_EQUIPMENT_CAPTURE
    with pytest.raises(CaptureError) as excinfo:
        read_and_normalize_input(
            missing, input_schema="generic_rdsr_like", settings=None,
            equipment_capture_context=context,
        )
    assert _code(excinfo) == CODE_INVALID_EQUIPMENT_CAPTURE


# ---------------------------------------------------------------------------
# Preparation binding: single preparation, mutated candidates reject
# ---------------------------------------------------------------------------


def test_single_preparation_binding(monkeypatch: Any, tmp_path: Path) -> None:
    import guiskindose.equipment_confirmation as confirmation_module

    session = assemble_session(documents=[_siemens_doc()])
    path = _write(tmp_path, "events.csv", _GENERIC_HEADER + "\n" + _GENERIC_ROW + "\n")
    context, _, _ = _live_capture(path, "generic_rdsr_like", session)
    real_prepare = confirmation_module.prepare_replay_settings
    calls: list[str] = []

    def _counting(*args: Any, **kwargs: Any) -> Any:
        calls.append("prepare")
        return real_prepare(*args, **kwargs)

    monkeypatch.setattr(confirmation_module, "prepare_replay_settings", _counting)
    fresh = _dose_settings()
    replayed = read_and_normalize_input(
        path, input_schema="generic_rdsr_like", settings=fresh, equipment_capture_context=context
    )
    assert not isinstance(replayed, list)
    assert calls == ["prepare"]


def test_mutated_candidate_rejected_and_caller_unchanged(monkeypatch: Any, tmp_path: Path) -> None:
    import guiskindose.equipment_confirmation as confirmation_module

    session = assemble_session(documents=[_siemens_doc()])
    path = _write(tmp_path, "events.csv", _GENERIC_HEADER + "\n" + _GENERIC_ROW + "\n")
    context, _, _ = _live_capture(path, "generic_rdsr_like", session)
    real_prepare = confirmation_module.prepare_replay_settings

    def _mutating(*args: Any, **kwargs: Any) -> Any:
        work = real_prepare(*args, **kwargs)
        work.normalization_settings.trans_offset.x = 9999.0
        return work

    monkeypatch.setattr(confirmation_module, "prepare_replay_settings", _mutating)
    fresh = _dose_settings()
    before = _snapshot_norm(fresh.normalization_settings)
    with pytest.raises(CaptureError) as excinfo:
        read_and_normalize_input(
            path, input_schema="generic_rdsr_like", settings=fresh, equipment_capture_context=context
        )
    assert _code(excinfo) == CODE_INVALID_EQUIPMENT_CAPTURE
    assert _snapshot_norm(fresh.normalization_settings) == before


# ---------------------------------------------------------------------------
# Offline replay, tampering, caller purity
# ---------------------------------------------------------------------------


def test_offline_bundles_broken(monkeypatch: Any, tmp_path: Path) -> None:
    from guiskindose.equipment_capture import capture_to_json
    from guiskindose.equipment_profiles.capture_codec import capture_from_json
    from guiskindose.settings import normalization_settings as normalization_module

    doc = _siemens_doc()
    path = tmp_path / "profiles.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    session = assemble_session(files=[FileSource(path)])
    csv_path = _write(tmp_path, "events.csv", _GENERIC_HEADER + "\n" + _GENERIC_ROW + "\n")
    context, frame, _ = _live_capture(csv_path, "generic_rdsr_like", session)
    parsed = capture_from_json(capture_to_json(context))
    path.unlink()

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
    fresh = _dose_settings()
    replayed = read_and_normalize_input(
        csv_path, input_schema="generic_rdsr_like", settings=fresh,
        equipment_capture_context=parsed,
    )
    assert not isinstance(replayed, list)
    assert replayed.normalized_data.equals(frame)
    assert replayed.equipment_receipt is None


def test_geometry_and_identity_tamper_rejected(tmp_path: Path) -> None:
    session = assemble_session(documents=[_siemens_doc()])
    path = _write(tmp_path, "events.csv", _GENERIC_HEADER + "\n" + _GENERIC_ROW + "\n")
    context, _, _ = _live_capture(path, "generic_rdsr_like", session)
    shifted = _GENERIC_ROW.replace("37.8,40.6,294.1", "1037.8,40.6,294.1")
    shifted_path = _write(tmp_path, "shifted.csv", _GENERIC_HEADER + "\n" + shifted + "\n")
    fresh = _dose_settings()
    with pytest.raises(CaptureError) as excinfo:
        read_and_normalize_input(
            shifted_path, input_schema="generic_rdsr_like", settings=fresh,
            equipment_capture_context=context,
        )
    assert _code(excinfo) == CODE_EQUIPMENT_GEOMETRY_MISMATCH
    renamed = _GENERIC_ROW.replace("Siemens,AXIOM-Artis", "Philips,Allura Clarity", 1)
    renamed_path = _write(tmp_path, "renamed.csv", _GENERIC_HEADER + "\n" + renamed + "\n")
    with pytest.raises(CaptureError) as excinfo:
        read_and_normalize_input(
            renamed_path, input_schema="generic_rdsr_like", settings=fresh,
            equipment_capture_context=context,
        )
    assert _code(excinfo) == CODE_INVALID_EQUIPMENT_CAPTURE


def test_caller_settings_preserved(tmp_path: Path) -> None:
    session = assemble_session(documents=[_siemens_doc()])
    path = _write(tmp_path, "events.csv", _GENERIC_HEADER + "\n" + _GENERIC_ROW + "\n")
    context, _, _ = _live_capture(path, "generic_rdsr_like", session)
    fresh = _dose_settings()
    before = _snapshot_norm(fresh.normalization_settings)
    replayed = read_and_normalize_input(
        path, input_schema="generic_rdsr_like", settings=fresh, equipment_capture_context=context
    )
    assert not isinstance(replayed, list)
    assert _snapshot_norm(fresh.normalization_settings) == before
    shifted = _GENERIC_ROW.replace("37.8,40.6,294.1", "1037.8,40.6,294.1")
    shifted_path = _write(tmp_path, "shifted.csv", _GENERIC_HEADER + "\n" + shifted + "\n")
    with pytest.raises(CaptureError):
        read_and_normalize_input(
            shifted_path, input_schema="generic_rdsr_like", settings=fresh,
            equipment_capture_context=context,
        )
    assert _snapshot_norm(fresh.normalization_settings) == before


def test_corrupt_live_receipt_rejected_before_import_options(monkeypatch: Any, tmp_path: Path) -> None:
    import dataclasses

    import guiskindose.input_adapters.registry as registry_module
    from guiskindose.input_adapters.import_options import TabularImportOptions

    session = assemble_session(documents=[_siemens_doc()])
    path = _write(tmp_path, "events.csv", _GENERIC_HEADER + "\n" + _GENERIC_ROW + "\n")
    settings = _dose_settings(session)
    result = read_and_normalize_input(path, input_schema="generic_rdsr_like", settings=settings)
    assert not isinstance(result, list)
    assert result.equipment_receipt is not None
    result.equipment_receipt = dataclasses.replace(result.equipment_receipt, frame_hash="0" * 64)
    monkeypatch.setattr(registry_module, "_dispatch_to_adapter", lambda *args, **kwargs: result)
    calls: list[str] = []

    def unexpected_options(*args: Any, **kwargs: Any) -> Any:
        calls.append("options")
        return result

    monkeypatch.setattr(registry_module, "_apply_import_options_to_results", unexpected_options)
    options = TabularImportOptions(swap_lat_lon=True)
    with pytest.raises(ValueError, match="receipt geometry"):
        read_and_normalize_input(path, input_schema="generic_rdsr_like", settings=settings, import_options=options)
    assert calls == []


@pytest.mark.parametrize("missing", [True, False])
def test_capture_load_and_header_errors_are_closed(tmp_path: Path, missing: bool) -> None:
    session = assemble_session(documents=[_siemens_doc()])
    source = _write(tmp_path, "events.csv", _GENERIC_HEADER + "\n" + _GENERIC_ROW + "\n")
    context, _, _ = _live_capture(source, "generic_rdsr_like", session)
    path = tmp_path / "PRIVATE_SOURCE_SENTINEL.csv"
    if not missing:
        path.write_text("PRIVATE_HEADER_SENTINEL\ninvalid\n", encoding="utf-8")
    settings = _dose_settings()
    with pytest.raises(CaptureError) as excinfo:
        read_and_normalize_input(path, input_schema="generic_rdsr_like", settings=settings, equipment_capture_context=context)
    assert _code(excinfo) == CODE_INVALID_EQUIPMENT_CAPTURE
    assert excinfo.value.__cause__ is None
    assert excinfo.value.__suppress_context__ is True
    assert "PRIVATE_SOURCE_SENTINEL" not in str(excinfo.value)
    assert "PRIVATE_HEADER_SENTINEL" not in str(excinfo.value)
