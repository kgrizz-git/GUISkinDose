import logging

import numpy as np
import pandas as pd

from mypyskindose.settings.normalization_settings import NormalizationSettings

from .constants import (
    KEY_NORMALIZATION_ACQUISITION_PLANE,
    KEY_NORMALIZATION_ACQUISITION_TYPE,
    KEY_NORMALIZATION_AIR_KERMA,
    KEY_NORMALIZATION_DEVICE_SERIAL,
    KEY_NORMALIZATION_DISTANCE_ISOCENTER_DETECTOR,
    KEY_NORMALIZATION_DISTANCE_SOURCE_DETECTOR,
    KEY_NORMALIZATION_DISTANCE_SOURCE_IRP,
    KEY_NORMALIZATION_DISTANCE_SOURCE_ISOCENTER,
    KEY_NORMALIZATION_FILTER_SIZE_ALUMINUM,
    KEY_NORMALIZATION_FILTER_SIZE_COPPER,
    KEY_NORMALIZATION_MODEL_NAME,
    KEY_NORMALIZATION_STATION_NAME,
    KEY_RDSR_DEVICE_SERIAL,
    KEY_RDSR_DISTANCE_SOURCE_DETECTOR,
    KEY_RDSR_FILTER_MATERIAL,
    KEY_RDSR_FILTER_MATERIAL_ALUMINUM,
    KEY_RDSR_FILTER_MATERIAL_COPPER,
    KEY_RDSR_FILTER_MAX,
    KEY_RDSR_FILTER_MIN,
    KEY_RDSR_STATION_NAME,
)
from .geom_calc import calculate_field_size
from .settings import PyskindoseSettings

logger = logging.getLogger("mypyskindose")


class RdsrUnitError(ValueError):
    """Raised when an RDSR reports a quantity in an unexpected physical unit.

    ``rdsr_parser`` encodes each measured value's DICOM unit into the column name
    (e.g. ``DoseRP_Gy``). When a report uses a unit this pipeline does not
    convert, the expected column is absent and a sibling ``{concept}_{other-unit}``
    column is present; the normalizer would otherwise fail with an opaque
    AttributeError. This surfaces a clear, unit-naming message instead. See
    dev-docs/INPUT_SCHEMA_DETECTION.md ("Unit handling").
    """


# Concept prefix (as produced by rdsr_parser) → (expected DICOM unit code,
# human-readable quantity label). These are the quantities the normalizer reads
# by unit-suffixed column name; a differing unit is a hard, un-converted mismatch.
_EXPECTED_UNITS: dict[str, tuple[str, str]] = {
    "DoseRP": ("Gy", "reference point dose"),
    "KVP": ("kV", "tube voltage (kVp)"),
    "DistanceSourcetoDetector": ("mm", "source-to-detector distance"),
    "DistanceSourcetoIsocenter": ("mm", "source-to-isocenter distance"),
    "TableLongitudinalPosition": ("mm", "table longitudinal position"),
    "TableLateralPosition": ("mm", "table lateral position"),
    "TableHeightPosition": ("mm", "table height position"),
    "PositionerPrimaryAngle": ("deg", "positioner primary angle"),
    "PositionerSecondaryAngle": ("deg", "positioner secondary angle"),
}


def _verify_expected_units(data_parsed: pd.DataFrame) -> None:
    """Raise :class:`RdsrUnitError` if a quantity is reported in an unexpected unit.

    For each expected ``{concept}_{unit}`` column that is absent, check whether a
    sibling ``{concept}_*`` column (same quantity, different unit) is present. If
    so, the report used a unit this pipeline does not convert; fail early with a
    clear message rather than a downstream AttributeError. A concept that is
    wholly absent is left to the existing missing-column handling.
    """
    columns = list(data_parsed.columns)
    for concept, (expected_unit, label) in _EXPECTED_UNITS.items():
        if f"{concept}_{expected_unit}" in columns:
            continue
        prefix = f"{concept}_"
        siblings = [c for c in columns if c.startswith(prefix)]
        if siblings:
            found_unit = siblings[0][len(prefix):]
            raise RdsrUnitError(
                f"This RDSR reports {label} in '{found_unit}', but MyPySkinDose expects "
                f"'{expected_unit}'. The report uses a unit this pipeline does not convert; "
                "verify the acquisition device's dose-report configuration."
            )


