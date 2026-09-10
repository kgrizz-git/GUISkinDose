"""Construct PyskindoseSettings from GUI AppState."""

from __future__ import annotations

from pathlib import Path

from guiskindose import load_settings_example_json
from guiskindose.settings import PyskindoseSettings

from .state import AppState


def fallback_normalization_exam_count(app_state: AppState) -> int:
    """Count loaded exams still using fallback normalization."""
    return sum(1 for m in app_state.loaded_exam_meta if m.get("normalization_method") == "Fallback")


def format_input_scanner_label(app_state: AppState) -> str:
    """Prefer actual input manufacturer/model; fall back to matched profile labels."""
    text = f"{app_state.input_manufacturer} {app_state.input_model}".strip()
    if not text:
        text = f"{app_state.manufacturer} {app_state.model}".strip()
    return text or "—"


def format_normalization_profile_label(app_state: AppState) -> str:
    """Describe the matched profile or Default fallback for Settings/Calculate."""
    if app_state.normalization_method == "Matched":
        matched = f"{app_state.manufacturer} {app_state.model}".strip()
        return f"Matched: {matched}" if matched else "Matched"
    if app_state.normalization_method == "Fallback":
        return "Default profile"
    return ""


def refresh_normalization_warnings(app_state: AppState) -> None:
    """Rebuild toast warnings from every loaded exam's fallback status.

    Multi-file uploads must accumulate per-exam messages; clearing on each file
    would leave only the last exam's warning.
    """
    warnings: list[str] = []
    multi = len(app_state.loaded_exam_meta) > 1
    for index, meta in enumerate(app_state.loaded_exam_meta):
        if meta.get("normalization_method") != "Fallback":
            continue
        scanner = f"{meta.get('input_manufacturer', '')} {meta.get('input_model', '')}".strip()
        if not scanner:
            scanner = "unknown scanner"
        prefix = f"Exam {index + 1}: " if multi else ""
        warnings.append(
            f"{prefix}Scanner '{scanner}' not found in normalization profiles. "
            "Using default normalization settings."
        )
    app_state.normalization_warnings = warnings


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
    base["beam_miss_warn"] = app_state.beam_miss_warn
    base["silence_pydicom_warnings"] = True

    base["kerma_meter_correction"] = {
        "enable": app_state.kerma_meter_enable,
        "mode": app_state.kerma_meter_mode,
        "file": app_state.kerma_meter_file or None,
        "file_sheet": app_state.kerma_meter_file_sheet or None,
        "default_factor": app_state.kerma_meter_default_factor,
        "explicit_label": app_state.kerma_meter_explicit_label or None,
        "prompt_at_calc": app_state.kerma_meter_prompt_at_calc,
    }

    base["phantom"]["model"] = app_state.phantom_model
    from guiskindose.phantom_mesh_names import resolve_human_mesh_stem

    base["phantom"]["human_mesh"] = resolve_human_mesh_stem(app_state.human_mesh)
    base["phantom"]["scale_lat"] = app_state.phantom_scale_lat
    base["phantom"]["scale_ap"] = app_state.phantom_scale_ap
    base["phantom"]["scale_lon"] = app_state.phantom_scale_lon
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
