"""Tests for value-safe CI title/body/commit-message admission."""

from scripts.check_ci_metadata import scan_event_payload


def test_ci_metadata_scans_pr_and_push_without_values() -> None:
    value = "person" + "@hospital.test"
    findings = scan_event_payload(
        {
            "pull_request": {"title": f"Review {value}", "body": "synthetic body"},
            "commits": [{"message": "synthetic commit"}],
        }
    )

    assert [(finding.source, finding.line, finding.rule) for finding in findings] == [
        ("pull_request_title", "1", "EMAIL_ADDRESS")
    ]
    assert value not in repr(findings)


def test_ci_metadata_accepts_value_free_event() -> None:
    assert scan_event_payload({"pull_request": {"title": "Privacy hardening", "body": None}}) == []
