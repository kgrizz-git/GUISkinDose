#!/usr/bin/env python3
"""Open an ignored local working copy of the getting-started notebook.

The tracked notebook remains a clean documentation source. This launcher creates
``tmp/notebooks/getting_started.local.ipynb`` on first use, then opens that
ignored copy in JupyterLab so execution counts and outputs do not dirty Git.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CANONICAL_NOTEBOOK = REPO_ROOT / "docs" / "source" / "getting_started" / "getting_started.ipynb"
LOCAL_NOTEBOOK = REPO_ROOT / "tmp" / "notebooks" / "getting_started.local.ipynb"


def prepare_local_notebook(source: Path, target: Path, *, reset: bool = False) -> bool:
    """Create or explicitly refresh ``target`` from the canonical ``source``.

    Returns ``True`` when a copy was created or refreshed. Existing local work
    is preserved unless the caller explicitly requests ``reset=True``.
    """
    if not source.is_file():
        raise FileNotFoundError(f"Canonical notebook is missing: {source}")
    if target.exists() and not reset:
        return False

    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    return True


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser for the local notebook launcher."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Replace the local notebook with the current canonical copy, discarding local outputs and edits.",
    )
    parser.add_argument(
        "--no-launch",
        action="store_true",
        help="Create or refresh the local copy without starting JupyterLab.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Prepare the local notebook copy and start JupyterLab unless suppressed."""
    args = build_parser().parse_args(argv)
    try:
        copied = prepare_local_notebook(CANONICAL_NOTEBOOK, LOCAL_NOTEBOOK, reset=args.reset)
    except FileNotFoundError as error:
        print(f"open_getting_started_notebook: {error}", file=sys.stderr)
        return 1

    if copied:
        action = "Refreshed" if args.reset else "Created"
        print(f"{action} local notebook: {LOCAL_NOTEBOOK.relative_to(REPO_ROOT)}")
    else:
        print(f"Using existing local notebook: {LOCAL_NOTEBOOK.relative_to(REPO_ROOT)}")

    if args.no_launch:
        return 0

    return subprocess.run(
        [sys.executable, "-m", "jupyter", "lab", str(LOCAL_NOTEBOOK)],
        cwd=REPO_ROOT,
        check=False,
    ).returncode


if __name__ == "__main__":
    raise SystemExit(main())
