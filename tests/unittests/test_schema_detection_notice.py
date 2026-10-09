"""Unit tests for import-preview schema detection notice lines."""

from __future__ import annotations

from types import SimpleNamespace

from guiskindose.gui.schema_detection_notice import schema_detection_notice_lines
from guiskindose.gui.ui_copy import copy_text
from guiskindose.input_adapters.models import InputProvenance
from guiskindose.input_adapters.registry import _AUTO_MIN_HITS


def _minimal_provenance(**overrides: object) -> InputProvenance:
    prov = InputProvenance(
        source_type="csv",
        schema_name="normalized",
        original_filename="events.csv",
        header_row_index=0,
        detected_encoding="utf-8",
        detected_delimiter=",",
        sheet_name=None,
        column_map={},
        unit_conversions={},
    )
    for key, value in overrides.items():
        setattr(prov, key, value)
    return prov


def test_auto_csv_returns_caption():
    prov = _minimal_provenance(detection_mode="auto", matched_column_count=5)
    lines = schema_detection_notice_lines(prov, "csv")
    assert lines == [copy_text("upload.schema_detection.caption")]


def test_auto_csv_two_hits_returns_caption_and_thin_match():
    prov = _minimal_provenance(detection_mode="auto", matched_column_count=_AUTO_MIN_HITS)
    lines = schema_detection_notice_lines(prov, "csv")
    assert lines == [
        copy_text("upload.schema_detection.caption"),
        copy_text("upload.schema_detection.thin_match"),
    ]


def test_explicit_returns_empty():
    prov = _minimal_provenance(detection_mode="explicit", matched_column_count=None)
    assert schema_detection_notice_lines(prov, "csv") == []


def test_dicom_returns_empty_even_when_auto_provenance():
    prov = _minimal_provenance(detection_mode="auto", matched_column_count=5)
    assert schema_detection_notice_lines(prov, "dicom") == []


def test_none_provenance_returns_empty():
    assert schema_detection_notice_lines(None, "csv") == []


def test_partial_provenance_without_detection_fields_returns_empty():
    prov = SimpleNamespace(schema_name="radimetrics")
    assert schema_detection_notice_lines(prov, "csv") == []
