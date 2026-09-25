"""Tests for the SonarQube issue-dump helper (offline parts only)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.dump_sonar_issues import (
    check_host_loopback,
    project_key_from_properties,
    prune_dumps,
    refresh_state_counts,
    summarize_issues,
)


def test_loopback_hosts_allowed_and_remote_refused() -> None:
    assert check_host_loopback("http://localhost:9000", allow_remote=False)
    with pytest.raises(ValueError, match="non-loopback"):
        check_host_loopback("https://sonar.example.com", allow_remote=False)
    assert check_host_loopback("https://sonar.example.com", allow_remote=True)


def test_project_key_from_properties(tmp_path: Path) -> None:
    (tmp_path / "sonar-project.properties").write_text(
        "# comment\nsonar.projectKey=my-key\n", encoding="utf-8"
    )
    assert project_key_from_properties(tmp_path) == "my-key"
    assert project_key_from_properties(tmp_path / "missing") is None


def test_summarize_issues_formats_locations() -> None:
    summary = summarize_issues(
        [
            {
                "severity": "MAJOR",
                "rule": "python:S100",
                "component": "proj:src/mod.py",
                "line": 12,
                "message": "Rename this.",
            }
        ]
    )
    assert "Total: 1" in summary
    assert "src/mod.py:12" in summary


def test_refresh_state_counts_preserves_scan_commit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import scripts.dump_sonar_issues as dump

    monkeypatch.setattr(dump, "repo_root", lambda: tmp_path)
    state_file = tmp_path / "tmp" / "sonar-state.json"
    state_file.parent.mkdir(parents=True)
    state_file.write_text(
        json.dumps({"last_scan_commit": "abc", "last_scan_time": "t", "issues_count": None}),
        encoding="utf-8",
    )
    assert refresh_state_counts(tmp_path, issues_count=7, issues_path="tmp/sonar-issues/x.json") is True
    state = json.loads(state_file.read_text(encoding="utf-8"))
    assert state["last_scan_commit"] == "abc"
    assert state["issues_count"] == 7


def test_refresh_state_counts_missing_file_is_false(tmp_path: Path) -> None:
    assert refresh_state_counts(tmp_path, issues_count=1, issues_path="tmp/sonar-issues/x.json") is False


def test_prune_dumps_keeps_recent_minimum(tmp_path: Path) -> None:
    issues_dir = tmp_path / "dumps"
    issues_dir.mkdir()
    for stamp in ("2026-09-20T120000Z", "2026-09-24T120000Z"):
        (issues_dir / f"{stamp}.json").write_text("[]", encoding="utf-8")
        (issues_dir / f"{stamp}.md").write_text("#", encoding="utf-8")
    removed, kept = prune_dumps(issues_dir)
    assert removed == 0
    assert kept == 2
