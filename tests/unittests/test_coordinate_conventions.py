"""Characterization tests for coordinate naming and normalization conventions."""

from __future__ import annotations

import pandas as pd
import pytest

from mypyskindose import PyskindoseSettings, load_settings_example_json
from mypyskindose.rdsr_normalizer import rdsr_normalizer


def _settings() -> PyskindoseSettings:
    settings = PyskindoseSettings(settings=load_settings_example_json())
    return settings


def _parsed_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Manufacturer": ["Default"],
            "ManufacturerModelName": ["Default"],
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
            "LeftShutter_mm": [50.0],
            "RightShutter_mm": [50.0],
            "TopShutter_mm": [50.0],
            "BottomShutter_mm": [50.0],
            "KVP_kV": [80.0],
            "DoseRP_Gy": [0.5],
        }
    )


def _ge_parsed_frame() -> pd.DataFrame:
    frame = _parsed_frame()
    frame.loc[0, "Manufacturer"] = "GE Medical Systems"
    frame.loc[0, "ManufacturerModelName"] = "Unknown GE Model"
    return frame


def test_dicom_table_position_attributes_map_to_tx_ty_tz_without_axis_relabeling():
    normalized = rdsr_normalizer(_parsed_frame(), _settings())

    assert normalized.loc[0, "Tx"] == 10.0
    assert normalized.loc[0, "Ty"] == 20.0
    assert normalized.loc[0, "Tz"] == 30.0


def test_current_plot_axis_titles_are_historical_pyskindose_aliases():
    from mypyskindose.constants import PLOT_AXIS_TITLE_X, PLOT_AXIS_TITLE_Y, PLOT_AXIS_TITLE_Z

    assert PLOT_AXIS_TITLE_X == "X - LON [cm]"
    assert PLOT_AXIS_TITLE_Y == "Y - VER [cm]"
    assert PLOT_AXIS_TITLE_Z == "Z - LAT [cm]"


@pytest.mark.parametrize(
    "manufacturer",
    [
        "GE Healthcare",
        "GEMS",
        "GE_HEALTHCARE",
        "GE Medical Systems",
    ],
)
def test_ge_manufacturer_wildcard_swaps_lateral_longitudinal_before_normalization(manufacturer):
    settings = _settings()
    frame = _ge_parsed_frame()
    frame.loc[0, "Manufacturer"] = manufacturer
    normalized = rdsr_normalizer(frame, settings)

    assert normalized.loc[0, "Tx"] == 30.0
    assert normalized.loc[0, "Ty"] == 20.0
    assert normalized.loc[0, "Tz"] == 10.0
    assert settings.normalization_settings.matched_manufacturer == "GE Healthcare"
    assert settings.normalization_settings.matched_model == "*"
    assert settings.normalization_settings.swap_lateral_longitudinal is True


@pytest.mark.parametrize(
    ("manufacturer", "model"),
    [
        ("Siemens", "AXIOM-Artis"),
        ("SIEMENS HEALTHINEERS", "AXIOM_Artis"),
        ("Siemens Medical Solutions", "AXIOM Artis"),
    ],
)
def test_siemens_manufacturer_and_model_variants_match_validated_settings(manufacturer, model):
    settings = _settings()
    frame = _parsed_frame()
    frame.loc[0, "Manufacturer"] = manufacturer
    frame.loc[0, "ManufacturerModelName"] = model
    normalized = rdsr_normalizer(frame, settings)

    assert normalized.loc[0, "Tx"] == 10.0
    assert normalized.loc[0, "Ty"] == 20.0
    assert normalized.loc[0, "Tz"] == 30.0
    assert settings.normalization_settings.matched_manufacturer == "Siemens"
    assert settings.normalization_settings.matched_model == "AXIOM-Artis"


@pytest.mark.parametrize(
    ("manufacturer", "model"),
    [
        ("Philips", "Allura Clarity"),
        ("Philips Healthcare", "Allura-Clarity"),
        ("Philips Medical Systems", "Allura_Clarity"),
    ],
)
def test_philips_manufacturer_and_model_variants_match_validated_settings(manufacturer, model):
    settings = _settings()
    frame = _parsed_frame()
    frame.loc[0, "Manufacturer"] = manufacturer
    frame.loc[0, "ManufacturerModelName"] = model
    normalized = rdsr_normalizer(frame, settings)

    assert normalized.loc[0, "Tx"] == pytest.approx(9.7)
    assert normalized.loc[0, "Ty"] == pytest.approx(85.5)
    assert normalized.loc[0, "Tz"] == pytest.approx(-143.35)
    assert settings.normalization_settings.matched_manufacturer == "Philips"
    assert settings.normalization_settings.matched_model == "Allura Clarity"
