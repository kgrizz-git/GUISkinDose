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
import sys
from pathlib import Path

SOURCE_REPO_FILE = Path("dev-docs/ui_copy.json")
TARGET_REPO_FILE = Path("src/guiskindose/gui/ui_copy.json")


def repo_root_from_script() -> Path:
    return Path(__file__).resolve().parent.parent


def main(*, check: bool) -> int:
    root = repo_root_from_script()
    source = root / SOURCE_REPO_FILE
    target = root / TARGET_REPO_FILE
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
    target.write_bytes(source.read_bytes())
    print(f"mirrored {SOURCE_REPO_FILE} -> {TARGET_REPO_FILE}")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit nonzero when the bundled copy drifts instead of fixing it.",
    )
    raise SystemExit(main(check=parser.parse_args().check))
