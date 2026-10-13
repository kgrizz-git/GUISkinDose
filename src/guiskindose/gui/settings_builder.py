"""Construct PyskindoseSettings from GUI AppState."""

from __future__ import annotations

import copy
from typing import TYPE_CHECKING

from guiskindose import load_settings_example_json
from guiskindose.equipment_profiles.capture import (
    CODE_INVALID_EQUIPMENT_CAPTURE,
    CaptureError,
    validate_constructed_context,
)
from guiskindose.equipment_profiles.constants import MAX_AGGREGATE_ROWS, MAX_PROFILES
from guiskindose.equipment_profiles.session import EquipmentProfileSession
from guiskindose.settings import PyskindoseSettings

from .state import AppState, reset_results

if TYPE_CHECKING:
    from guiskindose.equipment_profiles.capture import CapturedCoordinates
    from guiskindose.input_adapters.models import InputAdapterResult
    from guiskindose.settings.normalization_settings import NormalizationSettings


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


def bind_equipment_session(app_state: AppState, session: EquipmentProfileSession | None) -> None:
    """Bind (or clear) the live custom-profile session: import-before-data-load only.

    Refuses closed with loaded exams, legacy preview data, or an in-flight
    operation — activating, replacing, or clearing a session under loaded
    geometry would silently re-scope dose, so the caller unloads everything
    first, then binds, then loads. Binding a session while run-configuration
    equipment is staged is also refused (the staged captures would conflict
    with live resolution); clearing back to None stays allowed. A candidate
    failure leaves session, results, offsets, and exams untouched: every check
    runs before the single assignment, and results invalidate only on success
    (stale dose must never display under a new session). The session object
    itself is immutable and already assembled; no store or file is opened here.
    """
    if session is not None and not isinstance(session, EquipmentProfileSession):
        raise ValueError("Equipment session must be an EquipmentProfileSession or None.")
    if app_state.busy:
        raise ValueError("Cannot change the equipment-profile session while an operation is in flight.")
    if app_state.loaded_exams or app_state.rdsr_df is not None:
        raise ValueError(
            "Cannot change the equipment-profile session with exams loaded or preview "
            "data present; unload all exams first, then bind, then load."
        )
    if session is not None and app_state.equipment_pending:
        raise ValueError(
            "Cannot bind an equipment-profile session while run-configuration "
            "equipment is staged; load the staged exams first, or re-import without equipment."
        )
    app_state.equipment_profile_session = session
    reset_results(app_state)


