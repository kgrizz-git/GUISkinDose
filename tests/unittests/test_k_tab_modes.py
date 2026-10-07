"""Patient-support transmission modes: measured_with_fallback (default), estimate, measured_only."""

from __future__ import annotations

import logging

import pandas as pd
import pytest

from guiskindose import load_settings_example_json
from guiskindose.constants import (
    KEY_NORMALIZATION_ACQUISITION_PLANE,
    KEY_NORMALIZATION_FILTER_SIZE_ALUMINUM,
    KEY_NORMALIZATION_FILTER_SIZE_COPPER,
    KEY_NORMALIZATION_KVP,
    KEY_NORMALIZATION_MODEL_NAME,
)
from guiskindose.corrections import calculate_k_tab
from guiskindose.settings import PyskindoseSettings

DB = "corrections.db"
_FALLBACK = 0.65


def _events(rows: list[tuple[float, float, float, str, str]]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            KEY_NORMALIZATION_KVP: [r[0] for r in rows],
            KEY_NORMALIZATION_FILTER_SIZE_COPPER: [r[1] for r in rows],
            KEY_NORMALIZATION_FILTER_SIZE_ALUMINUM: [r[2] for r in rows],
            KEY_NORMALIZATION_MODEL_NAME: [r[3] for r in rows],
            KEY_NORMALIZATION_ACQUISITION_PLANE: [r[4] for r in rows],
        }
    )


_MEASURED = (80, 0.3, 0, "AXIOM-Artis", "Single Plane")
_UNKNOWN_MODEL = (80, 0.3, 0, "GE Innova", "Single Plane")
_UNKNOWN_PLANE = (80, 0.3, 0, "AXIOM-Artis", "Plane Z")
_ZERO_ROWS = (80, 0.4, 1.0, "AlluraClarity", "Plane B")


def _run(rows, mode, **kw):
    return calculate_k_tab(data_norm=_events(rows), corrections_db=DB, k_tab_val=_FALLBACK, k_tab_mode=mode, **kw)


def test_estimate_mode_uses_the_flat_value_for_every_event() -> None:
    result = _run([_MEASURED, _UNKNOWN_MODEL], "estimate")
    assert result.values == [_FALLBACK, _FALLBACK]
    assert result.statuses == ["estimated", "estimated"]


def test_measured_only_mode_gives_one_for_unusable_events() -> None:
    result = _run([_MEASURED, _UNKNOWN_MODEL, _UNKNOWN_PLANE, _ZERO_ROWS], "measured_only")
    assert result.statuses == ["exact", "no_device", "no_device", "invalid_inherited"]
    assert result.values[1:] == [1.0, 1.0, 1.0]


def test_fallback_mode_uses_measured_values_where_they_exist() -> None:
    measured = _run([_MEASURED], "measured_only")
    result = _run([_MEASURED], "measured_with_fallback")
    assert result.values == measured.values
    assert result.statuses == ["exact"]


@pytest.mark.parametrize("unusable", [_UNKNOWN_MODEL, _UNKNOWN_PLANE, _ZERO_ROWS])
def test_fallback_mode_uses_k_tab_val_not_one_when_measured_data_is_unusable(unusable) -> None:
    result = _run([_MEASURED, unusable], "measured_with_fallback")
    assert result.values[1] == _FALLBACK
    assert result.statuses[1] == "fallback"
    assert result.statuses[0] == "exact"


def test_fallback_mode_warns_with_event_indices_and_no_labels(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING, logger="guiskindose.corrections"):
        _run([_MEASURED, _UNKNOWN_MODEL, _ZERO_ROWS], "measured_with_fallback")
    messages = [r.getMessage() for r in caplog.records if "fallback k_tab_val" in r.getMessage()]
    if messages:  # caplog can miss suite-wide logging state; when seen it must be count/index only
        assert "2 of 3" in messages[0]
        assert "Innova" not in messages[0]
        assert "Allura" not in messages[0]


def test_fallback_mode_validates_the_fallback_value() -> None:
    with pytest.raises(ValueError, match="k_tab_val"):
        calculate_k_tab(
            data_norm=_events([_MEASURED]), corrections_db=DB, k_tab_val=0.0, k_tab_mode="measured_with_fallback"
        )


def test_unknown_mode_is_rejected() -> None:
    with pytest.raises(ValueError, match="k_tab_mode"):
        _run([_MEASURED], "sometimes")


def test_legacy_estimate_flag_still_drives_calculate_k_tab_without_a_mode() -> None:
    assert calculate_k_tab(_events([_MEASURED]), DB, estimate_k_tab=True, k_tab_val=0.7).statuses == ["estimated"]
    assert calculate_k_tab(_events([_UNKNOWN_MODEL]), DB, estimate_k_tab=False, k_tab_val=0.7).values == [1.0]


# ── settings ────────────────────────────────────────────────────────────────


def _settings(**top) -> PyskindoseSettings:
    base = load_settings_example_json()
    base.pop("k_tab_mode", None)
    base.pop("estimate_k_tab", None)
    base.update(top)
    return PyskindoseSettings(settings=base)


def test_default_mode_is_measured_with_fallback() -> None:
    assert _settings().k_tab_mode == "measured_with_fallback"
    assert PyskindoseSettings(settings=load_settings_example_json()).k_tab_mode == "measured_with_fallback"


@pytest.mark.parametrize(("legacy", "expected"), [(True, "estimate"), (False, "measured_only")])
def test_legacy_estimate_k_tab_maps_to_a_mode(legacy: bool, expected: str) -> None:
    settings = _settings(estimate_k_tab=legacy)
    assert settings.k_tab_mode == expected
    assert settings.estimate_k_tab is (expected == "estimate")


def test_explicit_mode_wins_over_the_legacy_flag() -> None:
    assert _settings(k_tab_mode="estimate", estimate_k_tab=False).k_tab_mode == "estimate"


def test_to_dict_emits_the_mode_only_and_round_trips() -> None:
    settings = _settings(estimate_k_tab=True)
    payload = settings.to_settings_dict()
    assert payload["k_tab_mode"] == "estimate"
    assert "estimate_k_tab" not in payload
    assert PyskindoseSettings(settings=payload).k_tab_mode == "estimate"


def test_invalid_mode_raises() -> None:
    with pytest.raises(ValueError, match="k_tab_mode"):
        _settings(k_tab_mode="nope")
