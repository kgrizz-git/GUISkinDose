#!/usr/bin/env python3
"""Run the OWASP Top 10 Semgrep ruleset against the project's code surfaces.

Exists so the scan target list and flags live in one place instead of being
duplicated between the pre-push hook and the CI job, and so both use the pinned
isolated Semgrep from :mod:`semgrep_tool` rather than whatever is on ``PATH``.

Scope is an include-list of code surfaces, narrowed further by explicit excludes for
approved asset/data directories that live under those surfaces, so example/phantom/table
data is never handed to this pass. The privacy admission gate remains
the authoritative full-content check (see
``dev-docs/PRIVACY_AND_SENSITIVE_ASSETS.md``).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Final

if __package__:
    from .semgrep_tool import SemgrepUnavailableError, semgrep_argv, tool_environment
else:  # pragma: no cover - direct script execution (hooks, CI)
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from semgrep_tool import SemgrepUnavailableError, semgrep_argv, tool_environment

# Registry ruleset; fetched over the network, so this gate needs connectivity.
_CONFIG: Final = "p/owasp-top-ten"

# Code surfaces only. Adding a data or fixture directory here would feed
# clinical-adjacent content to a scanner that does not need it.
_TARGETS: Final = ("src", "scripts", ".github/workflows", "docs/source/conf.py")

_FLAGS: Final = ("--error", "--metrics=off")

# Approved asset/data surfaces are kept out of this SAST pass even though they sit
# under `src`. Previously only the CI job passed these; the pre-push hook did not, so a
# local run scanned clinical-adjacent data the policy says not to feed to a scanner. Both
# now share this list, which means the local hook is deliberately *narrower* than it was,
# not just more consistent. (CI's `--exclude=tests/fixtures/**` is dropped: `tests` is not
# in _TARGETS, so it never applied.) See dev-docs/PRIVACY_AND_SENSITIVE_ASSETS.md.
_EXCLUDES: Final = (
    "--exclude=src/**/example_data/**",
    "--exclude=src/**/phantom_data/**",
    "--exclude=src/**/table_data/**",
)


def main(argv: list[str] | None = None) -> int:
    extra = list(sys.argv[1:] if argv is None else argv)
    try:
        command = semgrep_argv([f"--config={_CONFIG}", *_FLAGS, *_EXCLUDES, *_TARGETS, *extra])
    except SemgrepUnavailableError as exc:
        print(f"ERROR: OWASP Semgrep did not run ({exc}).", file=sys.stderr)
        return 2

    environment = tool_environment()
    # SEMGREP_SEND_METRICS=off, the app-token pop and the settings-file redirect now live in
    # tool_environment(), so both gates get them rather than only this one.
    environment["SEMGREP_ENABLE_VERSION_CHECK"] = "0"

    root = Path(__file__).resolve().parents[1]
    try:
        # argv is a list (no shell) rebuilt from module constants plus the pinned
        # tool spec, so nothing here is attacker-influenced.
        completed = subprocess.run(  # NOSONAR pythonsecurity:S8705
            command, cwd=root, env=environment, check=False
        )
    except OSError as exc:
        print(f"ERROR: OWASP Semgrep failed to start ({type(exc).__name__}).", file=sys.stderr)
        return 2
    return completed.returncode


if __name__ == "__main__":  # pragma: no cover - entry point, exercised via main()
    sys.exit(main())
