#!/usr/bin/env python3
"""Check for stale MyPySkinDose brand strings."""

import re
import subprocess
import sys
from pathlib import Path

# PR 0 live-package allowance.
# PR 1 will delete this constant or change it to "guiskindose" / None.
LIVE_PACKAGE_NAME = "mypyskindose"

BAD_STRINGS = ["mypyskindose", "MyPySkinDose", "MYPYSKINDOSE_"]

# Files or directories that are permanently allowed to contain the stale brand.
ALLOWED_PATHS = [
    "dev-docs/plans/archive/",
    "dev-docs/assessments/",
    "CHANGELOG.md",  # PR 1 should tighten this to only allow historical sections
    "dev-docs/plans/GUISKINDOSE_RENAME_PLAN.md",
    "dev-docs/plans/GUISKINDOSE_PRIVACY_REPUBLICATION_PLAN.md",
    "dev-docs/COORD_TRANSFORM_COMPARISON.md",
    "GUISKINDOSE_MIGRATION_STATUS.md",
    "scripts/check_stale_brand.py",
    "tests/unittests/test_check_stale_brand.py",
]

# Patterns within a line that are permanently allowed.
ALLOWED_PATTERNS = [
    re.compile(r"github\.com/kgrizz-git/MyPySkinDose"),
    re.compile(r"kgrizz-git_MyPySkinDose"),
    re.compile(r"sonar\.projectName=MyPySkinDose"),
    re.compile(r"#\s*nosemgrep:\s*mypyskindose-[a-zA-Z0-9_-]+"),
    re.compile(r"id:\s*mypyskindose-[a-zA-Z0-9_-]+"),
    # Rule IDs in tests (e.g., "mypyskindose-unsafe-gui-export-write")
    # Exclude temp prefixes and the semgrep yaml file name itself that must be renamed.
    re.compile(r"[\"']mypyskindose-(?!uploads|export|semgrep|hounddog|privacy)[a-zA-Z0-9_-]+[\"']"),
]

def is_path_allowed(rel_path: str) -> bool:
    return any(rel_path == allowed or rel_path.startswith(allowed) for allowed in ALLOWED_PATHS)

def get_git_files(repo_root: Path) -> list[str]:
    """Return all git-tracked files."""
    try:
        output = subprocess.check_output(
            ["git", "ls-files"], cwd=repo_root, text=True, stderr=subprocess.DEVNULL
        )
        return output.splitlines()
    except subprocess.CalledProcessError:
        # Fallback if git fails (e.g. not in a git repo)
        return [
            p.relative_to(repo_root).as_posix()
            for p in repo_root.rglob("*")
            if p.is_file() and ".git" not in p.parts and ".venv" not in p.parts
        ]

def check_file(path: Path, repo_root: Path, live_package_name: str | None = LIVE_PACKAGE_NAME) -> list[str]:
    """Check a file and return a list of error lines."""
    try:
        rel_path = path.relative_to(repo_root).as_posix()
    except ValueError:
        return []

    if is_path_allowed(rel_path):
        return []

    errors = []
    try:
        with path.open("r", encoding="utf-8", errors="surrogateescape") as f:
            for line_no, line in enumerate(f, start=1):
                # We skip checking very long lines to save time, unless they contain bad strings anyway.
                if not any(bad in line for bad in BAD_STRINGS):
                    continue

                line_to_check = line
                # Strip permanently allowed patterns
                for pattern in ALLOWED_PATTERNS:
                    line_to_check = pattern.sub("", line_to_check)
                
                # If PR 0 live-package allowance is active, strip all bad strings.
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
        pass
    
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