def build_settings(
    app_state: AppState,
    mode: str = "calculate_dose",
    output_format: str = "dict",
    patient_offset: tuple[float, float, float] | None = None,
) -> PyskindoseSettings:
    """Construct a PyskindoseSettings object from current UI state."""
    base = load_settings_example_json()

    base["mode"] = mode
    base["k_tab_mode"] = app_state.k_tab_mode
    base.pop("estimate_k_tab", None)
    base["k_tab_val"] = app_state.k_tab_val
    base["inherent_filtration"] = app_state.inherent_filtration
    base["remove_invalid_rows"] = app_state.remove_invalid_rows
    base["below_floor_kvp_policy"] = app_state.below_floor_kvp_policy
    base["below_floor_kvp_manual"] = app_state.below_floor_kvp_manual
    base["beam_miss_warn"] = app_state.beam_miss_warn
    base["rotational_handling"] = app_state.rotational_handling
    base["silence_pydicom_warnings"] = True

    # Imported run-state homes (None = example-JSON default, left in place).
    if app_state.include_static_pose is not None:
        base["include_static_pose"] = app_state.include_static_pose
    if app_state.angular_step_deg is not None:
        base["angular_step_deg"] = app_state.angular_step_deg
    if app_state.dosetrack_plane_code_map is not None:
        base["dosetrack_plane_code_map"] = app_state.dosetrack_plane_code_map
    if app_state.corrections_db_path is not None:
        base["corrections_db_path"] = app_state.corrections_db_path
    if app_state.phantom_dimensions is not None:
        # Overlay, never replace: partial hand-crafted documents cannot drop
        # keys the PhantomDimensions constructor requires.
        base["phantom"]["dimension"].update(app_state.phantom_dimensions)
    if app_state.max_events_for_patient_inclusion is not None:
        base["plot"]["max_events_for_patient_inclusion"] = app_state.max_events_for_patient_inclusion

    base["kerma_meter_correction"] = {
        "enable": app_state.kerma_meter_enable,
        "file": app_state.kerma_meter_file or None,
        "file_sheet": app_state.kerma_meter_file_sheet or None,
        "default_factor": app_state.kerma_meter_default_factor,
        "explicit_label": app_state.kerma_meter_explicit_label or None,
        "ask_for_missing": app_state.kerma_meter_ask_for_missing,
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

    normalization_arg = None
    if app_state.normalization_profiles:
        from guiskindose.settings.normalization_settings import NormalizationSettings

        # Wrap first: the PyskindoseSettings kwarg takes
        # Path | str | dict | NormalizationSettings | None, not a bare list.
        # An empty list means "unspecified" and keeps the default profiles:
        # a zero-profile build would silently disable vendor normalization.
        normalization_arg = NormalizationSettings(app_state.normalization_profiles)

    return PyskindoseSettings(
        settings=base,
        normalization_settings=normalization_arg,
        output_format=output_format,
        equipment_profile_session=app_state.equipment_profile_session,
    )


def settings_stripped(settings: PyskindoseSettings) -> PyskindoseSettings:
    """Remove the bound live session from caller-owned calculation settings.

    Captured calculation never resolves live; stripping here (rather than in
    the loaders) keeps the bound home intact for future loads while the
    calculation works on an isolated copy. Only ever called with fresh
    ``build_settings`` output, never caller-persisted state.
    """
    settings.equipment_profile_session = None
    return settings


def _validate_calculation_frames(
    loaded: list[InputAdapterResult], contexts: list[CapturedCoordinates | None]
) -> None:
    """Validate every authority and bound current rows before copying baselines."""
    from guiskindose.settings.normalization_settings import NormalizationSettings

    retained = 0
    for context, exam in zip(contexts, loaded, strict=True):
        if context is not None:
            validate_constructed_context(context)
        retained += len(exam.normalized_data)
        if retained > MAX_AGGREGATE_ROWS:
            raise CaptureError("Too many retained events for captured calculation.", CODE_INVALID_EQUIPMENT_CAPTURE)
        if context is None and not isinstance(exam.normalization_snapshot, NormalizationSettings):
            raise CaptureError(
                "An exam is missing its captured authority baseline; reload the exams.", CODE_INVALID_EQUIPMENT_CAPTURE
            )


def prepare_calculation_authority(
    app_state: AppState, settings: PyskindoseSettings
) -> tuple[
    PyskindoseSettings, list[CapturedCoordinates | None] | None, list[NormalizationSettings | None] | None
]:
    """Split live-session settings from captured-calculation authority.

    Collects each loaded exam's minted capture positionally. With no captures
    anywhere the caller's settings pass through untouched (pure and
    live-session paths behave exactly as before). With any capture present
    the bound live session is stripped from the calculation settings —
    captured calculation never resolves live — and every capture-less entry
    installs its own retained per-exam normalization snapshot (all-captured
    runs need no baselines). A capture-less entry with no snapshot is
    inconsistent authority (stripped provenance, not an intentional null) and
    fails closed before any dose. Exam/event ceilings are enforced here on
    O(1) counts plus early-exit sums — covering every retained row, captured
    or not — before any baseline is copied. The settings object must be
    caller-owned (``build_settings`` output): it is mutated only by session
    removal, never by capture content.
    """
    loaded = app_state.loaded_exams
    if len(loaded) > MAX_PROFILES:
        # Preserve unrestricted legacy baseline runs without materializing an
        # oversized authority list. Any captured or live authority is bounded.
        session = settings.equipment_profile_session
        if (session is not None and session.profiles) or any(exam.equipment_capture is not None for exam in loaded):
            raise CaptureError("Too many captured exams for one calculation.", CODE_INVALID_EQUIPMENT_CAPTURE)
        return settings, None, None
    contexts: list[CapturedCoordinates | None] = [exam.equipment_capture for exam in loaded]
    if not any(context is not None for context in contexts):
        return settings, None, None
    _validate_calculation_frames(loaded, contexts)
    # All bounds and baseline shapes pass before copying any snapshot.
    baselines = [
        copy.deepcopy(exam.normalization_snapshot) if context is None else None
        for context, exam in zip(contexts, loaded, strict=True)
    ]
    if not any(baseline is not None for baseline in baselines):
        return settings_stripped(settings), contexts, None
    return settings_stripped(settings), contexts, baselines
