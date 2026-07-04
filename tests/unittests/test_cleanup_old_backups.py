"""Tests for scripts/cleanup_old_backups.py."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from unittest.mock import patch

from scripts.cleanup_old_backups import cleanup_old_backups


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


def _commit_path(repo: Path, relative_path: str, content: str, message: str) -> None:
    path = repo / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    _git(repo, "add", relative_path)
    _git(repo, "commit", "-m", message)


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


def test_cleanup_keeps_new_untracked_backup_at_historical_path(tmp_path: Path) -> None:
    repo = tmp_path
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test User")

    backup_relative = "backups/example.py.bak"
    _commit_path(repo, backup_relative, "old backup", "add backup")
    _git(repo, "rm", backup_relative)
    _git(repo, "commit", "-m", "remove backup")

    for index in range(6):
        _commit_path(repo, f"file-{index}.txt", str(index), f"commit {index}")

    backup = repo / backup_relative
    backup.parent.mkdir(parents=True, exist_ok=True)
    backup.write_text("new backup that should not be deleted", encoding="utf-8")

    removed = cleanup_old_backups(repo, max_commits=5, dry_run=False)

    assert removed == []
    assert backup.exists()


def test_cleanup_keeps_new_staged_backup_at_historical_path(tmp_path: Path) -> None:
    repo = tmp_path
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test User")

    backup_relative = "backups/example.py.bak"
    _commit_path(repo, backup_relative, "old backup", "add backup")
    _git(repo, "rm", backup_relative)
    _git(repo, "commit", "-m", "remove backup")

    for index in range(6):
        _commit_path(repo, f"file-{index}.txt", str(index), f"commit {index}")

    backup = repo / backup_relative
    backup.parent.mkdir(parents=True, exist_ok=True)
    backup.write_text("new staged backup that should not be deleted", encoding="utf-8")
    _git(repo, "add", backup_relative)

    removed = cleanup_old_backups(repo, max_commits=5, dry_run=False)

    assert removed == []
    assert backup.exists()


def test_cleanup_keeps_freshly_staged_backup_still_in_head(tmp_path: Path) -> None:
    """A backup whose path remains tracked in HEAD but was recreated and force-staged
    with new content must not be deleted by stale commit age (reviewer follow-up)."""
    repo = tmp_path
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test User")

    backup_relative = "backups/example.py.bak"
    # Path is committed and never removed, so it stays present in HEAD.
    _commit_path(repo, backup_relative, "old backup content", "add backup")

    # Push the backup's last commit well beyond max_commits behind HEAD.
    for index in range(6):
        _commit_path(repo, f"file-{index}.txt", str(index), f"commit {index}")

    # Recreate the working-tree file with new content and force-stage it.
    backup = repo / backup_relative
    backup.write_text("brand new backup that should not be deleted", encoding="utf-8")
    _git(repo, "add", backup_relative)

    removed = cleanup_old_backups(repo, max_commits=5, dry_run=False)

    assert removed == []
    assert backup.exists()


def test_cleanup_keeps_modified_unstaged_backup_still_in_head(tmp_path: Path) -> None:
    """Same as above but the recreated file is left unstaged; pending working-tree
    changes alone must protect it from commit-age deletion."""
    repo = tmp_path
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test User")

    backup_relative = "backups/example.py.bak"
    _commit_path(repo, backup_relative, "old backup content", "add backup")

    for index in range(6):
        _commit_path(repo, f"file-{index}.txt", str(index), f"commit {index}")

    backup = repo / backup_relative
    backup.write_text("locally modified backup that should not be deleted", encoding="utf-8")

    removed = cleanup_old_backups(repo, max_commits=5, dry_run=False)

    assert removed == []
    assert backup.exists()


def test_cleanup_keeps_modified_unstaged_backup_still_in_head_with_old_mtime(tmp_path: Path) -> None:
    """Pending changes must win over the mtime fallback for tracked backups."""
    repo = tmp_path
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test User")

    backup_relative = "backups/example.py.bak"
    _commit_path(repo, backup_relative, "old backup content", "add backup")

    for index in range(6):
        _commit_path(repo, f"file-{index}.txt", str(index), f"commit {index}")

    backup = repo / backup_relative
    backup.write_text("locally modified backup that should not be deleted", encoding="utf-8")
    os.utime(backup, (1, 1))

    removed = cleanup_old_backups(repo, max_commits=5, dry_run=False)

    assert removed == []
    assert backup.exists()


def test_cleanup_keeps_staged_historical_backup_with_old_mtime(tmp_path: Path) -> None:
    """A force-staged backup at an old path must not be deleted before commit."""
    repo = tmp_path
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test User")

    backup_relative = "backups/example.py.bak"
    _commit_path(repo, backup_relative, "old backup", "add backup")
    _git(repo, "rm", backup_relative)
    _git(repo, "commit", "-m", "remove backup")

    for index in range(6):
        _commit_path(repo, f"file-{index}.txt", str(index), f"commit {index}")

    backup = repo / backup_relative
    backup.parent.mkdir(parents=True, exist_ok=True)
    backup.write_text("new staged backup that should not be deleted", encoding="utf-8")
    os.utime(backup, (1, 1))
    _git(repo, "add", backup_relative)

    removed = cleanup_old_backups(repo, max_commits=5, dry_run=False)

    assert removed == []
    assert backup.exists()


def test_cleanup_removes_stale_clean_tracked_backup_in_head(tmp_path: Path) -> None:
    """Guardrail: a tracked, unmodified backup last committed beyond max_commits is
    still deleted — the fix must not over-preserve genuinely stale backups."""
    repo = tmp_path
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test User")

    backup_relative = "backups/example.py.bak"
    _commit_path(repo, backup_relative, "old backup content", "add backup")

    for index in range(6):
        _commit_path(repo, f"file-{index}.txt", str(index), f"commit {index}")

    backup = repo / backup_relative

    removed = cleanup_old_backups(repo, max_commits=5, dry_run=False)

    assert removed == [backup]
    assert not backup.exists()
