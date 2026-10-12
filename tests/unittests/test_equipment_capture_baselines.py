"""Reject malformed or shared per-exam baseline snapshots before production."""

from __future__ import annotations

import copy
import importlib
from typing import Any

import pandas as pd
import pytest

from guiskindose import load_settings_example_json
from guiskindose.analyze_data import analyze_multiple_exams
from guiskindose.equipment_profiles.capture import CODE_INVALID_EQUIPMENT_CAPTURE, CaptureError
from guiskindose.input_adapters.models import InputAdapterResult, InputProvenance
from guiskindose.settings import PyskindoseSettings
from guiskindose.settings.normalization_settings import NormalizationSettings


def _settings() -> PyskindoseSettings:
    config = load_settings_example_json()
    config["mode"] = "calculate_dose"
    return PyskindoseSettings(settings=config, output_format="dict")


def _exam() -> InputAdapterResult:
    provenance = InputProvenance(
        source_type="csv", schema_name="normalized", original_filename="",
        header_row_index=0, detected_encoding="utf-8", detected_delimiter=",",
        sheet_name=None, column_map={}, unit_conversions={}, warnings=[],
    )
    return InputAdapterResult(
        normalized_data=pd.DataFrame(), raw_data=None, provenance=provenance, warnings=[]
    )


@pytest.mark.parametrize("bad", [42, {}, "SENTINEL", [None, None], [object()]])
def test_invalid_baseline_container_is_closed(monkeypatch: Any, bad: Any) -> None:
    calls: list[bool] = []

    def reject_production(*args: Any, **kwargs: Any) -> Any:
        calls.append(True)
        raise AssertionError("unexpected production")

    module = importlib.import_module("guiskindose.analyze_data")
    monkeypatch.setattr(module, "_process_exam", reject_production)
    settings = _settings()
    before = settings.to_settings_dict()
    exams = [_exam()]
    with pytest.raises(CaptureError) as caught:
        analyze_multiple_exams(
            exams, settings, equipment_capture_contexts=[None], per_exam_baselines=bad
        )
    assert caught.value.code == CODE_INVALID_EQUIPMENT_CAPTURE
    assert "SENTINEL" not in str(caught.value)
    assert calls == []
    assert settings.to_settings_dict() == before


@pytest.mark.parametrize("share_root", [True, False])
def test_shared_baseline_copy_is_closed(monkeypatch: Any, share_root: bool) -> None:
    class SharedBaseline(NormalizationSettings):
        def __deepcopy__(self, memo: Any) -> Any:
            if share_root:
                return self
            result = object.__new__(type(self))
            vars(result).update(vars(self))
            return result

    settings = _settings()
    baseline = object.__new__(SharedBaseline)
    vars(baseline).update(vars(copy.deepcopy(settings.normalization_settings)))
    before = copy.deepcopy(vars(settings.normalization_settings.trans_offset))
    handles = (baseline.trans_offset, baseline.trans_dir, baseline.rot_dir)
    calls: list[bool] = []

    def reject_production(*args: Any, **kwargs: Any) -> Any:
        calls.append(True)
        raise AssertionError("unexpected production")

    module = importlib.import_module("guiskindose.analyze_data")
    monkeypatch.setattr(module, "_process_exam", reject_production)
    exams = [_exam()]
    with pytest.raises(CaptureError) as caught:
        analyze_multiple_exams(
            exams, settings, equipment_capture_contexts=[None], per_exam_baselines=[baseline]
        )
    assert caught.value.code == CODE_INVALID_EQUIPMENT_CAPTURE
    assert calls == []
    assert baseline.trans_offset is handles[0]
    assert baseline.trans_dir is handles[1]
    assert baseline.rot_dir is handles[2]
    assert vars(settings.normalization_settings.trans_offset) == before


def test_baseline_on_captured_entry_refuses() -> None:
    from guiskindose.equipment_profiles import assemble_session
    from tests.unittests.test_equipment_captured_input import (
        _SIEMENS_DICOM,
        _live_capture_dicom,
        _siemens_doc,
    )

    session = assemble_session(documents=[_siemens_doc()])
    context, _ = _live_capture_dicom(_SIEMENS_DICOM, session)
    settings = _settings()
    baselines: list[NormalizationSettings | None] = [settings.normalization_settings]
    contexts = [context]
    exams = [_exam()]
    with pytest.raises(CaptureError) as caught:
        analyze_multiple_exams(
            exams, settings, equipment_capture_contexts=contexts, per_exam_baselines=baselines
        )
    assert caught.value.code == CODE_INVALID_EQUIPMENT_CAPTURE


def test_baseline_without_capture_authority_refuses() -> None:
    settings = _settings()
    exams = [_exam()]
    baselines: list[NormalizationSettings | None] = [settings.normalization_settings]
    with pytest.raises(CaptureError) as caught:
        analyze_multiple_exams(exams, settings, per_exam_baselines=baselines)
    assert caught.value.code == CODE_INVALID_EQUIPMENT_CAPTURE
