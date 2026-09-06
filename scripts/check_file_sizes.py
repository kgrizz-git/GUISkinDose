#!/usr/bin/env python3
import sys
from pathlib import Path

# Maximum line count allowed unless whitelisted
MAX_LINES = 800

# Files that are currently allowed to exceed the limit.
# These must be relative paths from the repository root.
# Outliers should be documented and eventually decomposed/refactored.
WHITELIST: set[str] = {
    "dev-docs/plans/PR_CODE_REVIEW_FIXES_PLAN.md",
    # Near limit before Phase 2 docstrings (797 lines); public method docs land at 828.
    "src/guiskindose/gui/tabs/geometry_builders.py",
}


def _iter_checked_files(repo_root: Path):
    """Yield supported files under the repository roots checked by this gate."""
    for directory_name in ("src", "scripts", "dev-docs"):
        directory = repo_root / directory_name
        if directory.exists():
            yield from (path for path in directory.rglob("*") if path.is_file() and path.suffix in {".py", ".md"})


def _check_file_size(file_path: Path, repo_root: Path) -> bool:
    """Check one file, returning false only for a non-whitelisted size violation."""
    try:
        relative_path = file_path.relative_to(repo_root).as_posix()
    except ValueError:
        return True
    try:
        with file_path.open("r", encoding="utf-8", errors="surrogateescape") as file_handle:
            line_count = sum(1 for _ in file_handle)
    except OSError as exc:
        print(f"Error reading {relative_path}: {exc}", file=sys.stderr)
        return True
    if line_count <= MAX_LINES:
        return True
    if relative_path in WHITELIST:
        print(f"INFO: Whitelisted outlier {relative_path} has {line_count} lines (limit: {MAX_LINES})")
        return True
    print(f"ERROR: {relative_path} exceeds line limit: {line_count} lines (max: {MAX_LINES})", file=sys.stderr)
    return False


def check_file_sizes(repo_root: Path | None = None) -> bool:
    """Return whether every checked source/document file fits the line budget."""
    if repo_root is None:
        repo_root = Path(__file__).resolve().parent.parent
    has_errors = False
    for file_path in _iter_checked_files(repo_root):
        if not _check_file_size(file_path, repo_root):
            has_errors = True
    return not has_errors

if __name__ == "__main__":
    success = check_file_sizes()
    if not success:
        print("ERROR: File size validation failed. Please keep source and documentation files under 800 lines.", file=sys.stderr)
        sys.exit(1)
    else:
        print("SUCCESS: All checked files are within limits.")
        sys.exit(0)
