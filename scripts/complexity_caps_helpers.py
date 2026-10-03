#!/usr/bin/env python3
"""Data, validation, cap-history, update, and migrate helpers for check_complexity."""

from __future__ import annotations

import ast
import json
import os
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


def _write_caps_atomic(path: Path, data: bytes) -> None:
    """Write bytes to ``path`` atomically via a same-directory replace."""
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(data)
    temporary.replace(path)


def _validate_cap_entries(entries: Any) -> list[str]:
    """Shape and ordering rules for the caps list."""
    errors: list[str] = []
    if not isinstance(entries, list):
        return ["caps must be a list"]
    keys: list[tuple[str, str]] = []
    for index, entry in enumerate(entries):
        entry_errors, key = _validate_cap_entry(index, entry)
        errors.extend(entry_errors)
        if key is not None:
            keys.append(key)
    if len(keys) != len(set(keys)):
        errors.append("duplicate (path, function) cap entries")
    if keys != sorted(keys):
        errors.append("caps entries must be sorted by (path, function), case-sensitive")
    return errors


def _validate_cap_entry(index: int, entry: Any) -> tuple[list[str], tuple[str, str] | None]:
    """Validate one cap and return its key for duplicate and ordering checks."""
    if not isinstance(entry, dict) or set(entry) != set(CAP_KEYS):
        return [f"caps[{index}] must be an object with exactly {CAP_KEYS}"], None
    errors: list[str] = []
    path = entry["path"]
    function = entry["function"]
    cap = entry["cap"]
    if not isinstance(path, str) or not path or "\\" in path:
        errors.append(f"caps[{index}].path must be a POSIX relative path")
    if not isinstance(function, str) or not function:
        errors.append(f"caps[{index}].function must be a non-empty string")
    if not isinstance(cap, int) or isinstance(cap, bool) or cap <= 0:
        errors.append(f"caps[{index}].cap must be a positive integer")
    key = (path, function) if isinstance(path, str) and isinstance(function, str) else None
    return errors, key


def _validate_migrations(entries: Any) -> list[str]:
    """Shape, ordering, and uniqueness rules for the migrations list."""
    errors: list[str] = []
    if not isinstance(entries, list):
        return ["migrations must be a list"]
    old_keys: list[tuple[str, str]] = []
    new_keys: list[tuple[str, str]] = []
    order_keys: list[tuple[str, str]] = []
    for index, entry in enumerate(entries):
        errors.extend(_validate_migration_entry(index, entry, old_keys, new_keys, order_keys))
    if len(old_keys) != len(set(old_keys)):
        errors.append("duplicate old key across migration records")
    if len(new_keys) != len(set(new_keys)):
        errors.append("duplicate new key across migration records")
    if order_keys != sorted(order_keys):
        errors.append("migrations must be sorted by (old_path, old_function)")
    return errors


def _validate_migration_entry(
    index: int,
    entry: Any,
    old_keys: list[tuple[str, str]],
    new_keys: list[tuple[str, str]],
    order_keys: list[tuple[str, str]],
) -> list[str]:
    """Validate one migration entry and record its keys for cross-entry checks."""
    errors: list[str] = []
    if not isinstance(entry, dict) or set(entry) != set(MIGRATION_KEYS):
        return [f"migrations[{index}] must be an object with exactly {MIGRATION_KEYS}"]
    for key in ("old_path", "old_function", "new_path", "new_function"):
        if not isinstance(entry[key], str) or not entry[key]:
            errors.append(f"migrations[{index}].{key} must be a non-empty string")
    for key in ("old_cap", "new_cap"):
        if not isinstance(entry[key], int) or isinstance(entry[key], bool) or entry[key] <= 0:
            errors.append(f"migrations[{index}].{key} must be a positive integer")
    if isinstance(entry["old_cap"], int) and isinstance(entry["new_cap"], int) and entry["new_cap"] > entry["old_cap"]:
        errors.append(f"migrations[{index}].new_cap must not exceed old_cap")
    old_path = entry.get("old_path")
    old_function = entry.get("old_function")
    new_path = entry.get("new_path")
    new_function = entry.get("new_function")
    if isinstance(old_path, str) and isinstance(old_function, str) and isinstance(new_path, str) and isinstance(new_function, str):
        old_keys.append((old_path, old_function))
        new_keys.append((new_path, new_function))
        order_keys.append((old_path, old_function))
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
                "lower it to the measured value (or run --update to do it automatically)"
            )
    for (path, function), cap in sorted(listed.items()):
        if (path, function) not in measured or measured[(path, function)] <= THRESHOLD:
            errors.append(f"stale cap entry: {path}::{function} cap {cap} has no over-limit function")
    return errors


