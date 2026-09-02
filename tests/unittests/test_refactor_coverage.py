"""Coverage for pure helpers extracted during the Sonar complexity refactor.

These target the small, GUI-free helpers in ``export/metrics.py``,
``export/cli_source.py``, and ``kerma_correction.py`` so the refactor's moved
lines stay under test.
"""

from __future__ import annotations

from typing import Any, cast

import pandas as pd
import pytest

from guiskindose import PyskindoseSettings, load_settings_example_json
from guiskindose.constants import (
    KEY_NORMALIZATION_ACQUISITION_TYPE,
    KEY_NORMALIZATION_AIR_KERMA,
)
from guiskindose.export.cli_source import build_export_source_from_cli
from guiskindose.export.metrics import _mean_or_none, _scalar_at, acquisition_breakdown
from guiskindose.format_export_data import ExamResult, MultiExamResult
from guiskindose.kerma_correction import _rows_to_factor_dict


def _settings() -> PyskindoseSettings:
    return PyskindoseSettings(settings=load_settings_example_json())


def test_mean_or_none_handles_scalar_sequence_and_empty() -> None:
    assert _mean_or_none(3.5) == 3.5
    assert _mean_or_none([2.0, 4.0]) == 3.0
    assert _mean_or_none([]) is None


def test_scalar_at_returns_default_when_out_of_range() -> None:
    assert _scalar_at([10.0, 20.0], 1) == 20.0
    assert _scalar_at([10.0], 5, default=-1.0) == -1.0


def test_acquisition_breakdown_accumulates_kerma_and_dap() -> None:
    df = pd.DataFrame(
        {
            KEY_NORMALIZATION_ACQUISITION_TYPE: ["Fluoroscopy", "Fluoroscopy"],
            KEY_NORMALIZATION_AIR_KERMA: [1.0, 2.0],
            "DoseAreaProduct_Gym2": [0.001, 0.002],
        }
    )

    breakdown = acquisition_breakdown(df)

    assert len(breakdown) == 1
    row = breakdown[0]
    assert row.event_count == 2
    assert row.air_kerma == pytest.approx(3.0)
    # 0.003 Gy·m² × 1e4 = 30 Gy·cm²
    assert row.dap_gycm2 == pytest.approx(30.0)


def test_rows_to_factor_dict_rejects_missing_and_nonnumeric_cf() -> None:
    with pytest.raises(ValueError):
        _rows_to_factor_dict([{"equipment": "unit-01", "tube": "single", "correction_factor": None}])
    with pytest.raises(ValueError):
        _rows_to_factor_dict([{"equipment": "unit-01", "tube": "single", "correction_factor": "abc"}])


def test_build_export_source_from_cli_multi_and_empty() -> None:
    settings = _settings()
    # Only exam_id / patient_offset / source_file / warnings are read by the
    # multi-exam CLI builder; the remaining strict-typed fields are unused here.
    multi = MultiExamResult(
        exams=[
            ExamResult(
                exam_id="exam-a",
                source_file="",
                event_count=1,
                patient_offset=[0.0, 0.0, 0.0],
                settings_snapshot={},
                output=cast(Any, {}),
                warnings=["w1"],
            )
        ],
        aggregate_dose_map=cast(Any, None),
        aggregate_psd=0.0,
        total_events=1,
        warnings=[],
    )

    multi_source = build_export_source_from_cli(settings, multi_exam_result=multi)
    assert len(multi_source.exams) == 1
    assert multi_source.exams[0].exam_id == "exam-a"
    assert multi_source.exams[0].extra_warnings == ["w1"]

    # Neither output_dict nor multi_exam_result → empty exam list.
    empty_source = build_export_source_from_cli(settings)
    assert empty_source.exams == []
