"""Rotational coverage-envelope candidate generation (non-GUI).

Pure geometry: given measured endpoint angles, produce the declared candidate
pose domain over which the envelope takes its pointwise maximum. No dose
physics here — candidates are angle sets; evaluation lives in the dose loop.
See ``dev-docs/plans/ROTATIONAL_COVERAGE_ENVELOPE_PLAN.md``.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

from guiskindose.rotational_acquisition import RotationalClassification


@dataclass(frozen=True)
class CandidatePath:
    path_id: str  # e.g. "primary_short", "primary_long", "coupled_s_l"
    ap1_angles_deg: tuple[float, ...]
    ap2_angles_deg: tuple[float, ...]


@dataclass
class CandidateDomain:
    paths: tuple[CandidatePath, ...] = ()
    include_static_pose: bool = True
    unique_pose_count: int = 0
    unique_poses: tuple[tuple[float, float], ...] = ()


def _canonical(angle: float) -> float:
    return angle % 360.0


def _path_angles(start: float, delta: float, count: int) -> tuple[float, ...]:
    """Interpolate ``count`` poses from canonical start along signed delta.

    Endpoints are pinned exactly so float drift cannot move them.
    """
    if count <= 1:
        return (_canonical(start),)
    out = []
    for j in range(count):
        if j == 0:
            out.append(_canonical(start))
        elif j == count - 1:
            out.append(_canonical(start + delta))
        else:
            out.append(_canonical(start + (j / (count - 1)) * delta))
    return tuple(out)


def _raw_displacements(start_raw: float, end_raw: float) -> tuple[float, float]:
    """Positive/negative wrapped displacements (sign-preserving)."""
    delta_pos = (end_raw - start_raw) % 360.0
    return delta_pos, delta_pos - 360.0


def _signed_displacements(start_raw: float, end_raw: float) -> tuple[float, float]:
    """Short/long signed displacements preserving wraparound direction."""
    delta_pos, delta_neg = _raw_displacements(start_raw, end_raw)
    if abs(delta_pos) <= abs(delta_neg):
        return delta_pos, delta_neg
    return delta_neg, delta_pos


def _path_labels(delta_pos: float, delta_neg: float) -> tuple[tuple[str, float], tuple[str, float]]:
    """Label the two hypotheses; at 180 neither is shorter, so name the sign."""
    if abs(delta_pos) == 180.0:
        return (("positive_180", delta_pos), ("negative_180", delta_neg))
    short, long = (
        (delta_pos, delta_neg)
        if abs(delta_pos) <= abs(delta_neg)
        else (delta_neg, delta_pos)
    )
    return (("short", short), ("long", long))


def wrapped_paths(
    start_raw: float,
    end_raw: float,
    *,
    step_deg: float,
    axis: str,
    other_start_raw: float = 0.0,
) -> tuple[CandidatePath, ...]:
    """Both wrapped endpoint-consistent paths for one changing axis.

    Short and long hypotheses preserve direction ambiguity instead of
    resolving it. At exactly 180 degrees both signed directions are kept.
    Must only be called for an axis carrying an endpoint-motion reason.
    ``other_start_raw`` fixes the non-moving axis (it must NOT inherit the
    moving axis start).
    """
    start = _canonical(start_raw)
    other = _canonical(other_start_raw)
    delta_pos = (end_raw - start_raw) % 360.0
    delta_neg = delta_pos - 360.0
    paths = []
    for label, delta in _path_labels(delta_pos, delta_neg):
        length = abs(delta)
        count = max(2, math.ceil(length / step_deg) + 1)
        angles = _path_angles(start, delta, count)
        ap1 = angles if axis == "primary" else tuple([other] * count)
        ap2 = angles if axis == "secondary" else tuple([other] * count)
        paths.append(CandidatePath(path_id=f"{axis}_{label}", ap1_angles_deg=ap1, ap2_angles_deg=ap2))
    return tuple(paths)


def _deduplicate(poses: list[tuple[float, float]], *, tolerance_deg: float = 1e-9) -> list[tuple[float, float]]:
    """Angle-level first-pass dedup over (Ap1, Ap2) pairs.

    The dose loop performs the final dedup over complete geometry poses
    before evaluating (a legacy static candidate may share angles while
    differing elsewhere); generator callers must not assume these poses
    are pairwise distinct in full geometry.
    """
    unique: list[tuple[float, float]] = []
    for ap1, ap2 in poses:
        if not any(
            abs(((ap1 - u1 + 180.0) % 360.0) - 180.0) <= tolerance_deg
            and abs(((ap2 - u2 + 180.0) % 360.0) - 180.0) <= tolerance_deg
            for u1, u2 in unique
        ):
            unique.append((ap1, ap2))
    return unique


def build_candidate_domain(
    *,
    ap1_start: float,
    ap2_start: float,
    ap1_end: float | None,
    ap2_end: float | None,
    primary_moves: bool,
    secondary_moves: bool,
    step_deg: float = 1.0,
    include_static_pose: bool = True,
    static_ap1: float | None = None,
    static_ap2: float | None = None,
) -> CandidateDomain:
    """Assemble the candidate pose domain for one rotational event.

    One-axis motion yields short+long paths (full-circle union, identity kept
    for disclosure). Two-axis motion yields the four short/long combinations
    coupled by shared path fraction. Static pose appended when requested.
    """
    paths: list[CandidatePath] = []
    if primary_moves and secondary_moves and ap1_end is not None and ap2_end is not None:
        primaries = _path_labels(*_raw_displacements(ap1_start, ap1_end))
        secondaries = _path_labels(*_raw_displacements(ap2_start, ap2_end))
        for p_label, p_delta in primaries:
            for s_label, s_delta in secondaries:
                # Shared count from the slower axis so neither advances
                # more than step_deg per sample; same t_j couples them.
                count = max(
                    2,
                    math.ceil(abs(p_delta) / step_deg) + 1,
                    math.ceil(abs(s_delta) / step_deg) + 1,
                )
                p_angles = _path_angles(_canonical(ap1_start), p_delta, count)
                s_angles = _path_angles(_canonical(ap2_start), s_delta, count)
                paths.append(
                    CandidatePath(
                        path_id=f"coupled_{p_label}_{s_label}",
                        ap1_angles_deg=p_angles,
                        ap2_angles_deg=s_angles,
                    )
                )
    elif primary_moves and ap1_end is not None:
        paths.extend(
            wrapped_paths(ap1_start, ap1_end, step_deg=step_deg, axis="primary", other_start_raw=ap2_start)
        )
    elif secondary_moves and ap2_end is not None:
        paths.extend(
            wrapped_paths(ap2_start, ap2_end, step_deg=step_deg, axis="secondary", other_start_raw=ap1_start)
        )

    poses: list[tuple[float, float]] = []
    for path in paths:
        poses.extend(zip(path.ap1_angles_deg, path.ap2_angles_deg, strict=True))
    if include_static_pose and static_ap1 is not None and static_ap2 is not None:
        poses.append((_canonical(static_ap1), _canonical(static_ap2)))
    unique = _deduplicate(poses)
    return CandidateDomain(
        paths=tuple(paths),
        include_static_pose=include_static_pose,
        unique_pose_count=len(unique),
        unique_poses=tuple(unique),
    )


def closed_circle_domain(
    *,
    ap1_start: float,
    ap2_fixed: float,
    step_deg: float = 1.0,
) -> CandidateDomain:
    """360-degree primary sweep for type-only rotation (no usable endpoints).

    N distinct poses, no 0/360 duplication; the reported static pose is a
    member by construction (j=0).
    """
    count = math.ceil(360.0 / step_deg)
    angles = tuple(_canonical(ap1_start + j * 360.0 / count) for j in range(count))
    path = CandidatePath(
        path_id="primary_full_circle",
        ap1_angles_deg=angles,
        ap2_angles_deg=tuple([_canonical(ap2_fixed)] * count),
    )
    unique = _deduplicate(list(zip(angles, path.ap2_angles_deg, strict=True)))
    return CandidateDomain(
        paths=(path,),
        include_static_pose=True,
        unique_pose_count=len(unique),
        unique_poses=tuple(unique),
    )


@dataclass(frozen=True)
class CandidateResult:
    """One candidate pose's full-K dose response (physics side provides it)."""

    candidate_id: str
    dose_vector: Any
    hit_count: int = 0
    missed: bool = True
    k_bs_min: float | None = None
    k_bs_max: float | None = None
    k_med: float | None = None


