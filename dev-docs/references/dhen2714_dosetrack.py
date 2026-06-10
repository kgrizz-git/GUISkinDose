from .analyze_data import analyze_data
from .helpers.parse_settings_to_settings_class import parse_settings_to_settings_class
from .settings import PyskindoseSettings
from .rdsr_normalizer import rdsr_normalizer
import pandas as pd
import numpy as np
import json

DOSETRACK2PSD = {
    "Plane Code": "AcquisitionPlane",
    "Study Date": "DateTimeStarted",
    "Acquisition Type": "IrradiationEventType",
    "Acquisition Protocol Name": "AcquisitionProtocol",
    "Irradiation Event UID": "IrradiationEventUID",
    "DAP (Gy*cm2)": "DoseAreaProduct_Gym2",
    "Air Kerma (mGy)": "DoseRP_Gy",
    "Positioner Primary Angle (deg)": "PositionerPrimaryAngle_deg",
    "Positioner Secondary Angle (deg)": "PositionerSecondaryAngle_deg",
    "Collimated Field Area (m2)": "CollimatedFieldArea_m2",
    "Filter Type": "XRayFilterType",
    "Filter Material": "XRayFilterMaterial",
    "Filter Thickness": "XRayFilterThicknessMinimum_mm",
    "Pulse Rate (pulse/s)": "PulseRate_{pulse}/s",
    "Tube Voltage Peak (kV)": "KVP_kV",
    "Tube Current (uA)": "XRayTubeCurrent_mA",
    "Pulse Width (ms)": "PulseWidth_ms",
    "mAs (mAs)": "Exposure_uAs",
    "Focal Spot Size (mm)": "FocalSpotSize_mm",
    "Distance Source to Detector (mm)": "DistanceSourcetoDetector_mm",
    "Distance Source To Isocenter (mm)": "DistanceSourcetoIsocenter_mm",
    "Table Longitudinal Position (mm)": "TableLongitudinalPosition_mm",
    "Table Lateral Position (mm)": "TableLateralPosition_mm",
    "Table Height Position (mm)": "TableHeightPosition_mm",
    "Target Region": "TargetRegion",
}

MODEL2MANUF = {"Azurion": "Philips", "AXIOM-Artis": "Siemens", "Allura Clarity": "Philips"}


def parse_axiom_artis(dframe: pd.DataFrame) -> pd.DataFrame:
    dframe = dframe[list(DOSETRACK2PSD.keys())].copy()
    dframe = dframe.ffill()
    dframe["Air Kerma (mGy)"] = dframe["Air Kerma (mGy)"] / 1000
    dframe["Tube Current (uA)"] = dframe["Tube Current (uA)"] / 1000
    dframe["Plane Code"] = _normalize_plane_name(dframe["Plane Code"])
    dframe = dframe.rename(columns=DOSETRACK2PSD)
    dframe["DoseAreaProduct_Gym2"] = dframe["DoseAreaProduct_Gym2"] / 10000
    dframe["Manufacturer"] = "Siemens"
    dframe["ManufacturerModelName"] = "AXIOM-Artis"
    dframe["XRayFilterThicknessMaximum_mm"] = dframe["XRayFilterThicknessMinimum_mm"]
    dframe["CollimatedFieldArea_m2"] = dframe["DoseAreaProduct_Gym2"] / (
        dframe["DoseRP_Gy"]
        * (((dframe["DistanceSourcetoIsocenter_mm"] - 150) / dframe["DistanceSourcetoDetector_mm"])) ** 2
    )
    return dframe


