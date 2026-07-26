"""Phase 0: StationName / DeviceSerialNumber capture from DICOM RDSR."""

from __future__ import annotations

from pathlib import Path

import pydicom
import pytest
from pydicom.dataset import Dataset
from pydicom.sequence import Sequence

from mypyskindose import load_settings_example_json
from mypyskindose.constants import (
    KEY_NORMALIZATION_DEVICE_SERIAL,
    KEY_NORMALIZATION_STATION_NAME,
    KEY_RDSR_DEVICE_SERIAL,
    KEY_RDSR_STATION_NAME,
)
from mypyskindose.rdsr_normalizer import rdsr_normalizer
from mypyskindose.rdsr_parser import rdsr_parser
from mypyskindose.settings import PyskindoseSettings

EXAMPLE_RDSR = Path(__file__).resolve().parents[2] / "src" / "mypyskindose" / "example_data" / "RDSR"

# Synthetic labels only — never log/assert site-specific strings beyond fixture stems.
EXPECTED_PRESENT = {
    "fake_scanner.dcm": ("AXIS01475", "146278"),
    "philips_allura_clarity_u104.dcm": ("INR Lab", "722013-362"),
    "philips_allura_clarity_u601.dcm": ("U601", "722010-564"),
    "siemens_axiom_artis.dcm": ("AXIS01475", "146278"),
}


def _minimal_event(data_raw: Dataset) -> Dataset:
    event = Dataset()
    code = Dataset()
    code.CodeMeaning = "Irradiation Event X-Ray Data"
    event.ConceptNameCodeSequence = Sequence([code])
    event.ContentSequence = Sequence([])
    data_raw.ContentSequence = Sequence([event])
    return data_raw


def test_parser_captures_station_and_serial_when_present():
    data_raw = Dataset()
    data_raw.Manufacturer = "TestCo"
    data_raw.ManufacturerModelName = "TestModel"
    data_raw.StationName = "unit-01"
    data_raw.DeviceSerialNumber = "serial-01"
    parsed = rdsr_parser(_minimal_event(data_raw))  # type: ignore[arg-type]
    assert parsed.iloc[0][KEY_RDSR_STATION_NAME] == "unit-01"
    assert parsed.iloc[0][KEY_RDSR_DEVICE_SERIAL] == "serial-01"


def test_parser_missing_station_and_serial_are_none():
    data_raw = Dataset()
    data_raw.Manufacturer = "TestCo"
    data_raw.ManufacturerModelName = "TestModel"
    parsed = rdsr_parser(_minimal_event(data_raw))  # type: ignore[arg-type]
    assert parsed.iloc[0][KEY_RDSR_STATION_NAME] is None
    assert parsed.iloc[0][KEY_RDSR_DEVICE_SERIAL] is None


@pytest.mark.parametrize("filename,expected", list(EXPECTED_PRESENT.items()))
def test_example_rdsr_station_serial_present(filename: str, expected: tuple[str, str]):
    path = EXAMPLE_RDSR / filename
    assert path.is_file()
    data_raw = pydicom.dcmread(path)
    parsed = rdsr_parser(data_raw)
    assert parsed.iloc[0][KEY_RDSR_STATION_NAME] == expected[0]
    assert parsed.iloc[0][KEY_RDSR_DEVICE_SERIAL] == expected[1]


def test_example_rdsr_missing_station_serial():
    path = EXAMPLE_RDSR / "siemens_axiom_example_procedure.dcm"
    data_raw = pydicom.dcmread(path)
    parsed = rdsr_parser(data_raw)
    assert parsed.iloc[0][KEY_RDSR_STATION_NAME] is None
    assert parsed.iloc[0][KEY_RDSR_DEVICE_SERIAL] is None


def test_normalizer_copies_station_serial_into_data_norm():
    path = EXAMPLE_RDSR / "siemens_axiom_artis.dcm"
    data_raw = pydicom.dcmread(path)
    parsed = rdsr_parser(data_raw)
    settings = PyskindoseSettings(settings=load_settings_example_json())
    data_norm = rdsr_normalizer(parsed, settings)
    assert KEY_NORMALIZATION_STATION_NAME in data_norm.columns
    assert KEY_NORMALIZATION_DEVICE_SERIAL in data_norm.columns
    assert data_norm.iloc[0][KEY_NORMALIZATION_STATION_NAME] == "AXIS01475"
    assert data_norm.iloc[0][KEY_NORMALIZATION_DEVICE_SERIAL] == "146278"