@dataclass(frozen=True, eq=False)
class EnvelopeEvaluation:
    """Streaming cellwise maximum over candidate responses.

    Only the running maximum is retained: N full maps never sit resident.
    """

    dose_vector: Any
    winner_candidate_id: str | None
    candidate_count: int
    hit_candidate_count: int
    total_miss: bool
    k_bs_range: tuple[float | None, float | None]
    k_med_range: tuple[float | None, float | None]


def evaluate_envelope(
    results: Iterable[CandidateResult],
    *,
    n_cells: int,
    zeros: Callable[[int], Any],
    maximum: Callable[[Any, Any], Any],
    argmax_cell: Callable[[Any], tuple[int, float]],
) -> EnvelopeEvaluation:
    """Fold candidate dose vectors into their cellwise maximum.

    ``zeros``/``maximum``/``argmax_cell`` are injected so this stays free of
    numpy: ``argmax_cell`` returns ``(index, value)`` of the hottest cell.
    An empty candidate stream yields an all-zero vector with no winner.
    """
    running = zeros(n_cells)
    winner: str | None = None
    best_value = 0.0
    count = 0
    hit_count = 0
    bs_min: float | None = None
    bs_max: float | None = None
    med_min: float | None = None
    med_max: float | None = None
    for result in results:
        count += 1
        if not result.missed:
            hit_count += 1
        running = maximum(running, result.dose_vector)
        _, value = argmax_cell(result.dose_vector)
        if not result.missed and value > best_value:
            best_value = value
            winner = result.candidate_id
        for bound, new in (("min", result.k_bs_min), ("max", result.k_bs_max)):
            if new is None or not math.isfinite(new):
                continue
            if bound == "min":
                bs_min = new if bs_min is None else min(bs_min, new)
            else:
                bs_max = new if bs_max is None else max(bs_max, new)
        if result.k_med is not None and math.isfinite(result.k_med):
            med_min = result.k_med if med_min is None else min(med_min, result.k_med)
            med_max = result.k_med if med_max is None else max(med_max, result.k_med)
    return EnvelopeEvaluation(
        dose_vector=running,
        winner_candidate_id=winner,
        candidate_count=count,
        hit_candidate_count=hit_count,
        total_miss=count > 0 and hit_count == 0,
        k_bs_range=(bs_min, bs_max),
        k_med_range=(med_min, med_max),
    )