GIT_TIMEOUT_SECONDS = 30


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run a bounded local Git command with an argument list (no shell)."""
    try:
        return subprocess.run(
            ["git", *args], capture_output=True, text=True, cwd=str(root), timeout=GIT_TIMEOUT_SECONDS
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"Git history lookup timed out after {GIT_TIMEOUT_SECONDS} seconds") from exc


def _in_git_repo(root: Path) -> bool:
    """True when ``root`` is inside a Git working tree."""
    return _git(root, "rev-parse", "--is-inside-work-tree").returncode == 0


def _caps_bytes_at_ref(root: Path, ref: str) -> bytes | None:
    """Caps file bytes at ``ref``, or None when the ref/path is absent."""
    try:
        result = subprocess.run(
            ["git", "show", f"{ref}:{CAPS_PATH.as_posix()}"],
            capture_output=True,
            cwd=str(root),
            timeout=GIT_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"Git history lookup timed out after {GIT_TIMEOUT_SECONDS} seconds") from exc
    if result.returncode != 0:
        return None
    return result.stdout


def _resolve_ref(root: Path, ref: str) -> str | None:
    """Resolve ``ref`` to a SHA, or None when it is unavailable."""
    result = _git(root, "rev-parse", "--verify", "--quiet", ref)
    if result.returncode != 0:
        return None
    result_object = _git(root, "cat-file", "-e", ref)
    if result_object.returncode != 0:
        return None
    return result.stdout.strip() or None


def _comparison_base_ref(root: Path) -> tuple[str | None, str | None]:
    """Return ``(ref, error)`` for the cap-history comparison target.

    CI env wins: ``GITHUB_BASE_REF`` (PR) or ``COMPLEXITY_BEFORE_SHA`` (main
    push). Otherwise compare with the current ``origin/main`` tip. Comparing
    with the base branch tip catches cap reductions made after this branch
    diverged. A missing base fails closed.
    """
    base_ref = os.environ.get("GITHUB_BASE_REF")
    if base_ref:
        target = _resolve_ref(root, f"origin/{base_ref}")
        if target is None:
            return None, f"origin/{base_ref} not available; run: git fetch origin {base_ref}"
        return target, None
    before = os.environ.get("COMPLEXITY_BEFORE_SHA")
    if before:
        if _resolve_ref(root, before) is None:
            return None, f"COMPLEXITY_BEFORE_SHA {before} not available locally"
        return before, None
    target = _resolve_ref(root, "origin/main")
    if target is None:
        return None, "origin/main unavailable; run: git fetch origin main"
    return target, None


def _first_caps_introduction_commit(root: Path, base: str | None) -> str | None:
    """Oldest commit adding the caps file after ``base``, or None when not in range."""
    range_args = [f"{base}..HEAD"] if base else ["HEAD"]
    result = _git(root, "log", "--diff-filter=A", "--reverse", "--format=%H", *range_args, "--", CAPS_PATH.as_posix())
    if result.returncode != 0:
        return None
    commits = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    return commits[0] if commits else None


def _migrations_unique(records: list[Any]) -> bool:
    """True when old keys and new keys are each unique across all records."""
    old_keys = [(r.get("old_path"), r.get("old_function")) for r in records if isinstance(r, dict)]
    new_keys = [(r.get("new_path"), r.get("new_function")) for r in records if isinstance(r, dict)]
    return len(old_keys) == len(set(old_keys)) and len(new_keys) == len(set(new_keys))


def _migration_record_errors(
    record: dict[str, Any],
    prior_cap: int,
    from_base: bool,
    new_caps: dict[tuple[str, str], int],
    successor_keys: set[tuple[str, str]],
) -> list[str]:
    """Check one migration against its predecessor and the final caps."""
    errors: list[str] = []
    old_key = (record["old_path"], record["old_function"])
    new_key = (record["new_path"], record["new_function"])
    if old_key in new_caps:
        errors.append(f"migrated old key still present: {old_key[0]}::{old_key[1]}")
    if new_key not in new_caps and new_key not in successor_keys:
        errors.append(f"migration target missing from caps: {new_key[0]}::{new_key[1]}")
    elif new_key in new_caps and new_caps[new_key] > record["new_cap"]:
        errors.append(f"migration cap exceeds recorded limit: {new_key[0]}::{new_key[1]} {new_caps[new_key]} > {record['new_cap']}")
    if record["old_cap"] > prior_cap or (from_base and record["old_cap"] != prior_cap):
        errors.append(f"migration old_cap mismatch: {old_key[0]}::{old_key[1]} {record['old_cap']} != {prior_cap}")
    if record["new_cap"] > prior_cap:
        errors.append(f"migration raised cap: {old_key[0]}::{old_key[1]} {prior_cap} -> {record['new_cap']}")
    return errors


def _new_migration_errors(
    records: list[dict[str, Any]], old_caps: dict[tuple[str, str], int], new_caps: dict[tuple[str, str], int]
) -> list[str]:
    """Follow new migration chains from base caps regardless of record sort order."""
    errors: list[str] = []
    available = dict(old_caps)
    pending = list(records)
    successor_keys = {(r["old_path"], r["old_function"]) for r in records}
    while pending:
        ready = [r for r in pending if (r["old_path"], r["old_function"]) in available]
        if not ready:
            errors.extend(f"migration references unknown old key: {r['old_path']}::{r['old_function']}" for r in pending)
            break
        for record in ready:
            old_key = (record["old_path"], record["old_function"])
            new_key = (record["new_path"], record["new_function"])
            errors.extend(_migration_record_errors(record, available[old_key], old_key in old_caps, new_caps, successor_keys))
            available[new_key] = record["new_cap"]
            pending.remove(record)
    return errors


def compare_caps_history(old: dict[str, Any] | None, new: dict[str, Any]) -> list[str]:
    """Cap-history rules between a base document and the working-tree document.

    ``old`` is None when the comparison base has no caps file; that is the
    bootstrap-permitted path and live validation of the new file is the only
    guard. Historical migration records must be preserved verbatim (as an
    unchanged subset, regardless of position in the merged sorted list);
    only genuinely new records are validated for this comparison.
    """
    if old is None:
        return []
    errors: list[str] = []
    old_caps = cap_index(old)
    new_caps = cap_index(new)
    old_records = old["migrations"]
    new_records = new["migrations"]
    old_serialized = [json.dumps(r, sort_keys=True) for r in old_records]
    new_serialized = [json.dumps(r, sort_keys=True) for r in new_records]
    if not all(record in new_serialized for record in old_serialized):
        errors.append("existing migration records must be preserved unchanged")
    genuinely_new = [r for r, s in zip(new_records, new_serialized, strict=True) if s not in old_serialized]
    if not _migrations_unique(new_records):
        errors.append("migration records must reference each old and new key at most once")
    errors.extend(_new_migration_errors(genuinely_new, old_caps, new_caps))
    new_record_targets = {(r["new_path"], r["new_function"]) for r in genuinely_new if isinstance(r, dict)}
    errors.extend(_metadata_drift_errors(old, new))
    for key, cap in sorted(new_caps.items()):
        if key in old_caps and cap > old_caps[key]:
            errors.append(f"raised cap: {key[0]}::{key[1]} {old_caps[key]} -> {cap}")
        elif key not in old_caps and key not in new_record_targets:
            errors.append(f"unexplained added cap: {key[0]}::{key[1]}")
    return errors


def _metadata_drift_errors(old: dict[str, Any], new: dict[str, Any]) -> list[str]:
    """Schema/metric/threshold metadata changes are unauthorized in caps edits."""
    errors: list[str] = []
    if old["schema_version"] != new["schema_version"]:
        errors.append("schema_version metadata changed; gate schema is fixed")
    if old["metric"] != new["metric"]:
        errors.append("metric metadata changed; metric is fixed")
    if old["threshold"] != new["threshold"]:
        errors.append("threshold metadata changed; threshold is fixed")
    return errors


def check_cap_history(root: Path, document: dict[str, Any], wt_bytes: bytes) -> list[str]:
    """Validate cap-file history for the current working tree.

    Base resolution fails closed when unavailable. When the current base branch
    lacks caps, the first introduction commit in
    ``base..HEAD`` supplies the comparison document so later caps-only changes
    on the same branch are still resisted. Working-tree bytes equal to the
    comparison base's cap bytes pass without further comparison.
    """
    if not _in_git_repo(root):
        return []
    base, error = _comparison_base_ref(root)
    if base is None:
        return [error] if error else ["could not establish cap-history base"]
    old_bytes = _caps_bytes_at_ref(root, base)
    if old_bytes is not None:
        if old_bytes == wt_bytes:
            return []
        try:
            old_doc = json.loads(old_bytes)
        except json.JSONDecodeError:
            return ["caps file at base unreadable"]
        base_errors = validate_caps_document(old_doc, document["tool_version"])
        if base_errors:
            return [f"caps file at base invalid: {error}" for error in base_errors]
        return compare_caps_history(old_doc, document)
    return _check_via_introduction_commit(root, base, document, wt_bytes)


def _check_via_introduction_commit(root: Path, base: str, document: dict[str, Any], wt_bytes: bytes) -> list[str]:
    """Compare WT against the branch's first caps-introduction commit when available."""
    first_commit = _first_caps_introduction_commit(root, base)
    if first_commit is not None:
        first_bytes = _caps_bytes_at_ref(root, first_commit)
        if first_bytes is None:
            return ["caps file introduction commit unreadable"]
        if first_bytes == wt_bytes:
            return []
        try:
            first_doc = json.loads(first_bytes)
        except json.JSONDecodeError:
            return ["caps file at introduction commit unreadable"]
        first_errors = validate_caps_document(first_doc, document["tool_version"])
        if first_errors:
            return [f"caps file at introduction commit invalid: {error}" for error in first_errors]
        return compare_caps_history(first_doc, document)
    head_bytes = _caps_bytes_at_ref(root, "HEAD")
    if head_bytes is None:
        # No caps file in history at all: the working-tree file is the pending
        # bootstrap candidate; live validation is the only guard.
        return []
    return ["caps file at HEAD not in comparison base and no introduction commit found; fail closed"]