def parse_philips(dframe: pd.DataFrame) -> pd.DataFrame:
    dframe = dframe[list(DOSETRACK2PSD.keys())].copy()
    dframe = dframe.ffill()
    dframe["Filter Type"] = dframe["Filter Type"].str.split(";")
    dframe["Air Kerma (mGy)"] = dframe["Air Kerma (mGy)"] / 1000
    dframe["Filter Thickness"] = (dframe["Filter Thickness"]).str.split(";")
    dframe["Tube Current (uA)"] = dframe["Tube Current (uA)"] / 1000
    dframe["Plane Code"] = _normalize_plane_name(dframe["Plane Code"])
    dframe = dframe.rename(columns=DOSETRACK2PSD)
    dframe["DoseAreaProduct_Gym2"] = dframe["DoseAreaProduct_Gym2"] / 10000
    dframe["Manufacturer"] = "Philips"
    dframe["ManufacturerModelName"] = "Allura Clarity"
    dframe["XRayFilterThicknessMinimum_mm"] = dframe["XRayFilterThicknessMinimum_mm"].apply(_striter2floatiter)
    dframe["XRayFilterThicknessMaximum_mm"] = dframe["XRayFilterThicknessMinimum_mm"]
    dframe["CollimatedFieldArea_m2"] = dframe["DoseAreaProduct_Gym2"] / (
        dframe["DoseRP_Gy"]
        * (((dframe["DistanceSourcetoIsocenter_mm"] - 150) / dframe["DistanceSourcetoDetector_mm"])) ** 2
    )
    dframe = dframe.rename(
        columns={
            "TableLateralPosition_mm": "TableLongitudinalPosition_mm",
            "TableLongitudinalPosition_mm": "TableLateralPosition_mm",
        }
    )
    return dframe


def _striter2floatiter(dfval):
    return tuple(float(_) for _ in dfval)


def _get_philips_al_thickness(dfval):
    return dfval[0]


def _get_philips_cu_thickness(dfval):
    return dfval[1]


def _normalize_plane_name(dfcolumn: pd.Series):
    """Assumes plane codes are integers and that Plane A is the lower integer."""
    plane_codes = np.sort(dfcolumn.unique())
    num_planes = len(plane_codes)
    if num_planes == 1:
        plane_dict = {plane_codes[0]: "Single Plane"}
    elif num_planes == 2:
        plane_dict = {plane_code: plane_name for plane_code, plane_name in zip(plane_codes, ("Plane A", "Plane B"))}
    else:
        raise ValueError("Expected only 1 or 2 Fluoro planes.")
    return dfcolumn.replace(plane_dict)


def dosetrack_parser(
    dosetrack_filepath: str,
    sheet_name: str | int | list = 0,
) -> pd.DataFrame:
    """
    Parse event data from DoseTrack export Excel file.

    Parameters
    ----------
    dosetrack_filepath : str | Path
        Data dump from DoseTrack in Excel format.
    sheet_name: str | int | list = 0
        Name of sheet where the data is to be parsed.

    Returns
    -------
    pd.DataFrame
        Parsed RDSR data from all irradiation events in the RDSR input file
    """
    df = pd.read_excel(dosetrack_filepath, sheet_name=sheet_name)
    model_name = df["Equipment Name"].unique()[0]
    manufacturer = MODEL2MANUF[model_name]

    if manufacturer == "Siemens":
        return parse_axiom_artis(df)
    elif manufacturer == "Philips":
        return parse_philips(df)


def read_and_normalize_dosetrack_data(
    dosetrack_filepath: str,
    settings: str | dict | PyskindoseSettings,
    sheet_name: str | int | list = 0,
) -> pd.DataFrame:
    parsed_data = dosetrack_parser(dosetrack_filepath, sheet_name=sheet_name)
    data_norm = rdsr_normalizer(parsed_data, settings)
    model_name = data_norm["model"].unique()[0]
    manufacturer = MODEL2MANUF[model_name]

    if manufacturer == "Siemens":
        data_norm["filter_thickness_Al"] = 0
        data_norm["filter_thickness_Cu"] = parsed_data["XRayFilterThicknessMaximum_mm"]
    elif manufacturer == "Philips":
        data_norm["filter_thickness_Al"] = parsed_data["XRayFilterThicknessMaximum_mm"].apply(_get_philips_al_thickness)
        data_norm["filter_thickness_Cu"] = parsed_data["XRayFilterThicknessMaximum_mm"].apply(_get_philips_cu_thickness)
    return data_norm


def process(
    dosetrack_filepath: str,
    settings: str,
    normalization_settings: str = None,
    sheet_name: str | int | list = 0,
):
    with open(settings, "rb") as f:
        settings = json.load(f)
    settings = parse_settings_to_settings_class(settings)
    if normalization_settings:
        with open(normalization_settings, "rb") as f:
            norm_dict = json.load(f)
            settings.normalization_settings = settings._initialize_normalization_settings(norm_dict)
    data_norm = read_and_normalize_dosetrack_data(dosetrack_filepath, settings=settings, sheet_name=sheet_name)

    return analyze_data(normalized_data=data_norm, settings=settings)
