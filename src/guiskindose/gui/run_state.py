"""Run-state document assembly (settings export, Phase 2).

Builds the versioned ``guiskindose.run_state`` JSON document from a
constructed `PyskindoseSettings` plus GUI state, and applies such documents
back to GUI state. The GUI surface wiring (controls, re-parse sequencing,
UI refresh) is Phase 3.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from guiskindose.privacy import opaque_exam_label

if TYPE_CHECKING:  # duck-typed at runtime; keeps this module GUI-light
    from guiskindose.gui.state import AppState
    from guiskindose.settings.pyskindose_settings import PyskindoseSettings

RUN_STATE_SCHEMA = "guiskindose.run_state"
RUN_STATE_SCHEMA_VERSION = 1

_TOP_LEVEL_PASSTHROUGH_EXCLUDE = frozenset(
    {
        "schema",
        "schema_version",
        "app_version",
        "created",
        "settings",
        "normalization_settings",
        "gui_state",
    }
)

# Settings-slice keys restored to same-named AppState fields.
_SCALAR_SETTING_TO_STATE = (
    "estimate_k_tab",
    "k_tab_val",
    "inherent_filtration",
    "remove_invalid_rows",
    "below_floor_kvp_policy",
    "below_floor_kvp_manual",
    "beam_miss_warn",
    "rotational_handling",
)

# document["settings"]["phantom"][key] -> AppState attribute.
_PHANTOM_SETTING_TO_STATE = (
    ("model", "phantom_model"),
    ("human_mesh", "human_mesh"),
    ("scale_lat", "phantom_scale_lat"),
    ("scale_ap", "phantom_scale_ap"),
    ("scale_lon", "phantom_scale_lon"),
    ("patient_orientation", "patient_orientation"),
)

# document kerma key -> AppState attribute (file handled under Tier 2, never
# written; file_sheet/explicit_label applied skip-if-null under Tier 3).
_KERMA_SETTING_TO_STATE = (
    ("enable", "kerma_meter_enable"),
    ("mode", "kerma_meter_mode"),
    ("default_factor", "kerma_meter_default_factor"),
    ("prompt_at_calc", "kerma_meter_prompt_at_calc"),
)

# Import-settable homes with no GUI widget (Phase 3 adds these AppState
# fields; setattr works before and after). None = example-JSON default.
# `phantom_dimensions` is a full dimension dict; `max_events...` a scalar.
_STATE_HOME_KEYS = (
    "normalization_profiles",
    "dosetrack_plane_code_map",
    "include_static_pose",
    "angular_step_deg",
    "corrections_db_path",
    "phantom_dimensions",
    "max_events_for_patient_inclusion",
)

_PLOT_SETTING_TO_STATE = (
    ("dark_mode", "dark_mode"),
    ("colorscale", "colorscale"),
    ("plot_dosemap", "plot_dosemap"),
)

_EXAM_TOGGLE_KEYS = (
    "swap_lat_lon",
    "flip_ap1",
    "flip_ap2",
    "flip_tx",
    "flip_ty",
    "flip_tz",
)

_EXAM_OFFSET_KEYS = ("d_lon", "d_ver", "d_lat")


def _gate(value: Any, include_identifiers: bool) -> Any:
    """Return ``value`` when identifiers are included, else ``None``."""
    return value if include_identifiers else None


def _sheet_value(value: Any, include_identifiers: bool) -> Any:
    """Redact sheet selections: string names ride the identifiers gate.

    Integer indices are positional and opaque, so they survive even in
    redacted exports. Falsy-but-valid index ``0`` is preserved (``None``-check
    only, never truthiness).
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return value if include_identifiers else None


def _basename_or_none(value: Any, include_identifiers: bool) -> Any:
    """Stringify a path value and reduce it to its basename when gated in.

    Returns ``None`` for ``None``/empty input, and ``None`` (redacted) for
    real paths unless identifiers are included — never an absolute path.
    Windows separators are normalized first so basenames extract correctly on
    any host OS (POSIX ``Path`` treats backslash as a regular character,
    which would otherwise leak full ``C:\\...`` paths through).
    """
    if value is None:
        return None
    text = str(value)
    if not text:
        return None
    if not include_identifiers:
        return None
    basename = text.replace("\\", "/").split("/")[-1]
    return basename or None


