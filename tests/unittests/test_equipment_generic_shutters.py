"""Tests for optional canonical shutter columns in generic_rdsr_like.

A real Philips DICOM's parsed table (with parser-generated shutter values in
mm) is exported to synthetic CSV/TSV/XLSX fixtures under ``tmp_path``; the
dual-material filter cells are scalarized to their copper layer because no
CSV-safe spelling carries both layers (documented below — dose differs from
the DICOM run by that physics alone, while every geometry column stays
byte-identical). Covers ASD live session, capture, offline replay, and
``analyze_data`` parity; string coercion and header case variants; missing
and invalid shutter edges failing closed; CFA independence from shutters;
and no shutter leakage into normalized output. No tracked fixtures.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from guiskindose import load_settings_example_json
from guiskindose.equipment_profiles import assemble_session
from guiskindose.equipment_profiles.capture import (
    CODE_EQUIPMENT_GEOMETRY_MISMATCH,
    CODE_INVALID_EQUIPMENT_CAPTURE,
    CaptureError,
)
from guiskindose.input_adapters.registry import read_and_normalize_input
from guiskindose.main import analyze_data, analyze_input_file
from guiskindose.settings import PyskindoseSettings

_PHILIPS_DICOM = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "guiskindose"
    / "example_data"
    / "RDSR"
    / "philips_allura_clarity_u104.dcm"
)

_GEOMETRY_COLUMNS = (
    "Tx",
    "Ty",
    "Tz",
    "Ap1",
    "Ap2",
    "kVp",
    "DSL",
    "FS_lat",
    "FS_long",
    "DSD",
    "DSI",
    "DID",
    "DSIRP",
    "K_IRP",
)


def _asd_coordinates() -> dict[str, Any]:
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


def _philips_session() -> Any:
    doc = {
        "schema_version": 1,
        "profiles": [
            {
                "profile_id": "g-asd",
                "manufacturer": "Philips",
                "models": ["Allura Clarity"],
                "coordinates": _asd_coordinates(),
            }
        ],
    }
    return assemble_session(documents=[doc])


def _dose_settings(session: Any = None) -> PyskindoseSettings:
    config = load_settings_example_json()
    config["mode"] = "calculate_dose"
    if session is None:
        return PyskindoseSettings(settings=config, output_format="dict")
    return PyskindoseSettings(
        settings=config, output_format="dict", equipment_profile_session=session
    )


def _export_philips_frame(tmp_path: Path, name: str) -> Path:
    """Export the real Philips parsed table to a CSV fixture (filters scalarized).

    Geometry, shutter, angle, kVp, and dose values stay byte-identical to the
    parser output. The dual-material filter cells have no CSV-safe spelling,
    so each is reduced to its copper layer: dose differs from the DICOM run
    by that filtration physics alone, which the parity tests below pin down
    to exactly the aluminium column.
    """
    import pydicom

    from guiskindose.rdsr_parser import rdsr_parser

    raw = pydicom.dcmread(str(_PHILIPS_DICOM))
    parsed = rdsr_parser(raw, silence_pydicom_warnings=True)
    exported = parsed.copy()

    def _scalarize(value: Any) -> Any:
        if isinstance(value, (list, tuple)) and len(value) > 0:
            return value[0]
        return value

    for column in (
        "XRayFilterMaterial",
        "XRayFilterThicknessMinimum_mm",
        "XRayFilterThicknessMaximum_mm",
    ):
        exported[column] = [_scalarize(value) for value in parsed[column]]
    path = tmp_path / name
    exported.to_csv(path, index=False)
    return path


def _live_capture(path: Path, session: Any) -> tuple[Any, Any, PyskindoseSettings]:
    """Real raw tabular load plus validated capture (no calculation)."""
    from guiskindose.equipment_capture import capture_from_receipt

    settings = _dose_settings(session)
    result = read_and_normalize_input(path, input_schema="generic_rdsr_like", settings=settings)
    assert not isinstance(result, list)
    assert result.equipment_receipt is not None
    receipt = result.equipment_receipt
    context = capture_from_receipt(receipt=receipt, frame=result.normalized_data, settings=settings)
    return context, result.normalized_data, settings


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
# Real Philips-derived ASD parity
# ---------------------------------------------------------------------------


def test_philips_export_asd_replay_parity(tmp_path: Path) -> None:
    session = _philips_session()
    path = _export_philips_frame(tmp_path, "philips_export.csv")
    live_output = analyze_input_file(str(path), settings=_dose_settings(session), input_schema="generic_rdsr_like")
    context, frame, _ = _live_capture(path, session)
    assert context.source == "custom"
    assert [column for column in frame.columns if "hutt" in column] == []
    fresh = _dose_settings()
    replayed = read_and_normalize_input(
        path, input_schema="generic_rdsr_like", settings=fresh, equipment_capture_context=context
    )
    assert not isinstance(replayed, list)
    assert replayed.equipment_receipt is None
    assert replayed.normalized_data.equals(frame)
    actual: Any = analyze_data(replayed.normalized_data, fresh, equipment_capture_context=context)
    assert actual["psd"] == live_output["psd"]
    assert actual["dose_map"] == live_output["dose_map"]
    assert actual["equipment_profile_match"] == live_output["equipment_profile_match"]


def test_exported_geometry_matches_dicom_run(tmp_path: Path) -> None:
    import pydicom

    from guiskindose.helpers.read_and_normalize_rdsr_data import read_and_normalise_rdsr_data
    from guiskindose.rdsr_parser import rdsr_parser

    session = _philips_session()
    path = _export_philips_frame(tmp_path, "philips_export.csv")
    context, frame, _ = _live_capture(path, session)
    raw = pydicom.dcmread(str(_PHILIPS_DICOM))
    parsed = rdsr_parser(raw, silence_pydicom_warnings=True)
    for column, expected in (
        ("LeftShutter_mm", 130.0),
        ("RightShutter_mm", 130.0),
        ("TopShutter_mm", 163.5),
        ("BottomShutter_mm", 163.5),
    ):
        assert float(parsed[column].iloc[0]) == expected
    dicom_settings = _dose_settings(session)
    dicom_frame = read_and_normalise_rdsr_data(str(_PHILIPS_DICOM), dicom_settings)
    assert len(dicom_frame) == len(frame)
    for column in _GEOMETRY_COLUMNS:
        assert (frame[column].to_numpy() == dicom_frame[column].to_numpy()).all()
    assert (frame["filter_thickness_Cu"].to_numpy() == dicom_frame["filter_thickness_Cu"].to_numpy()).all()
    assert not (frame["filter_thickness_Al"].to_numpy() == dicom_frame["filter_thickness_Al"].to_numpy()).all()
    fresh = _dose_settings()
    replayed = read_and_normalize_input(
        path, input_schema="generic_rdsr_like", settings=fresh, equipment_capture_context=context
    )
    assert not isinstance(replayed, list)
    assert replayed.normalized_data.equals(frame)


def test_formats_canonical_equivalence(tmp_path: Path) -> None:
    import openpyxl
    import pandas as pd

    session = _philips_session()
    csv_path = _export_philips_frame(tmp_path, "philips_export.csv")
    raw_frame = pd.read_csv(csv_path, dtype=str)
    tsv_path = tmp_path / "philips_export.tsv"
    raw_frame.to_csv(tsv_path, sep="\t", index=False)
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet.append(list(raw_frame.columns))
    for row in raw_frame.itertuples(index=False, name=None):
        sheet.append(list(row))
    xlsx_path = tmp_path / "philips_export.xlsx"
    workbook.save(xlsx_path)
    context, frame, _ = _live_capture(csv_path, session)
    for candidate in (tsv_path, xlsx_path):
        fresh = _dose_settings()
        replayed = read_and_normalize_input(
            candidate, input_schema="generic_rdsr_like", settings=fresh,
            equipment_capture_context=context,
        )
        assert not isinstance(replayed, list)
        assert replayed.normalized_data.equals(frame)


def test_header_case_variants(tmp_path: Path) -> None:
    import pandas as pd

    # Header matching is case-insensitive by construction; only the shutter
    # headers vary here so unrelated case quirks elsewhere stay out of scope.
    session = _philips_session()
    csv_path = _export_philips_frame(tmp_path, "philips_export.csv")
    context, frame, _ = _live_capture(csv_path, session)
    raw_frame = pd.read_csv(csv_path, dtype=str)
    shutters = ["LeftShutter_mm", "RightShutter_mm", "TopShutter_mm", "BottomShutter_mm"]
    raw_frame.columns = [str(name).upper() if name in shutters else name for name in raw_frame.columns]
    upper_path = tmp_path / "philips_upper.csv"
    raw_frame.to_csv(upper_path, index=False)
    fresh = _dose_settings()
    replayed = read_and_normalize_input(
        upper_path, input_schema="generic_rdsr_like", settings=fresh,
        equipment_capture_context=context,
    )
    assert not isinstance(replayed, list)
    assert replayed.normalized_data.equals(frame)


# ---------------------------------------------------------------------------
# Shutter edges: missing and invalid fail closed, CFA ignores shutters
# ---------------------------------------------------------------------------


def test_missing_edge_fails_closed(tmp_path: Path) -> None:
    import pandas as pd

    from guiskindose.rdsr_input_checks import RdsrInputError

    session = _philips_session()
    csv_path = _export_philips_frame(tmp_path, "philips_export.csv")
    raw_frame = pd.read_csv(csv_path, dtype=str)
    dropped = raw_frame.drop(columns=["BottomShutter_mm"])
    edge_path = tmp_path / "philips_no_edge.csv"
    dropped.to_csv(edge_path, index=False)
    path_str = str(edge_path)
    settings = _dose_settings(session)
    with pytest.raises(RdsrInputError):
        read_and_normalize_input(path_str, input_schema="generic_rdsr_like", settings=settings)


def test_invalid_shutter_stable_failure(tmp_path: Path) -> None:
    import pandas as pd

    from guiskindose.rdsr_input_checks import RdsrInputError

    session = _philips_session()
    csv_path = _export_philips_frame(tmp_path, "philips_export.csv")
    raw_frame = pd.read_csv(csv_path, dtype=str)
    raw_frame["TopShutter_mm"] = "abc"
    bad_path = tmp_path / "philips_bad.csv"
    raw_frame.to_csv(bad_path, index=False)
    path_str = str(bad_path)
    first_settings = _dose_settings(session)
    with pytest.raises(RdsrInputError):
        read_and_normalize_input(path_str, input_schema="generic_rdsr_like", settings=first_settings)
    second_settings = _dose_settings(session)
    with pytest.raises(RdsrInputError):
        read_and_normalize_input(path_str, input_schema="generic_rdsr_like", settings=second_settings)
    context, _, _ = _live_capture(csv_path, session)
    fresh = _dose_settings()
    with pytest.raises(CaptureError) as excinfo:
        read_and_normalize_input(
            bad_path, input_schema="generic_rdsr_like", settings=fresh,
            equipment_capture_context=context,
        )
    assert _code(excinfo) == CODE_INVALID_EQUIPMENT_CAPTURE


def test_cfa_ignores_missing_shutters(tmp_path: Path) -> None:
    header = (
        "Manufacturer,ManufacturerModelName,IrradiationEventType,AcquisitionPlane,"
        "DistanceSourcetoDetector_mm,DistanceSourcetoIsocenter_mm,"
        "TableLongitudinalPosition_mm,TableLateralPosition_mm,TableHeightPosition_mm,"
        "CollimatedFieldArea_m2,XRayFilterMaterial,XRayFilterThicknessMinimum_mm,"
        "XRayFilterThicknessMaximum_mm,PositionerPrimaryAngle_deg,PositionerSecondaryAngle_deg,"
        "KVP_kV,DoseRP_Gy"
    )
    row = (
        "Siemens,AXIOM-Artis,Fluoroscopy,Single Plane,1198,785,37.8,40.6,294.1,0.01,"
        "Copper or Copper compound,0.6,0.6,-0.1,-1.1,77.0,0.00003"
    )
    doc = {
        "schema_version": 1,
        "profiles": [
            {
                "profile_id": "g-cfa",
                "manufacturer": "Siemens",
                "models": ["AXIOM-Artis"],
                "coordinates": {
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
                },
            }
        ],
    }
    session = assemble_session(documents=[doc])
    path = tmp_path / "siemens.csv"
    path.write_text(header + "\n" + row + "\n", encoding="utf-8")
    live_output = analyze_input_file(str(path), settings=_dose_settings(session), input_schema="generic_rdsr_like")
    context, frame, _ = _live_capture(path, session)
    fresh = _dose_settings()
    before = _snapshot_norm(fresh.normalization_settings)
    replayed = read_and_normalize_input(
        path, input_schema="generic_rdsr_like", settings=fresh, equipment_capture_context=context
    )
    assert not isinstance(replayed, list)
    assert replayed.normalized_data.equals(frame)
    actual: Any = analyze_data(replayed.normalized_data, fresh, equipment_capture_context=context)
    assert actual["psd"] == live_output["psd"]
    assert actual["equipment_profile_match"] == live_output["equipment_profile_match"]
    assert _snapshot_norm(fresh.normalization_settings) == before


def test_mismatched_context_rejected(tmp_path: Path) -> None:
    session = _philips_session()
    csv_path = _export_philips_frame(tmp_path, "philips_export.csv")
    context, _, _ = _live_capture(csv_path, session)
    tampered = _export_philips_frame(tmp_path, "philips_shifted.csv")
    import pandas as pd

    shifted = pd.read_csv(tampered, dtype=str)
    shifted["TableLongitudinalPosition_mm"] = [
        str(float(value) + 1000.0) for value in shifted["TableLongitudinalPosition_mm"]
    ]
    shifted.to_csv(tampered, index=False)
    fresh = _dose_settings()
    with pytest.raises(CaptureError) as excinfo:
        read_and_normalize_input(
            tampered, input_schema="generic_rdsr_like", settings=fresh,
            equipment_capture_context=context,
        )
    assert _code(excinfo) == CODE_EQUIPMENT_GEOMETRY_MISMATCH