@dataclass(frozen=True)
class HandlingLedgerRow:
    event_index: int
    classification: str
    reason_codes: tuple[str, ...] = ()
    confidence: str = "none"
    requested_handling: str = "Auto"
    effective_handling: str = "static"
    fallback_reason: str = ""
    ap1_start: float | None = None
    ap2_start: float | None = None
    ap1_end: float | None = None
    ap2_end: float | None = None
    primary_separation_deg: float | None = None
    secondary_separation_deg: float | None = None
    candidate_domain: str = ""
    requested_path_count: int = 0
    unique_candidate_count: int = 0
    angular_step_deg: float = 1.0
    include_static_pose: bool = True
    direction_source: str = "unknown"
    kerma: float | None = None
    dap: float | None = None
    multiplier: float = 1.0
    aggregation_rule: str = "max_within_sum_between"


@dataclass
class LedgerEventInput:
    """One event's contribution to the handling ledger.

    ``requested_handling`` is what was asked (Auto/Coverage/Static);
    ``effective_handling`` is what ran. A static fallback is an effective
    ``static`` whose request was anything but an explicit ``Static``.
    """

    event_index: int
    classification: RotationalClassification
    requested_handling: str = "Auto"
    effective_handling: str = "static"
    fallback_reason: str = ""
    ap1_start: float | None = None
    ap2_start: float | None = None
    ap1_end: float | None = None
    ap2_end: float | None = None
    candidate_domain: str = ""
    requested_path_count: int = 0
    unique_candidate_count: int = 0
    angular_step_deg: float = 1.0
    include_static_pose: bool = True
    direction_source: str = "unknown"
    kerma: float | None = None
    dap: float | None = None


