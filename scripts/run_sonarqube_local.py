#!/usr/bin/env python3
"""Run a value-suppressed analysis against a self-hosted local SonarQube server."""

from __future__ import annotations

import argparse
from contextlib import suppress
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

SETTINGS_PATH = Path("sonar-project.properties")
ALLOWED_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
ALLOWED_SCANNER_NAMES = {"sonar-scanner", "sonar-scanner.bat"}
SOURCE_ROOTS = ("src", "scripts", "tests")
EXCLUDED_PARTS = {"__pycache__", ".scannerwork"}
EXCLUDED_PREFIXES = ("src/guiskindose/example_data/", "src/guiskindose/phantom_data/", "tests/fixtures/")
INVALID_HOST_URL = "invalid SonarQube host URL"


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def validate_scanner_binary(binary: str) -> Path:
    """Require an absolute sonar-scanner path with a known basename before exec."""
    path = Path(binary)
    if not path.is_absolute():
        raise ValueError("scanner binary must be an absolute path")
    resolved = path.resolve()
    if resolved.name not in ALLOWED_SCANNER_NAMES:
        raise ValueError("unexpected scanner binary name")
    if not resolved.is_file():
        raise ValueError("scanner binary is not a file")
    return resolved


def sanitize_host_url(url: str, *, allow_remote: bool) -> str:
    """Validate and rebuild a SonarQube URL from trusted parsed components only."""
    if any(ch in url for ch in "\r\n\x00"):
        raise ValueError(INVALID_HOST_URL)
    parsed = urlparse(url)
    scheme = (parsed.scheme or "").lower()
    hostname = (parsed.hostname or "").lower()
    if scheme not in {"http", "https"} or not hostname:
        raise ValueError(INVALID_HOST_URL)
    if hostname in ALLOWED_LOCAL_HOSTS:
        # Emit literals so downstream argv construction does not retain CLI taint.
        host = {"localhost": "localhost", "127.0.0.1": "127.0.0.1", "::1": "[::1]"}[hostname]
    elif allow_remote:
        if any(ch in hostname for ch in " \t\r\n\x00/;\\\"'"):
            raise ValueError(INVALID_HOST_URL)
        host = hostname if ":" not in hostname else f"[{hostname}]"
    else:
        raise ValueError("non-loopback SonarQube host requires --allow-remote")
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError(INVALID_HOST_URL) from exc
    if port is None:
        return f"{scheme}://{host}"
    return f"{scheme}://{host}:{int(port)}"


def validate_host(url: str, *, allow_remote: bool) -> None:
    sanitize_host_url(url, allow_remote=allow_remote)


def build_scanner_command(binary: Path, host_url: str, *, wait_for_quality_gate: bool) -> list[str]:
    """Build an argv list for sonar-scanner after host/binary validation."""
    command = [str(binary), f"-Dsonar.host.url={host_url}"]
    if wait_for_quality_gate:
        command.extend(["-Dsonar.qualitygate.wait=true", "-Dsonar.qualitygate.timeout=300"])
    return command


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--host-url",
        default=os.environ.get("SONAR_HOST_URL", "http://localhost:9000"),
        help="Self-hosted SonarQube URL; defaults to http://localhost:9000.",
    )
    parser.add_argument(
        "--allow-remote",
        action="store_true",
        help="Allow a non-loopback SonarQube host after a separate data-processing review.",
    )
    parser.add_argument("--no-quality-gate-wait", action="store_true", help="Do not wait for the quality gate result.")
    return parser.parse_args(argv)

