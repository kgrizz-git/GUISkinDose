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
    # Active frame (1 spin) + loaded exam (1 spin); each frame contributes.
    survey = rotational_survey(st)
    assert survey["rotational"] == 2
    assert survey["total"] == 4


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
