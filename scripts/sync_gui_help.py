#!/usr/bin/env python3
"""Mirror GUI help markdown from ``docs/source/gui_help/`` to ``src/mypyskindose/gui/help/``.

The docs directory is the single source of truth for in-app help content;
this script keeps the bundled copies in ``src/`` in sync. The standard
library is used so the script has no runtime dependencies and can be
invoked by pre-commit and CI without a virtual environment.
"""

from __future__ import annotations

import argparse
import filecmp
import sys
from pathlib import Path

SOURCE_REPO_SUBDIR = Path("docs/source/gui_help")
TARGET_REPO_SUBDIR = Path("src/mypyskindose/gui/help")


def repo_root_from_script() -> Path:
    return Path(__file__).resolve().parent.parent


def read_text(path: Path) -> str:
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        return fh.read().replace("\r\n", "\n").replace("\r", "\n")


def write_text(path: Path, text: str) -> None:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    with path.open("w", encoding="utf-8", newline="") as fh:
        fh.write(normalized)


def validate_source(source: Path) -> list[Path]:
    if not source.exists():
        sys.stderr.write(f"error: source directory does not exist: {source}\n")
        sys.exit(1)
    if not source.is_dir():
        sys.stderr.write(f"error: source path is not a directory: {source}\n")
        sys.exit(1)
    sources: list[Path] = []
    for entry in sorted(source.iterdir()):
        if entry.is_dir():
            sys.stderr.write(
                f"error: subdirectories are not allowed in {source}: {entry.name}\n"
            )
            sys.exit(1)
        if entry.suffix == ".md":
            sources.append(entry)
    if not sources:
        sys.stderr.write(
            f"error: source directory is empty: {source}\n"
            "       refusing to run to avoid deleting all target files.\n"
        )
        sys.exit(1)
    return sources


def diff_files(source: Path, target: Path) -> bool:
    if not target.exists():
        return True
    try:
        return not filecmp.cmp(str(source), str(target), shallow=False)
    except (OSError, ValueError):
        return True


def _prepare_target(target_dir: Path, *, check: bool) -> None:
    """Create a write target or fail safely when a check target is missing."""
    if not check and not target_dir.exists():
        target_dir.mkdir(parents=True, exist_ok=True)
    elif check and not target_dir.exists():
        sys.stderr.write(f"error: target directory does not exist: {target_dir}\n")
        sys.exit(1)


def _sync_source_files(sources: list[Path], target_dir: Path, *, check: bool) -> tuple[list[str], list[str]]:
    """Mirror changed source files and return drift names with completed actions."""
    drift: list[str] = []
    actions: list[str] = []
    for source_path in sources:
        target_path = target_dir / source_path.name
        if diff_files(source_path, target_path):
            drift.append(source_path.name)
            if not check:
                write_text(target_path, read_text(source_path))
                actions.append(f"mirrored {source_path.name}")
    return drift, actions


def _remove_stale_targets(target_dir: Path, source_basenames: set[str], *, check: bool) -> tuple[list[str], list[str]]:
    """Report or remove target-only help files without changing output ordering."""
    drift: list[str] = []
    actions: list[str] = []
    for target_path in target_dir.glob("*.md"):
        if target_path.name not in source_basenames:
            drift.append(f"stale {target_path.name}")
            if not check:
                target_path.unlink()
                actions.append(f"removed stale {target_path.name}")
    return drift, actions


def sync(
    source_dir: Path,
    target_dir: Path,
    *,
    check: bool,
) -> int:
    sources = validate_source(source_dir)
    _prepare_target(target_dir, check=check)
    source_basenames = {path.name for path in sources}
    source_drift, source_actions = _sync_source_files(sources, target_dir, check=check)
    stale_drift, stale_actions = _remove_stale_targets(target_dir, source_basenames, check=check)
    drift = [*source_drift, *stale_drift]
    actions = [*source_actions, *stale_actions]

    if check:
        if drift:
            sys.stderr.write(
                "error: GUI help files are out of sync; run "
                "scripts/sync_gui_help.py to fix:\n"
            )
            for name in drift:
                sys.stderr.write(f"  - {name}\n")
            return 1
        return 0

    if actions:
        print("GUI help sync:")
        for action in actions:
            print(f"  {action}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Mirror docs/source/gui_help/*.md to "
            "src/mypyskindose/gui/help/*.md (or check with --check)."
        )
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit non-zero if target is out of sync; do not write or delete files.",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=repo_root_from_script(),
        help="Repository root (default: parent of scripts/).",
    )
    args = parser.parse_args(argv)

    repo_root = args.repo_root.resolve()
    source_dir = repo_root / SOURCE_REPO_SUBDIR
    target_dir = repo_root / TARGET_REPO_SUBDIR
    return sync(source_dir, target_dir, check=args.check)


if __name__ == "__main__":
    sys.exit(main())
