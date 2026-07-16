#!/usr/bin/env python3
"""Run blocking privacy Semgrep rules with value-safe finding summaries."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Sequence


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _path_token(path: str) -> str:
    return hashlib.sha256(path.encode("utf-8")).hexdigest()[:12]


def _finding_location(result: dict[str, object], *, verbose_paths: bool) -> str:
    path = str(result.get("path", "unknown"))
    start = result.get("start")
    line = start.get("line") if isinstance(start, dict) else None
    location = path if verbose_paths else f"path_token={_path_token(path)}"
    return f"{location}:{line}" if isinstance(line, int) else location


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--verbose-paths",
        action="store_true",
        help="Show repository paths locally; default output uses non-reversible path tokens.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    semgrep = shutil.which("semgrep")
    if semgrep is None:
        print("ERROR: privacy Semgrep was not run (binary_missing).", file=sys.stderr)
        return 2

    root = repo_root()
    environment = os.environ.copy()
    environment["SEMGREP_ENABLE_VERSION_CHECK"] = "0"
    cert_file = Path("/etc/ssl/cert.pem")
    if cert_file.is_file():
        environment["SSL_CERT_FILE"] = str(cert_file)
    elif not environment.get("SSL_CERT_FILE"):
        environment.pop("SSL_CERT_FILE", None)
    command = [
        semgrep,
        "--config",
        str(root / ".semgrep" / "mypyskindose-privacy.yml"),
        "--metrics=off",
        "--json",
        "--quiet",
        "src",
        "scripts",
        "tests",
    ]
    try:
        with tempfile.TemporaryDirectory(prefix="mypyskindose-semgrep-") as temp_dir:
            environment["SEMGREP_LOG_FILE"] = str(Path(temp_dir) / "semgrep.log")
            environment["XDG_CACHE_HOME"] = str(Path(temp_dir) / "cache")
            completed = subprocess.run(
                command,
                cwd=root,
                check=False,
                capture_output=True,
                text=True,
                env=environment,
            )
        payload = json.loads(completed.stdout)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: privacy Semgrep did not complete ({type(exc).__name__}).", file=sys.stderr)
        return 2

    errors = payload.get("errors", [])
    if completed.returncode not in (0, 1) or errors:
        print("ERROR: privacy Semgrep did not complete (scanner_error).", file=sys.stderr)
        return 2

    results = payload.get("results", [])
    if not isinstance(results, list):
        print("ERROR: privacy Semgrep did not complete (invalid_result).", file=sys.stderr)
        return 2
    for result in results:
        if not isinstance(result, dict):
            continue
        rule_id = str(result.get("check_id", "unknown_rule")).split(".")[-1]
        location = _finding_location(result, verbose_paths=args.verbose_paths)
        print(f"ERROR: privacy rule {rule_id} at {location}.", file=sys.stderr)
    if results:
        print(f"Privacy Semgrep failed with {len(results)} finding(s).", file=sys.stderr)
        return 1
    print("Privacy Semgrep OK.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
