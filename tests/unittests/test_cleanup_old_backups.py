"""Tests for scripts/cleanup_old_backups.py."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from scripts.cleanup_old_backups import cleanup_old_backups


def test_cleanup_skips_recent_tracked_backup(tmp_path: Path) -> None:
    repo = tmp_path
    (repo / ".git").mkdir()
    backups = repo / "backups"
    backups.mkdir()
    backup = backups / "example.py.bak"
    backup.write_text("old content", encoding="utf-8")

    with patch("scripts.cleanup_old_backups._commits_since_last_git_touch", return_value=2):
        removed = cleanup_old_backups(repo, max_commits=5, dry_run=False)

    assert removed == []
    assert backup.exists()


def test_cleanup_removes_stale_tracked_backup(tmp_path: Path) -> None:
    repo = tmp_path
    (repo / ".git").mkdir()
    backups = repo / "backups"
    backups.mkdir()
    backup = backups / "example.py.bak"
    backup.write_text("old content", encoding="utf-8")

    with patch("scripts.cleanup_old_backups._commits_since_last_git_touch", return_value=6):
        removed = cleanup_old_backups(repo, max_commits=5, dry_run=False)

    assert removed == [backup]
    assert not backup.exists()


def test_cleanup_dry_run_does_not_delete(tmp_path: Path) -> None:
    repo = tmp_path
    (repo / ".git").mkdir()
    backups = repo / "backups"
    backups.mkdir()
    backup = backups / "example.py.bak"
    backup.write_text("old content", encoding="utf-8")

    with patch("scripts.cleanup_old_backups._commits_since_last_git_touch", return_value=10):
        removed = cleanup_old_backups(repo, max_commits=5, dry_run=True)

    assert removed == [backup]
    assert backup.exists()
