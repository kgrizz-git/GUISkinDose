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

# Import-settable homes with no GUI widget: `normalization_profiles`,
# `dosetrack_plane_code_map`, `include_static_pose`, `angular_step_deg`,
# `corrections_db_path`, `phantom_dimensions` (full dimension dict),
# `max_events_for_patient_inclusion` (scalar). None = example-JSON default.
# (Kept as a comment, not a tuple: the homes are written explicitly in
# `_apply_settings_slice`, so a central list would be dead inventory.)

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
        keys, and only when `include_identifiers` is set — unknown keys may
        carry identifiers, so a redacted export must never copy them.

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
    if passthrough and include_identifiers:
        for key, value in passthrough.items():
            document.setdefault(key, value)
    return document


class RunStateError(ValueError):
    """Raised when a run-state document cannot be applied.

    Carries a stable machine-readable `code` so callers can map failures to
    fixed user-facing messages without exposing document text (privacy).
    Every raise site passes an explicit code; structural problems use
    "malformed_document" via `_malformed()`.
    """

    def __init__(self, message: str, code: str = "malformed_document") -> None:
        super().__init__(message)
        self.code = code


def _malformed(message: str) -> RunStateError:
    """Build a structural-validation error with its code stated explicitly."""
    return RunStateError(message, code="malformed_document")


@dataclass
class ApplyResult:
    """Outcome of `apply_run_state` for the caller (Phase 3 surfaces these)."""

    mode: str = "calculate_dose"
    warnings: list[str] = field(default_factory=list)
    applied_exams: int = 0
    schema_or_sheet_changed: bool = False
    passthrough: dict[str, Any] = field(default_factory=dict)


# Every AppState attribute `apply_run_state` may write (kerma_meter_file is
# Tier-2 and never written). `loaded_exam_meta` entries are mutated in place
# and snapshotted separately (deep).
_SNAPSHOT_ATTRS = (
    "estimate_k_tab",
    "k_tab_val",
    "inherent_filtration",
    "remove_invalid_rows",
    "below_floor_kvp_policy",
    "below_floor_kvp_manual",
    "beam_miss_warn",
    "rotational_handling",
    "phantom_model",
    "human_mesh",
    "phantom_scale_lat",
    "phantom_scale_ap",
    "phantom_scale_lon",
    "patient_orientation",
    "d_lon",
    "d_ver",
    "d_lat",
    "dark_mode",
    "colorscale",
    "plot_dosemap",
    "kerma_meter_enable",
    "kerma_meter_mode",
    "kerma_meter_file_sheet",
    "kerma_meter_explicit_label",
    "kerma_meter_default_factor",
    "kerma_meter_prompt_at_calc",
    "kerma_meter_in_memory_table",
    "include_static_pose",
    "angular_step_deg",
    "dosetrack_plane_code_map",
    "corrections_db_path",
    "phantom_dimensions",
    "max_events_for_patient_inclusion",
    "normalization_profiles",
    "run_state_passthrough",
    "input_schema",
    "input_source_type",
    "input_sheet_name",
    "swap_lat_lon",
    "flip_ap1",
    "flip_ap2",
)


def snapshot_app_state(app_state: AppState) -> dict[str, Any]:
    """Capture everything `apply_run_state` may mutate, for rollback.

    Homes and tables are deep-copied (the applier rebinds them, but a later
    caller could mutate through); scalars are immutable. `loaded_exam_meta`
    entries are mutated in place by the applier, so they are deep-copied too.
    `loaded_exams` / `rdsr_df` / `rdsr_raw_df` are snapshotted by reference:
    the applier never touches them, and the loader only ever rebinds (never
    mutates in place), so restoring the saved references is exact and free —
    no DataFrame is ever copied. All other runtime objects (figures,
    `import_provenance`, warnings) are loader-owned and intentionally
    excluded.
    """
    import copy

    snapshot = {attr: copy.deepcopy(getattr(app_state, attr)) for attr in _SNAPSHOT_ATTRS}
    snapshot["loaded_exam_meta"] = copy.deepcopy(app_state.loaded_exam_meta)
    snapshot["loaded_exams"] = list(app_state.loaded_exams)
    snapshot["rdsr_df"] = app_state.rdsr_df
    snapshot["rdsr_raw_df"] = app_state.rdsr_raw_df
    return snapshot


def restore_app_state_snapshot(app_state: AppState, snapshot: dict[str, Any]) -> None:
    """Restore a snapshot from `snapshot_app_state` (failed-import rollback)."""
    import copy

    for attr in _SNAPSHOT_ATTRS:
        setattr(app_state, attr, copy.deepcopy(snapshot[attr]))
    app_state.loaded_exam_meta = copy.deepcopy(snapshot["loaded_exam_meta"])
    app_state.loaded_exams = list(snapshot["loaded_exams"])
    app_state.rdsr_df = snapshot["rdsr_df"]
    app_state.rdsr_raw_df = snapshot["rdsr_raw_df"]


def _require_section(document: dict, key: str) -> dict:
    """Return ``document[key]`` (or ``{}`` when absent/null), rejecting mistypes."""
    value = document.get(key)
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise _malformed(f"{key} must be a mapping, got {type(value).__name__}")
    return value


