"""Unit tests for scripts/check_changelog.py (base resolution + exemptions)."""

import subprocess

import pytest

from scripts import check_changelog


def _completed(returncode: int = 0, stdout: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr="")


def test_resolve_base_prefers_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_BASE_REF", "main")
    assert check_changelog.resolve_base() == "origin/main"


def test_resolve_base_merge_base(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GITHUB_BASE_REF", raising=False)
    monkeypatch.setattr(check_changelog, "_git", lambda *a: _completed(stdout="abc123\n"))
    assert check_changelog.resolve_base() == "abc123"


def test_resolve_base_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GITHUB_BASE_REF", raising=False)
    monkeypatch.setattr(check_changelog, "_git", lambda *a: _completed(returncode=1))
    assert check_changelog.resolve_base() is None


def _main_with_changed(monkeypatch: pytest.MonkeyPatch, changed: list[str]) -> int:
    monkeypatch.setattr(check_changelog, "resolve_base", lambda: "base")
    monkeypatch.setattr(check_changelog, "changed_files", lambda base: changed)
    return check_changelog.main()


def test_src_change_without_changelog_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    assert _main_with_changed(monkeypatch, ["src/a.py"]) == 1


def test_changelog_touched_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    assert _main_with_changed(monkeypatch, ["src/a.py", "CHANGELOG.md"]) == 0


def test_tests_only_without_changelog_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    assert _main_with_changed(monkeypatch, ["tests/test_a.py"]) == 1


def test_maintenance_log_exemption_for_tests_only_pr(monkeypatch: pytest.MonkeyPatch) -> None:
    """Process-only exemption: tests + maintenance log, no user-facing entry."""
    changed = ["tests/unittests/test_check_todo_cleanup.py", "dev-docs/MAINTENANCE_LOG.md"]
    assert _main_with_changed(monkeypatch, changed) == 0


def test_maintenance_log_does_not_exempt_src_changes(monkeypatch: pytest.MonkeyPatch) -> None:
    changed = ["src/a.py", "dev-docs/MAINTENANCE_LOG.md"]
    assert _main_with_changed(monkeypatch, changed) == 1
