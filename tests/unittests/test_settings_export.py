"""Phase 1 (chunk 1) — sub-object settings round-trips for export.

Covers `Plotsettings.to_dict()` (including the `colorscale` fix),
`PhantomSettings.to_dict()`, `PatientOffset.to_dict()`, reuse of the existing
`KermaMeterCorrectionSettings.to_dict()`, and removal of the dead root
`plot_event_index` key from `settings_example.json`.
"""

import json

from guiskindose import load_settings_example_json
from guiskindose.settings.kerma_meter_correction_settings import (
    KermaMeterCorrectionSettings,
)
from guiskindose.settings.patient_offset import PatientOffset
from guiskindose.settings.phantom_settings import PhantomSettings
from guiskindose.settings.plot_settings import Plotsettings


def _example_phantom_dict():
    return load_settings_example_json()["phantom"]


def test_plot_to_dict_round_trips_through_constructor():
    original = Plotsettings(plt_dict=load_settings_example_json()["plot"])

    rebuilt = Plotsettings(plt_dict=original.to_dict())

    assert rebuilt.to_dict() == original.to_dict()


def test_plot_colorscale_defaults_to_jet_when_absent():
    settings = Plotsettings(plt_dict={})

    assert settings.colorscale == "jet"
    assert settings.to_dict()["colorscale"] == "jet"


def test_plot_colorscale_custom_value_survives():
    settings = Plotsettings(plt_dict={"colorscale": "viridis"})

    rebuilt = Plotsettings(plt_dict=settings.to_dict())

    assert rebuilt.colorscale == "viridis"


def test_phantom_to_dict_round_trips_through_constructor():
    original = PhantomSettings(ptm_dim=_example_phantom_dict())

    rebuilt = PhantomSettings(ptm_dim=original.to_dict())

    assert rebuilt.to_dict() == original.to_dict()


def test_phantom_to_dict_carries_scales_offset_and_full_dimensions():
    serialized = PhantomSettings(ptm_dim=_example_phantom_dict()).to_dict()

    assert serialized["scale_lat"] == 1.0
    assert serialized["scale_ap"] == 1.0
    assert serialized["scale_lon"] == 1.0
    assert serialized["patient_offset"] == {"d_lat": 0, "d_ver": 0, "d_lon": 0}
    assert serialized["dimension"] == PhantomSettings(ptm_dim=_example_phantom_dict()).dimension.to_dict_pad()


def test_patient_offset_to_dict_round_trips_through_constructor():
    original = PatientOffset(offset={"d_lat": 1, "d_ver": -2, "d_lon": 3})

    rebuilt = PatientOffset(offset=original.to_dict())

    assert (rebuilt.d_lat, rebuilt.d_ver, rebuilt.d_lon) == (1, -2, 3)


def test_kerma_to_dict_round_trips_through_constructor():
    raw = load_settings_example_json().get("kerma_meter_correction", {})
    original = KermaMeterCorrectionSettings(raw)

    rebuilt = KermaMeterCorrectionSettings(original.to_dict())

    assert rebuilt.to_dict() == original.to_dict()


def test_example_json_has_no_dead_root_plot_event_index():
    example = load_settings_example_json()

    assert "plot_event_index" not in example
    assert example["plot"]["plot_event_index"] == 1


def test_example_json_plot_block_carries_colorscale():
    assert load_settings_example_json()["plot"]["colorscale"] == "jet"


def test_example_json_still_parses_as_valid_settings_dict():
    # The dead-key removal must not break the example as constructor input.
    raw = json.dumps(load_settings_example_json())

    assert json.loads(raw)["mode"] == "plot_event"
