"""Input hardening for parsed RDSR frames before normalization.

Real-world RDSRs (for example the OpenREM upstream test corpus) vary in ways
the normalizer cannot absorb: a concept reported twice per event, a dose in
``mGy`` instead of ``Gy``, or source-geometry concepts left out entirely. This
module runs before :func:`guiskindose.rdsr_normalizer.rdsr_normalizer` reads any
column, on the normalizer's private copy of the parsed frame (helpers that return
``None`` modify the frame they are given), and either repairs the frame (equal duplicates, scale-only units, the
Final-DSD fallback) or raises one clear :class:`RdsrInputError`.

Privacy: every message is built from the fixed label tables below and integer
counts. No file-derived string (unit text, manufacturer, value) is interpolated.
See ``dev-docs/plans/RDSR_INPUT_HARDENING_PLAN.md``.
"""

from __future__ import annotations

import logging
import math
from typing import Any

import pandas as pd

from guiskindose import constants as c
from guiskindose.privacy import UserFacingInputError

logger = logging.getLogger(__name__)


class RdsrInputError(UserFacingInputError):
    """Raised when a parsed RDSR cannot be normalized; the message is value-free."""


class RdsrUnitError(UserFacingInputError):
    """Raised when an RDSR reports a quantity in a unit this pipeline does not convert.

    ``rdsr_parser`` encodes each measured value's DICOM unit into the column name
    (e.g. ``DoseRP_Gy``). When a report uses a unit that is neither canonical nor a
    known scale-only variant, the expected column is absent and a sibling
    ``{concept}_{other-unit}`` column is present; the normalizer would otherwise
    fail with an opaque AttributeError. See dev-docs/INPUT_SCHEMA_DETECTION.md
    ("Unit handling").
    """


_DSD = "DistanceSourcetoDetector"
_FINAL_DSD = "FinalDistanceSourcetoDetector"

# Concept prefix (as produced by rdsr_parser) → (canonical unit, plain-language label).
_LABELS: dict[str, tuple[str, str]] = {
    "DoseRP": ("Gy", "reference point dose"),
    "KVP": ("kV", "tube voltage (kVp)"),
    _DSD: ("mm", "source-to-detector distance"),
    _FINAL_DSD: ("mm", "final source-to-detector distance"),
    "DistanceSourcetoIsocenter": ("mm", "source-to-isocenter distance"),
    "TableLongitudinalPosition": ("mm", "table longitudinal position"),
    "TableLateralPosition": ("mm", "table lateral position"),
    "TableHeightPosition": ("mm", "table height position"),
    "PositionerPrimaryAngle": ("deg", "positioner primary angle"),
    "PositionerSecondaryAngle": ("deg", "positioner secondary angle"),
    "PositionerPrimaryEndAngle": ("deg", "positioner primary end angle"),
    "PositionerSecondaryEndAngle": ("deg", "positioner secondary end angle"),
    "CollimatedFieldArea": ("m2", "collimated field area"),
    "LeftShutter": ("mm", "left shutter position"),
    "RightShutter": ("mm", "right shutter position"),
    "TopShutter": ("mm", "top shutter position"),
    "BottomShutter": ("mm", "bottom shutter position"),
    "XRayFilterThicknessMinimum": ("mm", "minimum filter thickness"),
    "XRayFilterThicknessMaximum": ("mm", "maximum filter thickness"),
}

# Scale-only unit variants: canonical unit → {variant unit: factor to canonical}.
# Linear factors only; area units are deliberately absent.
_SCALE_VARIANTS: dict[str, dict[str, float]] = {
    "Gy": {"mGy": 1e-3},
    "mm": {"cm": 10.0, "m": 1000.0},
}

# Filter thicknesses are lists aligned with the filter-material list (one entry per
# material). Collapsing them would break that alignment, so they are never collapsed.
_LIST_VALUED = {"XRayFilterThicknessMinimum", "XRayFilterThicknessMaximum"}
_SCALAR_COLUMNS = [
    f"{concept}_{unit}" for concept, (unit, _label) in _LABELS.items() if concept not in _LIST_VALUED
]

# Concepts whose value must be populated in every event (DSD is checked after the
# per-event Final-DSD fallback).
_ALWAYS_REQUIRED = [
    "DistanceSourcetoIsocenter",
    _DSD,
    "TableLongitudinalPosition",
    "TableLateralPosition",
    "TableHeightPosition",
    "PositionerPrimaryAngle",
    "PositionerSecondaryAngle",
    "KVP",
    "DoseRP",
]
_FIELD_SIZE_REQUIRED = {
    c.FIELD_SIZE_MODE_COLLIMATED_FIELD_AREA: ["CollimatedFieldArea"],
    c.FIELD_SIZE_MODE_ACTUAL_SHUTTER_DISTANCE: ["LeftShutter", "RightShutter", "TopShutter", "BottomShutter"],
}