def git_path(root: Path, name: str) -> Path:
    result = subprocess.run(
        ["git", "rev-parse", "--git-path", name],
        cwd=root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if result.returncode:
        raise RuntimeError("git_path_unavailable")
    path = Path(result.stdout.strip())
    return path if path.is_absolute() else root / path


def analysis_source_paths(root: Path) -> list[Path]:
    paths: list[Path] = []
    candidates = [root / SETTINGS_PATH]
    coverage = root / "coverage.xml"
    if coverage.is_file():
        candidates.append(coverage)
    for source_root in SOURCE_ROOTS:
        directory = root / source_root
        if directory.is_dir():
            candidates.extend(directory.rglob("*"))
    for path in candidates:
        if not path.is_file() or path.is_symlink():
            continue
        relative = path.relative_to(root)
        normalized = relative.as_posix()
        if any(part in EXCLUDED_PARTS for part in relative.parts):
            continue
        if normalized.startswith(EXCLUDED_PREFIXES):
            continue
        paths.append(relative)
    return sorted(paths)


def source_digest(root: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    paths = analysis_source_paths(root)
    for relative in paths:
        digest.update(relative.as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashlib.sha256((root / relative).read_bytes()).digest())
        digest.update(b"\n")
    return digest.hexdigest(), len(paths)


def scanner_version_digest(binary: str) -> str:
    completed = subprocess.run(
        [binary, "--version"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False
    )
    if completed.returncode or not completed.stdout:
        raise RuntimeError("sonar_scanner_version_unavailable")
    return hashlib.sha256(completed.stdout[:8192]).hexdigest()


def write_state(root: Path, payload: dict[str, object]) -> None:
    target = git_path(root, "sonarqube/last-run.json")
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with suppress(OSError):
        target.chmod(0o600)


def classify_failure(log_path: Path) -> str:
    try:
        content = log_path.read_text(encoding="utf-8", errors="replace").lower()
    except OSError:
        return "scanner_failed"
    if "not authorized" in content or "authentication" in content or "sonar.token" in content:
        return "authentication_required"
    if "quality gate" in content and ("failed" in content or "status is error" in content):
        return "quality_gate_failed"
    if "failed to connect" in content or "cannot reach" in content or "connection refused" in content:
        return "server_unreachable"
    return "scanner_failed"


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    root = repo_root()
    located = shutil.which("sonar-scanner")
    if located is None:
        print("ERROR: SonarQube local analysis did not run (scanner_missing).", file=sys.stderr)
        return 2
    try:
        safe_host_url = sanitize_host_url(args.host_url, allow_remote=args.allow_remote)
        binary = validate_scanner_binary(located)
        command = build_scanner_command(
            binary,
            safe_host_url,
            wait_for_quality_gate=not args.no_quality_gate_wait,
        )
    except ValueError as exc:
        print(f"ERROR: SonarQube local analysis refused ({exc}).", file=sys.stderr)
        return 2
    if not (root / SETTINGS_PATH).is_file():
        print("ERROR: SonarQube local settings are missing.", file=sys.stderr)
        return 2

    try:
        content_sha256, input_count = source_digest(root)
        version_sha256 = scanner_version_digest(str(binary))
        settings_sha256 = hashlib.sha256((root / SETTINGS_PATH).read_bytes()).hexdigest()
    except (OSError, RuntimeError) as exc:
        print(f"ERROR: SonarQube local analysis preparation failed ({type(exc).__name__}).", file=sys.stderr)
        return 2

    print(f"SonarQube local analysis started: tracked_inputs={input_count}; scanner output suppressed.", flush=True)
    with tempfile.TemporaryDirectory(prefix="sonarqube-private-log-") as temp_dir:
        log_path = Path(temp_dir) / "scanner.log"
        try:
            with log_path.open("wb") as log:
                # argv is a list (no shell); binary basename and host URL were rebuilt from allowlists.
                completed = subprocess.run(  # NOSONAR pythonsecurity:S8705
                    command,
                    cwd=root,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    check=False,
                )
        except OSError as exc:
            print(f"ERROR: SonarQube local analysis did not complete ({type(exc).__name__}).", file=sys.stderr)
            return 2
        failure_reason = None if completed.returncode == 0 else classify_failure(log_path)

    status = "passed" if completed.returncode == 0 else "failed"
    write_state(
        root,
        {
            "schema_version": 1,
            "status": status,
            "failure_reason": failure_reason,
            "quality_gate_waited": not args.no_quality_gate_wait,
            "source_sha256": content_sha256,
            "input_count": input_count,
            "settings_sha256": settings_sha256,
            "scanner_version_sha256": version_sha256,
            "completed_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    if completed.returncode:
        print(f"SonarQube local analysis did not pass ({failure_reason}); private state recorded.", file=sys.stderr)
        return 1
    print("SonarQube local analysis and quality gate passed; private state recorded under Git metadata.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