@dataclass(frozen=True)
class HandlingLedger:
    rows: tuple[HandlingLedgerRow, ...] = ()
    total_events: int = 0
    rotational_count: int = 0
    positioner_motion_count: int = 0
    static_count: int = 0
    unknown_count: int = 0
    rotational_kerma: float = 0.0
    total_kerma: float = 0.0
    any_fallback_to_static: bool = False


def build_handling_ledger(entries: list[LedgerEventInput]) -> HandlingLedger:
    """Assemble per-event ledger rows plus aggregate counts.

    Dose-weighted materiality (kerma sums) accompanies the counts so "1 of
    100 events" cannot mislead. ``any_fallback_to_static`` fires only for
    effective-``static`` outcomes that were NOT explicitly requested — an
    intentional Static override is recorded, not flagged. No dose math here.
    """
    rows: list[HandlingLedgerRow] = []
    rotational_kerma = 0.0
    total_kerma = 0.0
    counts = {"rotational": 0, "positioner_motion": 0, "static": 0, "unknown": 0}
    any_fallback = False
    for entry in entries:
        classification = entry.classification
        counts[classification.classification] = counts.get(classification.classification, 0) + 1
        if entry.kerma is not None and math.isfinite(entry.kerma):
            total_kerma += entry.kerma
            if classification.classification == "rotational":
                rotational_kerma += entry.kerma
        fallback = (
            entry.effective_handling == "static"
            and entry.requested_handling != "Static"
            and classification.classification in ("rotational", "positioner_motion")
        )
        any_fallback = any_fallback or fallback
        rows.append(
            HandlingLedgerRow(
                event_index=entry.event_index,
                classification=classification.classification,
                reason_codes=classification.reason_codes,
                confidence=classification.confidence,
                requested_handling=entry.requested_handling,
                effective_handling=entry.effective_handling,
                fallback_reason=entry.fallback_reason,
                ap1_start=entry.ap1_start,
                ap2_start=entry.ap2_start,
                ap1_end=entry.ap1_end,
                ap2_end=entry.ap2_end,
                primary_separation_deg=classification.primary_separation_deg,
                secondary_separation_deg=classification.secondary_separation_deg,
                candidate_domain=entry.candidate_domain,
                requested_path_count=entry.requested_path_count,
                unique_candidate_count=entry.unique_candidate_count,
                angular_step_deg=entry.angular_step_deg,
                include_static_pose=entry.include_static_pose,
                direction_source=entry.direction_source,
                kerma=entry.kerma,
                dap=entry.dap,
            )
        )
    return HandlingLedger(
        rows=tuple(rows),
        total_events=len(rows),
        rotational_count=counts.get("rotational", 0),
        positioner_motion_count=counts.get("positioner_motion", 0),
        static_count=counts.get("static", 0),
        unknown_count=counts.get("unknown", 0),
        rotational_kerma=rotational_kerma,
        total_kerma=total_kerma,
        any_fallback_to_static=any_fallback,
    )


__all__ = [
    "CandidateDomain",
    "CandidatePath",
    "HandlingLedger",
    "HandlingLedgerRow",
    "LedgerEventInput",
    "build_candidate_domain",
    "build_handling_ledger",
    "closed_circle_domain",
    "wrapped_paths",
]
