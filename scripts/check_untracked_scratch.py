#!/usr/bin/env python3
import sys
import subprocess
from pathlib import Path

# Patterns in filenames that suggest they are scratch/temporary files
SCRATCH_PATTERNS = ["scratch", "temp", "tmp", "debug_"]
SCRATCH_DIRS = {"tmp", "temp", "scratch"}

def check_untracked_scratch(mock_git_output: str | None = None) -> bool:
    repo_root = Path(__file__).resolve().parent.parent
    has_errors = False

    if mock_git_output is not None:
        stdout = mock_git_output
    else:
        try:
            # Run git status --porcelain to find untracked files (marked by '??')
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                capture_output=True,
                text=True,
                check=True,
                cwd=str(repo_root)
            )
            stdout = result.stdout
        except subprocess.SubprocessError as e:
            print(f"Error running git status: {e}", file=sys.stderr)
            # Fail-safe to true if git isn't available or fails
            return True

    untracked_files = []
    # Exclude checking the validator script itself and its unit test
    exclusions = {
        "scripts/check_untracked_scratch.py",
        "tests/unittests/test_check_untracked_scratch.py",
    }
    
    for line in stdout.splitlines():
        if line.startswith("?? "):
            # Get the path of the untracked file
            file_path_str = line[3:].strip()
            if file_path_str not in exclusions:
                untracked_files.append(file_path_str)

    for file_str in untracked_files:
        path = Path(file_str)
        name_lower = path.name.lower()
        parts_lower = {part.lower() for part in path.parts}

        # Check if the filename contains scratch patterns
        matches_pattern = any(pat in name_lower for pat in SCRATCH_PATTERNS)
        in_scratch_dir = bool(parts_lower & SCRATCH_DIRS)

        if matches_pattern or in_scratch_dir:
            print(
                f"ERROR: Found untracked scratch/temp file in non-ignored path: {file_str}\n"
                f"       Please delete this file, or rename/move it so it is gitignored (e.g., prefixing with 'scratch_').",
                file=sys.stderr
            )
            has_errors = True

    return not has_errors

if __name__ == "__main__":
    success = check_untracked_scratch()
    if not success:
        sys.exit(1)
    sys.exit(0)
