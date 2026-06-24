#!/usr/bin/env python3
"""Warn when PNG/HTML files outside PlotOutputs are untracked or gitignored.

Repository policy keeps ``*.png`` and ``*.html`` in ``.gitignore`` so local dose-map
exports do not clutter ``git status``, with ``!docs/**/*.png`` as the only broad
exception. Tracked assets under other paths (e.g. ``wiki/``) can silently fall out of
version control when someone runs ``git rm --cached``. This check is **advisory** by
default (exit 0); pass ``--strict`` to fail CI or pre-commit when warnings exist.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path, PurePosixPath

ASSET_SUFFIXES = {".png", ".html"}

# Paths where ignored PNG/HTML are expected (local outputs and build trees).
EXCLUDED_PREFIXES = (
    "PlotOutputs/",
    "docs/_build/",
    "site/",
    "htmlcov/",
    "build/",
    "dist/",
    ".venv/",
    "venv/",
    ".tox/",
    ".nox/",
    ".hypothesis/",
    ".mypy_cache/",
    ".ruff_cache/",
    ".pytest_cache/",
    ".basedpyright/",
)

EXCLUDED_DIR_NAMES = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    "node_modules",
    ".ipynb_checkpoints",
}


def repo_root_from_script() -> Path:
    return Path(__file__).resolve().parent.parent


def _normalize_repo_path(path_str: str) -> str:
    return PurePosixPath(path_str.replace("\\", "/")).as_posix()


def _is_asset_path(path_str: str) -> bool:
    return Path(path_str).suffix.lower() in ASSET_SUFFIXES


def _is_excluded_path(path_str: str) -> bool:
    normalized = _normalize_repo_path(path_str)
    if any(normalized == prefix.rstrip("/") or normalized.startswith(prefix) for prefix in EXCLUDED_PREFIXES):
        return True
    return any(part in EXCLUDED_DIR_NAMES for part in PurePosixPath(normalized).parts)


def _run_git(repo_root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )


def _collect_tracked_but_ignored(repo_root: Path, git_ls_files_output: str | None = None) -> list[str]:
    if git_ls_files_output is None:
        result = _run_git(repo_root, "ls-files", "-ci", "--exclude-standard")
        if result.returncode != 0:
            raise RuntimeError(f"git ls-files failed: {result.stderr.strip()}")
        git_ls_files_output = result.stdout

    paths: list[str] = []
    for line in git_ls_files_output.splitlines():
        path_str = line.strip()
        if not path_str or not _is_asset_path(path_str) or _is_excluded_path(path_str):
            continue
        paths.append(path_str)
    return sorted(set(paths))


def _collect_status_asset_paths(repo_root: Path, git_status_output: str | None = None) -> list[tuple[str, str]]:
    """Return (status_code, path) for untracked or ignored asset files."""
    if git_status_output is None:
        result = _run_git(repo_root, "status", "--ignored", "--porcelain", "-u", "--no-renames")
        if result.returncode != 0:
            raise RuntimeError(f"git status failed: {result.stderr.strip()}")
        git_status_output = result.stdout

    matches: list[tuple[str, str]] = []
    for line in git_status_output.splitlines():
        if len(line) < 4:
            continue
        status = line[:2].strip()
        path_str = line[3:].strip()
        if status not in {"??", "!!"}:
            continue
        if not _is_asset_path(path_str) or _is_excluded_path(path_str):
            continue
        matches.append((status, path_str))
    return matches


def check_ignored_asset_files(
    *,
    repo_root: Path | None = None,
    git_ls_files_output: str | None = None,
    git_status_output: str | None = None,
    strict: bool = False,
) -> bool:
    """Print advisory warnings for stray PNG/HTML assets. Returns True if no warnings."""
    root = repo_root or repo_root_from_script()
    warnings: list[str] = []

    for path_str in _collect_tracked_but_ignored(root, git_ls_files_output):
        warnings.append(
            f"tracked but gitignored (may be dropped by `git rm --cached`): {path_str}\n"
            f"       Force-add (`git add -f {path_str}`), move under docs/, or add a targeted\n"
            f"       `!path` exception in .gitignore if this asset must stay in version control."
        )

    status_hits = _collect_status_asset_paths(root, git_status_output)
    tracked_ignored = set(_collect_tracked_but_ignored(root, git_ls_files_output))
    for status, path_str in status_hits:
        if path_str in tracked_ignored:
            continue
        if status == "!!":
            warnings.append(
                f"gitignored asset on disk: {path_str}\n"
                f"       If intentional local output, move it under PlotOutputs/. Otherwise track it\n"
                f"       (`git add -f {path_str}`) or relocate under docs/."
            )
        else:
            warnings.append(
                f"untracked asset outside PlotOutputs/: {path_str}\n"
                f"       Add it to git if it belongs in the repo, or move generated output under PlotOutputs/."
            )

    if warnings:
        header = (
            "WARNING: PNG/HTML files outside PlotOutputs/ are untracked or gitignored.\n"
            "         The *.png / *.html rules can hide assets from version control."
        )
        print(header, file=sys.stderr)
        for message in warnings:
            print(f"  - {message}", file=sys.stderr)

    if strict and warnings:
        return False
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit 1 when warnings are found (optional CI/release gate).",
    )
    args = parser.parse_args()
    ok = check_ignored_asset_files(strict=args.strict)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
