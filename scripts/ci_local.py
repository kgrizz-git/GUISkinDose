#!/usr/bin/env python3
"""Run the CI gate locally, in one command, before pushing.

Mirrors the checks the GitHub ``ci`` workflow runs (ruff, basedpyright, the doc/registry
guards, and the tests) so failures are caught on your machine instead of after a push.

Crucially, the test step runs the **core suite with nicegui blocked** (via
``check_gui_test_placement.py --run``), reproducing the no-``gui``-extra core CI matrix even
though your local environment has the GUI deps installed — the exact blind spot that lets
GUI-import and gui-only-dep failures reach CI unseen. It then runs the GUI suite normally.

This does not reproduce dependency-version drift: CI installs the latest releases while your
environment may differ. Run ``uv sync --all-extras`` to match the pinned lockfile, and let the
scheduled ``ci-latest`` workflow surface upstream breakage.

Usage:
    python scripts/ci_local.py            # full gate
    python scripts/ci_local.py --fast     # skip the slower test steps (static checks only)
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_PY = sys.executable


def _steps(fast: bool) -> list[tuple[str, list[str]]]:
    static: list[tuple[str, list[str]]] = [
        ("ruff", ["ruff", "check", "src", "tests", "scripts"]),
        ("basedpyright", ["basedpyright"]),
        ("doc-freshness", [_PY, "scripts/check_doc_freshness.py"]),
        ("gui-help-sync", [_PY, "scripts/sync_gui_help.py", "--check"]),
        ("help-registry", [_PY, "scripts/check_help_registry.py"]),
        ("ui-copy", [_PY, "scripts/check_ui_copy.py"]),
        ("feature-doc-matrix", [_PY, "scripts/check_feature_doc_matrix.py"]),
        ("file-sizes", [_PY, "scripts/check_file_sizes.py"]),
    ]
    tests: list[tuple[str, list[str]]] = [
        # Core suite with nicegui blocked — reproduces the no-gui core CI matrix.
        ("core-tests (no gui)", [_PY, "scripts/check_gui_test_placement.py", "--run"]),
        ("gui-tests", [_PY, "-m", "pytest", "tests/gui", "-q"]),
    ]
    return static if fast else static + tests


def main() -> int:
    fast = "--fast" in sys.argv[1:]
    steps = _steps(fast)

    results: list[tuple[str, bool, float]] = []
    for name, cmd in steps:
        print(f"\n\033[1m▶ {name}\033[0m  ({' '.join(cmd)})", flush=True)
        start = time.monotonic()
        rc = subprocess.run(cmd, cwd=_REPO_ROOT).returncode
        results.append((name, rc == 0, time.monotonic() - start))

    print("\n" + "=" * 60)
    print("CI-local summary" + ("  (--fast: tests skipped)" if fast else ""))
    print("=" * 60)
    failed = 0
    for name, ok, secs in results:
        mark = "\033[32mPASS\033[0m" if ok else "\033[31mFAIL\033[0m"
        print(f"  {mark}  {name:<28} {secs:5.1f}s")
        failed += not ok

    if failed:
        print(f"\n\033[31m{failed} step(s) failed.\033[0m")
        return 1
    print("\n\033[32mAll checks passed.\033[0m")
    return 0


if __name__ == "__main__":
    sys.exit(main())