def _nest_in_memory_table(
    table: dict[tuple[str, str], float] | None,
) -> dict[str, dict[str, float]] | None:
    """Serialize the session CF override table to nested JSON form."""
    if table is None:
        return None
    nested: dict[str, dict[str, float]] = {}
    for (equipment, tube), factor in table.items():
        nested.setdefault(equipment, {})[tube] = factor
    return nested


def _serialize_exam(meta: dict, index: int, include_identifiers: bool) -> dict[str, Any]:
    """Serialize one ``loaded_exam_meta`` entry to a ``gui_state.exams[]`` item."""
    return {
        "label": opaque_exam_label(index),
        "d_lon": meta.get("d_lon", 0.0),
        "d_ver": meta.get("d_ver", 0.0),
        "d_lat": meta.get("d_lat", 0.0),
        "table_origin_override": meta.get("table_origin_override"),
        "table_origin_detected": meta.get("table_origin_detected"),
        "swap_lat_lon": bool(meta.get("swap_lat_lon", False)),
        "flip_ap1": bool(meta.get("flip_ap1", False)),
        "flip_ap2": bool(meta.get("flip_ap2", False)),
        "flip_tx": bool(meta.get("flip_tx", False)),
        "flip_ty": bool(meta.get("flip_ty", False)),
        "flip_tz": bool(meta.get("flip_tz", False)),
        "source_type": meta.get("source_type"),
        "schema": meta.get("schema"),
        "sheet": _sheet_value(meta.get("sheet"), include_identifiers),
        "normalization_method": meta.get("normalization_method"),
        "study_id": _gate(meta.get("study_id"), include_identifiers),
        "file_name": _gate(meta.get("file_name"), include_identifiers),
        "file_path": _basename_or_none(meta.get("file_path"), include_identifiers),
        "input_manufacturer": _gate(meta.get("input_manufacturer"), include_identifiers),
        "input_model": _gate(meta.get("input_model"), include_identifiers),
    }


def _serialize_settings(
    settings: PyskindoseSettings,
    app_state: AppState,
    include_identifiers: bool,
) -> dict[str, Any]:
    """Build the ``settings`` slice per the assembly rule.

    `PyskindoseSettings.to_settings_dict()` plus the AppState-override
    overlay (today only ``plot.plot_dosemap``). ``rdsr_filename`` has no GUI
    source and always exports ``null``. ``corrections_db_path`` and the
    kerma ``file``/``file_sheet``/``explicit_label`` ride the identifiers
    gate (paths basename-only; integer sheets exempt).
    """
    serialized = settings.to_settings_dict()
    serialized["plot"]["plot_dosemap"] = bool(app_state.plot_dosemap)
    serialized["rdsr_filename"] = None
    if not include_identifiers:
        serialized["corrections_db_path"] = None
    kerma = serialized["kerma_meter_correction"]
    kerma["file"] = _basename_or_none(kerma.get("file"), include_identifiers)
    kerma["file_sheet"] = _sheet_value(kerma.get("file_sheet"), include_identifiers)
    kerma["explicit_label"] = _gate(kerma.get("explicit_label"), include_identifiers)
    return serialized


