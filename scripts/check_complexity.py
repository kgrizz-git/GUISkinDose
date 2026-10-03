#!/usr/bin/env python3
"""Enforce per-function Ruff C901 complexity caps with a ratcheting caps file.

Metric: Ruff ``C901`` (McCabe cyclomatic complexity), threshold 10. New functions
at 11 or above fail. Grandfathered caps may only decrease or disappear.

Caps live in ``dev-docs/complexity_caps.json``; see the plan at
``dev-docs/plans/COMPLEXITY_GATES_PLAN.md``. ``--check`` (default) validates the
working tree against the caps file, ``--bootstrap`` creates the initial reviewed
baseline. ``--update`` and ``--migrate`` land in a later chunk.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
METRIC = "ruff-c901"
THRESHOLD = 10
CAPS_PATH = Path("dev-docs/complexity_caps.json")
SCAN_DIRS = ("src", "scripts")
CAP_KEYS = ("path", "function", "cap")
MIGRATION_KEYS = ("old_path", "old_function", "new_path", "new_function", "old_cap", "new_cap")
SCORE_RE = re.compile(r"^`([^`]+)` is too complex \((\d+) > (\d+)\)$")
VERSION_RE = re.compile(r"ruff (\d+\.\d+\.\d+)")


@dataclass(frozen=True)
class Finding:
    """One over-limit function keyed by POSIX-relative path and qualified name."""

    path: str
    function: str
    score: int
    row: int


def repo_root() -> Path:
    """Repository root inferred from this script's location."""
    return Path(__file__).resolve().parent.parent


def ruff_version(root: Path) -> str:
    """Exact Ruff version string reported by the locked environment."""
    result = subprocess.run(
        [sys.executable, "-m", "ruff", "--version"],
        capture_output=True,
        text=True,
        cwd=str(root),
    )
    if result.returncode != 0:
        raise RuntimeError(f"could not query ruff version: {result.stderr.strip()}")
    match = VERSION_RE.search(result.stdout)
    if match is None:
        raise RuntimeError(f"unparseable ruff version output: {result.stdout.strip()!r}")
    return match.group(1)


def ruff_findings_json(root: Path) -> list[dict[str, Any]]:
    """Raw Ruff C901 JSON diagnostics for the scanned directories."""
    targets = [directory for directory in SCAN_DIRS if (root / directory).is_dir()]
    if not targets:
        return []
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "ruff",
            "check",
            "--select",
            "C901",
            "--config",
            f"lint.mccabe.max-complexity={THRESHOLD}",
            "--output-format",
            "json",
            *targets,
        ],
        capture_output=True,
        text=True,
        cwd=str(root),
    )
    if result.returncode not in (0, 1):
        raise RuntimeError(f"ruff scan failed: {result.stderr.strip()}")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"ruff emitted no JSON: {exc}") from exc
    if not isinstance(payload, list):
        raise RuntimeError("ruff emitted unexpected JSON shape")
    return payload


def parse_findings(payload: list[dict[str, Any]]) -> list[tuple[Path, int, str, int]]:
    """Join raw diagnostics into (file, row, bare name, score) tuples.

    Raises ValueError on malformed entries so a broken tool contract fails the
    gate loudly instead of silently passing.
    """
    parsed: list[tuple[Path, int, str, int]] = []
    for item in payload:
        if not isinstance(item, dict) or item.get("code") != "C901" or item.get("name") != "complex-structure":
            raise ValueError(f"unexpected ruff diagnostic shape: {item!r}")
        try:
            filename = item["filename"]
            row = int(item["location"]["row"])
            message = str(item["message"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"malformed ruff diagnostic: {item!r}") from exc
        if not isinstance(filename, str) or not filename or row < 1:
            raise ValueError(f"malformed ruff diagnostic location: {item!r}")
        match = SCORE_RE.match(message)
        if match is None:
            raise ValueError(f"unparseable ruff message: {message!r}")
        bare_name, score_text, reported = match.groups()
        if int(reported) != THRESHOLD:
            raise ValueError(f"ruff reported threshold {reported}, expected {THRESHOLD}: {message!r}")
        parsed.append((Path(filename), row, bare_name, int(score_text)))
    return parsed


def qualified_names_by_row(path: Path) -> dict[int, str]:
    """Map each function/async-def definition row to its qualified dotted name.

    Nested functions include lexical parents (``outer.nested``); methods are
    ``Class.method``. Decorators do not change identity because Ruff reports the
    definition line even for decorated functions.
    """
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, UnicodeError) as exc:
        raise ValueError(f"cannot parse {path}: {exc}") from exc
    rows: dict[int, str] = {}

    def visit(node: ast.AST, scope: tuple[str, ...]) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.ClassDef):
                visit(child, (*scope, child.name))
            elif isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef):
                qualified = ".".join((*scope, child.name))
                if child.lineno in rows and rows[child.lineno] != qualified:
                    raise ValueError(f"ambiguous def row {child.lineno} in {path}")
                rows[child.lineno] = qualified
                visit(child, (*scope, child.name))
            else:
                visit(child, scope)

    visit(tree, ())
    return rows


