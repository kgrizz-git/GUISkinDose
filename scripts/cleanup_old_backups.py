#!/usr/bin/env python3
"""Remove stale agent backup files from ``backups/`` before git commit.

Purpose:
    Delete ``*.bak`` files under ``backups/`` when they are older than a
    configurable number of commits on the current branch.

Inputs:
    Repository root (auto-detected as parent of ``scripts/``, or ``--repo-root``).
    Optional ``--max-commits`` (default 5) and ``--dry-run``.

Outputs:
    Prints each deleted (or would-delete) path. Exit code 0 on success.

Usage:
    python scripts/cleanup_old_backups.py
    python scripts/cleanup_old_backups.py --dry-run
    python scripts/cleanup_old_backups.py --max-commits 5
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

DEFAULT_MAX_COMMITS = 5
BACKUPS_DIRNAME = "backups"
BACKUP_SUFFIX = ".bak"


def _run_git(repo_root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )


def _repo_root(explicit: Path | None) -> Path:
    root = explicit or Path(__file__).resolve().parent.parent
    if not (root / ".git").exists():
        raise SystemExit(f"Not a git repository: {root}")
    return root


def _is_tracked_in_head(repo_root: Path, relative_path: str) -> bool:
    """Return whether ``relative_path`` is tracked in the current ``HEAD`` tree."""
    tracked = _run_git(repo_root, "ls-tree", "--name-only", "HEAD", "--", relative_path)
    return tracked.returncode == 0 and tracked.stdout.strip() == relative_path


def _has_pending_changes(repo_root: Path, relative_path: str) -> bool:
    """Return whether ``relative_path`` has staged or unstaged changes vs the index/HEAD.

    A non-empty ``git status --porcelain`` line means the working-tree file differs
    from what is committed (e.g. a freshly recreated or force-staged backup), so it
    must not be judged stale by commit age. On any git error we assume changes are
    pending, erring toward keeping the file.
    """
    status = _run_git(repo_root, "status", "--porcelain", "--", relative_path)
    return status.returncode != 0 or bool(status.stdout.strip())


def _commits_since_last_git_touch(repo_root: Path, relative_path: str) -> int | None:
    """Return commits on HEAD since ``relative_path`` was last changed, or None if never committed."""
    if not _is_tracked_in_head(repo_root, relative_path):
        return None

    # A path can be tracked in HEAD yet have a brand-new working-tree file at it
    # (recreated and/or force-staged). Stale commit history would then wrongly age
    # out the fresh file, so defer to the mtime fallback when changes are pending.
    if _has_pending_changes(repo_root, relative_path):
        return None

    last = _run_git(repo_root, "log", "-1", "--format=%H", "--", relative_path)
    last_commit = last.stdout.strip()
    if not last_commit:
        return None

    count = _run_git(repo_root, "rev-list", "--count", f"{last_commit}..HEAD")
    if count.returncode != 0 or not count.stdout.strip().isdigit():
        return None
    return int(count.stdout.strip())


def _threshold_commit_timestamp(repo_root: Path, max_commits: int) -> int | None:
    """Unix timestamp of the commit ``max_commits`` behind HEAD, if it exists."""
    rev = _run_git(repo_root, "rev-parse", f"HEAD~{max_commits}")
    if rev.returncode != 0 or not rev.stdout.strip():
        return None

    ts = _run_git(repo_root, "show", "-s", "--format=%ct", rev.stdout.strip())
    if ts.returncode != 0 or not ts.stdout.strip().isdigit():
        return None
    return int(ts.stdout.strip())


def _is_stale_backup(
    repo_root: Path,
    backup_path: Path,
    max_commits: int,
) -> tuple[bool, str]:
    relative = backup_path.relative_to(repo_root).as_posix()
    commits_since = _commits_since_last_git_touch(repo_root, relative)

    if commits_since is not None:
        if commits_since > max_commits:
            return True, f"last touched {commits_since} commits ago"
        return False, f"last touched {commits_since} commits ago"

    if _has_pending_changes(repo_root, relative):
        return False, "has pending staged or unstaged changes"

    threshold_ts = _threshold_commit_timestamp(repo_root, max_commits)
    if threshold_ts is None:
        return False, "untracked and repository has fewer than max_commits + 1 commits"

    file_mtime = int(backup_path.stat().st_mtime)
    if file_mtime < threshold_ts:
        return True, "untracked and older than HEAD~{0}".format(max_commits)
    return False, "untracked and newer than HEAD~{0}".format(max_commits)


def cleanup_old_backups(
    repo_root: Path,
    *,
    max_commits: int = DEFAULT_MAX_COMMITS,
    dry_run: bool = False,
) -> list[Path]:
    backups_dir = repo_root / BACKUPS_DIRNAME
    if not backups_dir.is_dir():
        return []

    removed: list[Path] = []
    for backup_path in sorted(backups_dir.rglob(f"*{BACKUP_SUFFIX}")):
        if not backup_path.is_file():
            continue

        stale, reason = _is_stale_backup(repo_root, backup_path, max_commits)
        if not stale:
            continue

        removed.append(backup_path)
        action = "would remove" if dry_run else "removed"
        print(f"{action} {backup_path.relative_to(repo_root).as_posix()} ({reason})")
        if not dry_run:
            backup_path.unlink()

    return removed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Delete backup files older than N commits.")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="Repository root (default: parent of scripts/)",
    )
    parser.add_argument(
        "--max-commits",
        type=int,
        default=DEFAULT_MAX_COMMITS,
        help=f"Delete backups last touched more than this many commits ago (default: {DEFAULT_MAX_COMMITS})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print files that would be deleted without removing them",
    )
    args = parser.parse_args(argv)

    if args.max_commits < 1:
        parser.error("--max-commits must be at least 1")

    repo_root = _repo_root(args.repo_root)
    cleanup_old_backups(repo_root, max_commits=args.max_commits, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