def serialize_run_state(
    settings: PyskindoseSettings,
    app_state: AppState,
    *,
    normalization_profiles: list[dict[str, Any]] | None = None,
    include_identifiers: bool = False,
    app_version: str | None = None,
    created: str | None = None,
    passthrough: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Assemble the run-state document from settings plus GUI state.

    Parameters
    ----------
    settings : PyskindoseSettings
        Constructed settings (Phase 3 passes ``build_settings(...)`` output).
    app_state : AppState
        Live GUI state (duck-typed; only documented attributes are read —
        ``base_data`` DataFrames and other runtime objects are never touched).
    normalization_profiles : list[dict] | None
        Effective normalization profiles (Phase 3 passes the AppState home or
        the default list); ``None`` emits an empty list.
    include_identifiers : bool
        Include source identifiers (explicit user opt-in); default redacts.
    app_version : str | None
        Override for the emitting application version (defaults to the
        installed package version).
    created : str | None
        Override for the creation timestamp (defaults to current UTC;
        injectable for deterministic tests).
    passthrough : dict[str, Any] | None
        Unknown top-level keys preserved from a previously imported document
        (see `ApplyResult.passthrough`); merged without overwriting canonical
        keys.

    Returns
    -------
    dict
        JSON-serializable ``guiskindose.run_state`` v1 document.
    """
    if app_version is None:
        import guiskindose

        app_version = guiskindose.__version__
    if created is None:
        created = datetime.now(UTC).isoformat()
    document: dict[str, Any] = {
        "schema": RUN_STATE_SCHEMA,
        "schema_version": RUN_STATE_SCHEMA_VERSION,
        "app_version": app_version,
        "created": created,
        "settings": _serialize_settings(settings, app_state, include_identifiers),
        "normalization_settings": list(normalization_profiles or []),
        "gui_state": {
            "input_schema": app_state.input_schema,
            "input_source_type": app_state.input_source_type,
            "input_sheet_name": _sheet_value(app_state.input_sheet_name, include_identifiers),
            "swap_lat_lon": bool(app_state.swap_lat_lon),
            "flip_ap1": bool(app_state.flip_ap1),
            "flip_ap2": bool(app_state.flip_ap2),
            "kerma_meter_in_memory_table": _nest_in_memory_table(app_state.kerma_meter_in_memory_table),
            "exams": [
                _serialize_exam(meta, index, include_identifiers)
                for index, meta in enumerate(app_state.loaded_exam_meta)
            ],
        },
    }
    if passthrough:
        for key, value in passthrough.items():
            document.setdefault(key, value)
    return document


class RunStateError(ValueError):
    """Raised when a run-state document cannot be applied."""


@dataclass
class ApplyResult:
    """Outcome of `apply_run_state` for the caller (Phase 3 surfaces these)."""

    mode: str = "calculate_dose"
    warnings: list[str] = field(default_factory=list)
    applied_exams: int = 0
    schema_or_sheet_changed: bool = False
    passthrough: dict[str, Any] = field(default_factory=dict)


def validate_run_state_document(document: Any) -> None:
    """Check envelope schema/version, raising `RunStateError` when invalid.

    Greater-than-supported `schema_version` is rejected loudly; equal is
    accepted; older is accepted with a warning collected by the caller via
    `apply_run_state` (validation itself stays warning-free so the GUI can
    decide surfacing). Non-integer versions are rejected.
    """
    if not isinstance(document, dict):
        raise RunStateError(f"run-state document must be a mapping, got {type(document).__name__}")
    if document.get("schema") != RUN_STATE_SCHEMA:
        raise RunStateError(f"unsupported run-state schema {document.get('schema')!r}")
    version = document.get("schema_version")
    if isinstance(version, bool) or not isinstance(version, int):
        raise RunStateError(f"schema_version must be an integer, got {version!r}")
    if version > RUN_STATE_SCHEMA_VERSION:
        raise RunStateError(f"unsupported schema_version {version} (this build supports {RUN_STATE_SCHEMA_VERSION})")


def _display_basename(value: Any) -> str | None:
    """Best-effort basename of a live path value for mismatch comparison."""
    if value is None:
        return None
    text = str(value)
    if not text:
        return None
    return text.replace("\\", "/").split("/")[-1] or None


def _apply_present(target: Any, attr: str, value: Any) -> bool:
    """Write ``value`` to ``target.attr`` unless it is ``None`` (skip-if-null)."""
    if value is None:
        return False
    setattr(target, attr, value)
    return True


def _apply_sheet(target: dict | Any, key: str, value: Any) -> bool:
    """Apply a sheet selection: integers and non-null strings; else skip.

    Returns True when the value changed the target (for re-parse detection).
    """
    if value is None or isinstance(value, bool):
        return False
    if isinstance(target, dict):
        changed = target.get(key) != value
        target[key] = value
        return changed
    changed = getattr(target, key, None) != value
    setattr(target, key, value)
    return changed


def _unnest_in_memory_table(nested: Any) -> dict[tuple[str, str], float] | None:
    """Restore the session CF override table from nested JSON form."""
    if nested is None:
        return None
    if not isinstance(nested, dict):
        raise RunStateError(f"kerma_meter_in_memory_table must be a mapping, got {type(nested).__name__}")
    try:
        return {(equipment, tube): factor for equipment, tubes in nested.items() for tube, factor in tubes.items()}
    except (AttributeError, TypeError, ValueError) as exc:
        raise RunStateError(f"malformed kerma_meter_in_memory_table: {exc}") from exc


def _warn_file_mismatch(warnings: list[str], what: str, expected: str, live: str | None) -> None:
    """Record a loud mismatch warning; the live value is left untouched."""
    if live is None:
        warnings.append(f"{what} {expected!r} from the document is not loaded — re-select the file.")
    elif live != expected:
        warnings.append(f"{what} mismatch: document expects {expected!r}, session has {live!r}.")


def _apply_kerma_tier2(kerma: dict, app_state: AppState, warnings: list[str]) -> None:
    """Tier 2 for the kerma workbook: verify, never overwrite the live path."""
    expected = kerma.get("file")
    if expected is None:
        return
    _warn_file_mismatch(warnings, "kerma correction file", str(expected), _display_basename(app_state.kerma_meter_file))


def _apply_settings_slice(settings: dict, app_state: AppState, warnings: list[str]) -> str:
    """Apply Tier-3 configuration from the settings slice; return the mode."""
    for key in _SCALAR_SETTING_TO_STATE:
        _apply_present(app_state, key, settings.get(key))
    phantom = settings.get("phantom") or {}
    for doc_key, attr in _PHANTOM_SETTING_TO_STATE:
        _apply_present(app_state, attr, phantom.get(doc_key))
    offset = phantom.get("patient_offset") or {}
    for key in _EXAM_OFFSET_KEYS:
        _apply_present(app_state, key, offset.get(key))
    plot = settings.get("plot") or {}
    for doc_key, attr in _PLOT_SETTING_TO_STATE:
        _apply_present(app_state, attr, plot.get(doc_key))
    kerma = settings.get("kerma_meter_correction") or {}
    for doc_key, attr in _KERMA_SETTING_TO_STATE:
        _apply_present(app_state, attr, kerma.get(doc_key))
    _apply_present(app_state, "kerma_meter_file_sheet", kerma.get("file_sheet"))
    _apply_present(app_state, "kerma_meter_explicit_label", kerma.get("explicit_label"))
    _apply_kerma_tier2(kerma, app_state, warnings)
    _apply_present(app_state, "include_static_pose", settings.get("include_static_pose"))
    _apply_present(app_state, "angular_step_deg", settings.get("angular_step_deg"))
    _apply_present(app_state, "dosetrack_plane_code_map", settings.get("dosetrack_plane_code_map"))
    _apply_present(app_state, "corrections_db_path", settings.get("corrections_db_path"))
    _apply_present(app_state, "phantom_dimensions", phantom.get("dimension"))
    _apply_present(app_state, "max_events_for_patient_inclusion", plot.get("max_events_for_patient_inclusion"))
    return settings.get("mode", "calculate_dose")


def _verify_exam_pairing(exam: dict, meta: dict, index: int, warnings: list[str]) -> None:
    """Tier 1: derived data facts verify pairing; they are never written."""
    for key in ("study_id", "file_name", "input_manufacturer", "input_model"):
        expected, live = exam.get(key), meta.get(key)
        if expected is not None and live is not None and str(expected) != str(live):
            warnings.append(f"Exam {index + 1}: document {key} {expected!r} differs from loaded {live!r}.")
    expected_path, live_path = exam.get("file_path"), meta.get("file_path")
    if expected_path is not None and live_path is not None:
        _warn_file_mismatch(warnings, f"Exam {index + 1} input file", str(expected_path), _display_basename(live_path))
    elif expected_path is not None and live_path is None:
        _warn_file_mismatch(warnings, f"Exam {index + 1} input file", str(expected_path), None)


def _apply_exam(exam: dict, meta: dict, index: int, warnings: list[str]) -> bool:
    """Apply one document exam positionally to live meta; return sheet-changed."""
    _verify_exam_pairing(exam, meta, index, warnings)
    for key in _EXAM_OFFSET_KEYS:
        if exam.get(key) is not None:
            meta[key] = exam[key]
    if "table_origin_override" in exam:
        # Overrides are geometry, not identifiers: None clears a live override.
        meta["table_origin_override"] = exam["table_origin_override"]
    # table_origin_detected is intentionally not restored: it is recomputed at
    # load (see the plan's open questions); the import prerequisite (same
    # inputs loaded) keeps live and document values consistent.
    for key in _EXAM_TOGGLE_KEYS:
        if exam.get(key) is not None:
            meta[key] = exam[key]
    changed = _apply_sheet(meta, "sheet", exam.get("sheet"))
    if exam.get("schema") is not None and meta.get("schema") != exam["schema"]:
        changed = True
    return changed


def _sync_single_exam_couplings(app_state: AppState) -> None:
    """Mirror global toggles/offsets into meta[0] for single-exam sessions.

    Same direction as `offset_handlers.sync_global_patient_offset_to_single_exam_meta`
    (offsets) and the `import_preview` toggle behavior: single-exam
    calculation consumes the globals, so globals win on conflict. Inlined
    here because `offset_handlers` imports NiceGUI-bound `page_context` and
    this module stays GUI-light.
    """
    if len(app_state.loaded_exam_meta) != 1:
        return
    meta = app_state.loaded_exam_meta[0]
    meta["swap_lat_lon"] = bool(app_state.swap_lat_lon)
    meta["flip_ap1"] = bool(app_state.flip_ap1)
    meta["flip_ap2"] = bool(app_state.flip_ap2)
    meta["d_lon"] = app_state.d_lon
    meta["d_ver"] = app_state.d_ver
    meta["d_lat"] = app_state.d_lat


def apply_run_state(document: dict, app_state: AppState) -> ApplyResult:
    """Apply a run-state document to GUI state, returning warnings for the UI.

    Implements the three-tier import rule: derived data facts verify pairing
    only; picker-owned file handles are never downgraded (divergence warns
    loudly); every other non-null configuration value applies skip-if-null.
    Exam count mismatch raises `RunStateError` naming the counts. Unknown
    top-level keys are collected into `result.passthrough` for re-export.
    Tabular re-parse sequencing, `reset_results()` + UI refresh, and
    normalization-profile application to `PyskindoseSettings` are Phase-3
    caller responsibilities (this function is GUI-light and synchronous).
    """
    validate_run_state_document(document)
    result = ApplyResult()
    version = document.get("schema_version")
    if version != RUN_STATE_SCHEMA_VERSION:
        result.warnings.append(
            f"older schema_version {version} (supported {RUN_STATE_SCHEMA_VERSION}); proceeding best-effort."
        )
    result.passthrough = {key: value for key, value in document.items() if key not in _TOP_LEVEL_PASSTHROUGH_EXCLUDE}
    # Structural checks before any mutation: a count or shape mismatch must
    # fail with the session untouched, never half-applied.
    doc_exams = (document.get("gui_state") or {}).get("exams") or []
    live_metas = app_state.loaded_exam_meta
    if len(doc_exams) != len(live_metas):
        raise RunStateError(
            f"exam count mismatch: document has {len(doc_exams)} exam(s), "
            f"session has {len(live_metas)} loaded — load the same inputs in the same order/count."
        )
    profiles = document.get("normalization_settings")
    if profiles is not None and not isinstance(profiles, list):
        raise RunStateError(f"normalization_settings must be a list, got {type(profiles).__name__}")
    result.mode = _apply_settings_slice(document.get("settings") or {}, app_state, result.warnings)
    profiles = document.get("normalization_settings")
    if profiles is not None:
        from guiskindose.settings.normalization_settings import NormalizationSettings

        NormalizationSettings(profiles)  # validate shape now; Phase 3 applies to settings
        _apply_present(app_state, "normalization_profiles", profiles)
    gui = document.get("gui_state") or {}
    if gui.get("input_schema") is not None and gui["input_schema"] != app_state.input_schema:
        result.schema_or_sheet_changed = True
    _apply_present(app_state, "input_schema", gui.get("input_schema"))
    if _apply_sheet(app_state, "input_sheet_name", gui.get("input_sheet_name")):
        result.schema_or_sheet_changed = True
    for key in ("swap_lat_lon", "flip_ap1", "flip_ap2"):
        _apply_present(app_state, key, gui.get(key))
    if "kerma_meter_in_memory_table" in gui:
        app_state.kerma_meter_in_memory_table = _unnest_in_memory_table(gui["kerma_meter_in_memory_table"])
    for index, (exam, meta) in enumerate(zip(doc_exams, live_metas, strict=True)):
        if _apply_exam(exam, meta, index, result.warnings):
            result.schema_or_sheet_changed = True
    result.applied_exams = len(doc_exams)
    _sync_single_exam_couplings(app_state)
    return result
