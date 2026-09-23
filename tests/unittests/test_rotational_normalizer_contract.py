"""Contract tests for the additive rotational normalizer fields."""

from __future__ import annotations

import pandas as pd

from guiskindose.rdsr_normalizer import _normalize_beam_parameters, _normalize_machine_parameters
from guiskindose.settings.normalization_settings import NormalizationSettings


def _parsed_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "ManufacturerModelName": ["Alphenix"],
            "DistanceSourcetoDetector_mm": [1200.0],
            "FinalDistanceSourcetoDetector_mm": [1200.0],
            "DistanceSourcetoIsocenter_mm": [800.0],
            "IrradiationEventType": ["Rotational Acquisition"],
            "IrradiationEventType_CodeValue": ["113613"],
            "IrradiationEventType_CodingSchemeDesignator": ["DCM"],
            "AcquisitionPlane": ["Single Plane"],
            "PositionerPrimaryAngle_deg": [90.0],
            "PositionerSecondaryAngle_deg": [0.0],
            "PositionerPrimaryEndAngle_deg": [-120.0],
            "PositionerSecondaryEndAngle_deg": [0.0],
            "KVP_kV": [80.0],
            "DoseRP_Gy": [0.011],
            "CollimatedFieldArea_m2": [0.04],
        }
    )


def _norm_settings():
    norm = NormalizationSettings([])
    norm.field_size_mode = "CFA"
    norm.detector_side_length = "20.0"
    return norm


def test_end_angles_follow_rot_dir_and_codes_flow():
    parsed = _parsed_frame()
    norm_settings = _norm_settings()
    data_norm = pd.DataFrame(index=parsed.index)

    data_norm = _normalize_machine_parameters(parsed, data_norm, norm_settings)
    assert data_norm["acquisition_type_code"].iloc[0] == "113613"
    assert data_norm["acquisition_type_coding_scheme"].iloc[0] == "DCM"
    assert data_norm["acquisition_type_meaning"].iloc[0] == "Rotational Acquisition"

    data_norm = _normalize_beam_parameters(parsed, data_norm, norm_settings)
    assert data_norm["Ap1_end"].iloc[0] == -120.0
    assert data_norm["Ap2_end"].iloc[0] == 0.0

    norm_settings.rot_dir.Ap1 = -1
    flipped = _normalize_beam_parameters(parsed, pd.DataFrame(index=parsed.index), norm_settings)
    assert flipped["Ap1_end"].iloc[0] == 120.0


def test_missing_end_columns_yield_nan_not_crash():
    parsed = _parsed_frame().drop(
        columns=["PositionerPrimaryEndAngle_deg", "PositionerSecondaryEndAngle_deg"]
    )
    data_norm = _normalize_beam_parameters(parsed, pd.DataFrame(index=parsed.index), _norm_settings())
    assert pd.isna(data_norm["Ap1_end"].iloc[0])
    assert pd.isna(data_norm["Ap2_end"].iloc[0])


def test_missing_type_codes_yield_none():
    parsed = _parsed_frame().drop(
        columns=["IrradiationEventType_CodeValue", "IrradiationEventType_CodingSchemeDesignator"]
    )
    data_norm = _normalize_machine_parameters(parsed, pd.DataFrame(index=parsed.index), _norm_settings())
    assert data_norm["acquisition_type_code"].iloc[0] is None
    assert data_norm["acquisition_type_meaning"].iloc[0] == "Rotational Acquisition"
