from .analyze_data import analyze_data
from .helpers.parse_settings_to_settings_class import parse_settings_to_settings_class
from .settings import PyskindoseSettings
from .rdsr_normalizer import rdsr_normalizer
import pandas as pd
import json
from pathlib import Path


RADIMETRICS2PSD = {
    "Manufacturer": "Manufacturer",
    "Device": "ManufacturerModelName",
    "Acquisition Plane Code (RF)": "AcquisitionPlane",
    "Date Performed": "DateTimeStarted",
    "Irradiation Event Type (RF)": "IrradiationEventType",
    "Acquisition Protocol (RF)": "AcquisitionProtocol",
    # Can't find any UIDs
    "DAP (Total) Gy-cm2": "DoseAreaProduct_Gym2",
    "Reference Point Dose (Total) mGy": "DoseRP_Gy",  # CONVERSION REQUIRED
    "Primary Angle (RF) [°]": "PositionerPrimaryAngle_deg",
    "Secondary Angle (RF) [°]": "PositionerSecondaryAngle_deg",
    "Collimated Field Area (RF) [cm²]": "CollimatedFieldArea_m2",  # CONVERSION REQUIRED
    "Xray Filter Type Codes": "XRayFilterType",  # CONVERSION REQUIRED?
    "Xray Filter Material Codes (RF)": "XRayFilterMaterial",  # CONVERSION REQUIRED?
    "Xray Filter Min Thicknesses": "XRayFilterThicknessMinimum_mm",
    "Xray Filter Max Thicknesses": "XRayFilterThicknessMaximum_mm",
    "Pulse Rate (RF) [pulses/s]": "PulseRate_{pulse}/s",
    "kVp kV": "KVP_kV",
    "mA (RF)": "XRayTubeCurrent_mA",
    "Pulse Width (RF)": "PulseWidth_ms",
    "mAs mAs": "Exposure_uAs",  # CONVERSION REQUIRED
    "Focal Spots (RF) [mm]": "FocalSpotSize_mm",
    "Source To Detector Distance (RF) [mm]": "DistanceSourcetoDetector_mm",
    "Source To Isocenter Distance (RF) [mm]": "DistanceSourcetoIsocenter_mm",
    "Table Longitudinal Position [mm]": "TableLongitudinalPosition_mm",
    "Table Lateral Position [mm]": "TableLateralPosition_mm",
    "Table Height Position [mm]": "TableHeightPosition_mm",
    "Target Region (RF)": "TargetRegion",
}


def parse_axiom_artis(dframe: pd.DataFrame) -> pd.DataFrame:
    dframe = dframe[list(RADIMETRICS2PSD.keys())].copy()
    dframe = dframe.rename(columns=RADIMETRICS2PSD)
    # dframe["AcquisitionPlane"] = dframe["AcquisitionPlane"].str.lower()
    # dframe = dframe.drop(dframe[dframe["AcquisitionPlane"] == "Plane A"].index).reset_index()
    # dframe["AcquisitionPlane"] = "Single Plane"
    dframe["DoseRP_Gy"] = dframe["DoseRP_Gy"] / 1000
    dframe["CollimatedFieldArea_m2"] = dframe["CollimatedFieldArea_m2"] / (100 * 100)
    dframe["Exposure_uAs"] = dframe["Exposure_uAs"] * 1000
    return dframe


def radimetrics_parser_csv(radimetrics_csv_fpath: str | Path) -> pd.DataFrame:
    df = pd.read_csv(radimetrics_csv_fpath)
    return parse_axiom_artis(df)


def read_and_normalize_radimetrics_data(
    radimetrics_filepath: str,
    settings: str | dict | PyskindoseSettings,
) -> pd.DataFrame:
    parsed_data = radimetrics_parser_csv(radimetrics_filepath)
    data_norm = rdsr_normalizer(parsed_data, settings)
    data_norm["filter_thickness_Cu"] = parsed_data["XRayFilterThicknessMaximum_mm"]
    return data_norm


def process(
    radimetrics_filepath: str,
    settings: str,
    normalization_settings: str = None,
):
    with open(settings, "rb") as f:
        settings = json.load(f)
    settings = parse_settings_to_settings_class(settings)
    if normalization_settings:
        with open(normalization_settings, "rb") as f:
            norm_dict = json.load(f)
            settings.normalization_settings = settings._initialize_normalization_settings(norm_dict)
    data_norm = read_and_normalize_radimetrics_data(radimetrics_filepath, settings=settings)

    return analyze_data(normalized_data=data_norm, settings=settings)
