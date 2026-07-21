#!/usr/bin/env python3
"""Enforce protected output paths and content-bound privacy scanner receipts."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import fnmatch
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Literal, Sequence

POLICY_PATH = Path("dev-docs/privacy_admission_policy.json")
Mode = Literal["staged", "range", "all"]
# Keep the local NLP scanner responsive on repositories with many documentation
# files.  Each invocation receives a disjoint subset; the receipt still covers
# the complete, content-hashed input set.
PRESIDIO_BATCH_SIZE = 25
PRESIDIO_MAX_WORKERS = 8


@dataclass(frozen=True)
class ScannerRule:
    scanner_id: str
    version: str
    trigger_extensions: frozenset[str]
    trigger_prefixes: tuple[str, ...]
    diff_regex: str | None
    input_extensions: frozenset[str]
    input_prefixes: tuple[str, ...]
    scope: Literal["changed", "all_matching"]
    config_paths: tuple[str, ...]


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def normalize_path(value: str) -> str:
    normalized = PurePosixPath(value.replace("\\", "/")).as_posix()
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def path_token(value: str) -> str:
    return hashlib.sha256(normalize_path(value).encode("utf-8")).hexdigest()[:12]


def run_git(root: Path, *args: str, input_data: bytes | None = None) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", *args],
        cwd=root,
        input=input_data,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def revision_bytes(root: Path, path: Path, mode: Mode) -> bytes:
    if mode == "all":
        return (root / path).read_bytes()
    revision = f":{path.as_posix()}" if mode == "staged" else f"HEAD:{path.as_posix()}"
    result = run_git(root, "show", revision)
    if result.returncode:
        raise RuntimeError(f"required_revision_file_unavailable_{path_token(path.as_posix())}")
    return result.stdout


def load_policy(root: Path, mode: Mode = "all") -> tuple[dict[str, Any], list[ScannerRule]]:
    raw = revision_bytes(root, POLICY_PATH, mode)
    policy = json.loads(raw)
    if not isinstance(policy, dict) or policy.get("version") != 1:
        raise ValueError("unsupported privacy admission policy")
    rules: list[ScannerRule] = []
    for item in policy.get("scanners", []):
        if not isinstance(item, dict):
            raise ValueError("invalid scanner policy entry")
        rules.append(
            ScannerRule(
                scanner_id=str(item["id"]),
                version=str(item["version"]),
                trigger_extensions=frozenset(str(value).lower() for value in item.get("trigger_extensions", [])),
                trigger_prefixes=tuple(normalize_path(str(value)).rstrip("/") + "/" for value in item.get("trigger_prefixes", [])),
                diff_regex=str(item["diff_regex"]) if item.get("diff_regex") else None,
                input_extensions=frozenset(str(value).lower() for value in item.get("input_extensions", [])),
                input_prefixes=tuple(normalize_path(str(value)).rstrip("/") + "/" for value in item.get("input_prefixes", [])),
                scope=str(item.get("scope", "changed")),  # type: ignore[arg-type]
                config_paths=tuple(normalize_path(str(value)) for value in item.get("config_paths", [])),
            )
        )
    return policy, rules


def split_z(output: bytes) -> list[str]:
    return [normalize_path(value.decode("utf-8", "surrogateescape")) for value in output.split(b"\0") if value]


def tracked_paths(root: Path) -> list[str]:
    result = run_git(root, "ls-files", "-z")
    if result.returncode:
        raise RuntimeError("git_ls_files_failed")
    return sorted(split_z(result.stdout))


def resolve_base(root: Path) -> str:
    candidates = [os.environ.get("PRIVACY_BASE_REF"), "@{upstream}", "origin/main"]
    for candidate in candidates:
        if not candidate:
            continue
        result = run_git(root, "rev-parse", "--verify", candidate)
        if result.returncode == 0:
            return candidate
    raise RuntimeError("privacy_base_ref_unavailable")


def changed_paths(root: Path, mode: Mode) -> list[str]:
    if mode == "all":
        return tracked_paths(root)
    if mode == "staged":
        result = run_git(root, "diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z", "--")
    else:
        base = resolve_base(root)
        result = run_git(root, "diff", f"{base}...HEAD", "--name-only", "--diff-filter=ACMR", "-z", "--")
    if result.returncode:
        raise RuntimeError("git_changed_paths_failed")
    return sorted(split_z(result.stdout))


def diff_text(root: Path, mode: Mode) -> str:
    if mode == "all":
        return ""
    if mode == "staged":
        result = run_git(root, "diff", "--cached", "--unified=0", "--no-ext-diff", "--", "*.py")
    else:
        base = resolve_base(root)
        result = run_git(root, "diff", f"{base}...HEAD", "--unified=0", "--no-ext-diff", "--", "*.py")
    if result.returncode:
        raise RuntimeError("git_diff_failed")
    return result.stdout.decode("utf-8", "replace")


def matches(path: str, extensions: frozenset[str], prefixes: tuple[str, ...]) -> bool:
    normalized = normalize_path(path)
    suffix_match = not extensions or Path(normalized).suffix.lower() in extensions
    prefix_match = not prefixes or any(normalized.startswith(prefix) for prefix in prefixes)
    return suffix_match and prefix_match


def required_rules(rules: Sequence[ScannerRule], paths: Sequence[str], patch: str) -> list[ScannerRule]:
    required: list[ScannerRule] = []
    for rule in rules:
        if not any(matches(path, rule.trigger_extensions, rule.trigger_prefixes) for path in paths):
            continue
        if rule.diff_regex and not re.search(rule.diff_regex, patch):
            continue
        required.append(rule)
    return required


def forbidden_paths(policy: dict[str, Any], paths: Sequence[str]) -> list[str]:
    prefixes = tuple(normalize_path(str(value)).rstrip("/") + "/" for value in policy["never_track_prefixes"])
    names = {str(value) for value in policy["never_track_names"]}
    patterns = tuple(str(value) for value in policy.get("never_track_patterns", []))
    return sorted(
        path
        for path in paths
        if any(normalize_path(path).startswith(prefix) for prefix in prefixes)
        or PurePosixPath(path).name in names
        or any(
            fnmatch.fnmatch(normalize_path(path), pattern) or fnmatch.fnmatch(PurePosixPath(path).name, pattern)
            for pattern in patterns
        )
    )


def missing_ignore_patterns(ignore_bytes: bytes, policy: dict[str, Any]) -> list[str]:
    lines = {
        line.strip()
        for line in ignore_bytes.decode("utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    return sorted(str(value) for value in policy["protected_ignore_patterns"] if str(value) not in lines)


def index_entries(root: Path) -> dict[str, str]:
    result = run_git(root, "ls-files", "-s", "-z")
    if result.returncode:
        raise RuntimeError("git_index_failed")
    entries: dict[str, str] = {}
    for row in result.stdout.split(b"\0"):
        if not row:
            continue
        metadata, path_bytes = row.split(b"\t", 1)
        _mode, oid, stage = metadata.split()
        if stage == b"0":
            entries[normalize_path(path_bytes.decode("utf-8", "surrogateescape"))] = oid.decode("ascii")
    return entries


def head_entries(root: Path) -> dict[str, str]:
    result = run_git(root, "ls-tree", "-r", "-z", "HEAD")
    if result.returncode:
        raise RuntimeError("git_head_tree_failed")
    entries: dict[str, str] = {}
    for row in result.stdout.split(b"\0"):
        if not row:
            continue
        metadata, path_bytes = row.split(b"\t", 1)
        _mode, kind, oid = metadata.split()
        if kind == b"blob":
            entries[normalize_path(path_bytes.decode("utf-8", "surrogateescape"))] = oid.decode("ascii")
    return entries


def rule_inputs(rule: ScannerRule, changed: Sequence[str], entries: dict[str, str]) -> dict[str, str]:
    candidates = changed if rule.scope == "changed" else sorted(entries)
    return {
        path: entries[path]
        for path in candidates
        if path in entries and matches(path, rule.input_extensions, rule.input_prefixes)
    }


def digest_mapping(values: dict[str, str]) -> str:
    digest = hashlib.sha256()
    for path, oid in sorted(values.items()):
        digest.update(path_token(path).encode("ascii"))
        digest.update(b"\0")
        digest.update(oid.encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def config_digest(rule: ScannerRule, policy_bytes: bytes, entries: dict[str, str]) -> str:
    digest = hashlib.sha256(policy_bytes)
    for rel_path in sorted(rule.config_paths):
        digest.update(rel_path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(entries.get(rel_path, "MISSING").encode("ascii"))
    return digest.hexdigest()


def receipts_dir(root: Path) -> Path:
    result = run_git(root, "rev-parse", "--git-path", "privacy-scan-receipts")
    if result.returncode:
        raise RuntimeError("git_path_failed")
    value = Path(result.stdout.decode("utf-8").strip())
    return value if value.is_absolute() else root / value


def tool_version_digest(scanner_id: str) -> str:
    commands = {
        "hounddog": ["hounddog", "--version"],
        "image-ocr": ["tesseract", "--version"],
        "dicom-phi-scan": ["dicom-phi-scan", "--help"],
    }
    command = commands.get(scanner_id)
    if command is None:
        return hashlib.sha256(scanner_id.encode("utf-8")).hexdigest()
    if shutil.which(command[0]) is None:
        raise RuntimeError(f"{scanner_id}_tool_missing")
    completed = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    if completed.returncode not in (0, 2) or not completed.stdout:
        raise RuntimeError(f"{scanner_id}_version_unavailable")
    return hashlib.sha256(completed.stdout[:4096]).hexdigest()


def receipt_path(root: Path, scanner_id: str, input_digest: str) -> Path:
    safe_id = re.sub(r"[^a-z0-9_.-]", "-", scanner_id.lower())
    return receipts_dir(root) / f"{safe_id}-{input_digest[:20]}.json"


def expected_receipt(
    rule: ScannerRule,
    inputs: dict[str, str],
    policy_bytes: bytes,
    entries: dict[str, str],
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "scanner_id": rule.scanner_id,
        "scanner_policy_version": rule.version,
        "tool_version_sha256": tool_version_digest(rule.scanner_id),
        "policy_config_sha256": config_digest(rule, policy_bytes, entries),
        "input_sha256": digest_mapping(inputs),
        "input_count": len(inputs),
        "status": "clean",
    }


def verify_receipt(root: Path, expected: dict[str, Any], max_age_hours: int) -> str | None:
    path = receipt_path(root, str(expected["scanner_id"]), str(expected["input_sha256"]))
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "missing_or_invalid"
    for key, value in expected.items():
        if payload.get(key) != value:
            return f"mismatch_{key}"
    try:
        completed = datetime.fromisoformat(str(payload["completed_at"]))
    except (KeyError, ValueError):
        return "invalid_completion_time"
    if completed.tzinfo is None or datetime.now(timezone.utc) - completed > timedelta(hours=max_age_hours):
        return "expired"
    return None


def materialize_index(root: Path, destination: Path) -> None:
    prefix = str(destination.resolve()) + os.sep
    result = run_git(root, "checkout-index", "--all", f"--prefix={prefix}")
    if result.returncode:
        raise RuntimeError("index_materialization_failed")


def materialize_head(root: Path, destination: Path) -> None:
    result = run_git(root, "archive", "--format=tar", "HEAD")
    if result.returncode:
        raise RuntimeError("head_materialization_failed")
    with tarfile.open(fileobj=io.BytesIO(result.stdout), mode="r:") as archive:
        archive.extractall(destination, filter="data")


def run_scanner(root: Path, snapshot: Path, rule: ScannerRule, input_paths: Sequence[str]) -> int:
    python = sys.executable
    project_args = ["--project", str(root)]
    environment = os.environ.copy()
    uv_cache = git_path_directory(root, "privacy-uv-cache")
    uv_cache.mkdir(parents=True, exist_ok=True, mode=0o700)
    environment.setdefault("UV_CACHE_DIR", str(uv_cache))
    if rule.scanner_id == "presidio":
        command = [
            "uv", "run", *project_args, "--no-sync", "python", str(snapshot / "scripts/run_presidio_advisory.py"),
            "--scan-root", str(snapshot), "--fail-on-findings", "--max-displayed-findings", "100",
        ]
        # Keep this in sync with ``run_presidio_advisory.PRESIDIO_EXCLUDED_PATHS``.
        # The policy receipt still binds pyproject.toml as scanner configuration,
        # while the advisory scanner deliberately excludes its author contacts.
        scanned_paths = [path for path in input_paths if path != "pyproject.toml"]
        batches = [
            scanned_paths[offset : offset + PRESIDIO_BATCH_SIZE]
            for offset in range(0, len(scanned_paths), PRESIDIO_BATCH_SIZE)
        ]

        def scan_batch(paths: Sequence[str]) -> int:
            return subprocess.run([*command, *paths], cwd=snapshot, env=environment, check=False).returncode

        with ThreadPoolExecutor(max_workers=PRESIDIO_MAX_WORKERS) as executor:
            return 0 if all(code == 0 for code in executor.map(scan_batch, batches)) else 1
    elif rule.scanner_id == "hounddog":
        command = [
            python, str(snapshot / "scripts/run_hounddog_advisory.py"),
            "--scan-root", str(snapshot), "--require-installed",
        ]
    elif rule.scanner_id == "phi-scan":
        command = [
            "uvx", "--from", "phi-scan==0.7.0", "phi-scan", "scan", ".", "--config",
            str(snapshot / ".phi-scanner.yml"), "--baseline", "--no-cache", "--quiet", "--workers", "4",
        ]
    elif rule.scanner_id == "dicom-phi-scan":
        command = [
            python, str(snapshot / "scripts/run_dicom_phi_advisory.py"),
            "--scan-root", str(snapshot), *input_paths,
        ]
    elif rule.scanner_id == "image-ocr":
        command = [
            "uv", "run", *project_args, "--no-sync", "python", str(snapshot / "scripts/run_image_privacy_advisory.py"),
            "--scan-root", str(snapshot), *input_paths,
        ]
    else:
        raise RuntimeError("unknown_scanner")
    completed = subprocess.run(command, cwd=snapshot, env=environment, check=False)
    return completed.returncode


def git_path_directory(root: Path, name: str) -> Path:
    result = run_git(root, "rev-parse", "--git-path", name)
    if result.returncode:
        raise RuntimeError("git_path_failed")
    value = Path(result.stdout.decode("utf-8").strip())
    return value if value.is_absolute() else root / value


def command_check(root: Path, mode: Mode) -> int:
    policy, _rules = load_policy(root, mode)
    missing = missing_ignore_patterns(revision_bytes(root, Path(".gitignore"), mode), policy)
    if mode == "all":
        paths = tracked_paths(root)
    elif mode == "staged":
        paths = sorted(index_entries(root))
    else:
        paths = sorted(head_entries(root))
    forbidden = forbidden_paths(policy, paths)
    for _pattern in missing:
        print("ERROR: required privacy ignore rule is missing (value suppressed).", file=sys.stderr)
    for path in forbidden:
        print(f"ERROR: forbidden tracked path path_token={path_token(path)}.", file=sys.stderr)
    if missing or forbidden:
        return 1
    print("Privacy admission policy check OK.")
    return 0


def command_route(root: Path, mode: Mode) -> tuple[list[ScannerRule], list[str]]:
    _policy, rules = load_policy(root, mode)
    paths = changed_paths(root, mode)
    required = required_rules(rules, paths, diff_text(root, mode))
    names = ",".join(rule.scanner_id for rule in required) if required else "none"
    print(f"Privacy scanner route: changed_paths={len(paths)} required={names}.")
    return required, paths


def command_verify(root: Path, mode: Mode) -> int:
    policy, _rules = load_policy(root, mode)
    required, paths = command_route(root, mode)
    entries = index_entries(root) if mode == "staged" else head_entries(root)
    policy_bytes = revision_bytes(root, POLICY_PATH, mode)
    failures = 0
    for rule in required:
        inputs = rule_inputs(rule, paths, entries)
        try:
            expected = expected_receipt(rule, inputs, policy_bytes, entries)
            reason = verify_receipt(root, expected, int(policy["receipt_max_age_hours"]))
        except RuntimeError as exc:
            reason = str(exc)
        if reason:
            print(f"ERROR: required {rule.scanner_id} receipt unavailable ({reason}).", file=sys.stderr)
            failures += 1
    if failures:
        print(f"Run: python scripts/privacy_admission.py run --mode {mode}", file=sys.stderr)
        return 1
    print("Privacy scanner receipts OK.")
    return 0


def command_run(root: Path, mode: Mode) -> int:
    if mode == "all":
        print("ERROR: scanner execution requires --mode staged or --mode range.", file=sys.stderr)
        return 2
    policy, _rules = load_policy(root, mode)
    required, paths = command_route(root, mode)
    if not required:
        print("No conditional privacy scanners are required.")
        return 0
    entries = index_entries(root) if mode == "staged" else head_entries(root)
    policy_bytes = revision_bytes(root, POLICY_PATH, mode)
    receipt_root = receipts_dir(root)
    receipt_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.TemporaryDirectory(prefix="privacy-index-") as temp_dir:
        snapshot = Path(temp_dir)
        if mode == "staged":
            materialize_index(root, snapshot)
        else:
            materialize_head(root, snapshot)
        for rule in required:
            inputs = rule_inputs(rule, paths, entries)
            expected = expected_receipt(rule, inputs, policy_bytes, entries)
            print(f"Running required privacy scanner: {rule.scanner_id} ({len(inputs)} input file(s)).")
            returncode = run_scanner(root, snapshot, rule, sorted(inputs))
            if returncode:
                print(f"ERROR: {rule.scanner_id} did not complete cleanly (exit_code={returncode}).", file=sys.stderr)
                return 1
            payload = {**expected, "completed_at": datetime.now(timezone.utc).isoformat()}
            target = receipt_path(root, rule.scanner_id, str(expected["input_sha256"]))
            target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            try:
                target.chmod(0o600)
            except OSError:
                pass
    print("Required privacy scanner receipts recorded under Git metadata.")
    return 0


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("check", "route", "verify", "run"):
        subparser = subparsers.add_parser(name)
        choices = ("staged", "range", "all") if name != "run" else ("staged", "range")
        subparser.add_argument("--mode", choices=choices, default="staged")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    root = repo_root()
    try:
        if args.command == "check":
            return command_check(root, args.mode)
        if args.command == "route":
            command_route(root, args.mode)
            return 0
        if args.command == "verify":
            return command_verify(root, args.mode)
        return command_run(root, args.mode)
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"ERROR: privacy admission did not complete ({type(exc).__name__}: {exc}).", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
