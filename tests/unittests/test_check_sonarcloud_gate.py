"""Tests for SonarCloud quality-gate reporter (offline)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

import scripts.check_sonarcloud_gate as gate


def test_format_gate_report_lists_failing_conditions() -> None:
    text = gate.format_gate_report(
        "proj-key",
        {
            "projectStatus": {
                "status": "ERROR",
                "conditions": [
                    {"metricKey": "new_reliability_rating", "status": "ERROR", "actualValue": "3", "errorThreshold": "1"},
                    {"metricKey": "new_coverage", "status": "OK", "actualValue": "90", "errorThreshold": "80"},
                ],
            }
        },
        {"total": 2, "issues": [{"type": "BUG", "severity": "MAJOR", "rule": "x", "component": "p:src/a.py", "line": 1}]},
        {"total": 1, "issues": []},
        sample_limit=5,
    )
    assert "status=ERROR" in text
    assert "new_reliability_rating" in text
    assert "new_coverage" not in text
    assert "bugs=1" in text


def test_main_missing_token_returns_2(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(gate, "repo_root", lambda: tmp_path)
    (tmp_path / "sonar-project.properties").write_text("sonar.projectKey=k\n", encoding="utf-8")
    monkeypatch.setattr(gate, "resolve_cloud_token", lambda _root: None)
    assert gate.main([]) == 2


@pytest.mark.parametrize("body", [b"\xff", b"not JSON", b'[]', b'{"errors": [{"msg": "private-response"}]}'])
def test_main_response_errors_are_private(body, monkeypatch, capsys) -> None:
    monkeypatch.setattr(gate, "resolve_cloud_token", lambda _root: "private-response")
    response = MagicMock()
    response.__enter__.return_value = response
    response.status = 200
    response.read.return_value = body
    monkeypatch.setattr(gate._NO_REDIRECT_OPENER, "open", lambda *_args, **_kwargs: response)
    assert gate.main(["--project-key", "k"]) == 1
    output = capsys.readouterr()
    assert "private-response" not in output.err + output.out
    assert "query failed" in output.err


@pytest.mark.parametrize(("status", "expected"), [("OK", 0), ("ERROR", 1), ("NONE", 1)])
def test_main_caps_page_size_and_enforces_gate(status, expected, monkeypatch) -> None:
    monkeypatch.setattr(gate, "resolve_cloud_token", lambda _root: "offline-test")
    monkeypatch.setattr(gate, "fetch_project_status", lambda *_args: {"projectStatus": {"status": status}})
    pages = []

    def fetch(*_args, page_size, issue_types):
        pages.append((page_size, issue_types))
        return {"total": 0, "issues": []}

    monkeypatch.setattr(gate, "fetch_new_code_issues", fetch)
    assert gate.main(["--project-key", "k", "--sample-limit", "1000", "--fail-on-error"]) == expected
    assert pages == [(500, None), (10, "BUG")]
