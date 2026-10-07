"""Run-state handling for per-exam kerma-meter state.

Per-exam manual factors (``(exam, equipment, tube)`` keys) and per-exam
calibration-period choices are session state keyed by the opaque exam label.
Equipment labels are site identifiers, so both are written only when identifiers
are included, and importing a redacted document leaves the live values untouched.
The legacy two-part ``(equipment, tube)`` entries stay in
``gui_state.kerma_meter_in_memory_table`` (see ``run_state``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # duck-typed at runtime, like run_state
    from .state import AppState

EXAM_FACTORS_KEY = "kerma_meter_exam_factors"
PERIODS_KEY = "kerma_meter_periods"


def nest_exam_factors(table: dict[tuple[str, ...], float] | None) -> dict[str, dict[str, dict[str, float]]]:
    """Nest per-exam entries as ``{exam: {equipment: {tube: factor}}}``."""
    nested: dict[str, dict[str, dict[str, float]]] = {}
    for key, factor in (table or {}).items():
        if len(key) == 3:
            exam, equipment, tube = key
            nested.setdefault(exam, {}).setdefault(equipment, {})[tube] = factor
    return nested


def serialize_exam_kerma(app_state: AppState, gui_section: dict[str, Any]) -> None:
    """Add per-exam factors and calibration periods to *gui_section* (identifier-gated callers only)."""
    gui_section[EXAM_FACTORS_KEY] = nest_exam_factors(app_state.kerma_meter_in_memory_table)
    gui_section[PERIODS_KEY] = dict(app_state.kerma_meter_periods)


def validate_exam_kerma(gui: dict[str, Any]) -> None:
    """Reject malformed per-exam factor or period values in a run-state ``gui_state``."""
    from .run_state import _malformed

    periods = gui.get(PERIODS_KEY)
    if periods is not None and (
        not isinstance(periods, dict)
        or any(not isinstance(k, str) or not isinstance(v, str) for k, v in periods.items())
    ):
        raise _malformed(f"{PERIODS_KEY} must be a mapping of strings")
    _validate_exam_factors(gui.get(EXAM_FACTORS_KEY), _malformed)


def _validate_exam_factors(nested: Any, _malformed: Any) -> None:
    """Reject a per-exam factor mapping that is not ``exam -> equipment -> tube -> number``."""
    if nested is None:
        return
    if not isinstance(nested, dict):
        raise _malformed(f"{EXAM_FACTORS_KEY} must be a mapping")
    for equipment_map in nested.values():
        if not isinstance(equipment_map, dict) or any(not isinstance(t, dict) for t in equipment_map.values()):
            raise _malformed(f"{EXAM_FACTORS_KEY} must be a mapping of mappings of mappings")
        for tubes in equipment_map.values():
            if any(isinstance(f, bool) or not isinstance(f, (int, float)) for f in tubes.values()):
                raise _malformed(f"{EXAM_FACTORS_KEY} factors must be numbers")


def apply_exam_kerma(gui: dict[str, Any], app_state: AppState) -> None:
    """Apply per-exam factors (replacing only the per-exam part of the table) and periods."""
    if PERIODS_KEY in gui:
        app_state.kerma_meter_periods = dict(gui[PERIODS_KEY] or {})
    if EXAM_FACTORS_KEY not in gui:
        return
    table = {k: v for k, v in (app_state.kerma_meter_in_memory_table or {}).items() if len(k) != 3}
    for exam, equipment_map in (gui[EXAM_FACTORS_KEY] or {}).items():
        for equipment, tubes in equipment_map.items():
            for tube, factor in tubes.items():
                table[(exam, equipment, tube)] = factor
    app_state.kerma_meter_in_memory_table = table or None


def apply_legacy_k_tab(settings: dict[str, Any], app_state: AppState) -> None:
    """Map a legacy ``estimate_k_tab`` boolean onto ``k_tab_mode`` when the document has no mode.

    ``True`` maps to ``estimate`` and ``False`` to ``measured_only``. An explicit
    ``k_tab_mode`` in the document always wins (it is applied by the scalar loop).
    """
    if settings.get("k_tab_mode") is None and isinstance(settings.get("estimate_k_tab"), bool):
        app_state.k_tab_mode = "estimate" if settings["estimate_k_tab"] else "measured_only"
