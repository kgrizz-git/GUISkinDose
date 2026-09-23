"""Unit tests for the rotational envelope candidate generator."""

from __future__ import annotations

import pytest

from guiskindose.rotational_envelope import (
    build_candidate_domain,
    build_handling_ledger,
    closed_circle_domain,
    wrapped_paths,
)


def test_wrapped_paths_keep_both_directions():
    short, long = wrapped_paths(90.0, -120.0, step_deg=1.0, axis="primary")
    assert short.path_id == "primary_short"
    assert long.path_id == "primary_long"
    assert short.ap1_angles_deg[0] == pytest.approx(90.0)
    assert short.ap1_angles_deg[-1] == pytest.approx(240.0)  # +150 short way
    assert long.ap1_angles_deg[-1] == pytest.approx(240.0)  # -210 lands same endpoint
    assert len(long.ap1_angles_deg) == 211  # ceil(210/1)+1
    assert len(short.ap1_angles_deg) == 151
    # Non-moving axis held at canonical start.
    assert set(long.ap2_angles_deg) == {0.0}


def test_exact_180_keeps_both_signed_paths():
    short, long = wrapped_paths(0.0, 180.0, step_deg=1.0, axis="primary")
    assert len(short.ap1_angles_deg) == len(long.ap1_angles_deg) == 181
    assert {short.path_id, long.path_id} == {"primary_positive_180", "primary_negative_180"}


def test_domain_carries_deduplicated_poses():
    domain = build_candidate_domain(
        ap1_start=90.0,
        ap2_start=0.0,
        ap1_end=-120.0,
        ap2_end=0.0,
        primary_moves=True,
        secondary_moves=False,
        step_deg=1.0,
        include_static_pose=True,
        static_ap1=90.0,
        static_ap2=0.0,
    )
    assert domain.unique_pose_count == len(domain.unique_poses) == 360
    assert (90.0, 0.0) in domain.unique_poses


def test_endpoints_pinned_exactly():
    (path,) = [p for p in wrapped_paths(10.3, 200.7, step_deg=7.0, axis="primary") if p.path_id == "primary_short"]
    assert path.ap1_angles_deg[0] == pytest.approx(10.3)
    assert path.ap1_angles_deg[-1] == pytest.approx(200.7)


def test_build_domain_deduplicates_static_endpoint():
    domain = build_candidate_domain(
        ap1_start=90.0,
        ap2_start=0.0,
        ap1_end=-120.0,
        ap2_end=0.0,
        primary_moves=True,
        secondary_moves=False,
        step_deg=1.0,
        include_static_pose=True,
        static_ap1=90.0,
        static_ap2=0.0,
    )
    assert len(domain.paths) == 2
    # 151 short + 211 long poses, static 90/0 already an endpoint.
    assert domain.unique_pose_count == 151 + 211 - 2  # shared endpoints deduped


def test_build_domain_coupled_four_paths():
    domain = build_candidate_domain(
        ap1_start=0.0,
        ap2_start=0.0,
        ap1_end=90.0,
        ap2_end=45.0,
        primary_moves=True,
        secondary_moves=True,
        step_deg=1.0,
        include_static_pose=False,
    )
    assert {p.path_id for p in domain.paths} == {
        "coupled_short_short",
        "coupled_short_long",
        "coupled_long_short",
        "coupled_long_long",
    }
    # Shared count from the slower axis per combination.
    counts = {p.path_id: len(p.ap1_angles_deg) for p in domain.paths}
    assert counts == {
        "coupled_short_short": 91,
        "coupled_short_long": 316,
        "coupled_long_short": 271,
        "coupled_long_long": 316,
    }


def test_closed_circle_has_no_duplicate_endpoint():
    domain = closed_circle_domain(ap1_start=30.0, ap2_fixed=5.0, step_deg=1.0)
    assert domain.unique_pose_count == 360
    assert domain.paths[0].ap1_angles_deg[0] == pytest.approx(30.0)
    assert all(a == pytest.approx(5.0) for a in domain.paths[0].ap2_angles_deg)


def test_handling_ledger_reports_kerma_weighted_counts():
    from guiskindose.rotational_acquisition import classify_rotational_event
    from guiskindose.rotational_envelope import LedgerEventInput

    spin = classify_rotational_event(
        {
            "Ap1": 90.0,
            "Ap2": 0.0,
            "Ap1_end": -120.0,
            "Ap2_end": 0.0,
            "acquisition_type": "Rotational Acquisition",
            "acquisition_type_code": "113613",
            "acquisition_type_coding_scheme": "DCM",
        }
    )
    plain = classify_rotational_event({"Ap1": 0.0, "Ap2": 0.0, "Ap1_end": 0.0, "Ap2_end": 0.0})
    ledger = build_handling_ledger(
        [
            LedgerEventInput(
                event_index=48,
                classification=spin,
                requested_handling="Auto",
                effective_handling="coverage",
                ap1_start=90.0,
                ap2_start=0.0,
                ap1_end=-120.0,
                ap2_end=0.0,
                candidate_domain="primary_short+primary_long",
                requested_path_count=2,
                unique_candidate_count=360,
                kerma=11.0,
                dap=1.0,
            ),
            LedgerEventInput(
                event_index=0, classification=plain, effective_handling="static", kerma=89.0, dap=9.0
            ),
        ]
    )
    assert ledger.total_events == 2
    assert ledger.rotational_count == 1
    assert ledger.static_count == 1
    assert ledger.rotational_kerma == pytest.approx(11.0)
    assert ledger.total_kerma == pytest.approx(100.0)
    assert ledger.any_fallback_to_static is False
    row = ledger.rows[0]
    assert row.reason_codes and row.confidence == "coded"
    assert row.ap1_end == pytest.approx(-120.0)
    assert row.primary_separation_deg == pytest.approx(150.0)
    assert row.unique_candidate_count == 360
    assert row.multiplier == pytest.approx(1.0)
    assert row.aggregation_rule == "max_within_sum_between"


def test_handling_ledger_flags_static_fallback():
    from guiskindose.rotational_acquisition import classify_rotational_event
    from guiskindose.rotational_envelope import LedgerEventInput

    spin = classify_rotational_event(
        {
            "Ap1": 90.0,
            "Ap2": 0.0,
            "Ap1_end": -120.0,
            "Ap2_end": 0.0,
            "acquisition_type": "Rotational Acquisition",
        }
    )
    ledger = build_handling_ledger(
        [
            LedgerEventInput(
                event_index=0,
                classification=spin,
                requested_handling="Auto",
                effective_handling="static",
                fallback_reason="trajectory_unresolved",
                kerma=5.0,
                dap=None,
            )
        ]
    )
    assert ledger.any_fallback_to_static is True
    assert ledger.rows[0].fallback_reason == "trajectory_unresolved"


def test_handling_ledger_explicit_static_is_not_fallback():
    from guiskindose.rotational_acquisition import classify_rotational_event
    from guiskindose.rotational_envelope import LedgerEventInput

    spin = classify_rotational_event(
        {
            "Ap1": 90.0,
            "Ap2": 0.0,
            "Ap1_end": -120.0,
            "Ap2_end": 0.0,
            "acquisition_type": "Rotational Acquisition",
        }
    )
    ledger = build_handling_ledger(
        [
            LedgerEventInput(
                event_index=0,
                classification=spin,
                requested_handling="Static",
                effective_handling="static",
                kerma=5.0,
                dap=None,
            )
        ]
    )
    assert ledger.any_fallback_to_static is False