# Columns the normalizer indexes directly; blank values are handled downstream.
_PRESENCE_ONLY = [
    "IrradiationEventType",
    "AcquisitionPlane",
    c.KEY_RDSR_FILTER_MATERIAL,
    c.KEY_RDSR_FILTER_MIN,
    c.KEY_RDSR_FILTER_MAX,
]
_PRESENCE_LABELS = {
    "IrradiationEventType": "irradiation event type",
    "AcquisitionPlane": "acquisition plane",
    c.KEY_RDSR_FILTER_MATERIAL: "filter material",
    c.KEY_RDSR_FILTER_MIN: "minimum filter thickness",
    c.KEY_RDSR_FILTER_MAX: "maximum filter thickness",
}

_REL_TOL = 1e-9


def _is_blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, (list, tuple)):
        return all(_is_blank(v) for v in value)
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _flatten(value: Any) -> list[Any]:
    if isinstance(value, (list, tuple)):
        return [leaf for item in value for leaf in _flatten(item)]
    return [value]


def _scale(value: Any, factor: float) -> Any:
    """Scale a scalar or (nested) list of numeric values, preserving list shape."""
    if isinstance(value, (list, tuple)):
        return type(value)(_scale(v, factor) for v in value)
    if _is_blank(value):
        return value
    return float(value) * factor


def _same(a: Any, b: Any) -> bool:
    flat_a, flat_b = _flatten(a), _flatten(b)
    if len(flat_a) != len(flat_b):
        return False
    for x, y in zip(flat_a, flat_b, strict=True):
        if _is_blank(x) and _is_blank(y):
            continue
        if _is_blank(x) or _is_blank(y):
            return False
        if not math.isclose(float(x), float(y), rel_tol=_REL_TOL, abs_tol=0.0):
            return False
    return True


def _all_agree(a: Any, b: Any) -> bool:
    """Whether every populated leaf of a scalar concept's two cells is the same value."""
    leaves = [v for v in _flatten(a) + _flatten(b) if not _is_blank(v)]
    return all(_same(leaves[0], v) for v in leaves[1:])


def _merge_variant(frame: pd.DataFrame, canonical: str, variant: str, factor: float, label: str) -> None:
    """Fold a scale-only variant column into its canonical column, per event.

    Scalar concepts agree when every populated copy is equal, so a canonical
    duplicate ``[0.3, 0.3]`` agrees with a variant ``300 mGy`` (the duplicate is
    collapsed afterwards). List-valued filter thicknesses must match entry by entry.
    """
    agree = _same if canonical.rsplit("_", 1)[0] in _LIST_VALUED else _all_agree
    scaled = frame[variant].map(lambda v: _scale(v, factor))
    if canonical not in frame.columns:
        frame[canonical] = scaled
    else:
        merged = frame[canonical].astype(object).copy()
        conflicts = 0
        for idx, extra in scaled.items():
            current = merged.at[idx]
            if _is_blank(extra):
                continue
            if _is_blank(current):
                merged.at[idx] = extra
            elif not agree(current, extra):
                conflicts += 1
        if conflicts:
            raise RdsrInputError(
                f"This RDSR reports the {label} twice in different units, and the two values disagree "
                f"in {conflicts} event(s). GUISkinDose cannot tell which value is correct."
            )
        frame[canonical] = merged
    del frame[variant]
    logger.info("Converted %s to its canonical unit (scale-only conversion).", label)


def convert_scale_only_units(frame: pd.DataFrame) -> None:
    """Convert known scale-only unit variants (mGy, cm, m) into canonical columns in place."""
    for concept, (unit, label) in _LABELS.items():
        for variant_unit, factor in _SCALE_VARIANTS.get(unit, {}).items():
            variant = f"{concept}_{variant_unit}"
            if variant in frame.columns:
                _merge_variant(frame, f"{concept}_{unit}", variant, factor, label)


def verify_expected_units(frame: pd.DataFrame) -> None:
    """Raise :class:`RdsrUnitError` if a quantity is reported only in an unconvertible unit.

    For each concept whose canonical ``{concept}_{unit}`` column is absent, check
    whether a sibling ``{concept}_*`` column (same quantity, other unit) exists. A
    concept that is wholly absent is left to :func:`verify_required_concepts`.
    """
    columns = list(frame.columns)
    for concept, (unit, label) in _LABELS.items():
        if f"{concept}_{unit}" in columns:
            continue
        prefix = f"{concept}_"
        # A longer concept sharing the prefix (e.g. PositionerPrimaryEndAngle vs
        # PositionerPrimaryAngle) does not, since "_" ends the concept name.
        if any(col.startswith(prefix) for col in columns):
            raise RdsrUnitError(
                f"This RDSR reports the {label} in a unit GUISkinDose does not convert "
                f"(expected '{unit}'). Verify the acquisition device's dose-report configuration."
            )


