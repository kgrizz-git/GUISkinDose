"""Run-state document assembly (settings export, Phase 2).

Builds the versioned ``guiskindose.run_state`` JSON document from a
constructed `PyskindoseSettings` plus GUI state. The applier lives in this
module too (added in chunk C); the GUI surface wiring is Phase 3.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from guiskindose.privacy import opaque_exam_label

if TYPE_CHECKING:  # duck-typed at runtime; keeps this module GUI-light
    from guiskindose.gui.state import AppState
    from guiskindose.settings.pyskindose_settings import PyskindoseSettings

RUN_STATE_SCHEMA = "guiskindose.run_state"
RUN_STATE_SCHEMA_VERSION = 1


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
    """
    if value is None:
        return None
    text = str(value)
    if not text:
        return None
    if not include_identifiers:
        return None
    return Path(text).name


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
    return {
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
