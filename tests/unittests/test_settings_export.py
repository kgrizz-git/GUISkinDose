"""Phase 1 (chunk 1) — sub-object settings round-trips for export.

Covers `Plotsettings.to_dict()` (including the `colorscale` fix),
`PhantomSettings.to_dict()`, `PatientOffset.to_dict()`, reuse of the existing
`KermaMeterCorrectionSettings.to_dict()`, and removal of the dead root
`plot_event_index` key from `settings_example.json`.
"""

import json
from pathlib import Path

from guiskindose import load_settings_example_json
from guiskindose.gui.run_state import (
    RUN_STATE_SCHEMA,
    RUN_STATE_SCHEMA_VERSION,
    serialize_run_state,
)
from guiskindose.gui.state import AppState
from guiskindose.settings.kerma_meter_correction_settings import (
    KermaMeterCorrectionSettings,
)
from guiskindose.settings.normalization_settings import NormalizationSettings
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


# --- Phase 2 chunk A: NormalizationSettings.to_profile_list ---


def _default_profiles():
    from pathlib import Path

    return json.loads(
        (Path(__file__).parent.parent.parent / "src" / "guiskindose" / "normalization_settings.json").read_text()
    )["normalization_settings"]


def test_normalization_to_profile_list_round_trips_through_constructor():
    original = NormalizationSettings(_default_profiles())

    rebuilt = NormalizationSettings(original.to_profile_list())

    assert rebuilt.to_profile_list() == original.to_profile_list()


def test_normalization_to_profile_list_matches_on_disk_shape():
    profiles = NormalizationSettings(_default_profiles()).to_profile_list()

    assert profiles == _default_profiles()
    assert profiles[0]["translation_offset"] == {"x": 0.0, "y": 0.0, "z": 0.0}
    assert profiles[0]["translation_direction"] == {"x": "+", "y": "+", "z": "+"}


def test_normalization_to_profile_list_returns_copies_not_aliases():
    original = NormalizationSettings(_default_profiles())

    exported = original.to_profile_list()
    exported[0]["manufacturer"] = "MUTATED"
    exported[0]["translation_offset"]["x"] = 999.0

    assert original.to_profile_list()[0]["manufacturer"] != "MUTATED"
    assert original.to_profile_list()[0]["translation_offset"]["x"] != 999.0


def test_normalization_custom_profile_with_swap_flag_survives():
    profiles = _default_profiles()
    profiles[0]["swap_lateral_longitudinal"] = True

    rebuilt = NormalizationSettings(NormalizationSettings(profiles).to_profile_list())

    assert rebuilt.to_profile_list()[0]["swap_lateral_longitudinal"] is True


# --- Phase 2 chunk B: run-state serializer ---


def _example_settings():
    return PyskindoseSettings(settings=load_settings_example_json())


def _populated_state():
    state = AppState()
    state.input_schema = "dosetrack"
    state.input_source_type = "xlsx"
    state.input_sheet_name = "Events"
    state.swap_lat_lon = True
    state.flip_ap1 = True
    state.kerma_meter_in_memory_table = {("Acme", "TubeA"): 1.02}
    state.loaded_exam_meta = [
        {
            "d_lon": 1.0,
            "d_ver": 2.0,
            "d_lat": 3.0,
            "table_origin_override": {"x": 0.0, "y": 0.0, "z": 0.0},
            "table_origin_detected": {"x": 1.0, "y": 2.0, "z": 3.0},
            "swap_lat_lon": True,
            "flip_ap1": False,
            "flip_ap2": True,
            "flip_tx": True,
            "flip_ty": False,
            "flip_tz": True,
            "source_type": "xlsx",
            "schema": "dosetrack",
            "sheet": "Events",
            "normalization_method": "Matched",
            "study_id": "STUDY-1",
            "file_name": "export.xlsx",
            "file_path": Path("/data/inbox/export.xlsx"),
            "input_manufacturer": "Acme",
            "input_model": "X1000",
        }
    ]
    return state


def _settings_with_kerma_file():
    base = load_settings_example_json()
    base["kerma_meter_correction"] = {
        "enable": True,
        "mode": "file",
        "file": "/data/cf/corrections.xlsx",
        "file_sheet": "CF",
        "default_factor": 1.02,
        "explicit_label": "Lab-1",
        "prompt_at_calc": False,
    }
    return PyskindoseSettings(settings=base)


