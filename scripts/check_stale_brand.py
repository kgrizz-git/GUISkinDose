#!/usr/bin/env python3
"""Check for stale MyPySkinDose brand strings.

Scans git-tracked text files. ``CHANGELOG.md`` is not wholly exempt: Unreleased
(and any later ``1.x`` sections) are scanned, then the gate stops at the first
``## [25.`` historical header. Dual-read leftovers and rename-prose phrases are
allowlisted; an unquoted ``import mypyskindose`` in Unreleased still fails.
"""

import re
import subprocess
import sys
from pathlib import Path

# After the src/ rename, any value other than "mypyskindose" (including None) makes
# leftover pre-rename package/brand tokens fail this gate. Dual-read fallbacks and
# historical identity phrases are allowlisted in ALLOWED_PATTERNS, not here.
LIVE_PACKAGE_NAME = "guiskindose"

BAD_STRINGS = ["mypyskindose", "MyPySkinDose", "MYPYSKINDOSE_"]

# Files or directories that are permanently allowed to contain the stale brand.
ALLOWED_PATHS = [
    "dev-docs/plans/archive/",
    "dev-docs/assessments/",
    "dev-docs/plans/GUISKINDOSE_RENAME_PLAN.md",
    "dev-docs/plans/GUISKINDOSE_GITHUB_RENAME_PLAN.md",
    "dev-docs/plans/GUISKINDOSE_PRIVACY_REPUBLICATION_PLAN.md",
    "dev-docs/COORD_TRANSFORM_COMPARISON.md",
    "dev-docs/GUISKINDOSE_MIGRATION_STATUS.md",  # created in PR 1; allowlist it now
    "scripts/check_stale_brand.py",
    "tests/unittests/test_check_stale_brand.py",
    "scripts/rewrite_package_paths.py",
    "tests/unittests/test_rewrite_package_paths.py",
]

# Patterns within a line that are permanently allowed.
# (The pre-rename GitHub URL / Sonar key patterns were removed 2026-09-04: the live
# strings now point at GUISkinDose, and the gate REJECTS the old live URLs/keys.)
ALLOWED_PATTERNS = [
    re.compile(r"#\s*nosemgrep:\s*mypyskindose-[a-zA-Z0-9_-]+"),
    re.compile(r"id:\s*mypyskindose-[a-zA-Z0-9_-]+"),
    # Rule IDs in tests (e.g., "mypyskindose-unsafe-gui-export-write")
    # Exclude temp prefixes and the semgrep yaml file name itself that must be renamed.
    re.compile(r"[\"']mypyskindose-(?!uploads|export|semgrep|hounddog|privacy)[a-zA-Z0-9_-]+[\"']"),
    # Dual-read config/env leftovers that must remain until users migrate.
    # Scoped to the exact leftover forms so a live `from .mypyskindose import x`
    # or `pkg.mypyskindose` still fails the gate.
    re.compile(r"MYPYSKINDOSE_SHOW_DEMO_PHANTOMS"),
    re.compile(r"~/\.mypyskindose"),
    re.compile(r"\.mypyskindose\.local\.json"),
    re.compile(r"""["']\.mypyskindose["']"""),
    re.compile(r"mypyskindose-privacy\.yml"),
    # Historical identity (formerly the MyPySkinDose / mypyskindose names).
    # Case-insensitive so "Formerly MyPySkinDose" prose variants cannot slip through.
    re.compile(r"(?i)formerly\s+[`']?mypyskindose[`']?"),
    re.compile(r"(?i)formerly\s+MyPySkinDose"),
    re.compile(r"MyPySkinDose\s+[`']?25\.2\.0[`']?"),
    # Dual-read traceback sanitizer: package dir names in Path.parts.
    re.compile(r"""\(['\"]guiskindose['\"],\s*['\"]mypyskindose['\"]\)"""),
    re.compile(r"``mypyskindose/?``"),
]

# Keep a Changelog MyPySkinDose version sections (## [25.x.x] and older).
CHANGELOG_HISTORICAL_START = re.compile(r"^## \[25\.")

