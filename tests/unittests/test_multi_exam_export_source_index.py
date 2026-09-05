"""Regression: multi-exam export must map result rows by opaque Exam N index.

When a middle exam is excluded from ``MultiExamResult.exams``, enumerating that
list is no longer aligned with the full ``loaded_exams`` / CLI ``inputs`` list.
Export builders must use the opaque label (``Exam 3`` → index 2) so later
successful exams keep their own normalized frames and provenance.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import pandas as pd

from guiskindose import load_settings_example_json
from guiskindose.export.cli_source import build_export_source_from_cli
from guiskindose.format_export_data import ExamResult, MultiExamResult
from guiskindose.gui.export_source import build_export_source_from_gui
from guiskindose.gui.state import AppState
from guiskindose.input_adapters.models import InputAdapterResult, InputProvenance
from guiskindose.privacy import opaque_exam_index, opaque_exam_label, resolve_loaded_exam_index
from guiskindose.settings import PyskindoseSettings


def _settings() -> PyskindoseSettings:
    return PyskindoseSettings(settings=load_settings_example_json(), output_format="dict")


def _provenance(name: str) -> InputProvenance:
    return InputProvenance(
        source_type="csv",
        schema_name="normalized",
        original_filename=name,
        header_row_index=0,
        detected_encoding="utf-8",
        detected_delimiter=",",
        sheet_name=None,
        column_map={},
        unit_conversions={},
        warnings=[],
    )


def _adapter(filename: str, marker: str) -> InputAdapterResult:
    return InputAdapterResult(
        normalized_data=pd.DataFrame({"marker": [marker]}),
        raw_data=None,
        provenance=_provenance(filename),
        warnings=[],
    )


def _exam_result(exam_index: int, source_file: str) -> ExamResult:
    return ExamResult(
        exam_id=opaque_exam_label(exam_index),
        source_file=source_file,
        event_count=1,
        patient_offset=[0.0, 0.0, 0.0],
        settings_snapshot={},
        output=cast(Any, SimpleNamespace()),
        warnings=[],
    )


def test_opaque_exam_index_round_trips() -> None:
    assert opaque_exam_index(opaque_exam_label(0)) == 0
    assert opaque_exam_index(opaque_exam_label(2)) == 2
    assert resolve_loaded_exam_index("Exam 3", result_index=0, n_loaded=3) == 2
    assert resolve_loaded_exam_index("custom", result_index=1, n_loaded=3) == 1
    assert resolve_loaded_exam_index("Exam 9", result_index=0, n_loaded=2) is None
    # Non-canonical suffixes must fall back to result_index (or None if OOB).
    assert resolve_loaded_exam_index("Exam 03", result_index=1, n_loaded=3) == 1
    assert resolve_loaded_exam_index("Exam \u0663", result_index=0, n_loaded=3) == 0


def test_cli_export_source_skips_excluded_middle_exam() -> None:
    """Exam 2 excluded → second result row must still bind to input index 2."""
    inputs = [
        _adapter("a.csv", "A"),
        _adapter("b.csv", "B-excluded"),
        _adapter("c.csv", "C"),
    ]
    multi = MultiExamResult(
        exams=[_exam_result(0, "a.csv"), _exam_result(2, "c.csv")],
        aggregate_dose_map=cast(Any, None),
        aggregate_psd=0.0,
        total_events=2,
        warnings=["Exam 2 excluded"],
        exams_attempted=3,
        exams_excluded=1,
    )

    source = build_export_source_from_cli(_settings(), multi_exam_result=multi, inputs=inputs)
    assert [exam.exam_id for exam in source.exams] == ["Exam 1", "Exam 3"]
    assert source.exams[0].normalized_data["marker"].tolist() == ["A"]
    assert source.exams[1].normalized_data["marker"].tolist() == ["C"]
    assert source.exams[1].provenance is not None
    assert source.exams[1].provenance.original_filename == "c.csv"


def test_gui_export_source_skips_excluded_middle_exam() -> None:
    state = AppState()
    state.loaded_exams = [
        _adapter("a.csv", "A"),
        _adapter("b.csv", "B-excluded"),
        _adapter("c.csv", "C"),
    ]
    state.loaded_exam_meta = [
        {"file_name": "a.csv", "swap_lat_lon": False},
        {"file_name": "b.csv", "swap_lat_lon": True},
        {"file_name": "c.csv", "swap_lat_lon": False, "flip_ap1": True},
    ]
    state.multi_exam_result = MultiExamResult(
        exams=[_exam_result(0, "a.csv"), _exam_result(2, "c.csv")],
        aggregate_dose_map=cast(Any, None),
        aggregate_psd=0.0,
        total_events=2,
        warnings=["Exam 2 excluded"],
        exams_attempted=3,
        exams_excluded=1,
    )

    source = build_export_source_from_gui(state)
    assert len(source.exams) == 2
    assert source.exams[1].exam_id == "Exam 3"
    assert source.exams[1].normalized_data["marker"].tolist() == ["C"]
    assert source.exams[1].transform_meta.get("file_name") == "c.csv"
    assert source.exams[1].transform_meta.get("flip_ap1") is True
    # Must not inherit the excluded middle exam's transform flags.
    assert source.exams[1].transform_meta.get("swap_lat_lon") is False