def rdsr_normalizer(data_parsed: pd.DataFrame, settings: PyskindoseSettings) -> pd.DataFrame:
    """Normalize RDSR data for PySkinDose compliance.

    Parameters
    ----------
    data_parsed : pd.DataFrame
        Parsed RDSR data from all irradiation events in the RDSR input file,
        i.e. output of function rdsr_parser
    settings : PyskindoseSettings
        The PySkinDose settings object containing the normalization settings

    Returns
    -------
    data_norm : pd.DataFrame
        DataFrame with the following columns
            - model (str)
                device model, e.g. 'AXIOM-artis
            - DSD (float)
                Distance Source to detector (DSD) in cm.
            - DSI (float)
                Distance Source to Isocenter (DSI) in cm.
            - DID (float)
                Distance Isocenter to Detector (DID) in cm.
            - DSIRP (float)
                Distance Source to intercentional reference point (DSIRP) in
                cm.
            - acquisition_type (str)
                Type of irradiation event, i.e. 'fluoroscopy, or stationary
                acquisition.
            - acquisition_plane (str)
                plane used for image acquisition. Either 'single plane',
                'plane a', or 'plane b'.
            - Tx (float)
                Normalized table translation column in cm. It is populated from
                DICOM TableLongitudinalPosition_mm after vendor offset/sign and
                optional lateral/longitudinal swap handling. In DICOM table
                coordinates this value corresponds to table X motion; for
                head-first supine positioning this is physical lateral motion.
            - Ty (float)
                Normalized table height translation column in cm, populated from
                DICOM TableHeightPosition_mm after vendor offset/sign handling.
            - Tz (float)
                Normalized table translation column in cm. It is populated from
                DICOM TableLateralPosition_mm after vendor offset/sign and
                optional lateral/longitudinal swap handling. In DICOM table
                coordinates this value corresponds to table Z motion; for
                head-first supine positioning this is physical longitudinal
                motion.

                .. image:: user/figures/table/table_translate.svg

            - At1 (int)
                Rotation angle of the patient support table about the isocenter
                y-axis. The center of rotation is located at the centerpoint
                of the table. Positive direction is determined by
                the right-hand rule for curve orientation about the positive
                isocenter y-axis.

                .. image:: user/figures/table/table_at1.svg

            -At2 (int)
                Tilt angel of the patient support table about the isocenter
                x-axis. The center of the tilt is located at the center of the
                table, with positive direction determined by the right-hand
                rule for curve orientations  about the positiove isocenter
                x-axis.

                .. image:: user/figures/table/table_at2.svg

            - At3 (int)
                Cradle angle of the patient support table about the isocenter
                z-axis. The center of rotation is located at the centerpoint
                of the table. Positive direction is determined by the
                right-hand rule for curve orientation about the positive
                isocenter z-axis.

                .. image:: user/figures/table/table_at3.svg

            - Ap1 (int)
                Rotation angle of the X-ray source about the isocenter z-axis.
                Positive direction is determined by the right-hand rule for
                curve orientation about the positive isocenter z-axis.

                .. image:: user/figures/beam/beam_ap1.svg

            - Ap2 (int)
                Rotation angle of the X-ray source about the isocenter x-axis.
                Positive direction is determined by the right-hand rule for
                curve orientation about the positive isocenter x-axis.

                .. image:: user/figures/beam/beam_ap2.svg

    Ap3 : int
        Rotation angle of the X-ray detector about the isocenter y-axis.
        Positive direction is determined by the right-hand rule for curve
        orientation about the positive isocenter y-axis.


    DSL : float
        Detector Side Length (DSL) in cm.
    FS_lat : float
        Side length of the X-ray field in the lateral direction at the image
        receptor plane.
    FS_long : float
        Side length of the X-ray field in the longitudinal direction at the
        image receptor plane.
    kVp : float
        Tube voltage in kV
    K_IRP : float
        IRP air kerma at the Interventional Reference Point (IRP).
    filter_thickness_Cu : float
        Copper X-ray filter thickness in mm.
    filter_thickness_Al : float
        Aluminum X-ray filter thickness in mm.
    """
    data_norm = pd.DataFrame()

    _verify_expected_units(data_parsed)

    settings.normalization_settings.update_used_settings(data_parsed=data_parsed)

    for append_normalization in [
        _normalize_machine_parameters,
        _normalize_table_parameters,
        _normalize_xray_filter_materials,
        _normalize_beam_parameters,
    ]:
        data_norm = append_normalization(
            data_parsed=data_parsed, data_norm=data_norm, norm=settings.normalization_settings
        )

    return data_norm