def collapse_duplicate_scalars(frame: pd.DataFrame) -> None:
    """Collapse per-event duplicates of scalar concepts when every copy is equal, in place.

    The parser stores a concept seen twice in one event as a list or tuple. For
    scalar concepts, equal copies collapse to one float; copies that disagree raise
    :class:`RdsrInputError`. Filter thickness lists are never touched.
    """
    for column in _SCALAR_COLUMNS:
        if column not in frame.columns:
            continue
        values = frame[column]
        is_multi = values.map(lambda v: isinstance(v, (list, tuple)))
        if not is_multi.any():
            continue
        conflicts = 0
        collapsed = values.astype(object).copy()
        for idx in values.index[is_multi]:
            leaves = [v for v in _flatten(values.at[idx]) if not _is_blank(v)]
            if not leaves:
                collapsed.at[idx] = None
            elif all(_same(leaves[0], v) for v in leaves[1:]):
                collapsed.at[idx] = float(leaves[0])
            else:
                conflicts += 1
        concept = column.rsplit("_", 1)[0]
        label = _LABELS[concept][1]
        if conflicts:
            raise RdsrInputError(
                f"This RDSR reports more than one differing {label} in {conflicts} event(s). "
                "GUISkinDose cannot tell which value is correct."
            )
        frame[column] = collapsed


def resolve_source_detector_distance(frame: pd.DataFrame) -> None:
    """Fill blank source-to-detector distances from the final DSD, per event, in place."""
    dsd, final = f"{_DSD}_mm", f"{_FINAL_DSD}_mm"
    if final not in frame.columns:
        return
    if dsd not in frame.columns:
        frame[dsd] = frame[final]
        return
    blank = frame[dsd].map(_is_blank)
    if blank.any():
        frame[dsd] = frame[dsd].astype(object).where(~blank, frame[final])


def ensure_irradiation_events(frame: pd.DataFrame) -> None:
    """Raise :class:`RdsrInputError` when the parsed report has no irradiation events."""
    if frame.empty:
        raise RdsrInputError(
            "This file contains no X-ray irradiation events, so there is nothing to calculate. "
            "It may be a different kind of dose report."
        )


def ensure_device_columns(frame: pd.DataFrame) -> None:
    """Add blank manufacturer/model columns when absent, so the default profile applies."""
    for column in (c.KEY_RDSR_MANUFACTURER, c.KEY_RDSR_MANUFACTURER_MODEL_NAME):
        if column not in frame.columns:
            frame[column] = None


def _required_columns(field_size_mode: str | None) -> list[tuple[str, str]]:
    """Return (column, label) for every concept that must be populated per event."""
    concepts = _ALWAYS_REQUIRED + _FIELD_SIZE_REQUIRED.get(field_size_mode or "", [])
    return [(f"{concept}_{_LABELS[concept][0]}", _LABELS[concept][1]) for concept in concepts]


def _blank_mask(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(True, index=frame.index)
    return frame[column].map(_is_blank).astype(bool)


def _zero_dose_mask(frame: pd.DataFrame) -> pd.Series:
    dose_column = f"DoseRP_{_LABELS['DoseRP'][0]}"
    if dose_column not in frame.columns:
        return pd.Series(False, index=frame.index)
    return pd.to_numeric(frame[dose_column], errors="coerce").eq(0)


def enforce_required_concepts(frame: pd.DataFrame, field_size_mode: str | None) -> pd.DataFrame:
    """Check every required concept; return the frame without dose-free incomplete events, or raise.

    A concept counts as missing in an event when its column is absent or its
    value is blank. Presence-only columns must exist but may be blank.

    Events with exactly zero reference-point dose contribute no skin dose whatever
    their geometry. When they are the *only* incomplete events, they are dropped
    (logged as a count) instead of rejecting the whole report. Otherwise one
    :class:`RdsrInputError` lists every missing concept with counts over all
    events. The returned frame keeps the input's index labels, so callers can map
    each kept event back to its source row.
    """
    n_events = len(frame)
    zero_dose = _zero_dose_mask(frame)
    problems: list[str] = []
    incomplete = pd.Series(False, index=frame.index)
    dosed_gap = False
    for column, label in _required_columns(field_size_mode):
        blank = _blank_mask(frame, column)
        incomplete |= blank
        dosed_gap |= bool((blank & ~zero_dose).any())
        if blank.any():
            problems.append(f"{label} (missing in {int(blank.sum())} of {n_events} events)")
    for column in _PRESENCE_ONLY:
        if column not in frame.columns:
            problems.append(f"{_PRESENCE_LABELS[column]} (not reported)")
            dosed_gap = True
    if not problems:
        return frame
    if not dosed_gap and not incomplete.all():
        logger.warning(
            "Dropped %d zero-dose event(s) with incomplete geometry; they contribute no dose.", int(incomplete.sum())
        )
        return frame.loc[~incomplete]
    raise RdsrInputError(
        "This RDSR lacks data GUISkinDose needs to place the beam and patient: "
        + "; ".join(problems)
        + ". GUISkinDose does not guess missing geometry, because a guess would change the dose estimate."
    )