def _update_caps_document(document: dict[str, Any], findings: list[Finding]) -> tuple[dict[str, Any], list[str]]:
    """Lower or drop caps to current measured scores; never add or raise."""
    measured = {(f.path, f.function): f.score for f in findings if f.score > THRESHOLD}
    new_caps: list[dict[str, Any]] = []
    changes: list[str] = []
    for entry in document["caps"]:
        key = (entry["path"], entry["function"])
        if key not in measured:
            changes.append(f"removed stale cap {key[0]}::{key[1]}")
            continue
        score = measured[key]
        if score < entry["cap"]:
            changes.append(f"lowered {key[0]}::{key[1]} {entry['cap']} -> {score}")
            new_caps.append({"path": key[0], "function": key[1], "cap": score})
        elif score > entry["cap"]:
            changes.append(f"kept {key[0]}::{key[1]} at {entry['cap']} (measured {score} is higher; a raise needs review)")
            new_caps.append(dict(entry))
        else:
            new_caps.append(dict(entry))
    new_caps.sort(key=lambda e: (e["path"], e["function"]))
    updated = dict(document)
    updated["caps"] = new_caps
    updated["migrations"] = sorted(document["migrations"], key=lambda m: (m["old_path"], m["old_function"]))
    return updated, changes


def update(root: Path) -> list[str]:
    """Rewrite caps to measured scores (lower/remove only); never adds."""
    try:
        findings = collect_findings(root)
        version = ruff_version(root)
    except (ValueError, RuntimeError) as exc:
        return [f"could not collect complexity data: {exc}"]
    caps_path = root / CAPS_PATH
    if not caps_path.is_file():
        return [f"caps file missing: {CAPS_PATH}"]
    try:
        document = json.loads(caps_path.read_bytes())
    except (OSError, json.JSONDecodeError) as exc:
        return [f"caps file unreadable: {exc}"]
    schema_errors = validate_caps_document(document, version)
    if schema_errors:
        return schema_errors
    updated, changes = _update_caps_document(document, findings)
    if updated["caps"] == document["caps"] and updated["migrations"] == document["migrations"]:
        print("update: no changes")
        return []
    try:
        _write_caps_atomic(caps_path, canonicalize(updated))
    except OSError as exc:
        return [f"cannot write caps file: {exc}"]
    for change in changes:
        print(f"update: {change}")
    print("update: caps file rewritten; run --check to re-verify")
    return []


