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
from guiskindose.settings.pyskindose_settings import PyskindoseSettings


def _example_phantom_dict():
    return load_settings_example_json()["phantom"]


def test_plot_to_dict_round_trips_through_constructor():
    source = load_settings_example_json()["plot"]
    original = Plotsettings(plt_dict=source)

    # Pin against the source dict: idempotence alone cannot catch a dropped
    # optional key (both sides would share the same blind spot via defaults).
    assert original.to_dict() == source

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
    source = _example_phantom_dict()
    original = PhantomSettings(ptm_dim=source)

    # Pin against the source dict (see plot test: idempotence alone cannot
    # catch a dropped optional key).
    assert original.to_dict() == source

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
    source = load_settings_example_json().get("kerma_meter_correction", {})
    original = KermaMeterCorrectionSettings(source)

    # Pin against the source dict (see plot test: idempotence alone cannot
    # catch a dropped optional key).
    assert original.to_dict() == source

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


# --- Phase 1 chunk 2: top-level PyskindoseSettings round-trip ---

EXPECTED_TOP_LEVEL_KEYS = {
    "mode",
    "rdsr_filename",
    "estimate_k_tab",
    "k_tab_val",
    "inherent_filtration",
    "silence_pydicom_warnings",
    "remove_invalid_rows",
    "below_floor_kvp_policy",
    "below_floor_kvp_manual",
    "beam_miss_warn",
    "rotational_handling",
    "include_static_pose",
    "angular_step_deg",
    "corrections_db_path",
    "phantom",
    "plot",
    "kerma_meter_correction",
    "dosetrack_plane_code_map",
}


def test_top_level_key_inventory_matches_normalized_example_keys():
    example_keys = set(load_settings_example_json())
    serialized = PyskindoseSettings(settings=load_settings_example_json()).to_settings_dict()

    # The only sanctioned difference: the nullable dosetrack map, absent from
    # the example file, is always emitted (None when unset).
    assert set(serialized) == EXPECTED_TOP_LEVEL_KEYS
    assert example_keys | {"dosetrack_plane_code_map"} == EXPECTED_TOP_LEVEL_KEYS


def test_to_settings_dict_excludes_runtime_only_state():
    serialized = PyskindoseSettings(settings=load_settings_example_json()).to_settings_dict()

    for key in ("output_format", "file_result_output_path", "normalization_settings", "in_memory_table"):
        assert key not in serialized
    assert "in_memory_table" not in serialized["kerma_meter_correction"]


def test_top_level_to_settings_dict_matches_example_values():
    example = load_settings_example_json()
    serialized = PyskindoseSettings(settings=example).to_settings_dict()

    expected = dict(example)
    expected.setdefault("dosetrack_plane_code_map", None)
    assert serialized == expected


def test_top_level_idempotence_through_reconstruction():
    first = PyskindoseSettings(settings=load_settings_example_json()).to_settings_dict()

    second = PyskindoseSettings(settings=first).to_settings_dict()

    assert second == first


def test_to_json_parses_back_to_settings_dict():
    settings = PyskindoseSettings(settings=load_settings_example_json())

    assert json.loads(settings.to_json()) == settings.to_settings_dict()


def test_dosetrack_plane_code_map_round_trips_on_api_path():
    base = load_settings_example_json()
    base["dosetrack_plane_code_map"] = {"1": "Single Plane", "2": "Plane A"}
    settings = PyskindoseSettings(settings=base)

    serialized = settings.to_settings_dict()

    assert serialized["dosetrack_plane_code_map"] == {"1": "Single Plane", "2": "Plane A"}
    rebuilt = PyskindoseSettings(settings=serialized)
    assert rebuilt.dosetrack_plane_code_map == {1: "Single Plane", 2: "Plane A"}
    assert rebuilt.to_settings_dict() == serialized


def test_settings_slice_accepted_as_constructor_input():
    # Simulates `--settings` receiving an extracted document["settings"] slice.
    document = {"settings": PyskindoseSettings(settings=load_settings_example_json()).to_settings_dict()}

    settings = PyskindoseSettings(settings=document["settings"])

    assert settings.to_settings_dict() == document["settings"]
