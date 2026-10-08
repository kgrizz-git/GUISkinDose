"""Regression tests for RDSR input hardening (``rdsr_input_checks``).

Each failure class found on the upstream OpenREM RF corpus is reproduced here
synthetically, by mutating the parsed frame of a bundled example RDSR. No
upstream file is vendored (they carry identifiers). See
``dev-docs/plans/RDSR_INPUT_HARDENING_PLAN.md``.
"""

from __future__ import annotations

import io
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pydicom
import pytest

from guiskindose import constants as c
from guiskindose import get_path_to_example_rdsr_files, load_settings_example_json
from guiskindose.privacy import UserFacingInputError, install_value_safe_excepthook
from guiskindose.rdsr_input_checks import (
    RdsrInputError,
    RdsrUnitError,
    collapse_duplicate_scalars,
    enforce_required_concepts,
)
from guiskindose.rdsr_normalizer import rdsr_normalizer
from guiskindose.rdsr_parser import rdsr_parser
from guiskindose.settings import PyskindoseSettings

_EXAMPLE = get_path_to_example_rdsr_files() / "siemens_axiom_artis.dcm"
_N_EVENTS = 21
_DSD = "DistanceSourcetoDetector_mm"
_FINAL_DSD = "FinalDistanceSourcetoDetector_mm"
_HEIGHT = "TableHeightPosition_mm"
_CANONICAL_COLUMNS = ["DSD", "DSI", "Tx", "Ty", "Tz", "Ap1", "Ap2", "kVp", "K_IRP", "FS_lat", "FS_long"]


def _parsed() -> pd.DataFrame:
    return rdsr_parser(pydicom.dcmread(str(_EXAMPLE)), silence_pydicom_warnings=True)


def _settings() -> PyskindoseSettings:
    base = load_settings_example_json()
    base["mode"] = "calculate_dose"
    return PyskindoseSettings(settings=base, output_format="dict")


def _normalize(frame: pd.DataFrame) -> pd.DataFrame:
    return rdsr_normalizer(frame, settings=_settings())


def _assert_same_geometry(got: pd.DataFrame, want: pd.DataFrame) -> None:
    for column in _CANONICAL_COLUMNS:
        np.testing.assert_allclose(
            got[column].astype(float), want[column].astype(float), rtol=1e-12, err_msg=column
        )


@pytest.fixture(scope="module")
def baseline() -> pd.DataFrame:
    return _normalize(_parsed())


# ── A. duplicate scalar measurements ─────────────────────────────────────────


def test_equal_duplicate_list_collapses(baseline: pd.DataFrame) -> None:
    """Philips Azurion pattern: two equal TableHeightPosition items per event (direct path → list)."""
    frame = _parsed()
    frame[_HEIGHT] = [[v, v] for v in frame[_HEIGHT]]
    _assert_same_geometry(_normalize(frame), baseline)


def test_three_equal_nested_copies_collapse(baseline: pd.DataFrame) -> None:
    frame = _parsed()
    frame[_HEIGHT] = pd.Series([((v, v), v) for v in frame[_HEIGHT]], dtype=object)
    _assert_same_geometry(_normalize(frame), baseline)


def test_disagreeing_duplicates_raise_with_count() -> None:
    frame = _parsed()
    heights = frame[_HEIGHT].astype(object).tolist()
    heights[2] = [100.0, 101.0]
    frame[_HEIGHT] = pd.Series(heights, dtype=object)
    with pytest.raises(RdsrInputError, match=r"table height position in 1 event"):
        _normalize(frame)


def test_filter_thickness_lists_are_never_collapsed() -> None:
    """Thickness lists stay aligned with their materials even when the entries are equal."""
    frame = pd.DataFrame(
        {
            c.KEY_RDSR_FILTER_MATERIAL: [[c.KEY_RDSR_FILTER_MATERIAL_COPPER, c.KEY_RDSR_FILTER_MATERIAL_ALUMINUM]],
            c.KEY_RDSR_FILTER_MIN: [[0.1, 0.1]],
            c.KEY_RDSR_FILTER_MAX: [[0.1, 0.1]],
        }
    )
    collapse_duplicate_scalars(frame)
    assert frame.at[0, c.KEY_RDSR_FILTER_MIN] == [0.1, 0.1]
    assert frame.at[0, c.KEY_RDSR_FILTER_MAX] == [0.1, 0.1]


