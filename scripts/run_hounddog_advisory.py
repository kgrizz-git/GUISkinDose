#!/usr/bin/env python3
"""Run HoundDog's local dataflow scan as a non-blocking, local-only advisory.

HoundDog traces named sensitive values through source code into sinks (logs,
files, storage, third-party SDKs, AI). It complements the deterministic
``check_sensitive_content.py`` gate (which cannot follow a value through code)
and the text/DICOM scanners (which cannot see dataflow).

Policy (``dev-docs/references/LOCAL_PII_MODELS.md``): **local-only**. This runner
invokes only the standalone binary with console output--no API key, cloud
platform, GitHub App, managed scan, PR comment, report upload, or AI analysis.
It is advisory: it always exits 0 and never blocks a commit or push, and it
skips cleanly when the binary is not installed so contributors without HoundDog
are never gated.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def main() -> int:
    binary = shutil.which("hounddog")
    if binary is None:
        print(
            "ADVISORY: HoundDog not found on PATH; skipping local dataflow scan. "
            "Install the standalone binary to enable it "
            "(see dev-docs/references/LOCAL_PII_MODELS.md)."
        )
        return 0

    # Plain local scan only: no cloud/API/upload/AI flags are ever passed.
    command = [binary, "scan", str(repo_root()), "--no-color", "--no-tips"]
    print(f"ADVISORY: HoundDog local dataflow scan ({' '.join(command)})", flush=True)
    try:
        completed = subprocess.run(command, check=False)
    except OSError as exc:  # Never let an execution error block the hook.
        print(f"ADVISORY: HoundDog could not run ({type(exc).__name__}); skipping.")
        return 0

    if completed.returncode != 0:
        print(
            "ADVISORY: HoundDog reported findings or exited non-zero; review the "
            "output above. This check is advisory and does not block."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