# Extra allowances only in CHANGELOG.md before the first historical 25.x header.
# These describe the rename and pre-rename Unreleased work; they must not hide
# an unquoted ``import mypyskindose``.
CHANGELOG_CURRENT_PATTERNS = [
    re.compile(r"src/mypyskindose"),
    re.compile(r"legacy mypyskindose"),
    re.compile(r"mypyskindose → guiskindose"),
    re.compile(r"[`'\"]mypyskindose(?:-\*)?[`'\"]"),
    re.compile(r"not MyPySkinDose"),
    re.compile(r"MyPySkinDose [`']?26\.0\.0[`']?"),
    re.compile(r"python -m mypyskindose"),
    re.compile(r"[`']MyPySkinDose[`']"),
    re.compile(r"remain MyPySkinDose history"),
]


def is_path_allowed(rel_path: str) -> bool:
    """Return True when *rel_path* is an allowlisted file or under an allowlisted directory.

    Directory entries in ``ALLOWED_PATHS`` end with ``/`` and match as a prefix.
    File entries match exactly so a suffix such as ``scripts/check_stale_brand.py.backup`` is not exempt.
    """
    return any(
        rel_path.startswith(allowed) if allowed.endswith("/") else rel_path == allowed for allowed in ALLOWED_PATHS
    )


def get_git_files(repo_root: Path) -> list[str]:
    """Return all git-tracked files."""
    try:
        output = subprocess.check_output(["git", "ls-files"], cwd=repo_root, text=True, stderr=subprocess.DEVNULL)
        return output.splitlines()
    except (subprocess.CalledProcessError, OSError):
        # Fallback if git fails (e.g. not in a git repo)
        return [
            p.relative_to(repo_root).as_posix()
            for p in repo_root.rglob("*")
            if p.is_file() and ".git" not in p.parts and ".venv" not in p.parts
        ]


def _is_probably_text(path: Path) -> bool:
    """Skip NUL-containing files so the gate does not scan binaries."""
    try:
        with path.open("rb") as handle:
            sample = handle.read(4096)
    except OSError:
        return False
    return b"\x00" not in sample


def check_file(path: Path, repo_root: Path, live_package_name: str | None = LIVE_PACKAGE_NAME) -> list[str]:
    """Check a file and return a list of error lines."""
    try:
        rel_path = path.relative_to(repo_root).as_posix()
    except ValueError:
        return []

    if is_path_allowed(rel_path):
        return []
    if not _is_probably_text(path):
        return []

    errors = []
    changelog_current = rel_path == "CHANGELOG.md"
    try:
        with path.open("r", encoding="utf-8", errors="surrogateescape") as f:
            for line_no, line in enumerate(f, start=1):
                if changelog_current and CHANGELOG_HISTORICAL_START.match(line):
                    break
                # We skip checking very long lines to save time, unless they contain bad strings anyway.
                if not any(bad in line for bad in BAD_STRINGS):
                    continue

                line_to_check = line
                # Strip permanently allowed patterns
                for pattern in ALLOWED_PATTERNS:
                    line_to_check = pattern.sub("", line_to_check)
                if changelog_current:
                    for pattern in CHANGELOG_CURRENT_PATTERNS:
                        line_to_check = pattern.sub("", line_to_check)

                # Kept for tests (test_stale_brand_live_package_allowance) and PR 0 mode;
                # production LIVE_PACKAGE_NAME is guiskindose.
                if live_package_name == "mypyskindose":
                    for bad in BAD_STRINGS:
                        line_to_check = line_to_check.replace(bad, "")

                # Check for any remaining bad strings
                for bad in BAD_STRINGS:
                    if bad in line_to_check:
                        # Print only a snippet
                        snippet = line.strip()
                        if len(snippet) > 100:
                            snippet = snippet[:100] + "..."
                        errors.append(f"{rel_path}:{line_no}: {snippet}")
                        break
    except OSError:
        # Skip unreadable files so one permission error cannot abort the repo-wide gate.
        return []

    return errors


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    files = get_git_files(repo_root)

    all_errors = []
    for rel_path in files:
        # Skip binary noise
        if rel_path == "uv.lock":
            continue
        file_path = repo_root / rel_path
        if file_path.exists():
            all_errors.extend(check_file(file_path, repo_root))

    if all_errors:
        print("ERROR: Stale brand strings found:", file=sys.stderr)
        for error in all_errors:
            print(error, file=sys.stderr)
        return 1

    print("SUCCESS: No disallowed stale brand strings found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
