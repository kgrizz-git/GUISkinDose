"""Shared rotational-acquisition classifier (non-GUI).

Estimate-grade detection for rotational / moving positioner events. Pure
function over normalized event fields so calculation, GUI, CLI, and export
share one semantic — export metrics must consume this, never substring-match.
See ``dev-docs/plans/ROTATIONAL_COVERAGE_ENVELOPE_PLAN.md``.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

MOTION_THRESHOLD_DEG = 2.0

CODE_ROTATIONAL = "113613"
CODE_STEPPING = "113612"
CODE_STATIONARY = "113611"

MEANING_ROTATIONAL = "rotational acquisition"
MEANING_STEPPING = "stepping acquisition"
MEANING_STATIONARY = "stationary acquisition"

TEXT_ALIASES = ("dynact", "spin", "roll")
_TOKEN_RE = re.compile(r"[a-z0-9]+")

# Normalized-frame numeric prerequisites for a usable baseline geometry.
# Only keys actually present in the input are checked: absence is not
# evidence of unusability (the classifier also serves minimal/partial rows;
# the envelope builder re-validates evaluability before computing), but a
# present-but-nonfinite value fails the baseline.
BASELINE_NUMERIC_FIELDS = (
    "Tx",
    "Ty",
    "Tz",
    "Ap1",
    "Ap2",
    "Ap3",
    "At1",
    "At2",
    "At3",
    "kVp",
    "K_IRP",
    "DSD",
    "DSI",
    "FS_lat",
    "FS_long",
    "DSL",
)

_BLANK_TOKENS = frozenset({"", "none", "nan", "nat", "<na>", "n/a", "na"})


def _normalize_meaning(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    try:
        text = str(value).strip().lower()
    except Exception:
        return ""
    if text in _BLANK_TOKENS:
        return ""
    return text


def _normalize_code(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    try:
        text = str(value).strip()
    except Exception:
        return ""
    if text.lower() in _BLANK_TOKENS:
        return ""
    # Accept 113613.0-style floats from tabular sources.
    try:
        as_float = float(text)
        if as_float.is_integer():
            return str(int(as_float))
    except (TypeError, ValueError):
        pass
    return text


def _finite_deg(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def circular_separation_deg(start: float, end: float) -> float:
    """Smallest angular distance on the circle, in [0, 180]."""
    return abs((end - start + 180.0) % 360.0 - 180.0)


def _text_alias_present(*texts: object) -> bool:
    tokens: set[str] = set()
    for text in texts:
        if text is None:
            continue
        try:
            lowered = str(text).lower()
        except Exception:
            continue
        tokens.update(_TOKEN_RE.findall(lowered))
    return any(alias in tokens for alias in TEXT_ALIASES)


@dataclass(frozen=True)
class RotationalClassification:
    classification: str  # rotational | positioner_motion | static | unknown
    reason_codes: tuple[str, ...] = ()
    confidence: str = "none"  # coded | meaning | text_alias | angle_motion | none
    usable_endpoints: bool = False
    usable_baseline_geometry: bool = False
    primary_separation_deg: float | None = None
    secondary_separation_deg: float | None = None


@dataclass
class RotationalEventInput:
    acquisition_type: object = None
    acquisition_type_code: object = None
    acquisition_type_coding_scheme: object = None
    acquisition_type_meaning: object = None
    protocol_text: object = None
    ap1: object = None
    ap2: object = None
    ap1_end: object = None
    ap2_end: object = None
    extra: dict = field(default_factory=dict)


def _coalesce_meaning(*values: object) -> str:
    """First non-blank normalized meaning, without truth-testing raw values.

    Raw values may be ``pd.NA`` (ambiguous truth value); normalize each to a
    string first and only then rely on emptiness.
    """
    for value in values:
        text = _normalize_meaning(value)
        if text:
            return text
    return ""


def _baseline_usable(data: RotationalEventInput, raw: dict | None) -> bool:
    """Whether all present baseline-geometry prerequisites are finite."""
    candidates: dict[str, object] = {}
    if raw is not None:
        candidates.update({str(key).lower(): value for key, value in raw.items()})
    if data.extra:
        candidates.update({str(key).lower(): value for key, value in data.extra.items()})
    for name in BASELINE_NUMERIC_FIELDS:
        key = name.lower()
        if key in candidates and _finite_deg(candidates[key]) is None:
            return False
    return True


def classify_rotational_event(event: RotationalEventInput | dict) -> RotationalClassification:
    """Classify one normalized event row for rotational handling.

    Coded identities only count with an explicit ``DCM`` coding scheme: a
    bare ``113613`` from a source that does not declare its scheme falls back
    to meaning matching, never to coded confidence.
    """
    raw: dict | None = event if isinstance(event, dict) else None
    if isinstance(event, dict):
        data = RotationalEventInput(
            acquisition_type=event.get("acquisition_type"),
            acquisition_type_code=event.get("acquisition_type_code"),
            acquisition_type_coding_scheme=event.get("acquisition_type_coding_scheme"),
            acquisition_type_meaning=event.get(
                "acquisition_type_meaning", event.get("acquisition_type")
            ),
            protocol_text=event.get("protocol_text", event.get("AcquisitionProtocol")),
            ap1=event.get("Ap1", event.get("ap1")),
            ap2=event.get("Ap2", event.get("ap2")),
            ap1_end=event.get("Ap1_end", event.get("ap1_end")),
            ap2_end=event.get("Ap2_end", event.get("ap2_end")),
            extra={
                key: value
                for key, value in event.items()
                if str(key).lower()
                not in {
                    "acquisition_type",
                    "acquisition_type_code",
                    "acquisition_type_coding_scheme",
                    "acquisition_type_meaning",
                    "protocol_text",
                    "acquisitionprotocol",
                    "ap1",
                    "ap2",
                    "ap1_end",
                    "ap2_end",
                }
            },
        )
    else:
        data = event

    meaning = _coalesce_meaning(data.acquisition_type_meaning, data.acquisition_type)
    code = _normalize_code(data.acquisition_type_code)
    scheme = _normalize_meaning(data.acquisition_type_coding_scheme)
    code_effective = code if (code and scheme == "dcm") else ""

    is_stepping = code_effective == CODE_STEPPING or (
        not code_effective and meaning == MEANING_STEPPING
    )
    is_rotational_type = code_effective == CODE_ROTATIONAL or (
        not code_effective and meaning == MEANING_ROTATIONAL
    )
    is_stationary = code_effective == CODE_STATIONARY or (
        not code_effective and meaning == MEANING_STATIONARY
    )
    has_alias = _text_alias_present(data.acquisition_type, data.acquisition_type_meaning, data.protocol_text)

    ap1 = _finite_deg(data.ap1)
    ap2 = _finite_deg(data.ap2)
    ap1_end = _finite_deg(data.ap1_end)
    ap2_end = _finite_deg(data.ap2_end)

    primary_sep = (
        circular_separation_deg(ap1, ap1_end) if ap1 is not None and ap1_end is not None else None
    )
    secondary_sep = (
        circular_separation_deg(ap2, ap2_end) if ap2 is not None and ap2_end is not None else None
    )
    primary_motion = primary_sep is not None and primary_sep >= MOTION_THRESHOLD_DEG
    secondary_motion = secondary_sep is not None and secondary_sep >= MOTION_THRESHOLD_DEG
    any_motion = primary_motion or secondary_motion

    endpoints_populated = (primary_sep is not None) or (secondary_sep is not None)
    equal_endpoints = endpoints_populated and not any_motion
    usable_baseline = (
        ap1 is not None and ap2 is not None and _baseline_usable(data, raw)
    )
    # Usable when at least one axis moves and any non-moving axis still has a
    # finite start to hold fixed.
    usable_endpoints = any_motion and usable_baseline

    reasons: list[str] = []
    if code_effective == CODE_ROTATIONAL:
        reasons.append("type_code_rotational")
    elif code_effective == CODE_STEPPING:
        reasons.append("type_code_stepping")
    elif code_effective == CODE_STATIONARY:
        reasons.append("type_code_stationary")
    elif not code_effective and meaning == MEANING_ROTATIONAL:
        reasons.append("type_meaning_rotational")
    elif not code_effective and meaning == MEANING_STEPPING:
        reasons.append("type_meaning_stepping")
    elif not code_effective and meaning == MEANING_STATIONARY:
        reasons.append("type_meaning_stationary")
    elif meaning:
        reasons.append("unrecognized_type")
    if has_alias:
        reasons.append("text_alias_rotational")
    if primary_motion:
        reasons.append("primary_endpoint_motion")
    if secondary_motion:
        reasons.append("secondary_endpoint_motion")
    if equal_endpoints:
        reasons.append("equal_endpoints")
    if not endpoints_populated and (is_rotational_type or has_alias or is_stepping):
        reasons.append("missing_or_invalid_endpoints")
    if not usable_baseline and (is_rotational_type or has_alias or any_motion or is_stepping):
        reasons.append("missing_baseline_geometry")

    # Deterministic precedence: stepping wins positioner_motion; stationary
    # plus motion is contradictory (neither wins silently); rotational
    # identity/alias/motion yields rotational; stationary or equal endpoints
    # yields static; the rest is unknown.
    if is_stepping:
        classification = "positioner_motion"
        confidence = "coded" if code_effective else "meaning"
    elif is_stationary and any_motion:
        classification = "unknown"
        confidence = "coded" if code_effective else "meaning"
        reasons.append("contradictory_static")
    elif is_rotational_type or has_alias or any_motion:
        classification = "rotational"
        if code_effective == CODE_ROTATIONAL:
            confidence = "coded"
        elif not code_effective and meaning == MEANING_ROTATIONAL:
            confidence = "meaning"
        elif has_alias:
            confidence = "text_alias"
        else:
            confidence = "angle_motion"
    elif is_stationary or equal_endpoints:
        classification = "static"
        if code_effective == CODE_STATIONARY:
            confidence = "coded"
        elif meaning == MEANING_STATIONARY:
            confidence = "meaning"
        else:
            # Static via equal endpoints with an unrecognized meaning (e.g.
            # plain fluoroscopy): the basis is measured stillness, not text.
            confidence = "none"
    else:
        classification = "unknown"
        confidence = "none"
        if not reasons:
            reasons.append("unrecognized_type" if meaning else "missing_or_invalid_endpoints")

    return RotationalClassification(
        classification=classification,
        reason_codes=tuple(reasons),
        confidence=confidence,
        usable_endpoints=usable_endpoints,
        usable_baseline_geometry=usable_baseline,
        primary_separation_deg=primary_sep,
        secondary_separation_deg=secondary_sep,
    )


__all__ = [
    "CODE_ROTATIONAL",
    "CODE_STATIONARY",
    "CODE_STEPPING",
    "MOTION_THRESHOLD_DEG",
    "RotationalClassification",
    "RotationalEventInput",
    "circular_separation_deg",
    "classify_rotational_event",
]
