#!/usr/bin/env python3
"""Run HoundDog's local dataflow scan as a value-safe, local-only advisory.

HoundDog traces named sensitive values through source code into sinks (logs,
files, storage, third-party SDKs, AI). It complements the deterministic
``check_sensitive_content.py`` gate (which cannot follow a value through code)
and the text/DICOM scanners (which cannot see dataflow).

Policy (``dev-docs/references/LOCAL_PII_MODELS.md``): **local-only**. This runner
invokes only the standalone binary with console output--no API key, cloud
platform, GitHub App, managed scan, PR comment, report upload, or AI analysis.
It is optional to install, but findings are not optional to triage: a completed
scan exits 1 when risky dataflows exist. A missing binary is reported distinctly
as ``NOT RUN`` so it can never be mistaken for a clean scan.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
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

    # Plain local scan only: no cloud/API/upload/AI flags are ever passed. JSON
    # stays in a private ephemeral directory because it can contain code context.
    print("ADVISORY: HoundDog local dataflow scan started.", flush=True)
    try:
        with tempfile.TemporaryDirectory(prefix="mypyskindose-hounddog-") as temp_dir:
            report_path = Path(temp_dir) / "report.json"
            command = [
                binary,
                "scan",
                ".",
                "--no-color",
                "--no-tips",
                "--output-format",
                "json",
                "--output-path",
                str(report_path),
            ]
            completed = subprocess.run(command, cwd=repo_root(), check=False, capture_output=True, text=True)
            payload = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ADVISORY: HoundDog NOT RUN ({type(exc).__name__}).")
        return 0

    if completed.returncode != 0:
        print(f"ADVISORY: HoundDog NOT RUN (exit_code={completed.returncode}).")
        return 0
    dataflows = payload.get("dataflows", []) if isinstance(payload, dict) else []
    if not isinstance(dataflows, list):
        print("ADVISORY: HoundDog NOT RUN (invalid_result).")
        return 0
    if dataflows:
        print(f"ADVISORY: HoundDog found {len(dataflows)} risky dataflow(s); triage is required.")
        return 1
    print("ADVISORY: HoundDog clean (0 risky dataflows).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