def _normalize_machine_parameters(
    data_parsed: pd.DataFrame, data_norm: pd.DataFrame, norm: NormalizationSettings
) -> pd.DataFrame:
    """Normalize manufacturer/model and related machine identity fields."""

    data_norm[KEY_NORMALIZATION_MODEL_NAME] = data_parsed.ManufacturerModelName

    # Per-unit identity for kerma-meter correction (optional; None when absent).
    if KEY_RDSR_STATION_NAME in data_parsed.columns:
        data_norm[KEY_NORMALIZATION_STATION_NAME] = data_parsed[KEY_RDSR_STATION_NAME]
    else:
        data_norm[KEY_NORMALIZATION_STATION_NAME] = None
    if KEY_RDSR_DEVICE_SERIAL in data_parsed.columns:
        data_norm[KEY_NORMALIZATION_DEVICE_SERIAL] = data_parsed[KEY_RDSR_DEVICE_SERIAL]
    else:
        data_norm[KEY_NORMALIZATION_DEVICE_SERIAL] = None

    # Find indices of nans in DistanceSourcetoDetector
    if "nan" in str(data_parsed[KEY_RDSR_DISTANCE_SOURCE_DETECTOR]).lower():
        nan_indices = data_parsed.index[data_parsed[KEY_RDSR_DISTANCE_SOURCE_DETECTOR].apply(np.isnan)]
        # Replace those nans with the corresponding value in
        # FinalDistanceSourcetoDetector
        data_parsed.loc[:, "DistanceSourcetoDetector_mm"] = data_parsed.DistanceSourcetoDetector_mm.fillna(
            data_parsed.FinalDistanceSourcetoDetector_mm[nan_indices]
        )

    data_norm[KEY_NORMALIZATION_DISTANCE_SOURCE_DETECTOR] = data_parsed.DistanceSourcetoDetector_mm / 10
    data_norm[KEY_NORMALIZATION_DISTANCE_SOURCE_ISOCENTER] = data_parsed.DistanceSourcetoIsocenter_mm / 10
    data_norm[KEY_NORMALIZATION_DISTANCE_ISOCENTER_DETECTOR] = data_norm.DSD - data_norm.DSI
    data_norm[KEY_NORMALIZATION_DISTANCE_SOURCE_IRP] = data_norm.DSI - 15
    data_norm[KEY_NORMALIZATION_ACQUISITION_TYPE] = data_parsed.IrradiationEventType
    data_norm[KEY_NORMALIZATION_ACQUISITION_PLANE] = data_parsed.AcquisitionPlane

    return data_norm


def _normalize_table_parameters(
    data_parsed: pd.DataFrame, data_norm: pd.DataFrame, norm: NormalizationSettings
) -> pd.DataFrame:
    """Normalize table position fields into the internal centimetre frame."""

    table_longitudinal_mm = data_parsed.TableLongitudinalPosition_mm
    table_lateral_mm = data_parsed.TableLateralPosition_mm
    if norm.swap_lateral_longitudinal:
        table_longitudinal_mm, table_lateral_mm = table_lateral_mm, table_longitudinal_mm

    # Table translations
    data_norm["Tx"] = norm.trans_offset.x + norm.trans_dir.x * table_longitudinal_mm / 10

    data_norm["Ty"] = norm.trans_offset.y + norm.trans_dir.y * data_parsed.TableHeightPosition_mm / 10

    data_norm["Tz"] = norm.trans_offset.z + norm.trans_dir.z * table_lateral_mm / 10

    # Table rotations
    data_norm["At1"] = norm.rot_dir.At1 * [0] * len(data_norm)
    data_norm["At2"] = norm.rot_dir.At2 * [0] * len(data_norm)
    data_norm["At3"] = norm.rot_dir.At3 * [0] * len(data_norm)

    return data_norm


