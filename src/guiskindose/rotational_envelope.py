"""Rotational coverage-envelope candidate generation (non-GUI).

Pure geometry: given measured endpoint angles, produce the declared candidate
pose domain over which the envelope takes its pointwise maximum. No dose
physics here — candidates are angle sets; evaluation lives in the dose loop.
See ``dev-docs/plans/ROTATIONAL_COVERAGE_ENVELOPE_PLAN.md``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


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


def _signed_displacements(start_raw: float, end_raw: float) -> tuple[float, float]:
    """Short/long signed displacements preserving wraparound direction."""
    delta_pos = (end_raw - start_raw) % 360.0
    delta_neg = delta_pos - 360.0
    if abs(delta_pos) <= abs(delta_neg):
        return delta_pos, delta_neg
    return delta_neg, delta_pos


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
    short, long = _signed_displacements(start_raw, end_raw)
    paths = []
    for label, delta in (("short", short), ("long", long)):
        length = abs(delta)
        count = max(2, math.ceil(length / step_deg) + 1)
        angles = _path_angles(start, delta, count)
        ap1 = angles if axis == "primary" else tuple([other] * count)
        ap2 = angles if axis == "secondary" else tuple([other] * count)
        paths.append(CandidatePath(path_id=f"{axis}_{label}", ap1_angles_deg=ap1, ap2_angles_deg=ap2))
    return tuple(paths)


def _deduplicate(poses: list[tuple[float, float]], *, tolerance_deg: float = 1e-9) -> list[tuple[float, float]]:
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
        primaries = _signed_displacements(ap1_start, ap1_end)
        secondaries = _signed_displacements(ap2_start, ap2_end)
        for p_label, p_delta in zip(("short", "long"), primaries, strict=True):
            for s_label, s_delta in zip(("short", "long"), secondaries, strict=True):
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
    return CandidateDomain(paths=tuple(paths), include_static_pose=include_static_pose, unique_pose_count=len(unique))


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
    return CandidateDomain(paths=(path,), include_static_pose=True, unique_pose_count=len(set(angles)))


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


def build_handling_ledger(
    classifications: list[tuple[int, object, str, float | None, float | None]],
) -> HandlingLedger:
    """Assemble per-event ledger rows plus aggregate counts.

    Each entry is ``(event_index, classification, effective_handling, kerma,
    dap)`` where ``classification`` is a ``RotationalClassification``.
    Dose-weighted materiality (kerma sums) accompanies the counts so "1 of
    100 events" cannot mislead. No dose math happens here.
    """
    rows: list[HandlingLedgerRow] = []
    rotational_kerma = 0.0
    total_kerma = 0.0
    counts = {"rotational": 0, "positioner_motion": 0, "static": 0, "unknown": 0}
    any_fallback = False
    for event_index, classification, handling, kerma, dap in classifications:
        counts[classification.classification] = counts.get(classification.classification, 0) + 1
        if kerma is not None and math.isfinite(kerma):
            total_kerma += kerma
            if classification.classification == "rotational":
                rotational_kerma += kerma
        if handling == "static" and classification.classification in ("rotational", "positioner_motion"):
            any_fallback = True
        rows.append(
            HandlingLedgerRow(
                event_index=event_index,
                classification=classification.classification,
                reason_codes=classification.reason_codes,
                confidence=classification.confidence,
                effective_handling=handling,
                ap1_start=None,
                kerma=kerma,
                dap=dap,
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
    "build_candidate_domain",
    "build_handling_ledger",
    "closed_circle_domain",
    "wrapped_paths",
]
