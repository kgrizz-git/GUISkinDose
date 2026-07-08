#!/usr/bin/env python3
"""Reproduce the core CI test-collection condition locally, without uninstalling GUI deps.

The core CI ``build`` matrix installs the package **without** the optional ``gui`` extra
and runs ``pytest --ignore=tests/gui``. A test collected there that imports ``nicegui``
at module load — directly or transitively via ``mypyskindose.gui.*`` — breaks collection
with ``ModuleNotFoundError: No module named 'nicegui'`` on every platform. The failure
only shows up in full CI, because local dev and pre-commit have the ``gui`` extra
installed and do not run pytest without it.

The safe patterns for a GUI-dependent test are:

* put it under ``tests/gui/`` (its ``conftest.py`` does ``pytest.importorskip("nicegui")``,
  and the ``gui-smoke`` job installs the extra), or
* keep a module-level ``pytest.importorskip("nicegui")`` **before** any GUI import so the
  module skips cleanly when the extra is absent.

Rather than statically guess which ``mypyskindose.gui`` submodules pull in nicegui (some,
like ``gui.state``, do not), this check installs an import hook that makes ``nicegui``
unimportable and then runs ``pytest --collect-only`` over the non-``tests/gui`` suite in a
subprocess. Any module that hard-imports nicegui at load time fails collection here — the
exact core-CI failure — while correctly guarded modules skip. Zero false positives.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]

# Runs inside the subprocess: block nicegui, then invoke pytest with the args this
# script was given (passed through argv). Collection-only by default; `--run` executes
# the core suite so function-level GUI imports (which only fail at test time) are caught too.
_CHILD = textwrap.dedent(
    """
    import sys

    class _BlockNicegui:
        def find_spec(self, name, path=None, target=None):
            if name == "nicegui" or name.startswith("nicegui."):
                raise ModuleNotFoundError(f"No module named '{name}' (blocked by check_gui_test_placement)")
            return None

    sys.meta_path.insert(0, _BlockNicegui())

    import pytest

    raise SystemExit(pytest.main(sys.argv[1:]))
    """
)

_BASE_ARGS = ["-p", "no:cacheprovider", "--ignore=tests/gui", "tests"]


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    full_run = "--run" in argv

    try:
        import pytest  # noqa: F401
    except ImportError:
        print("check_gui_test_placement: pytest not installed; skipping.")
        return 0

    pytest_args = (["-q"] if full_run else ["--collect-only", "-q"]) + _BASE_ARGS
    proc = subprocess.run(
        [sys.executable, "-c", _CHILD, *pytest_args],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
    )
    if proc.returncode == 0:
        mode = "runs" if full_run else "collects"
        print(f"GUI test placement OK: core suite {mode} with nicegui unavailable.")
        return 0

    print("ERROR: a test outside tests/gui/ requires nicegui (which the core CI matrix does")
    print("not install). Move the test under tests/gui/, or add a module-level")
    print('`pytest.importorskip("nicegui")` before the GUI import.\n')
    # Surface pytest's collection/failure output (it names the offending file).
    sys.stdout.write(proc.stdout)
    sys.stderr.write(proc.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