def _normalize_xray_filter_materials(
    data_parsed: pd.DataFrame, data_norm: pd.DataFrame, norm: NormalizationSettings
) -> pd.DataFrame:
    """Normalize X-ray filter materials and thicknesses."""
    # parse filter material and thickness

    # Load filter min and max, and fill all NANs with zeros
    for key in [KEY_RDSR_FILTER_MIN, KEY_RDSR_FILTER_MAX]:
        data_parsed[key] = data_parsed[key].fillna(0.0)

    # Add columns for filter materials in data_norm, and initialize to zero
    for key in [
        KEY_NORMALIZATION_FILTER_SIZE_COPPER,
        KEY_NORMALIZATION_FILTER_SIZE_ALUMINUM,
    ]:
        data_norm[key] = 0.0

    # for each irradiation event
    for event_index in range(len(data_parsed)):
        # fetch filter materials from data_parsed
        event_filter_materials = data_parsed[KEY_RDSR_FILTER_MATERIAL][event_index]

        # fetch filter min and max thicknesses
        event_filter_minmax = np.array(
            [
                data_parsed[KEY_RDSR_FILTER_MIN][event_index],
                data_parsed[KEY_RDSR_FILTER_MAX][event_index],
            ]
        )

        # calculate filter mean thicknesses
        event_filter_means = np.mean(event_filter_minmax, axis=0)

        if isinstance(event_filter_materials, str):
            event_filter_means = [event_filter_means]

        if not isinstance(event_filter_means, (list, np.ndarray)) and np.isnan(event_filter_materials):
            logger.debug("Skipping mean value filter thickness calculation for event with no filter")
            continue

        # if copper filter in use
        if KEY_RDSR_FILTER_MATERIAL_COPPER in event_filter_materials:
            # append copper filtration to normalized data
            data_norm.loc[event_index, KEY_NORMALIZATION_FILTER_SIZE_COPPER] = event_filter_means[
                event_filter_materials.index(KEY_RDSR_FILTER_MATERIAL_COPPER)
            ]
        # if aluminum filter in use
        if KEY_RDSR_FILTER_MATERIAL_ALUMINUM in event_filter_materials:
            # append aluminum filtration to normalized data
            data_norm.loc[event_index, KEY_NORMALIZATION_FILTER_SIZE_ALUMINUM] = event_filter_means[
                event_filter_materials.index(KEY_RDSR_FILTER_MATERIAL_ALUMINUM)
            ]

    return data_norm


def _normalize_beam_parameters(
    data_parsed: pd.DataFrame, data_norm: pd.DataFrame, norm: NormalizationSettings
) -> pd.DataFrame:
    """Normalize beam angulation, FS, and related beam geometry fields."""

    # beam angulation
    data_norm["Ap1"] = norm.rot_dir.Ap1 * data_parsed.PositionerPrimaryAngle_deg
    data_norm["Ap2"] = norm.rot_dir.Ap2 * data_parsed.PositionerSecondaryAngle_deg
    # temp set to zero
    data_norm["Ap3"] = norm.rot_dir.Ap3 * [0] * len(data_norm)

    # detector side length
    data_norm["DSL"] = norm.detector_side_length

    FS_lat, FS_long = calculate_field_size(
        field_size_mode=norm.field_size_mode,
        data_parsed=data_parsed,
        data_norm=data_norm,
    )

    data_norm["FS_lat"] = FS_lat
    data_norm["FS_long"] = FS_long

    data_norm["kVp"] = data_parsed.KVP_kV
    data_norm[KEY_NORMALIZATION_AIR_KERMA] = data_parsed.DoseRP_Gy * 1000

    return data_norm
