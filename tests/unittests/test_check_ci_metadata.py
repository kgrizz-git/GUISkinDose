"""Tests for value-safe CI title/body/commit-message admission."""

import pytest

from scripts.check_ci_metadata import scan_event_payload
from scripts.check_sensitive_content import text_findings
from scripts.git_identity_trailers import is_allowlisted_git_identity_trailer


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


def test_ci_metadata_allows_dependabot_signed_off_by_trailer() -> None:
    """Dependabot always appends Signed-off-by with the GitHub support address on push."""
    bot = "support@" + "github.com"
    message = "chore(deps): bump astral-sh/setup-uv from 8.3.2 to 9.0.0\n\n" f"Signed-off-by: dependabot[bot] <{bot}>\n"
    assert scan_event_payload({"commits": [{"message": message}]}) == []


def test_ci_metadata_allows_github_noreply_coauthored_trailer() -> None:
    noreply = "maintainer@" + "users.noreply.github.com"
    message = "fix: preserve import warnings\n\n" f"Co-authored-by: maintainer <{noreply}>\n"
    assert scan_event_payload({"commits": [{"message": message}]}) == []


@pytest.mark.parametrize("field", ["title", "body"])
def test_ci_metadata_flags_approved_trailers_in_pull_request_fields(field: str) -> None:
    """Allowlisted trailers apply only to push commit messages, not PR title/body."""
    bot = "support@" + "github.com"
    noreply = "maintainer@" + "users.noreply.github.com"
    trailer_lines = {
        "title": f"Signed-off-by: dependabot[bot] <{bot}>",
        "body": f"Co-authored-by: maintainer <{noreply}>",
    }
    pull_request: dict[str, object] = {
        "title": "Privacy hardening",
        "body": "synthetic body",
    }
    pull_request[field] = trailer_lines[field]
    findings = scan_event_payload({"pull_request": pull_request})
    assert [(finding.source, finding.line, finding.rule) for finding in findings] == [
        (f"pull_request_{field}", "1", "EMAIL_ADDRESS")
    ]
    assert bot not in repr(findings)
    assert noreply not in repr(findings)


def test_ci_metadata_still_flags_institutional_email_in_commit() -> None:
    value = "physicist" + "@hospital.test"
    findings = scan_event_payload({"commits": [{"message": f"Notes for {value}\n"}]})
    assert [(finding.source, finding.line, finding.rule) for finding in findings] == [
        ("push_commit_1", "1", "EMAIL_ADDRESS")
    ]
    assert value not in repr(findings)


def test_ci_metadata_still_flags_institutional_email_in_coauthored_trailer() -> None:
    value = "physicist" + "@hospital.test"
    message = f"fix: offsets\n\nCo-authored-by: Physicist <{value}>\n"
    findings = scan_event_payload({"commits": [{"message": message}]})
    assert [(finding.source, finding.line, finding.rule) for finding in findings] == [
        ("push_commit_1", "3", "EMAIL_ADDRESS")
    ]
    assert value not in repr(findings)


@pytest.mark.parametrize("trailer_type", ["Signed-off-by", "Co-authored-by"])
def test_text_findings_reports_institutional_address_hiding_in_trailer_display_name(
    trailer_type: str,
) -> None:
    """An institutional address in the display name must not be suppressed."""
    institutional = "employee@" + "hospital.example"
    noreply = "123@" + "users.noreply.github.com"
    line = f"{trailer_type}: {institutional} <{noreply}>"
    assert is_allowlisted_git_identity_trailer(line) is False
    findings = text_findings("COMMIT_MESSAGE", line + "\n", allow_git_identity_trailers=True)
    assert [(finding.rule, finding.location) for finding in findings] == [("EMAIL_ADDRESS", "1")]
    assert institutional not in repr(findings)