def _split_key(token: str) -> tuple[str, str] | None:
    """Split ``path:function`` on the last colon (Windows-drive-safe)."""
    if ":" not in token:
        return None
    path, function = token.rsplit(":", 1)
    if not path or not function:
        return None
    return path, function


def _migration_target_errors(
    old: tuple[str, str], new: tuple[str, str], caps: dict[tuple[str, str], int], measured: dict[tuple[str, str], int]
) -> list[str]:
    """Reject a rename that would create a missing or unusable cap."""
    if old not in caps:
        return [f"old cap not found: {old[0]}::{old[1]}"]
    if new in caps:
        return [f"new key already capped: {new[0]}::{new[1]}"]
    if new not in measured:
        return [f"new function not over-limit: {new[0]}::{new[1]} (cap would be stale)"]
    if measured[new] > caps[old]:
        return [f"new function exceeds old cap: {new[0]}::{new[1]} measured {measured[new]} > cap {caps[old]}"]
    return []


def migrate(root: Path, old_token: str, new_token: str) -> list[str]:
    """Atomically rename a cap, recording the migration; cap never raises."""
    old = _split_key(old_token)
    new = _split_key(new_token)
    if old is None or new is None:
        return ["expected OLD_PATH:OLD_FUNCTION NEW_PATH:NEW_FUNCTION"]
    try:
        findings = collect_findings(root)
        version = ruff_version(root)
    except (ValueError, RuntimeError) as exc:
        return [f"could not collect complexity data: {exc}"]
    caps_path = root / CAPS_PATH
    if not caps_path.is_file():
        return [f"caps file missing: {CAPS_PATH}"]
    try:
        document = json.loads(caps_path.read_bytes())
    except (OSError, json.JSONDecodeError) as exc:
        return [f"caps file unreadable: {exc}"]
    schema_errors = validate_caps_document(document, version)
    if schema_errors:
        return schema_errors
    caps = cap_index(document)
    measured = {(f.path, f.function): f.score for f in findings if f.score > THRESHOLD}
    target_errors = _migration_target_errors(old, new, caps, measured)
    if target_errors:
        return target_errors
    old_cap = caps[old]
    new_cap = measured[new]
    document["caps"] = sorted(
        [e for e in document["caps"] if (e["path"], e["function"]) != old] + [{"path": new[0], "function": new[1], "cap": new_cap}],
        key=lambda e: (e["path"], e["function"]),
    )
    document["migrations"] = sorted(
        document["migrations"]
        + [
            {
                "old_path": old[0],
                "old_function": old[1],
                "new_path": new[0],
                "new_function": new[1],
                "old_cap": old_cap,
                "new_cap": new_cap,
            }
        ],
        key=lambda m: (m["old_path"], m["old_function"]),
    )
    try:
        _write_caps_atomic(caps_path, canonicalize(document))
    except OSError as exc:
        return [f"cannot write caps file: {exc}"]
    print(f"migrate: {old[0]}::{old[1]} -> {new[0]}::{new[1]} cap {old_cap} -> {new_cap}")
    return []
