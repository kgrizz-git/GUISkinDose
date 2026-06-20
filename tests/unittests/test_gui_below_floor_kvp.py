"""GUI-side smoke tests for the below-floor kVp policy (Phase 2).

The policy itself is exercised in ``test_geom_calc.py``; here we only confirm the
GUI wiring: the detection helper sums sub-floor events across loaded exams, the
new settings reach ``PyskindoseSettings`` via ``build_settings``, and the policy
options match the canonical constant list.
"""

from __future__ import annotations

from types import SimpleNamespace

import pandas as pd
import pytest

pytest.importorskip("nicegui")

from mypyskindose.constants import BELOW_FLOOR_KVP_POLICIES
from mypyskindose.gui.helpers import below_floor_event_count, build_settings
from mypyskindose.gui.state import AppState
from mypyskindose.gui.tabs.settings import BELOW_FLOOR_KVP_OPTIONS


def _exam(kvp_list: list[float]) -> SimpleNamespace:
    return SimpleNamespace(normalized_data=pd.DataFrame({"kVp": kvp_list}))


def test_below_floor_event_count_sums_across_exams():
    st = AppState()
    # Exam 1: one below-floor (10). Exam 2: two below-floor (5, 24.9). 25 is on-floor.
    st.loaded_exams = [_exam([70.0, 10.0, 25.0]), _exam([5.0, 24.9, 80.0])]
    assert below_floor_event_count(st) == 3


def test_below_floor_event_count_zero_when_all_in_floor():
    st = AppState()
    st.loaded_exams = [_exam([70.0, 80.0, 25.0])]
    assert below_floor_event_count(st) == 0


def test_below_floor_event_count_no_exams():
    assert below_floor_event_count(AppState()) == 0


def test_build_settings_propagates_below_floor_policy():
    st = AppState()
    st.below_floor_kvp_policy = "manual"
    st.below_floor_kvp_manual = 66.0

    settings = build_settings(st)

    assert settings.below_floor_kvp_policy == "manual"
    assert settings.below_floor_kvp_manual == 66.0


def test_build_settings_default_policy_is_snap():
    settings = build_settings(AppState())
    assert settings.below_floor_kvp_policy == "snap"


def test_settings_options_match_constant_policies():
    assert tuple(BELOW_FLOOR_KVP_OPTIONS.keys()) == BELOW_FLOOR_KVP_POLICIES
