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
    message = f"chore(deps): bump astral-sh/setup-uv from 8.3.2 to 9.0.0\n\nSigned-off-by: dependabot[bot] <{bot}>\n"
    assert scan_event_payload({"commits": [{"message": message}]}) == []


def test_ci_metadata_allows_github_noreply_coauthored_trailer() -> None:
    noreply = "maintainer@" + "users.noreply.github.com"
    message = f"fix: preserve import warnings\n\nCo-authored-by: maintainer <{noreply}>\n"
    assert scan_event_payload({"commits": [{"message": message}]}) == []


@pytest.mark.parametrize(
    ("display_name", "email"),
    [
        ("Claude Opus 5.5", "noreply@" + "anthropic.com"),
        ("Cursor", "cursoragent@" + "cursor.com"),
        ("Codex", "noreply@" + "openai.com"),
        ("Qwen Coder", "qwen-coder@" + "alibabacloud.com"),
        ("Toast (Polecat)", "toast@" + "gastown.kilo.ai"),
        ("kiloconnect[bot]", "240665456+kiloconnect[bot]@" + "users.noreply.github.com"),
    ],
)
def test_ci_metadata_allows_ai_agent_coauthored_trailers(display_name: str, email: str) -> None:
    message = f"fix(run-state): example\n\nCo-authored-by: {display_name} <{email}>\n"
    assert is_allowlisted_git_identity_trailer(f"Co-authored-by: {display_name} <{email}>")
    assert scan_event_payload({"commits": [{"message": message}]}) == []


def test_ci_metadata_allows_anthropic_trailer_on_multiline_commit_like_pr147() -> None:
    """Regression: #147 merge push failed when an included commit had a Claude co-author trailer."""
    anthropic = "noreply@" + "anthropic.com"
    message = (
        "fix(run-state): let |= on frozen overrides decline instead of raising\n\n"
        "Adds a regression assertion for that behavior.\n\n"
        f"Co-Authored-By: Claude Opus 5.5 <{anthropic}>\n"
    )
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


def test_ci_metadata_scans_pr_commit_messages_without_values() -> None:
    """Regression: a personal Co-authored-by address passed the PR and failed only on push to main."""
    from scripts.check_ci_metadata import scan_commit_messages

    value = "person" + "@hospital.test"
    findings = scan_commit_messages(
        [
            ("abc1234", "fix: ok\n\nCo-authored-by: Cursor <cursoragent@" + "cursor.com>\n"),
            ("def5678", f"fix: example\n\nbody line\n\nCo-authored-by: person <{value}>\n"),
        ]
    )

    assert [(f.source, f.line, f.rule) for f in findings] == [("pr_commit_def5678", "5", "EMAIL_ADDRESS")]
    assert value not in repr(findings)


def test_read_commit_messages_parses_git_log(tmp_path, monkeypatch) -> None:
    import subprocess

    from scripts import check_ci_metadata

    fake = "aaa1111\x00subject one\n\nbody\n\x1e\nbbb2222\x00subject two\n\x1e\n"
    monkeypatch.setattr(
        check_ci_metadata.subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(a, 0, stdout=fake, stderr=""),
    )

    assert check_ci_metadata.read_commit_messages("base..head") == [
        ("aaa1111", "subject one\n\nbody\n"),
        ("bbb2222", "subject two\n"),
    ]
