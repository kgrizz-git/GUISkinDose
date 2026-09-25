#!/usr/bin/env python3
"""Local SonarQube freshness gate.

Stdlib-only gate used on two hook stages:

* ``--stage commit`` (default, the pre-commit hook) blocks the commit once the
  number of commits on HEAD since the last successful local scan (plus the
  in-flight commit) reaches ``SONAR_GATE_MAX_COMMITS`` (default 10).
* ``--stage push`` (the pre-push hook) blocks the push if **any** commit has
  been made since the last scan, so a fresh scan happens before every push and
  new issues are caught right away.

Both stages point the user at the dumped issues and the refresh command.

Reads repo-root ``.env`` itself (``pre-commit`` does not load direnv) using an
``os.environ.setdefault`` pattern — never overrides an already-exported value.
Does not import application code.

The state file (``tmp/sonar-state.json`` by default) is written by
``scripts/run_sonarqube_local.py`` after each successful local analysis and by
``scripts/dump_sonar_issues.py`` (issue counts/summary paths). Only
``last_scan_commit`` is required; the remaining keys feed the hint text.

Exit codes:
    0 - gate off, or within budget.
    1 - missing/invalid state, stale (rebase/amend), or over budget / stale scan.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


DEFAULT_STATE_PATH = "tmp/sonar-state.json"
DEFAULT_MAX_COMMITS = 10
WARN_FRACTION = 0.8

REFRESH_COMMAND = "colima start default && python scripts/run_sonarqube_local.py"

# Git hook/test runners export these so child `git` uses the parent repo.
# Gate commands must honor `cwd=repo_root()` instead.
GIT_DIR_OVERRIDE_VARS = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_INDEX_FILE",
    "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_COMMON_DIR",
    "GIT_NAMESPACE",
)


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _git_cwd_env() -> dict[str, str]:
    env = os.environ.copy()
    for key in GIT_DIR_OVERRIDE_VARS:
        env.pop(key, None)
    return env


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    with open(path, encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


def env_is_on(name: str) -> bool:
    value = os.environ.get(name)
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes"}


def git_head_sha() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root(),
        text=True,
        env=_git_cwd_env(),
    ).strip()


def is_ancestor(ancestor: str, descendant: str) -> bool:
    try:
        subprocess.check_call(
            ["git", "merge-base", "--is-ancestor", ancestor, descendant],
            cwd=repo_root(),
            env=_git_cwd_env(),
        )
    except subprocess.CalledProcessError:
        return False
    return True


def commits_since(ancestor: str) -> int:
    count = subprocess.check_output(
        ["git", "rev-list", "--count", f"{ancestor}..HEAD"],
        cwd=repo_root(),
        text=True,
        env=_git_cwd_env(),
    ).strip()
    return int(count)


def load_state(state_path: Path) -> dict:
    with open(state_path, encoding="utf-8") as handle:
        return json.load(handle)


def resolve_max_commits() -> int:
    raw = os.environ.get("SONAR_GATE_MAX_COMMITS")
    if raw is None or raw == "":
        return DEFAULT_MAX_COMMITS
    try:
        value = int(raw)
    except ValueError:
        print(
            f"SONAR_GATE_MAX_COMMITS is not an integer: {raw!r}; "
            f"treating as {DEFAULT_MAX_COMMITS}.",
            file=sys.stderr,
        )
        return DEFAULT_MAX_COMMITS
    return value if value >= 1 else DEFAULT_MAX_COMMITS


def _refresh_hint(
    last_scan_commit: str,
    last_time: str,
    issues_count: object,
    issues_summary: str,
) -> str:
    return (
        f"Last scan: {last_scan_commit[:12]} at {last_time}\n"
        f"Issues on record: {issues_count}\n"
        f"Dumped issues: {issues_summary}\n"
        "Re-run the scan to refresh:\n"
        f"    {REFRESH_COMMAND}"
    )


def run_gate(state_path: Path, max_commits: int, stage: str) -> int:
    if not state_path.exists():
        print(
            "Sonar freshness gate: no scan on record (tmp/sonar-state.json missing).\n"
            "Run a baseline scan first:\n"
            f"    {REFRESH_COMMAND}",
            file=sys.stderr,
        )
        return 1

    try:
        state = load_state(state_path)
    except (json.JSONDecodeError, OSError) as exc:
        print(
            f"Sonar freshness gate: state file is invalid ({exc}).\n"
            "Re-run the scan to regenerate it:\n"
            f"    {REFRESH_COMMAND}",
            file=sys.stderr,
        )
        return 1

    last_scan_commit = state.get("last_scan_commit")
    if not last_scan_commit or not isinstance(last_scan_commit, str):
        print(
            "Sonar freshness gate: state file has no last_scan_commit.\n"
            "Re-run the scan to regenerate it:\n"
            f"    {REFRESH_COMMAND}",
            file=sys.stderr,
        )
        return 1

    last_time = state.get("last_scan_time", "unknown")
    issues_count = state.get("issues_count")
    issues_summary = state.get("issues_summary_path", "tmp/sonar-latest-issues.md")

    try:
        head_sha = git_head_sha()
    except subprocess.CalledProcessError as exc:
        print(f"Sonar freshness gate: failed to resolve HEAD ({exc}).", file=sys.stderr)
        return 1

    if not is_ancestor(last_scan_commit, head_sha):
        print(
            f"Sonar freshness gate: last scan commit {last_scan_commit[:12]} is not an "
            f"ancestor of HEAD ({head_sha[:12]}) — history was rewritten since the last scan.\n"
            f"{_refresh_hint(last_scan_commit, last_time, issues_count, issues_summary)}",
            file=sys.stderr,
        )
        return 1

    try:
        commits_count = commits_since(last_scan_commit)
    except subprocess.CalledProcessError as exc:
        print(
            f"Sonar freshness gate: failed to count commits since last scan ({exc}).",
            file=sys.stderr,
        )
        return 1

    if stage == "push":
        if commits_count > 0:
            print(
                f"Sonar freshness gate BLOCKED push: {commits_count} commit(s) "
                f"since the last scan.\n"
                f"{_refresh_hint(last_scan_commit, last_time, issues_count, issues_summary)}",
                file=sys.stderr,
            )
            return 1
        return 0

    pending = commits_count + 1  # +1 for the in-flight commit
    warn_threshold = max(1, int(max_commits * WARN_FRACTION))

    if pending >= max_commits:
        print(
            f"Sonar freshness gate BLOCKED: {pending} commits pending "
            f"(>= budget of {max_commits}, counting the in-flight commit).\n"
            f"Last scan: {last_scan_commit[:12]} at {last_time}\n"
            f"Issues on record: {issues_count}\n"
            f"Dumped issues: {issues_summary}\n"
            "Re-run the scan to reset the budget:\n"
            f"    {REFRESH_COMMAND}",
            file=sys.stderr,
        )
        return 1

    if pending >= warn_threshold:
        print(
            f"Sonar freshness gate WARNING: {pending} commits pending "
            f"(budget {max_commits}); consider re-scanning soon.\n"
            f"Last scan: {last_scan_commit[:12]} at {last_time}\n"
            f"Dumped issues: {issues_summary}",
            file=sys.stderr,
        )

    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--state",
        default=str(repo_root() / DEFAULT_STATE_PATH),
        help=f"Path to sonar-state.json (default: {DEFAULT_STATE_PATH}).",
    )
    parser.add_argument(
        "--stage",
        choices=("commit", "push"),
        default="commit",
        help="Which hook stage is running the gate (default: commit).",
    )
    args = parser.parse_args(argv)

    load_env_file(repo_root() / ".env")

    if not env_is_on("SONAR_FRESHNESS_GATE"):
        return 0

    return run_gate(Path(args.state), resolve_max_commits(), args.stage)


if __name__ == "__main__":
    raise SystemExit(main())
