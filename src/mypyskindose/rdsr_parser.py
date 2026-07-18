import pandas as pd
import pydicom

from mypyskindose.constants import (
    KEY_RDSR_ACQUISITION_DATA,
    KEY_RDSR_COMMENT,
    KEY_RDSR_CONCEPT_CODE_SEQUENCE,
    KEY_RDSR_CONTENT_SEQUENCE,
    KEY_RDSR_DETECTORSIZE_MM,
    KEY_RDSR_EVENT_XRAY_DATA,
    KEY_RDSR_II_DIAMETER_SRDATA,
    KEY_RDSR_MANUFACTURER,
    KEY_RDSR_MANUFACTURER_MODEL_NAME,
    KEY_RDSR_MEASURED_VALUE_SEQUENCE,
    KEY_RDSR_TEXT_VALUE,
    KEY_RDSR_UID,
)


def _normalized_tag(content: pydicom.Dataset) -> str:
    """Return the legacy normalized form of an RDSR concept-name code."""
    return (
        content.ConceptNameCodeSequence[0]
        .CodeMeaning.replace(" ", "")
        .replace("-", "")
        .replace("(", "")
        .replace(")", "")
        .replace(".", "")
    )


def _store_value(
    parsed: dict,
    tag: str,
    value: object,
    *,
    duplicate_as_tuple: bool = False,
) -> None:
    """Store an extracted value, preserving the parser's legacy duplicate form."""
    if tag not in parsed:
        parsed[tag] = value
    elif duplicate_as_tuple:
        parsed[tag] = (parsed[tag], value)
    else:
        parsed[tag] = [parsed[tag], value]


def _extract_detector_size(parsed: dict, comment: str) -> None:
    """Extract a Siemens static-acquisition detector size from a comment."""
    comment_parts = comment.split("/")
    if KEY_RDSR_ACQUISITION_DATA not in comment_parts[0]:
        return

    for part in comment_parts:
        if KEY_RDSR_II_DIAMETER_SRDATA in part and "=" in part:
            parsed[KEY_RDSR_DETECTORSIZE_MM] = part.split("=")[1].replace('"', "")


def _measured_tag(content: pydicom.Dataset, *, remove_unit_dots: bool) -> str:
    """Return a measurement tag in the direct or nested legacy format."""
    unit = content.MeasuredValueSequence[0].MeasurementUnitsCodeSequence[0].CodeValue
    if remove_unit_dots:
        unit = unit.replace(".", "")
    return "_".join([_normalized_tag(content), unit])


def _store_content_value(
    parsed: dict,
    content: pydicom.Dataset,
    *,
    nested: bool,
) -> None:
    """Extract one leaf content item into ``parsed``.

    The direct and nested paths intentionally differ in unit normalisation and
    duplicate measured-value representation because downstream compatibility
    depends on the historical output.
    """
    tag = _normalized_tag(content)

    if KEY_RDSR_CONCEPT_CODE_SEQUENCE in content:
        _store_value(parsed, tag, content.ConceptCodeSequence[0].CodeMeaning)
    elif KEY_RDSR_MEASURED_VALUE_SEQUENCE in content:
        tag = _measured_tag(content, remove_unit_dots=not nested)
        _store_value(
            parsed,
            tag,
            content.MeasuredValueSequence[0].NumericValue,
            duplicate_as_tuple=nested,
        )
    elif KEY_RDSR_TEXT_VALUE in content:
        if not nested and tag == KEY_RDSR_COMMENT:
            _extract_detector_size(parsed, content.TextValue)
        else:
            _store_value(parsed, tag, content.TextValue)
    elif KEY_RDSR_UID in content:
        _store_value(parsed, tag, content.UID)
    else:
        parsed[tag] = None


def _parse_event_content(parsed: dict, content: pydicom.Dataset) -> None:
    """Parse one direct event item or its one-level nested contents."""
    leaf_value_keys = (
        KEY_RDSR_CONCEPT_CODE_SEQUENCE,
        KEY_RDSR_MEASURED_VALUE_SEQUENCE,
        KEY_RDSR_TEXT_VALUE,
        KEY_RDSR_UID,
    )
    if any(key in content for key in leaf_value_keys):
        _store_content_value(parsed, content, nested=False)
        return

    if KEY_RDSR_CONTENT_SEQUENCE in content:
        for subcontent in content.ContentSequence:
            _store_content_value(parsed, subcontent, nested=True)
    else:
        _store_content_value(parsed, content, nested=False)


def _parse_irradiation_event(data_raw: pydicom.FileDataset, event: pydicom.Dataset) -> dict:
    """Extract the legacy flat dictionary for one irradiation event."""
    parsed = {
        KEY_RDSR_MANUFACTURER: data_raw.Manufacturer,
        KEY_RDSR_MANUFACTURER_MODEL_NAME: data_raw.ManufacturerModelName,
    }
    for content in event.ContentSequence:
        _parse_event_content(parsed, content)
    return parsed


def _is_irradiation_event(content: pydicom.Dataset) -> bool:
    """Whether a top-level RDSR content item is an irradiation event."""
    return content.ConceptNameCodeSequence[0].CodeMeaning == KEY_RDSR_EVENT_XRAY_DATA


def rdsr_parser(data_raw: pydicom.FileDataset, silence_pydicom_warnings: bool = False) -> pd.DataFrame:
    """Parse event data from radiation dose structure reports (RDSR).

    Parameters
    ----------
    data_raw:
        RDSR file from fluoroscopic device, opened with package pydicom.
    silence_pydicom_warnings:
        Ignore pydicom validation warnings while reading legacy reports.

    Returns
    -------
    pd.DataFrame
        Parsed RDSR data from all irradiation events in the RDSR input file.
    """
    if silence_pydicom_warnings:
        pydicom.config.settings.reading_validation_mode = pydicom.config.IGNORE  # type: ignore[attr-defined]

    event_dicts = [
        _parse_irradiation_event(data_raw, content)
        for content in data_raw.ContentSequence
        if _is_irradiation_event(content)
    ]
    return pd.DataFrame(event_dicts)