# ── B. scale-only units ──────────────────────────────────────────────────────


def test_mgy_dose_matches_gy(baseline: pd.DataFrame) -> None:
    """Canon Ultimaxi pattern: reference-point dose reported in mGy."""
    frame = _parsed()
    frame["DoseRP_mGy"] = frame.pop("DoseRP_Gy").astype(float) * 1000
    _assert_same_geometry(_normalize(frame), baseline)


@pytest.mark.parametrize(("unit", "divisor"), [("cm", 10.0), ("m", 1000.0)])
def test_cm_and_m_distances_match_mm(baseline: pd.DataFrame, unit: str, divisor: float) -> None:
    frame = _parsed()
    for concept in ("DistanceSourcetoDetector", "DistanceSourcetoIsocenter", "TableHeightPosition"):
        frame[f"{concept}_{unit}"] = frame.pop(f"{concept}_mm").astype(float) / divisor
    _assert_same_geometry(_normalize(frame), baseline)


def test_variant_unit_fills_blank_canonical_events(baseline: pd.DataFrame) -> None:
    frame = _parsed()
    frame["DoseRP_mGy"] = np.nan
    frame.loc[:4, "DoseRP_mGy"] = frame.loc[:4, "DoseRP_Gy"].astype(float) * 1000
    frame["DoseRP_Gy"] = frame["DoseRP_Gy"].astype(object)
    frame.loc[:4, "DoseRP_Gy"] = None
    _assert_same_geometry(_normalize(frame), baseline)


def test_conflicting_mixed_units_raise() -> None:
    frame = _parsed()
    frame["DoseRP_mGy"] = frame["DoseRP_Gy"].astype(float) * 1000
    frame.loc[0, "DoseRP_mGy"] = 999.0
    with pytest.raises(RdsrInputError, match=r"twice in different units.*1 event"):
        _normalize(frame)


def test_unknown_unit_still_raises_unit_error_without_echoing_it() -> None:
    frame = _parsed()
    frame["DoseRP_SENTINELUNIT"] = frame.pop("DoseRP_Gy")
    with pytest.raises(RdsrUnitError) as excinfo:
        _normalize(frame)
    assert "SENTINELUNIT" not in str(excinfo.value)
    assert "reference point dose" in str(excinfo.value)


# ── C. required concepts and DSD resolution ─────────────────────────────────


@pytest.mark.parametrize(
    ("column", "label"),
    [
        ("DistanceSourcetoIsocenter_mm", "source-to-isocenter distance"),
        ("TableLongitudinalPosition_mm", "table longitudinal position"),
        ("TableLateralPosition_mm", "table lateral position"),
        (_HEIGHT, "table height position"),
        ("PositionerPrimaryAngle_deg", "positioner primary angle"),
        ("PositionerSecondaryAngle_deg", "positioner secondary angle"),
        ("KVP_kV", "tube voltage"),
        ("DoseRP_Gy", "reference point dose"),
        ("CollimatedFieldArea_m2", "collimated field area"),
    ],
)
def test_missing_required_column_is_named(column: str, label: str) -> None:
    frame = _parsed().drop(columns=[column])
    with pytest.raises(RdsrInputError, match=rf"{label}.*missing in {_N_EVENTS} of {_N_EVENTS} events"):
        _normalize(frame)


def test_partially_blank_required_value_counts_events() -> None:
    frame = _parsed()
    frame["DistanceSourcetoIsocenter_mm"] = frame["DistanceSourcetoIsocenter_mm"].astype(object)
    frame.loc[[1, 3], "DistanceSourcetoIsocenter_mm"] = None
    with pytest.raises(RdsrInputError, match=rf"source-to-isocenter distance \(missing in 2 of {_N_EVENTS}"):
        _normalize(frame)


def test_presence_only_column_must_exist() -> None:
    frame = _parsed().drop(columns=[c.KEY_RDSR_FILTER_MAX])
    with pytest.raises(RdsrInputError, match=r"maximum filter thickness \(not reported\)"):
        _normalize(frame)


def test_all_missing_concepts_are_reported_together() -> None:
    frame = _parsed().drop(columns=["KVP_kV", "DistanceSourcetoIsocenter_mm"])
    with pytest.raises(RdsrInputError) as excinfo:
        _normalize(frame)
    assert "tube voltage" in str(excinfo.value)
    assert "source-to-isocenter distance" in str(excinfo.value)


