"""Tests for SonarCloud quality-gate reporter (offline)."""

from __future__ import annotations

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
