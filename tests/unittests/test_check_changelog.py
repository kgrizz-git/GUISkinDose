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


def _main_with_diff(monkeypatch: pytest.MonkeyPatch, changed: list[str], added: dict[str, list[str]]) -> int:
    monkeypatch.setattr(check_changelog, "resolve_base", lambda: "base")
    monkeypatch.setattr(check_changelog, "changed_files", lambda base: changed)
    monkeypatch.setattr(check_changelog, "_added_lines", lambda base, path: added.get(path, []))
    return check_changelog.main()


def test_comment_only_src_change_is_satisfied_by_the_maintenance_log(monkeypatch: pytest.MonkeyPatch) -> None:
    """CHANGELOG.md documents itself as user-facing; a comment has no honest entry there."""
    assert (
        _main_with_diff(
            monkeypatch,
            ["src/a.py", "dev-docs/MAINTENANCE_LOG.md"],
            {"src/a.py": ["# explain why the flag exists", ""]},
        )
        == 0
    )


def test_comment_only_still_needs_the_maintenance_log(monkeypatch: pytest.MonkeyPatch) -> None:
    assert _main_with_diff(monkeypatch, ["src/a.py"], {"src/a.py": ["# just a comment"]}) == 1


@pytest.mark.parametrize(
    "line",
    [
        "value = 1",
        "helper()",
        "import os",
        "def f() -> None:",
        "class C:",
        "    return None",
    ],
)
def test_one_added_statement_disqualifies_the_exemption(monkeypatch: pytest.MonkeyPatch, line: str) -> None:
    """The exemption must not become a way to slip behaviour past the changelog."""
    assert (
        _main_with_diff(
            monkeypatch,
            ["src/a.py", "dev-docs/MAINTENANCE_LOG.md"],
            {"src/a.py": ["# a comment", line]},
        )
        == 1
    )


def test_a_pure_deletion_is_not_comment_only(monkeypatch: pytest.MonkeyPatch) -> None:
    """Removing code changes behaviour, and shows up as no added lines at all."""
    assert _main_with_diff(monkeypatch, ["src/a.py", "dev-docs/MAINTENANCE_LOG.md"], {"src/a.py": []}) == 1


def test_a_non_python_src_change_is_never_comment_only(monkeypatch: pytest.MonkeyPatch) -> None:
    assert (
        _main_with_diff(
            monkeypatch,
            ["src/guiskindose/gui/ui_copy.json", "dev-docs/MAINTENANCE_LOG.md"],
            {"src/guiskindose/gui/ui_copy.json": ["  // note"]},
        )
        == 1
    )