def synthesize_findings(root: Path, parsed: list[tuple[Path, int, str, int]]) -> list[Finding]:
    """Synthesize qualified findings and reject missing joins or collisions."""
    findings: list[Finding] = []
    seen: dict[tuple[str, str], int] = {}
    cache: dict[Path, dict[int, str]] = {}
    for file_path, row, bare_name, score in parsed:
        try:
            relative = file_path.resolve().relative_to(root.resolve())
        except (ValueError, OSError) as exc:
            raise ValueError(f"ruff reported path outside root: {file_path}") from exc
        if file_path not in cache:
            cache[file_path] = qualified_names_by_row(file_path)
        qualified = cache[file_path].get(row)
        if qualified is None:
            raise ValueError(f"no def at row {row} for {bare_name!r} in {relative}")
        if qualified.split(".")[-1] != bare_name:
            raise ValueError(f"name mismatch for {bare_name!r} at row {row} in {relative}")
        key = (relative.as_posix(), qualified)
        if key in seen:
            raise ValueError(f"collision on qualified key {key}")
        seen[key] = score
        findings.append(Finding(relative.as_posix(), qualified, score, row))
    return findings


def collect_findings(root: Path) -> list[Finding]:
    """Run Ruff and return synthesized over-limit findings for the tree."""
    payload = ruff_findings_json(root)
    parsed = parse_findings(payload)
    return synthesize_findings(root, parsed)


def over_limit(findings: list[Finding], threshold: int = THRESHOLD) -> list[Finding]:
    """Findings with a measured score above the threshold."""
    return [finding for finding in findings if finding.score > threshold]


def canonical_document(tool_version: str, caps: list[Finding]) -> dict[str, Any]:
    """Canonical caps document with deterministic key and entry ordering."""
    return {
        "schema_version": SCHEMA_VERSION,
        "metric": METRIC,
        "tool_version": tool_version,
        "threshold": THRESHOLD,
        "caps": [
            {"path": finding.path, "function": finding.function, "cap": finding.score}
            for finding in sorted(caps, key=lambda f: (f.path, f.function))
        ],
        "migrations": [],
    }