def validate_run_state_document(document: Any) -> None:
    """Check envelope schema/version and section shapes, raising `RunStateError`.

    Greater-than-supported `schema_version` is rejected loudly; equal is
    accepted; older is accepted (the caller warns). Non-integer versions are
    rejected. Every structural check runs here — before `apply_run_state`
    mutates anything — so malformed inner types (`settings` as a list,
    `exams` holding strings, non-dict profiles, ragged kerma tables) fail
    with the session untouched instead of `AttributeError` mid-apply.
    """
    if not isinstance(document, dict):
        raise _malformed(f"run-state document must be a mapping, got {type(document).__name__}")
    if document.get("schema") != RUN_STATE_SCHEMA:
        raise RunStateError(f"unsupported run-state schema {document.get('schema')!r}", code="unsupported_schema")
    version = document.get("schema_version")
    if isinstance(version, bool) or not isinstance(version, int):
        raise RunStateError(f"schema_version must be an integer, got {version!r}", code="unsupported_schema_version")
    if version > RUN_STATE_SCHEMA_VERSION:
        raise RunStateError(
            f"unsupported schema_version {version} (this build supports {RUN_STATE_SCHEMA_VERSION})",
            code="unsupported_schema_version",
        )
    settings = _require_section(document, "settings")
    for key in ("phantom", "plot", "kerma_meter_correction"):
        if settings.get(key) is not None and not isinstance(settings[key], dict):
            raise _malformed(f"settings.{key} must be a mapping, got {type(settings[key]).__name__}")
    phantom = settings.get("phantom") or {}
    for key in ("patient_offset", "dimension"):
        if phantom.get(key) is not None and not isinstance(phantom[key], dict):
            raise _malformed(f"settings.phantom.{key} must be a mapping, got {type(phantom[key]).__name__}")
    gui = _require_section(document, "gui_state")
    exams = gui.get("exams")
    if exams is not None:
        if not isinstance(exams, list):
            raise _malformed(f"gui_state.exams must be a list, got {type(exams).__name__}")
        for index, exam in enumerate(exams):
            if not isinstance(exam, dict):
                raise _malformed(f"gui_state.exams[{index}] must be a mapping, got {type(exam).__name__}")
    profiles = document.get("normalization_settings")
    if profiles is not None:
        if not isinstance(profiles, list):
            raise _malformed(f"normalization_settings must be a list, got {type(profiles).__name__}")
        for index, profile in enumerate(profiles):
            if not isinstance(profile, dict):
                raise _malformed(f"normalization_settings[{index}] must be a mapping, got {type(profile).__name__}")
    table = gui.get("kerma_meter_in_memory_table")
    if table is not None:
        if not isinstance(table, dict) or any(not isinstance(tubes, dict) for tubes in table.values()):
            raise _malformed("kerma_meter_in_memory_table must be a mapping of mappings")
        for equipment, tubes in table.items():
            for tube, factor in tubes.items():
                if isinstance(factor, bool) or not isinstance(factor, (int, float)):
                    raise _malformed(f"kerma_meter_in_memory_table[{equipment!r}][{tube!r}] must be a number")


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
        raise _malformed(f"kerma_meter_in_memory_table must be a mapping, got {type(nested).__name__}")
    try:
        return {(equipment, tube): factor for equipment, tubes in nested.items() for tube, factor in tubes.items()}
    except (AttributeError, TypeError, ValueError) as exc:
        # Static message: {exc} may carry document-derived text; the chain
        # (`from exc`) preserves detail for debugging without surfacing it.
        raise _malformed("malformed kerma_meter_in_memory_table entries") from exc


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

    The single-exam test is `len(loaded_exam_meta) == 1`, which coincides with
    `not is_multi_exam` by the documented invariant that `loaded_exam_meta`
    is parallel to `loaded_exams` (multi-exam means >1 loaded).

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


def _trial_apply_settings(settings: dict, profiles: Any, app_state: AppState) -> None:
    """Validate the merged post-import state by building settings on a copy.

    Applies the settings slice to a shallow copy — scalar rebinding only, so
    the live session cannot be affected — then constructs the real settings
    object from it. Constructor failures (invalid plane-code map, out-of-range
    angular step, non-bool flags) become `RunStateError` here at import time
    instead of surfacing later at calculation with half-applied state behind
    them. The message keeps the underlying detail for logs/tests; the GUI
    surfaces only the fixed per-code message.
    """
    import copy

    from guiskindose.gui.settings_builder import build_settings

    trial = copy.copy(app_state)
    _apply_settings_slice(settings, trial, [])
    if profiles:
        trial.normalization_profiles = profiles
    try:
        build_settings(trial)
    except Exception as exc:
        raise RunStateError(f"imported settings failed validation: {exc}", code="invalid_settings") from exc


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
    # fail with the session untouched, never half-applied (shapes already
    # validated above; only counts remain).
    gui_section = _require_section(document, "gui_state")
    doc_exams = gui_section.get("exams") or []
    live_metas = app_state.loaded_exam_meta
    if len(doc_exams) != len(live_metas):
        raise RunStateError(
            f"exam count mismatch: document has {len(doc_exams)} exam(s), "
            f"session has {len(live_metas)} loaded — load the same inputs in the same order/count.",
            code="exam_count_mismatch",
        )
    _trial_apply_settings(_require_section(document, "settings"), document.get("normalization_settings"), app_state)
    app_state.run_state_passthrough = dict(result.passthrough)
    result.mode = _apply_settings_slice(_require_section(document, "settings"), app_state, result.warnings)
    profiles = document.get("normalization_settings")
    if profiles:
        _apply_present(app_state, "normalization_profiles", profiles)
    elif profiles is not None:
        # An empty list means "unspecified", never "wipe all profiles": a
        # zero-profile build would silently disable vendor normalization.
        result.warnings.append("empty normalization_settings ignored; keeping current profiles.")
    gui = gui_section
    if gui.get("input_schema") is not None and gui["input_schema"] != app_state.input_schema:
        result.schema_or_sheet_changed = True
    _apply_present(app_state, "input_schema", gui.get("input_schema"))
    if gui.get("input_source_type"):
        # Truthy (not just non-null): the loader owns this descriptor, and an
        # empty-string document value must not wipe a loaded session's type.
        app_state.input_source_type = gui["input_source_type"]
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
