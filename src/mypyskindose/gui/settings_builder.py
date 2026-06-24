"""Construct PyskindoseSettings from GUI AppState."""

from __future__ import annotations

from pathlib import Path

from mypyskindose import load_settings_example_json
from mypyskindose.settings import PyskindoseSettings

from .state import AppState


def fallback_normalization_exam_count(app_state: AppState) -> int:
    return sum(1 for m in app_state.loaded_exam_meta if m.get("normalization_method") == "Fallback")


def build_settings(
    app_state: AppState,
    mode: str = "calculate_dose",
    output_format: str = "dict",
    patient_offset: tuple[float, float, float] | None = None,
) -> PyskindoseSettings:
    """Construct a PyskindoseSettings object from current UI state."""
    base = load_settings_example_json()

    base["mode"] = mode
    base["estimate_k_tab"] = app_state.estimate_k_tab
    base["k_tab_val"] = app_state.k_tab_val
    base["inherent_filtration"] = app_state.inherent_filtration
    base["remove_invalid_rows"] = app_state.remove_invalid_rows
    base["below_floor_kvp_policy"] = app_state.below_floor_kvp_policy
    base["below_floor_kvp_manual"] = app_state.below_floor_kvp_manual
    base["silence_pydicom_warnings"] = True

    base["phantom"]["model"] = app_state.phantom_model
    base["phantom"]["human_mesh"] = app_state.human_mesh
    base["phantom"]["patient_orientation"] = app_state.patient_orientation
    if patient_offset is not None:
        d_lon, d_ver, d_lat = patient_offset
    else:
        d_lon, d_ver, d_lat = app_state.d_lon, app_state.d_ver, app_state.d_lat
    base["phantom"]["patient_offset"]["d_lon"] = d_lon
    base["phantom"]["patient_offset"]["d_ver"] = d_ver
    base["phantom"]["patient_offset"]["d_lat"] = d_lat

    base["plot"]["dark_mode"] = app_state.dark_mode
    base["plot"]["plot_dosemap"] = False  # we handle plotting ourselves
    base["plot"]["interactivity"] = True
    base["plot"]["notebook_mode"] = False
    base["plot"]["colorscale"] = app_state.colorscale

    # Point corrections DB to the package root
    db_path = Path(__file__).parent.parent.parent.parent / "corrections.db"
    if db_path.exists():
        base["corrections_db_path"] = str(db_path)

    return PyskindoseSettings(settings=base, output_format=output_format)