def canonicalize(document: dict[str, Any]) -> bytes:
    """Byte-exact canonical serialization: indent 2, no ASCII escaping, LF end."""
    return (json.dumps(document, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def _validate_cap_entries(entries: Any) -> list[str]:
    """Shape and ordering rules for the caps list."""
    errors: list[str] = []
    if not isinstance(entries, list):
        return ["caps must be a list"]
    keys: list[tuple[str, str]] = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict) or set(entry) != set(CAP_KEYS):
            errors.append(f"caps[{index}] must be an object with exactly {CAP_KEYS}")
            continue
        if not isinstance(entry["path"], str) or not entry["path"] or entry["path"] != entry["path"].replace("\\", "/"):
            errors.append(f"caps[{index}].path must be a POSIX relative path")
        if not isinstance(entry["function"], str) or not entry["function"]:
            errors.append(f"caps[{index}].function must be a non-empty string")
        if not isinstance(entry["cap"], int) or isinstance(entry["cap"], bool) or entry["cap"] <= 0:
            errors.append(f"caps[{index}].cap must be a positive integer")
        if isinstance(entry.get("path"), str) and isinstance(entry.get("function"), str):
            keys.append((entry["path"], entry["function"]))
    if len(keys) != len(set(keys)):
        errors.append("duplicate (path, function) cap entries")
    if keys != sorted(keys):
        errors.append("caps entries must be sorted by (path, function), case-sensitive")
    return errors


def _validate_migrations(entries: Any) -> list[str]:
    """Shape rules for the migrations list (populated from chunk 2 onward)."""
    errors: list[str] = []
    if not isinstance(entries, list):
        return ["migrations must be a list"]
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict) or set(entry) != set(MIGRATION_KEYS):
            errors.append(f"migrations[{index}] must be an object with exactly {MIGRATION_KEYS}")
            continue
        for key in ("old_path", "old_function", "new_path", "new_function"):
            if not isinstance(entry[key], str) or not entry[key]:
                errors.append(f"migrations[{index}].{key} must be a non-empty string")
        for key in ("old_cap", "new_cap"):
            if not isinstance(entry[key], int) or isinstance(entry[key], bool) or entry[key] <= 0:
                errors.append(f"migrations[{index}].{key} must be a positive integer")
    return errors


def validate_caps_document(data: Any, tool_version: str) -> list[str]:
    """Return schema errors for a parsed caps document, or an empty list."""
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["caps file must contain a JSON object"]
    expected_keys = {"schema_version", "metric", "tool_version", "threshold", "caps", "migrations"}
    if set(data) != expected_keys:
        errors.append(f"top-level keys must be exactly {sorted(expected_keys)}")
        return errors
    if data["schema_version"] != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    if data["metric"] != METRIC:
        errors.append(f"metric must be {METRIC!r}")
    if data["tool_version"] != tool_version:
        errors.append(f"tool_version {data['tool_version']!r} does not match locked ruff {tool_version!r}")
    if data["threshold"] != THRESHOLD:
        errors.append(f"threshold must be {THRESHOLD}")
    errors.extend(_validate_cap_entries(data["caps"]))
    errors.extend(_validate_migrations(data["migrations"]))
    return errors


def validate_caps_file(path: Path, tool_version: str) -> tuple[dict[str, Any] | None, list[str]]:
    """Parse and validate the caps file, including byte-canonical formatting."""
    try:
        raw = path.read_bytes()
    except OSError as exc:
        return None, [f"cannot read caps file: {exc}"]
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        return None, [f"caps file is not valid JSON: {exc}"]
    schema_errors = validate_caps_document(data, tool_version)
    if not isinstance(data, dict):
        return None, schema_errors
    errors = list(schema_errors)
    try:
        if raw != canonicalize(data):
            errors.append("caps file is not in canonical form (reserialize and restage)")
        elif raw[-1:] != b"\n":
            errors.append("caps file must end with a newline")
    except (TypeError, ValueError) as exc:
        errors.append(f"caps file cannot be canonicalized: {exc}")
    return (data if not errors else None), errors


def cap_index(document: dict[str, Any]) -> dict[tuple[str, str], int]:
    """Map (path, function) to cap for measurement comparisons."""
    return {(entry["path"], entry["function"]): entry["cap"] for entry in document["caps"]}


def measurement_errors(findings: list[Finding], document: dict[str, Any]) -> list[str]:
    """Reconcile measured over-limit findings with the recorded caps."""
    errors: list[str] = []
    listed = cap_index(document)
    measured = {(f.path, f.function): f.score for f in findings}
    for finding in sorted(findings, key=lambda f: (f.path, f.function)):
        if finding.score <= THRESHOLD:
            continue
        key = (finding.path, finding.function)
        if key not in listed:
            errors.append(f"unlisted over-limit function: {key[0]}::{key[1]} score {finding.score} > {THRESHOLD}")
        elif listed[key] < finding.score:
            errors.append(f"over cap: {key[0]}::{key[1]} measured {finding.score} > cap {listed[key]}")
        elif listed[key] > finding.score:
            errors.append(
                f"cap above measured score: {key[0]}::{key[1]} cap {listed[key]} > measured {finding.score}; "
                "lower it to the measured value (a future --update will automate this)"
            )
    for (path, function), cap in sorted(listed.items()):
        if (path, function) not in measured or measured[(path, function)] <= THRESHOLD:
            errors.append(f"stale cap entry: {path}::{function} cap {cap} has no over-limit function")
    return errors