def test_serializer_redacts_identifiers_by_default():
    document = serialize_run_state(_settings_with_kerma_file(), _populated_state(), created="2026-09-24T00:00:00+00:00")

    assert document["schema"] == RUN_STATE_SCHEMA
    assert document["schema_version"] == RUN_STATE_SCHEMA_VERSION
    assert document["settings"]["rdsr_filename"] is None
    assert document["settings"]["corrections_db_path"] is None
    kerma = document["settings"]["kerma_meter_correction"]
    assert kerma["file"] is None
    assert kerma["file_sheet"] is None
    assert kerma["explicit_label"] is None
    assert kerma["default_factor"] == 1.02  # non-identifying config survives
    gui_state = document["gui_state"]
    assert gui_state["input_sheet_name"] is None  # string name gated
    exam = gui_state["exams"][0]
    assert exam["label"] == "Exam 1"  # always opaque
    assert exam["sheet"] is None
    assert exam["study_id"] is None
    assert exam["file_name"] is None
    assert exam["file_path"] is None
    assert exam["input_manufacturer"] is None
    assert exam["input_model"] is None
    # Non-identifying reconstruction state survives redaction.
    assert exam["d_lon"] == 1.0
    assert exam["flip_tx"] is True
    assert exam["normalization_method"] == "Matched"


def test_serializer_include_identifiers_restores_gated_values_basename_only():
    document = serialize_run_state(_settings_with_kerma_file(), _populated_state(), include_identifiers=True)

    kerma = document["settings"]["kerma_meter_correction"]
    assert kerma["file"] == "corrections.xlsx"  # basename only, never absolute
    assert kerma["file_sheet"] == "CF"
    assert kerma["explicit_label"] == "Lab-1"
    gui_state = document["gui_state"]
    assert gui_state["input_sheet_name"] == "Events"
    exam = gui_state["exams"][0]
    assert exam["sheet"] == "Events"
    assert exam["study_id"] == "STUDY-1"
    assert exam["file_name"] == "export.xlsx"
    assert exam["file_path"] == "export.xlsx"  # Path object stringified to basename
    assert exam["input_manufacturer"] == "Acme"
    assert exam["input_model"] == "X1000"


def test_serializer_integer_sheet_indices_survive_redacted_exports():
    state = AppState()
    state.input_sheet_name = 2
    state.loaded_exam_meta = [{"sheet": 0}]

    document = serialize_run_state(_example_settings(), state)

    assert document["gui_state"]["input_sheet_name"] == 2
    assert document["gui_state"]["exams"][0]["sheet"] == 0  # falsy-but-valid index kept


def test_serializer_basename_never_leaks_windows_paths():
    state = AppState()
    state.loaded_exam_meta = [
        {"file_path": "C:\\fakepath\\export.xlsx"},
        {"file_path": "C:\\"},
        {"file_path": "/"},
    ]

    document = serialize_run_state(_example_settings(), state, include_identifiers=True)
    exams = document["gui_state"]["exams"]

    # Backslash separators normalize on any host OS: no absolute path leaks.
    assert exams[0]["file_path"] == "export.xlsx"
    # Bare roots have no basename: None, not "".
    assert exams[1]["file_path"] is None
    assert exams[2]["file_path"] is None


def test_serializer_applies_plot_dosemap_overlay():
    state = AppState()
    state.plot_dosemap = True

    document = serialize_run_state(_example_settings(), state)

    # The example builds plot_dosemap False (build_settings forces False);
    # the export reads the AppState value instead.
    assert document["settings"]["plot"]["plot_dosemap"] is True


def test_serializer_nests_in_memory_table():
    redacted = serialize_run_state(_example_settings(), _populated_state())
    assert redacted["gui_state"]["kerma_meter_in_memory_table"] == {"Acme": {"TubeA": 1.02}}

    empty = serialize_run_state(_example_settings(), AppState())
    assert empty["gui_state"]["kerma_meter_in_memory_table"] is None


def test_serializer_document_is_json_serializable_with_no_runtime_leakage():
    import pandas as pd

    state = _populated_state()
    state.rdsr_df = pd.DataFrame({"a": [1]})  # runtime object must never leak in

    document = serialize_run_state(
        _example_settings(),
        state,
        normalization_profiles=_default_profiles(),
        app_version="1.0.0",
        created="2026-09-24T00:00:00+00:00",
    )

    assert json.loads(json.dumps(document)) == document
    assert document["normalization_settings"] == _default_profiles()
    assert document["app_version"] == "1.0.0"
    assert document["created"] == "2026-09-24T00:00:00+00:00"
    assert [exam["label"] for exam in document["gui_state"]["exams"]] == ["Exam 1"]


def test_serializer_defaults_for_empty_state():
    document = serialize_run_state(_example_settings(), AppState())

    assert document["gui_state"]["exams"] == []
    assert document["gui_state"]["input_sheet_name"] == 0  # default index preserved
    assert document["normalization_settings"] == []
    assert document["created"]  # current UTC timestamp by default
    assert document["app_version"]  # installed package version by default
