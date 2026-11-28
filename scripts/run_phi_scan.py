#!/usr/bin/env python3
"""Run the pinned, isolated phi-scan with the arguments given.

This is the single entry point used by the workflow and by manual runs, so the
resolved environment cannot drift from the one ``scripts/privacy_admission.py``
uses. Arguments are forwarded verbatim to phi-scan, for example::

    python scripts/run_phi_scan.py scan . --config .phi-scanner.yml --baseline --quiet

The working directory stays whatever the caller chose: phi-scan scans ``.`` there.
"""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

if __package__:
    from .phi_scan_tool import PhiScanUnavailableError, phi_scan_argv, tool_environment
else:  # pragma: no cover - direct script execution (hooks, CI)
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from phi_scan_tool import PhiScanUnavailableError, phi_scan_argv, tool_environment


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    try:
        command = phi_scan_argv(args)
    except PhiScanUnavailableError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    try:
        completed = subprocess.run(command, env=tool_environment(), check=False)
    except OSError as error:
        # A scanner that cannot start must fail the gate, never pass quietly.
        print(f"ERROR: could not start phi-scan ({type(error).__name__}).", file=sys.stderr)
        return 1
    return completed.returncode


if __name__ == "__main__":
    sys.exit(main())
