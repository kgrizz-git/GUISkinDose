"""GUI-side wiring tests for rotational handling (pre-calc prompt + settings).

The classifier and envelope math are exercised in
``test_rotational_acquisition.py`` / ``test_rotational_envelope*.py``; here we
only confirm the GUI layer: the survey counts classifications across loaded
frames, the handling choice reaches ``PyskindoseSettings`` via
``build_settings``, and invalid values fail fast.
"""

from __future__ import annotations

from types import SimpleNamespace

import pandas as pd
import pytest

pytest.importorskip("nicegui")

from guiskindose.gui.helpers import build_settings, rotational_survey
from guiskindose.gui.state import AppState


def _spin_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Ap1": 0.0,
                "Ap2": 0.0,
                "Ap1_end": 0.0,
                "Ap2_end": 0.0,
                "acquisition_type": "Fluoroscopy",
            },
            {
                "Ap1": 90.0,
                "Ap2": 0.0,
                "Ap1_end": -120.0,
                "Ap2_end": 0.0,
                "acquisition_type": "Rotational Acquisition",
                "acquisition_type_code": "113613",
                "acquisition_type_coding_scheme": "DCM",
            },
        ]
    )


def test_rotational_survey_counts_across_frames():
    st = AppState()
    st.rdsr_df = _spin_frame()
    st.loaded_exams = [SimpleNamespace(normalized_data=_spin_frame())]
    # rdsr_df is the concatenation of loaded exams: count exams only, once.
    survey = rotational_survey(st)
    assert survey["rotational"] == 1
    assert survey["total"] == 2
    assert survey["unresolved"] == []


def test_rotational_survey_falls_back_to_rdsr_df():
    st = AppState()
    st.rdsr_df = _spin_frame()
    survey = rotational_survey(st)
    assert survey["rotational"] == 1
    assert survey["total"] == 2


def test_rotational_survey_lists_unresolved():
    st = AppState()
    frame = pd.DataFrame(
        [
            {
                "Ap1": 90.0,
                "Ap2": 0.0,
                "Ap1_end": None,
                "Ap2_end": None,
                "acquisition_type": "Rotational Acquisition",
            },
            {
                "Ap1": 0.0,
                "Ap2": 0.0,
                "Ap1_end": 10.0,
                "Ap2_end": 0.0,
                "acquisition_type": "Stepping Acquisition",
                "acquisition_type_code": "113612",
                "acquisition_type_coding_scheme": "DCM",
            },
        ]
    )
    st.loaded_exams = [SimpleNamespace(normalized_data=frame)]
    survey = rotational_survey(st)
    assert survey["rotational"] == 1
    assert survey["positioner_motion"] == 1
    unresolved = survey["unresolved"]
    assert isinstance(unresolved, list)
    assert len(unresolved) == 2
    labels = {(entry[0], entry[1], entry[2]) for entry in unresolved}
    assert ("Exam 1", 0, "rotational") in labels
    assert ("Exam 1", 1, "positioner_motion") in labels
    # Privacy-safe: indices + reason codes only, no values.
    first = unresolved[0]
    assert isinstance(first, tuple)
    assert first[3] and all(isinstance(reason, str) for reason in first[3])


def test_rotational_survey_zero_when_static():
    st = AppState()
    st.rdsr_df = pd.DataFrame(
        [{"Ap1": 0.0, "Ap2": 0.0, "Ap1_end": 0.0, "Ap2_end": 0.0, "acquisition_type": "Fluoroscopy"}]
    )
    survey = rotational_survey(st)
    assert survey["rotational"] == 0
    assert survey["positioner_motion"] == 0
    assert survey["total"] == 1


def test_rotational_survey_empty_state():
    assert rotational_survey(AppState()) == {
        "rotational": 0,
        "positioner_motion": 0,
        "unknown": 0,
        "total": 0,
        "unresolved": [],
    }


def test_build_settings_propagates_rotational_handling():
    st = AppState()
    st.rotational_handling = "static"
    assert build_settings(st).rotational_handling == "static"


def test_build_settings_default_handling_is_coverage():
    assert build_settings(AppState()).rotational_handling == "coverage"


def test_build_settings_rejects_invalid_handling():
    st = AppState()
    st.rotational_handling = "bogus"
    with pytest.raises(ValueError, match="rotational_handling"):
        build_settings(st)


def test_rotational_survey_flags_contradictory_rows():
    st = AppState()
    frame = pd.DataFrame(
        [
            {
                "Ap1": 0.0,
                "Ap2": 0.0,
                "Ap1_end": 50.0,
                "Ap2_end": 0.0,
                "acquisition_type": "Stationary Acquisition",
                "acquisition_type_code": "113611",
                "acquisition_type_coding_scheme": "DCM",
            },
        ]
    )
    st.loaded_exams = [SimpleNamespace(normalized_data=frame)]
    survey = rotational_survey(st)
    assert survey["rotational"] == 0
    assert survey["positioner_motion"] == 0
    unresolved = survey["unresolved"]
    assert isinstance(unresolved, list) and len(unresolved) == 1
    first = unresolved[0]
    assert isinstance(first, tuple) and "contradictory_static" in first[3]


def test_cli_default_handling_is_coverage():
    """Headless runs default to coverage; the prompt lives in GUI code only."""
    from guiskindose import load_settings_example_json
    from guiskindose.settings import PyskindoseSettings

    settings = PyskindoseSettings(settings=load_settings_example_json())
    assert settings.rotational_handling == "coverage"
    import guiskindose.calculate_dose.calculate_irradiation_event_result as loop

    assert not hasattr(loop, "rotational_prompt")


def test_prompt_required_on_contradictory_only_dataset():
    from guiskindose.gui.tabs.calculate import rotational_prompt_required

    st = AppState()
    frame = pd.DataFrame(
        [
            {
                "Ap1": 0.0,
                "Ap2": 0.0,
                "Ap1_end": 50.0,
                "Ap2_end": 0.0,
                "acquisition_type": "Stationary Acquisition",
                "acquisition_type_code": "113611",
                "acquisition_type_coding_scheme": "DCM",
            },
        ]
    )
    st.loaded_exams = [SimpleNamespace(normalized_data=frame)]
    assert rotational_prompt_required(rotational_survey(st)) is True


def test_prompt_not_required_for_all_static():
    from guiskindose.gui.tabs.calculate import rotational_prompt_required

    st = AppState()
    st.rdsr_df = pd.DataFrame(
        [{"Ap1": 0.0, "Ap2": 0.0, "Ap1_end": 0.0, "Ap2_end": 0.0, "acquisition_type": "Fluoroscopy"}]
    )
    assert rotational_prompt_required(rotational_survey(st)) is False
