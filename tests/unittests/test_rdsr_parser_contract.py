"""Focused compatibility tests for the RDSR parser's legacy extraction rules."""

from pathlib import Path

from pydicom.dataset import Dataset
from pydicom.sequence import Sequence

from guiskindose.constants import KEY_RDSR_DETECTORSIZE_MM
from guiskindose.main import preview_input_file
from guiskindose.rdsr_parser import rdsr_parser


def _code_sequence(code_meaning: str) -> Sequence:
    code = Dataset()
    code.CodeMeaning = code_meaning
    return Sequence([code])


def _content(code_meaning: str) -> Dataset:
    content = Dataset()
    content.ConceptNameCodeSequence = _code_sequence(code_meaning)
    return content


def _measured_content(code_meaning: str, value: float, unit: str) -> Dataset:
    content = _content(code_meaning)
    measurement = Dataset()
    measurement.NumericValue = value
    unit_code = Dataset()
    unit_code.CodeValue = unit
    measurement.MeasurementUnitsCodeSequence = Sequence([unit_code])
    content.MeasuredValueSequence = Sequence([measurement])
    return content


def _event_dataset() -> Dataset:
    data_raw = Dataset()
    data_raw.Manufacturer = "Test Manufacturer"
    data_raw.ManufacturerModelName = "Test Model"

    event = _content("Irradiation Event X-Ray Data")
    direct_one = _measured_content("Dose Area Product", 1.0, "m.Gy")
    direct_two = _measured_content("Dose Area Product", 2.0, "m.Gy")

    nested = _content("Acquisition Parameters")
    nested_one = _measured_content("Pulse Rate", 3.0, "m.Gy")
    nested_two = _measured_content("Pulse Rate", 4.0, "m.Gy")
    nested.ContentSequence = Sequence([nested_one, nested_two])

    comment = _content("Comment")
    comment.TextValue = 'AcquisitionData/iiDiameter SRData="250"'
    event.ContentSequence = Sequence([direct_one, direct_two, nested, comment])
    data_raw.ContentSequence = Sequence([event])
    return data_raw


def test_parser_preserves_legacy_duplicate_measurement_and_detector_rules():
    parsed = rdsr_parser(_event_dataset())  # type: ignore[arg-type]
    row = parsed.iloc[0]

    assert row["DoseAreaProduct_mGy"] == [1.0, 2.0]
    assert row["PulseRate_m.Gy"] == (3.0, 4.0)
    assert row[KEY_RDSR_DETECTORSIZE_MM] == "250"


def test_parser_tolerates_missing_manufacturer_model_name():
    """Upstream Allura pattern: absent top-level model tag parses as None."""
    data_raw = _event_dataset()
    del data_raw.ManufacturerModelName

    parsed = rdsr_parser(data_raw)  # type: ignore[arg-type]

    assert len(parsed) == 1
    assert parsed.iloc[0]["ManufacturerModelName"] is None


def test_parser_tolerates_empty_measured_value_sequence():
    """Upstream GE pattern: valueless angle concepts parse as None."""
    data_raw = _event_dataset()
    event = data_raw.ContentSequence[0]
    empty_angles = _content("Positioner Primary Angle")
    empty_angles.MeasuredValueSequence = Sequence([])
    event.ContentSequence.append(empty_angles)
    unitless = _measured_content("Positioner Secondary Angle", 5.0, "deg")
    unitless.MeasuredValueSequence[0].MeasurementUnitsCodeSequence = Sequence([])
    event.ContentSequence.append(unitless)

    parsed = rdsr_parser(data_raw)  # type: ignore[arg-type]
    row = parsed.iloc[0]

    assert row["PositionerPrimaryAngle"] is None
    assert row["PositionerSecondaryAngle"] is None
    # Unaffected values on the same event still parse.
    assert row["DoseAreaProduct_mGy"] == [1.0, 2.0]


def test_preview_suppresses_event_values_by_default(capsys):
    input_file = Path(__file__).resolve().parent.parent / "fixtures" / "tabular_inputs" / "normalized_events.csv"

    preview_input_file(input_file, input_schema="normalized")

    output = capsys.readouterr().out
    assert "Exam:" in output
    assert "Identifiers, warning text, and event values are never printed." in output
    assert "First 5 normalized events:" not in output
    assert "File:" not in output
    assert "Study ID:" not in output
