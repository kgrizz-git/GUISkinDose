#!/usr/bin/env python3
"""Mirror the UI-copy catalog into the installable package.

``dev-docs/ui_copy.json`` is the single source of truth for in-app copy, but
``dev-docs/`` is never packaged — and ``copy_text()`` runs on every GUI page
render, so a non-editable install would raise ``FileNotFoundError``. This
script keeps the bundled copy at ``src/guiskindose/gui/ui_copy.json`` in sync
(byte-identical). The standard library is used so the script has no runtime
dependencies and can be invoked by pre-commit and CI without a virtual
environment.
"""

from __future__ import annotations

import argparse
import filecmp
import shutil
import sys
from pathlib import Path

SOURCE_REPO_FILE = Path("dev-docs/ui_copy.json")
TARGET_REPO_FILE = Path("src/guiskindose/gui/ui_copy.json")


def repo_root_from_script() -> Path:
    return Path(__file__).resolve().parent.parent


def sync(source: Path, target: Path, *, check: bool) -> int:
    """Mirror ``source`` to ``target`` (or report drift with ``check``)."""
    if not source.is_file():
        sys.stderr.write(f"error: source catalog does not exist: {source}\n")
        return 1
    if check and not target.is_file():
        sys.stderr.write(f"error: bundled catalog does not exist: {target}\n")
        return 1
    in_sync = target.is_file() and filecmp.cmp(str(source), str(target), shallow=False)
    if in_sync:
        return 0
    if check:
        sys.stderr.write(
            "error: bundled UI-copy catalog is out of sync; run "
            "scripts/sync_ui_copy.py to fix.\n"
        )
        return 1
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp_target = target.with_name(f"{target.name}.tmp")
    shutil.copyfile(source, tmp_target)
    tmp_target.replace(target)
    print(f"mirrored {source.name} -> {target}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Mirror dev-docs/ui_copy.json to src/guiskindose/gui/ui_copy.json "
            "(or check with --check)."
        )
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit non-zero if the bundled copy drifts; do not write.",
    )
    args = parser.parse_args(argv)

    # The repository root is always derived from this script's location; no CLI
    # option can redirect the mirror's reads or writes outside the checkout.
    repo_root = repo_root_from_script()
    return sync(repo_root / SOURCE_REPO_FILE, repo_root / TARGET_REPO_FILE, check=args.check)


if __name__ == "__main__":
    sys.exit(main())