def check(root: Path) -> list[str]:
    """Return all gate errors for one working tree; empty list means pass."""
    try:
        findings = collect_findings(root)
        version = ruff_version(root)
    except (ValueError, RuntimeError) as exc:
        return [f"could not collect complexity data: {exc}"]
    over = over_limit(findings)
    caps_path = root / CAPS_PATH
    if not caps_path.is_file():
        return [f"caps file missing: {CAPS_PATH} (run scripts/check_complexity.py --bootstrap after review)"]
    document, errors = validate_caps_file(caps_path, version)
    if document is None:
        return errors
    errors.extend(measurement_errors(over, document))
    return errors


def _ref_has_caps_file(ref: str, root: Path) -> bool | None:
    """True/False whether ``ref`` has the caps file; None when the ref is unavailable."""
    verify = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", ref],
        capture_output=True,
        text=True,
        cwd=str(root),
    )
    if verify.returncode != 0:
        return None
    result = subprocess.run(
        ["git", "ls-tree", ref, "--", CAPS_PATH.as_posix()],
        capture_output=True,
        text=True,
        cwd=str(root),
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip() != ""


def bootstrap_blocked(root: Path) -> list[str]:
    """Reasons bootstrap may not run; empty means it may proceed."""
    errors: list[str] = []
    if (root / CAPS_PATH).exists():
        errors.append("caps file already exists in the working tree")
    head = _ref_has_caps_file("HEAD", root)
    if head is True:
        errors.append("caps file already present at HEAD")
    elif head is None:
        errors.append("git HEAD unavailable; cannot verify bootstrap precondition")
    base = _ref_has_caps_file("origin/main", root)
    if base is True:
        errors.append("caps file already present at origin/main")
    elif base is None:
        errors.append("origin/main ref unavailable; cannot prove the branch base has no caps file")
    return errors


def bootstrap(root: Path) -> list[str]:
    """Write the initial canonical caps file; refuse to overwrite or re-run."""
    blocked = bootstrap_blocked(root)
    if blocked:
        return blocked
    try:
        findings = collect_findings(root)
        version = ruff_version(root)
    except (ValueError, RuntimeError) as exc:
        return [f"could not collect complexity data: {exc}"]
    over = over_limit(findings)
    document = canonical_document(version, over)
    caps_path = root / CAPS_PATH
    try:
        caps_path.parent.mkdir(parents=True, exist_ok=True)
        caps_path.write_bytes(canonicalize(document))
    except OSError as exc:
        return [f"cannot write caps file: {exc}"]
    print(f"bootstrap: wrote {CAPS_PATH} with {len(over)} caps at ruff {version}")
    return []


def main(argv: list[str] | None = None) -> int:
    """Parse flags and dispatch the selected mode."""
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--check", action="store_true", help="validate the tree against caps (default)")
    parser.add_argument("--bootstrap", action="store_true", help="create the initial reviewed caps baseline")
    parser.add_argument("--update", action="store_true", help="lower/remove caps only (later chunk)")
    parser.add_argument("--migrate", nargs=2, metavar=("OLD_PATH:OLD_FUNCTION", "NEW_PATH:NEW_FUNCTION"), help="rename a cap (later chunk)")
    args = parser.parse_args(argv)
    modes = [args.check, args.bootstrap, args.update, args.migrate is not None]
    if sum(modes) > 1:
        parser.error("choose exactly one of --check/--bootstrap/--update/--migrate")
    root = repo_root()
    if args.bootstrap:
        errors = bootstrap(root)
    elif args.update or args.migrate is not None:
        print("--update/--migrate are not implemented yet (chunk 2).", file=sys.stderr)
        return 2
    else:
        errors = check(root)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print("SUCCESS: complexity gate passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