def test_shutter_mode_requires_all_four_shutters() -> None:
    frame = pd.DataFrame({"LeftShutter_mm": [1.0]})
    with pytest.raises(RdsrInputError) as excinfo:
        enforce_required_concepts(frame, c.FIELD_SIZE_MODE_ACTUAL_SHUTTER_DISTANCE)
    message = str(excinfo.value)
    assert "left shutter" not in message
    for side in ("right", "top", "bottom"):
        assert f"{side} shutter position" in message
    assert "collimated field area" not in message


def test_blank_dsd_falls_back_to_final_dsd(baseline: pd.DataFrame) -> None:
    frame = _parsed()
    frame[_FINAL_DSD] = frame[_DSD]
    frame[_DSD] = frame[_DSD].astype(object)
    frame.loc[[0, 5], _DSD] = None
    _assert_same_geometry(_normalize(frame), baseline)


def test_absent_dsd_column_uses_final_dsd(baseline: pd.DataFrame) -> None:
    frame = _parsed()
    frame[_FINAL_DSD] = frame.pop(_DSD)
    _assert_same_geometry(_normalize(frame), baseline)


def test_blank_dsd_without_final_dsd_raises_clear_error() -> None:
    """RF-Pat-Orientation-Modifier-Missing pattern: this used to be an AttributeError."""
    frame = _parsed()
    frame[_DSD] = frame[_DSD].astype(object)
    frame.loc[[0, 5], _DSD] = None
    with pytest.raises(RdsrInputError, match=rf"source-to-detector distance \(missing in 2 of {_N_EVENTS}"):
        _normalize(frame)


# ── zero-dose events with incomplete geometry ───────────────────────────────


def test_zero_dose_incomplete_events_are_dropped(baseline: pd.DataFrame) -> None:
    """Azurion pattern: zero-dose events without kVp contribute nothing and are dropped."""
    frame = _parsed()
    frame["KVP_kV"] = frame["KVP_kV"].astype(object)
    frame.loc[[0, 1], "KVP_kV"] = None
    frame["DoseRP_Gy"] = frame["DoseRP_Gy"].astype(object)
    frame.loc[[0, 1], "DoseRP_Gy"] = 0.0
    normalized = _normalize(frame)
    assert len(normalized) == _N_EVENTS - 2
    _assert_same_geometry(normalized, baseline.iloc[2:].reset_index(drop=True))


def test_dosed_incomplete_event_is_not_dropped() -> None:
    frame = _parsed()
    frame["KVP_kV"] = frame["KVP_kV"].astype(object)
    frame.loc[0, "KVP_kV"] = None
    with pytest.raises(RdsrInputError, match=rf"tube voltage \(kVp\) \(missing in 1 of {_N_EVENTS}"):
        _normalize(frame)


def test_all_zero_dose_incomplete_report_is_rejected_not_emptied() -> None:
    frame = _parsed()
    frame["KVP_kV"] = None
    frame["DoseRP_Gy"] = 0.0
    with pytest.raises(RdsrInputError, match=r"tube voltage"):
        _normalize(frame)


# ── D. no events, missing device identity, no default profile ───────────────


def test_report_without_events_raises_clear_error() -> None:
    """Siemens Varic ESR pattern: no irradiation events, so the parsed frame is empty."""
    empty = pd.DataFrame()
    with pytest.raises(RdsrInputError, match=r"no X-ray irradiation events"):
        _normalize(empty)


def test_missing_device_columns_use_default_profile(baseline: pd.DataFrame) -> None:
    frame = _parsed().drop(columns=[c.KEY_RDSR_MANUFACTURER, c.KEY_RDSR_MANUFACTURER_MODEL_NAME])
    settings = _settings()
    rdsr_normalizer(frame, settings=settings)
    assert settings.normalization_settings.normalization_method == "Fallback"


def test_no_default_profile_raises_input_error() -> None:
    settings = _settings()
    norm = settings.normalization_settings
    norm.normalization_settings_list = [
        entry for entry in norm.normalization_settings_list if entry[c.KEY_NORMALIZATION_MANUFACTURER] != "Default"
    ]
    frame = _parsed()
    frame[c.KEY_RDSR_MANUFACTURER] = "SENTINEL-MFR"
    with pytest.raises(RdsrInputError) as excinfo:
        rdsr_normalizer(frame, settings=settings)
    assert "SENTINEL-MFR" not in str(excinfo.value)


