#!/usr/bin/env python3
"""
Enforce CHANGELOG.md updates when src/ or tests/ files change.

In CI (pull_request):  compares PR head against origin/$GITHUB_BASE_REF.
Local (pre-push):      compares HEAD against the merge-base with origin/main.

Exit 0 (pass) when:
  - No src/ or tests/ files changed.
  - CHANGELOG.md is among the changed files.
  - The only non-test changes add or remove `#` comments, and MAINTENANCE_LOG.md is updated.
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


def _changed_lines(base: str, path: str) -> tuple[list[str], list[str]] | None:
    """Added and removed content lines for ``path``, or None if the diff is unreadable.

    File headers (``+++``/``---``) are dropped by exact prefix rather than by looking at the
    following characters: an earlier version skipped any added line starting with ``++``,
    which also hid a real statement like ``++i`` from the check.
    """
    result = _git("diff", "--unified=0", f"{base}...HEAD", "--", path)
    if result.returncode != 0:
        return None
    added: list[str] = []
    removed: list[str] = []
    for line in result.stdout.splitlines():
        if line.startswith(("+++", "---")):
            continue
        if line.startswith("+"):
            added.append(line[1:].strip())
        elif line.startswith("-"):
            removed.append(line[1:].strip())
    return added, removed


def is_comment_only(base: str, path: str) -> bool:
    """Whether a Python file's diff only adds or removes ``#`` comments and blank lines.

    Deliberately literal rather than clever, twice over. A first version allowed any added
    line lacking a statement-like marker so docstring prose would qualify, but a bare
    ``return None`` has no marker either and slipped through. A second version inspected only
    *added* lines, which let the everyday "comment out the code" edit through — delete
    ``x = compute_psd()``, add ``# temporarily disabled`` — a behavioural change with no
    changelog entry. Removed lines are therefore held to the same rule as added ones.

    The cost is that a docstring-only edit still demands a CHANGELOG entry. That is the safe
    direction: the exemption exists so a comment need not be announced to users, not to make
    the changelog optional for anything that merely looks harmless.
    """
    if not path.endswith(".py"):
        return False
    changed = _changed_lines(base, path)
    if changed is None:
        return False
    added, removed = changed
    if not added and not removed:
        return False
    return all(not line or line.startswith("#") for line in (*added, *removed))


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

    # Process-only exemption: when the only src/tests changes are test files
    # and the PR also touches MAINTENANCE_LOG.md (the maintainer-facing log),
    # the entry belongs there, not in the user-facing CHANGELOG. Backlog
    # cleanups (TO_DO item removals with test pinning) are the recurring case.
    non_test = [f for f in substantive if not f.startswith("tests/")]
    if not non_test and "dev-docs/MAINTENANCE_LOG.md" in changed:
        return 0

    # Same exemption, extended to src changes whose added and removed lines are all comments.
    # CHANGELOG.md documents its own scope as notable *user-facing* changes and points
    # maintainer-facing work at MAINTENANCE_LOG.md, so a comment has no honest entry in it;
    # demanding one there trains readers to skim the file. Any behavioural change still
    # requires CHANGELOG.md: is_comment_only() disqualifies a file as soon as any added OR
    # removed line looks like a statement, so commenting code out does not qualify either.
    if "dev-docs/MAINTENANCE_LOG.md" in changed and all(is_comment_only(base, f) for f in non_test):
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
