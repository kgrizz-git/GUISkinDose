#!/usr/bin/env python3
"""Report documentation that may need pruning or archiving.

This check is advisory by default: it prints stale active execution plans and
assessments, but exits 0 unless ``--strict`` is passed. Documentation can be
historically useful, so this script should not auto-delete maintainer docs.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

DEFAULT_MAX_DAYS = 30
DEFAULT_MAX_COMMITS = 10


@dataclass(frozen=True)
class GitAge:
    days_since_touch: int
    commits_since_touch: int | None


@dataclass(frozen=True)
class PruningCandidate:
    path: Path
    category: str
    days_since_touch: int
    commits_since_touch: int | None
    recommendation: str


class GitAgeProvider(Protocol):
    def __call__(self, relative_path: str) -> GitAge | None:
        ...


def repo_root_from_script() -> Path:
    return Path(__file__).resolve().parent.parent


def _run_git(repo_root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )


def git_age_provider(repo_root: Path, *, now: int | None = None) -> GitAgeProvider:
    current_time = int(time.time()) if now is None else now

    def _age(relative_path: str) -> GitAge | None:
        last = _run_git(repo_root, "log", "-1", "--format=%H:%ct", "--", relative_path)
        value = last.stdout.strip()
        if last.returncode != 0 or not value or ":" not in value:
            return None

        last_commit, raw_timestamp = value.rsplit(":", 1)
        if not last_commit or not raw_timestamp.isdigit():
            return None

        days_since_touch = max(0, (current_time - int(raw_timestamp)) // 86_400)
        count = _run_git(repo_root, "rev-list", "--count", f"{last_commit}..HEAD")
        commits_since_touch = int(count.stdout.strip()) if count.returncode == 0 and count.stdout.strip().isdigit() else None
        return GitAge(days_since_touch=days_since_touch, commits_since_touch=commits_since_touch)

    return _age


def iter_prunable_docs(repo_root: Path) -> list[tuple[Path, str, str]]:
    """Return ``(path, category, recommendation)`` tuples for docs with retention rules."""
    candidates: list[tuple[Path, str, str]] = []

    plans_dir = repo_root / "dev-docs" / "plans"
    if plans_dir.is_dir():
        for path in sorted(plans_dir.glob("*.md")):
            if path.name.endswith("_PLAN.md"):
                continue
            candidates.append(
                (
                    path,
                    "active execution plan",
                    "archive under dev-docs/plans/archive/ if complete or superseded",
                )
            )

    assessments_dir = repo_root / "dev-docs" / "assessments"
    if assessments_dir.is_dir():
        for path in sorted(assessments_dir.glob("*.md")):
            candidates.append(
                (
                    path,
                    "assessment",
                    "review for freshness; keep if still referenced, otherwise archive or delete intentionally",
                )
            )

    return candidates


def collect_pruning_candidates(
    repo_root: Path,
    *,
    max_days: int = DEFAULT_MAX_DAYS,
    max_commits: int = DEFAULT_MAX_COMMITS,
    age_provider: GitAgeProvider | None = None,
) -> list[PruningCandidate]:
    age_for = age_provider or git_age_provider(repo_root)
    stale: list[PruningCandidate] = []

    for path, category, recommendation in iter_prunable_docs(repo_root):
        relative_path = path.relative_to(repo_root).as_posix()
        age = age_for(relative_path)
        if age is None or age.commits_since_touch is None:
            continue
        if age.days_since_touch < max_days or age.commits_since_touch < max_commits:
            continue

        stale.append(
            PruningCandidate(
                path=Path(relative_path),
                category=category,
                days_since_touch=age.days_since_touch,
                commits_since_touch=age.commits_since_touch,
                recommendation=recommendation,
            )
        )

    return stale


def format_candidate(candidate: PruningCandidate) -> str:
    return (
        f"warning {candidate.path}: stale {candidate.category} "
        f"({candidate.days_since_touch} days, {candidate.commits_since_touch} commits since last touch) - "
        f"{candidate.recommendation}"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Report stale docs that may need pruning or archiving.")
    parser.add_argument("--repo-root", type=Path, default=repo_root_from_script())
    parser.add_argument("--max-days", type=int, default=DEFAULT_MAX_DAYS)
    parser.add_argument("--max-commits", type=int, default=DEFAULT_MAX_COMMITS)
    parser.add_argument("--strict", action="store_true", help="Exit 1 when stale candidates are found.")
    args = parser.parse_args(argv)

    if args.max_days < 1:
        parser.error("--max-days must be at least 1")
    if args.max_commits < 1:
        parser.error("--max-commits must be at least 1")

    repo_root = args.repo_root.resolve()
    stale = collect_pruning_candidates(repo_root, max_days=args.max_days, max_commits=args.max_commits)
    for candidate in stale:
        print(format_candidate(candidate), file=sys.stderr)

    if stale:
        print(
            f"Doc pruning found {len(stale)} stale candidate(s). "
            "This is advisory unless --strict is used.",
            file=sys.stderr,
        )
        return 1 if args.strict else 0

    print("Doc pruning OK.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