# ── surfacing and privacy ───────────────────────────────────────────────────


def test_input_errors_are_user_facing() -> None:
    assert issubclass(RdsrInputError, UserFacingInputError)
    assert issubclass(RdsrUnitError, UserFacingInputError)
    assert issubclass(UserFacingInputError, ValueError)


def test_cli_excepthook_prints_user_facing_message(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "excepthook", sys.excepthook)
    stderr = io.StringIO()
    monkeypatch.setattr(sys, "stderr", stderr)
    install_value_safe_excepthook(logging.getLogger("test"))
    exc = RdsrInputError("This file contains no X-ray irradiation events.")
    sys.excepthook(RdsrInputError, exc, None)
    assert "no X-ray irradiation events" in stderr.getvalue()
    assert "Operation failed" not in stderr.getvalue()


def test_cli_excepthook_keeps_generic_message_for_other_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "excepthook", sys.excepthook)
    stderr = io.StringIO()
    monkeypatch.setattr(sys, "stderr", stderr)
    install_value_safe_excepthook(logging.getLogger("test"))
    sys.excepthook(ValueError, ValueError("SENTINEL raw detail"), None)
    assert "SENTINEL" not in stderr.getvalue()
    assert "Operation failed" in stderr.getvalue()


def test_input_error_messages_and_logs_carry_no_file_values(caplog: pytest.LogCaptureFixture) -> None:
    """Sentinel values in the file must not reach the error message or DEBUG logs of the checks."""
    frame = _parsed()
    frame["StationName"] = "SENTINEL-STATION"
    frame["DoseRP_mGy"] = frame.pop("DoseRP_Gy").astype(float) * 1000
    frame.loc[0, "DoseRP_mGy"] = 123456.789
    frame = frame.drop(columns=["KVP_kV"])
    with caplog.at_level(logging.DEBUG, logger="guiskindose.rdsr_input_checks"), pytest.raises(
        RdsrInputError
    ) as excinfo:
        _normalize(frame)
    text = str(excinfo.value) + caplog.text
    for sentinel in ("SENTINEL-STATION", "123456", "siemens_axiom"):
        assert sentinel not in text


def test_tabular_adapter_keeps_the_input_error_message(tmp_path) -> None:
    """The adapter pipeline used to wrap every normalizer failure in a generic ValueError."""
    from guiskindose.input_adapters.registry import read_and_normalize_input

    fixture = pd.read_csv(Path(__file__).resolve().parents[1] / "fixtures" / "tabular_inputs" / "generic_rdsr_events.csv")
    kvp_column = next(col for col in fixture.columns if "kvp" in col.lower())
    dose_column = next(col for col in fixture.columns if col.lower().startswith("doserp"))
    row = int(fixture.index[pd.to_numeric(fixture[dose_column], errors="coerce") > 0][0])
    fixture[kvp_column] = fixture[kvp_column].astype(object)
    fixture.loc[row, kvp_column] = None
    path = tmp_path / "events.csv"
    fixture.to_csv(path, index=False)
    settings = _settings()
    with pytest.raises(RdsrInputError, match=r"tube voltage \(kVp\) \(missing in 1 of"):
        read_and_normalize_input(path, input_schema="generic_rdsr_like", settings=settings)


# ── caller frames are never modified ─────────────────────────────────────────


def test_normalizer_does_not_modify_the_callers_frame() -> None:
    frame = _parsed()
    frame["DoseRP_mGy"] = frame.pop("DoseRP_Gy").astype(float) * 1000
    frame[_HEIGHT] = [[v, v] for v in frame[_HEIGHT]]
    frame["KVP_kV"] = frame["KVP_kV"].astype(object)
    frame.loc[0, "KVP_kV"] = None
    frame.loc[0, "DoseRP_mGy"] = 0.0
    before = frame.copy(deep=True)
    normalized = _normalize(frame)
    assert len(normalized) == _N_EVENTS - 1
    pd.testing.assert_frame_equal(frame, before)


