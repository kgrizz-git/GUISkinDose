"""Equivalence tests for the O(N) spatial-hash `_deduplicate`.

Keeps a copy of the legacy O(N^2) pairwise implementation as a reference
oracle and asserts byte-identical output (same original tuples, same order).
"""

from __future__ import annotations

import random

from guiskindose.rotational_envelope import _deduplicate, build_candidate_domain


def _legacy_deduplicate(
    poses: list[tuple[float, float]], *, tolerance_deg: float = 1e-9
) -> list[tuple[float, float]]:
    """Pre-Phase-3 O(N^2) implementation, frozen as the semantics oracle."""
    unique: list[tuple[float, float]] = []
    for ap1, ap2 in poses:
        if not any(
            abs(((ap1 - u1 + 180.0) % 360.0) - 180.0) <= tolerance_deg
            and abs(((ap2 - u2 + 180.0) % 360.0) - 180.0) <= tolerance_deg
            for u1, u2 in unique
        ):
            unique.append((ap1, ap2))
    return unique


def test_matches_oracle_on_seeded_near_duplicates():
    rng = random.Random(20261002)
    tol = 1e-9
    poses: list[tuple[float, float]] = []
    for _ in range(300):
        base1, base2 = rng.uniform(0.0, 360.0), rng.uniform(0.0, 360.0)
        poses.append((base1, base2))
        poses.append((base1 + tol / 2, base2 - tol / 3))  # within tolerance -> dup
        poses.append((base1 + tol * 3, base2))  # just beyond on one axis -> kept
        poses.append((base1, base2 + tol * 3))  # just beyond on other axis -> kept
        poses.append((base1, base2))  # exact repeat -> dup
    assert _deduplicate(poses, tolerance_deg=tol) == _legacy_deduplicate(poses, tolerance_deg=tol)


def test_matches_oracle_with_wide_tolerance():
    rng = random.Random(77)
    tol = 0.5
    poses = [(rng.uniform(-720.0, 720.0), rng.uniform(-720.0, 720.0)) for _ in range(500)]
    assert _deduplicate(poses, tolerance_deg=tol) == _legacy_deduplicate(poses, tolerance_deg=tol)


def test_wrap_straddle_at_zero():
    poses = [
        (359.9999999999, 0.0),  # 1e-10 from 0 -> dup of the next pose
        (0.0, 0.0),
        (-1e-12, 0.0),  # wraps to ~360 -> dup
        (359.999999, 0.0),  # 1e-6 away -> kept
        (0.0, 359.9999999999),
        (360.0, 0.0),  # exact wrap of an earlier kept pose -> dup
    ]
    assert _deduplicate(poses) == _legacy_deduplicate(poses) == [(359.9999999999, 0.0), (359.999999, 0.0)]


def test_negative_angles_match_oracle():
    poses = [
        (-90.0, -180.0),
        (270.0, 180.0),  # same wrapped pose -> dup
        (-90.0 + 5e-10, -180.0),  # within tolerance -> dup
        (-90.0, -179.0),  # 1 deg away on ap2 -> kept
        (-450.0, 540.0),  # wraps to (270, 180) -> dup
    ]
    assert _deduplicate(poses) == _legacy_deduplicate(poses) == [(-90.0, -180.0), (-90.0, -179.0)]


def test_exact_180_stays_distinct():
    poses = [(0.0, 0.0), (180.0, 0.0), (180.0, 0.0), (0.0, 180.0), (180.0, 180.0)]
    assert _deduplicate(poses) == _legacy_deduplicate(poses) == [(0.0, 0.0), (180.0, 0.0), (0.0, 180.0), (180.0, 180.0)]


def test_partial_bucket_seam_reproducer():
    # 360 / (2 * 0.7) is not an integer; the pair straddles the 0/360 seam.
    poses = [(0.3, 0.0), (359.7, 0.0)]
    assert _legacy_deduplicate(poses, tolerance_deg=0.7) == [(0.3, 0.0)]
    assert _deduplicate(poses, tolerance_deg=0.7) == [(0.3, 0.0)]


def test_partial_bucket_seam_on_ap2_axis():
    poses = [(0.0, 0.3), (0.0, 359.7)]
    assert _legacy_deduplicate(poses, tolerance_deg=0.7) == [(0.0, 0.3)]
    assert _deduplicate(poses, tolerance_deg=0.7) == [(0.0, 0.3)]


def test_matches_oracle_near_seam_for_non_dividing_tolerances():
    rng = random.Random(4242)
    for tol in (0.7, 0.33, 1.1, 7.0, 100.0, 200.0):
        poses: list[tuple[float, float]] = []
        for _ in range(200):
            # Concentrate near the seam (within +/-2*tol of 0/360) plus uniform cover.
            if rng.random() < 0.5:
                seam = rng.choice((rng.uniform(-2 * tol, 2 * tol), rng.uniform(360.0 - 2 * tol, 360.0 + 2 * tol)))
                poses.append((seam, rng.uniform(-2 * tol, 2 * tol)))
            else:
                poses.append((rng.uniform(0.0, 360.0), rng.uniform(0.0, 360.0)))
        assert _deduplicate(poses, tolerance_deg=tol) == _legacy_deduplicate(poses, tolerance_deg=tol)


def test_original_tuples_returned_unmodified():
    poses = [(-1e-12, 720.0), (359.9999999999, 720.0)]
    assert _deduplicate(poses) == poses[:1]
    assert _deduplicate(poses)[0] == (-1e-12, 720.0)


def test_degenerate_tolerances_match_oracle():
    poses = [(0.0, 0.0), (0.0, 0.0), (360.0, 0.0), (1e-12, 0.0)]
    assert _deduplicate(poses, tolerance_deg=0.0) == _legacy_deduplicate(poses, tolerance_deg=0.0)
    assert _deduplicate(poses, tolerance_deg=-1.0) == _legacy_deduplicate(poses, tolerance_deg=-1.0)


def test_coupled_like_4000_pose_domain_matches_oracle():
    domain = build_candidate_domain(
        ap1_start=0.0,
        ap2_start=0.0,
        ap1_end=90.0,
        ap2_end=45.0,
        primary_moves=True,
        secondary_moves=True,
        step_deg=0.2,
        include_static_pose=False,
    )
    # Raw flattened sweeps (pre-dedup): paths share endpoints and crossings.
    poses = [pose for path in domain.paths for pose in zip(path.ap1_angles_deg, path.ap2_angles_deg, strict=True)]
    assert len(poses) >= 4000
    assert _deduplicate(poses) == _legacy_deduplicate(poses)
    assert len(_deduplicate(poses)) < len(poses)  # shared endpoints actually collapse


def test_out_of_hash_range_inputs_match_oracle():
    """Huge, non-finite and sub-1e-12-tolerance inputs take the exact fallback."""
    nan, inf = float("nan"), float("inf")
    huge = [(4529231890312341.0, 0.0), (21.147679423935166, 0.0)]
    assert _deduplicate(huge) == _legacy_deduplicate(huge) == huge[:1]
    non_finite = [(nan, 0.0), (inf, 0.0), (0.0, 0.0), (nan, 0.0)]
    assert _deduplicate(non_finite) == _legacy_deduplicate(non_finite)
    tiny = [(0.0, 0.0), (0.0, 0.0), (1e-300, 0.0)]
    assert _deduplicate(tiny, tolerance_deg=1e-306) == _legacy_deduplicate(tiny, tolerance_deg=1e-306)
