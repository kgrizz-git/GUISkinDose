#!/usr/bin/env python3
"""Run HoundDog's local dataflow scan as a value-safe, local-only advisory.

HoundDog traces named sensitive values through source code into sinks (logs,
files, storage, third-party SDKs, AI). It complements the deterministic
``check_sensitive_content.py`` gate (which cannot follow a value through code)
and the text/DICOM scanners (which cannot see dataflow).

Policy (``dev-docs/references/LOCAL_PII_MODELS.md``): **local-only**. This runner
invokes only the standalone binary with console output--no API key, cloud
platform, GitHub App, managed scan, PR comment, report upload, or AI analysis.
Manual use is optional, but conditional privacy admission passes
``--require-installed`` and fails if the scanner is absent. Findings are never
optional to triage: a completed scan exits 1 when risky dataflows exist. A
missing binary is reported distinctly as ``NOT RUN`` so it can never be
mistaken for a clean scan.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scan-root",
        type=Path,
        default=repo_root(),
        help="Directory to scan; defaults to the repository root.",
    )
    parser.add_argument(
        "--require-installed",
        action="store_true",
        help="Fail when HoundDog is missing or does not complete; used by privacy receipts.",
    )
    return parser.parse_args(argv)


def _not_run(reason: str, *, require_installed: bool) -> int:
    """Report an incomplete scan while preserving required/advisory exit behavior."""
    print(f"ADVISORY: HoundDog NOT RUN ({reason}).")
    return 2 if require_installed else 0


def _scan_report(binary: str, scan_root: Path) -> tuple[int, object]:
    """Run the local binary and return its exit status with parsed private report."""
    # Plain local scan only: no cloud/API/upload/AI flags are ever passed. JSON
    # stays in a private ephemeral directory because it can contain code context.
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
        completed = subprocess.run(command, cwd=scan_root, check=False, capture_output=True, text=True)
        payload = json.loads(report_path.read_text(encoding="utf-8"))
    return completed.returncode, payload


def _report_outcome(returncode: int, payload: object, *, require_installed: bool) -> int:
    """Render a value-safe scanner outcome from its exit status and JSON shape."""
    if returncode != 0:
        return _not_run(f"exit_code={returncode}", require_installed=require_installed)
    dataflows = payload.get("dataflows", []) if isinstance(payload, dict) else []
    if not isinstance(dataflows, list):
        return _not_run("invalid_result", require_installed=require_installed)
    if dataflows:
        print(f"ADVISORY: HoundDog found {len(dataflows)} risky dataflow(s); triage is required.")
        return 1
    print("ADVISORY: HoundDog clean (0 risky dataflows).")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Run HoundDog and map completed, incomplete, and finding outcomes to exit codes."""
    args = parse_args(argv)
    binary = shutil.which("hounddog")
    if binary is None:
        print(
            "ADVISORY: HoundDog not found on PATH; skipping local dataflow scan. "
            "Install the standalone binary to enable it "
            "(see dev-docs/references/LOCAL_PII_MODELS.md)."
        )
        return 2 if args.require_installed else 0

    scan_root = args.scan_root.resolve()
    if not scan_root.is_dir():
        return _not_run("scan_root_unavailable", require_installed=args.require_installed)
    print("ADVISORY: HoundDog local dataflow scan started.", flush=True)
    try:
        returncode, payload = _scan_report(binary, scan_root)
    except (OSError, json.JSONDecodeError) as exc:
        return _not_run(type(exc).__name__, require_installed=args.require_installed)
    return _report_outcome(returncode, payload, require_installed=args.require_installed)


if __name__ == "__main__":
    sys.exit(main())