def test_source_rows_map_kept_events_to_input_positions() -> None:
    from guiskindose.rdsr_normalizer import rdsr_normalizer_with_source_rows

    frame = _parsed()
    frame["KVP_kV"] = frame["KVP_kV"].astype(object)
    frame.loc[[0, 4], "KVP_kV"] = None
    frame["DoseRP_Gy"] = frame["DoseRP_Gy"].astype(object)
    frame.loc[[0, 4], "DoseRP_Gy"] = 0.0
    frame.index = frame.index + 100  # labels must not leak into the positions
    normalized, rows = rdsr_normalizer_with_source_rows(frame, settings=_settings())
    assert rows == [i for i in range(_N_EVENTS) if i not in (0, 4)]
    assert len(normalized) == len(rows)


@pytest.mark.parametrize(
    ("column", "variant", "label"),
    [
        ("CollimatedFieldArea_m2", "CollimatedFieldArea_cm2", "collimated field area"),
        ("XRayFilterThicknessMinimum_mm", "XRayFilterThicknessMinimum_in", "minimum filter thickness"),
        ("TableHeightPosition_mm", "TableHeightPosition_in", "table height position"),
    ],
)
def test_unconvertible_units_rejected_for_other_concept_families(column: str, variant: str, label: str) -> None:
    """Area units are never rescaled; unknown length units are rejected, not guessed."""
    frame = _parsed()
    frame[variant] = frame.pop(column)
    with pytest.raises(RdsrUnitError, match=label):
        _normalize(frame)


def test_shutter_unit_variant_is_converted() -> None:
    frame = pd.DataFrame({"LeftShutter_cm": [1.5], "LeftShutter_mm": [None]})
    from guiskindose.rdsr_input_checks import convert_scale_only_units

    convert_scale_only_units(frame)
    assert list(frame.columns) == ["LeftShutter_mm"]
    assert frame.at[0, "LeftShutter_mm"] == pytest.approx(15.0)


def test_tabular_dap_stays_aligned_when_zero_dose_events_are_dropped(tmp_path) -> None:
    """Per-event DAP is carried across by input position, skipping dropped events."""
    from guiskindose.input_adapters.base import DAP_INTERNAL_COL
    from guiskindose.input_adapters.registry import read_and_normalize_input

    fixture_path = Path(__file__).resolve().parents[1] / "fixtures" / "tabular_inputs" / "dosetrack_events.csv"
    fixture = pd.read_csv(fixture_path)
    fixture["DAP (Gy*cm2)"] = [0.1 * (i + 1) for i in range(len(fixture))]  # distinct per event
    dropped = 1
    fixture["Air Kerma (mGy)"] = fixture["Air Kerma (mGy)"].astype(float)
    fixture.loc[dropped, "Air Kerma (mGy)"] = 0.0
    fixture["Tube Voltage Peak (kV)"] = fixture["Tube Voltage Peak (kV)"].astype(object)
    fixture.loc[dropped, "Tube Voltage Peak (kV)"] = None
    complete_path, gap_path = tmp_path / "complete.csv", tmp_path / "gap.csv"
    fixture.assign(**{"Tube Voltage Peak (kV)": pd.read_csv(fixture_path)["Tube Voltage Peak (kV)"]}).to_csv(
        complete_path, index=False
    )
    fixture.to_csv(gap_path, index=False)
    settings = _settings()

    complete = read_and_normalize_input(complete_path, input_schema="dosetrack", settings=settings)
    gap = read_and_normalize_input(gap_path, input_schema="dosetrack", settings=_settings())

    expected = complete.normalized_data[DAP_INTERNAL_COL].drop(index=dropped).to_numpy()
    assert len(gap.normalized_data) == len(complete.normalized_data) - 1
    np.testing.assert_allclose(gap.normalized_data[DAP_INTERNAL_COL].to_numpy(), expected)


def test_canonical_duplicate_agrees_with_variant_unit(baseline: pd.DataFrame) -> None:
    """A duplicated canonical dose and an agreeing mGy copy are not a conflict."""
    frame = _parsed()
    frame["DoseRP_mGy"] = frame["DoseRP_Gy"].astype(float) * 1000
    frame["DoseRP_Gy"] = pd.Series([[v, v] for v in frame["DoseRP_Gy"]], dtype=object)
    _assert_same_geometry(_normalize(frame), baseline)
