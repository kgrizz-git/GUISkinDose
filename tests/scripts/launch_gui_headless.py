#!/usr/bin/env python3
"""
Run MyPySkinDose GUI smoke tests without a visible browser.

Harness Phase 5 maintainer script. Uses NiceGUI user simulation via pytest;
does not start ui.run() or open a desktop window.

Usage (from repository root, with GUI extras installed):
    python tests/scripts/launch_gui_headless.py

Requires: pip install -e '.[gui]'
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> int:
    repo_root = Path(__file__).resolve().parents[2]
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "tests/gui/",
        "-v",
        "--tb=short",
    ]
    print("Running GUI smoke tests:", " ".join(cmd))
    return subprocess.call(cmd, cwd=repo_root)


if __name__ == "__main__":
    raise SystemExit(main())
