#!/usr/bin/env python3
import sys
from pathlib import Path

# Maximum line count allowed unless whitelisted
MAX_LINES = 800

# Files that are currently allowed to exceed the limit.
# These must be relative paths from the repository root.
# Outliers should be documented and eventually decomposed/refactored.
WHITELIST: set[str] = set()

def check_file_sizes(repo_root: Path | None = None) -> bool:
    if repo_root is None:
        repo_root = Path(__file__).resolve().parent.parent
    has_errors = False

    # Directories to scan
    scan_dirs = ["src", "scripts", "dev-docs"]

    # File patterns to check
    extensions = {".py", ".md"}

    for dir_name in scan_dirs:
        target_dir = repo_root / dir_name
        if not target_dir.exists():
            continue

        for file_path in target_dir.rglob("*"):
            if not file_path.is_file():
                continue
            if file_path.suffix not in extensions:
                continue

            # Get relative path for whitelist checking
            try:
                rel_path = file_path.relative_to(repo_root)
                rel_path_str = rel_path.as_posix()
            except ValueError:
                continue

            # Read line count
            try:
                # Use utf-8 with surrogateescape to avoid decoding issues on non-standard characters
                with open(file_path, "r", encoding="utf-8", errors="surrogateescape") as f:
                    lines = sum(1 for _ in f)
            except Exception as e:
                print(f"Error reading {rel_path_str}: {e}", file=sys.stderr)
                continue

            if lines > MAX_LINES:
                if rel_path_str in WHITELIST:
                    # Permitted outlier, print an advisory note
                    print(f"INFO: Whitelisted outlier {rel_path_str} has {lines} lines (limit: {MAX_LINES})")
                else:
                    print(f"ERROR: {rel_path_str} exceeds line limit: {lines} lines (max: {MAX_LINES})", file=sys.stderr)
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
