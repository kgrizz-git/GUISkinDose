#!/usr/bin/env python3
"""
Enforce CHANGELOG.md updates when src/ or tests/ files change.

In CI (pull_request):  compares PR head against origin/$GITHUB_BASE_REF.
Local (pre-push):      compares HEAD against the merge-base with origin/main.

Exit 0 (pass) when:
  - No src/ or tests/ files changed.
  - CHANGELOG.md is among the changed files.
  - Base ref cannot be determined (fail-open to avoid blocking offline work).
Exit 1 (fail) when src/ or tests/ files changed but CHANGELOG.md was not updated.
"""
from __future__ import annotations

import os
import subprocess
import sys


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], capture_output=True, text=True)


def changed_files(base: str) -> list[str]:
    """Files changed between base and HEAD using a three-dot merge-base diff."""
    result = _git("diff", "--name-only", f"{base}...HEAD")
    if result.returncode != 0:
        return []
    return [f for f in result.stdout.splitlines() if f]


def resolve_base() -> str | None:
    """Return a git ref to diff against, or None if undetermined."""
    base_ref = os.environ.get("GITHUB_BASE_REF")
    if base_ref:
        return f"origin/{base_ref}"

    r = _git("merge-base", "HEAD", "origin/main")
    if r.returncode == 0:
        sha = r.stdout.strip()
        if sha:
            return sha

    return None


def main() -> int:
    base = resolve_base()
    if base is None:
        print("check_changelog: base ref undetermined — skipping check.", file=sys.stderr)
        return 0

    changed = changed_files(base)
    if not changed:
        return 0

    substantive = [f for f in changed if f.startswith(("src/", "tests/"))]
    if not substantive:
        return 0

    if "CHANGELOG.md" in changed:
        return 0

    print("check_changelog: CHANGELOG.md not updated.", file=sys.stderr)
    print(
        f"  {len(substantive)} source/test file(s) changed but CHANGELOG.md was not.",
        file=sys.stderr,
    )
    print("  Add a changelog entry before pushing.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
