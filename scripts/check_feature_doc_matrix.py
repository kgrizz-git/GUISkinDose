#!/usr/bin/env python3
"""Validate feature-to-documentation traceability metadata."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

MATRIX_PATH = Path("dev-docs/feature_doc_matrix.json")

# Conservative allowlist for git refs passed to ``git diff`` (Sonar S8705).
_SAFE_GIT_REF_RE = re.compile(r"^[\w./@{}^~-]+$")


def _resolve_within(path: Path, root: Path) -> Path:
    """Resolve ``path`` and require it stays under ``root`` (Sonar S8707)."""
    resolved = path.expanduser().resolve()
    root = root.resolve()
    if not (resolved == root or resolved.is_relative_to(root)):
        raise ValueError("changed-paths file escapes the repository root")
    return resolved
ALLOWED_STATUSES = {
    "roadmap",
    "shipped",
    "shipped_with_leftovers",
    "shipped_with_open_validation",
    "deferred",
    "retired",
}


@dataclass
class ValidationResult:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def repo_root_from_script() -> Path:
    return Path(__file__).resolve().parent.parent


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _is_non_empty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def load_matrix(repo_root: Path, result: ValidationResult) -> dict[str, Any] | None:
    path = repo_root / MATRIX_PATH
    if not path.is_file():
        result.errors.append(f"missing feature doc matrix: {MATRIX_PATH}")
        return None
    try:
        data = load_json(path)
    except json.JSONDecodeError as exc:
        result.errors.append(f"{MATRIX_PATH}: invalid JSON: {exc}")
        return None
    if not isinstance(data, dict):
        result.errors.append(f"{MATRIX_PATH}: root must be an object")
        return None
    if data.get("schema_version") != 1:
        result.errors.append(f"{MATRIX_PATH}: schema_version must be 1")
    features = data.get("features")
    if not isinstance(features, dict):
        result.errors.append(f"{MATRIX_PATH}: features must be an object")
        return None
    return data


def _path_list(feature_name: str, feature: dict[str, Any], field_name: str, result: ValidationResult) -> list[str]:
    value = feature.get(field_name)
    if not isinstance(value, list) or not all(_is_non_empty_string(item) for item in value):
        result.errors.append(f"{feature_name}: {field_name} must be a list of non-empty strings")
        return []
    return [str(item) for item in value]


def validate_feature_doc_matrix(repo_root: Path) -> ValidationResult:
    repo_root = repo_root.resolve()
    result = ValidationResult()
    data = load_matrix(repo_root, result)
    if data is None:
        return result
    features = data["features"]
    assert isinstance(features, dict)

    for feature_name, raw_feature in features.items():
        _validate_feature_entry(feature_name, raw_feature, repo_root, result)
    return result


def _validate_feature_entry(
    feature_name: str,
    raw_feature: object,
    repo_root: Path,
    result: ValidationResult,
) -> None:
    """Validate one feature entry while retaining all matrix error wording."""
    if not isinstance(raw_feature, dict):
        result.errors.append(f"{feature_name}: feature entry must be an object")
        return
    status = raw_feature.get("status")
    if not _is_non_empty_string(status):
        result.errors.append(f"{feature_name}: status must be a non-empty string")
    elif status not in ALLOWED_STATUSES:
        result.errors.append(f"{feature_name}: unknown status {status!r}")
    for field_name in ("code", "tests", "docs", "help"):
        for rel_path in _path_list(feature_name, raw_feature, field_name, result):
            if not (repo_root / rel_path).exists():
                result.errors.append(f"{feature_name}: missing {field_name} path {rel_path}")


def _feature_paths(feature: dict[str, Any], fields: tuple[str, ...]) -> set[str]:
    paths: set[str] = set()
    for field_name in fields:
        value = feature.get(field_name)
        if isinstance(value, list):
            paths.update(str(item) for item in value if isinstance(item, str))
    return paths


def _path_matches(changed_path: str, registered_path: str) -> bool:
    normalized_changed = changed_path.strip()
    normalized_registered = registered_path.rstrip("/")
    return normalized_changed == normalized_registered or normalized_changed.startswith(normalized_registered + "/")


def evaluate_doc_impact(
    repo_root: Path,
    *,
    changed_paths: list[str],
    strict_impact: bool = False,
) -> ValidationResult:
    repo_root = repo_root.resolve()
    result = validate_feature_doc_matrix(repo_root)
    if result.errors:
        return result
    data = load_matrix(repo_root, result)
    if data is None:
        return result
    features = data["features"]
    assert isinstance(features, dict)
    changed = [path.strip() for path in changed_paths if path.strip()]
    if not changed:
        return result

    for feature_name, raw_feature in features.items():
        if not isinstance(raw_feature, dict):
            continue
        implementation_paths = _feature_paths(raw_feature, ("code", "tests"))
        doc_paths = _feature_paths(raw_feature, ("docs", "help"))
        implementation_changed = any(
            _path_matches(changed_path, registered_path)
            for changed_path in changed
            for registered_path in implementation_paths
        )
        if not implementation_changed:
            continue
        docs_changed = any(
            _path_matches(changed_path, registered_path)
            for changed_path in changed
            for registered_path in doc_paths
        )
        if docs_changed:
            continue
        linked = ", ".join(sorted(doc_paths))
        message = f"{feature_name}: changed implementation path requires linked doc/help review ({linked})"
        if strict_impact:
            result.errors.append(message)
        else:
            result.warnings.append(message)
    return result


def changed_paths_from_file(path: Path, repo_root: Path) -> list[str]:
    safe_path = _resolve_within(path, repo_root)
    return safe_path.read_text(encoding="utf-8").splitlines()


def changed_paths_from_git(repo_root: Path, ref: str) -> tuple[list[str], str | None]:
    if not _SAFE_GIT_REF_RE.match(ref):
        raise ValueError("--against-ref does not match the allowed git-ref pattern")
    completed = subprocess.run(
        ["git", "diff", "--name-only", f"{ref}...HEAD"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return [], completed.stderr.strip() or completed.stdout.strip() or "git diff failed"
    return completed.stdout.splitlines(), None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate feature documentation traceability metadata.")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=repo_root_from_script(),
        help="Repository root (default: parent of scripts/)",
    )
    parser.add_argument("--changed-paths", type=Path, help="File containing changed paths, one per line.")
    parser.add_argument("--against-ref", help="Run git diff --name-only REF...HEAD for doc-impact warnings.")
    parser.add_argument("--strict-impact", action="store_true", help="Fail when changed implementation lacks doc/help changes.")
    args = parser.parse_args(argv)

    repo_root = args.repo_root.resolve()
    changed: list[str] = []
    git_warning: str | None = None
    if args.changed_paths:
        changed = changed_paths_from_file(args.changed_paths, repo_root)
    elif args.against_ref:
        changed, git_warning = changed_paths_from_git(repo_root, args.against_ref)

    result = (
        evaluate_doc_impact(repo_root, changed_paths=changed, strict_impact=args.strict_impact)
        if changed
        else validate_feature_doc_matrix(repo_root)
    )
    if git_warning:
        result.warnings.append(f"could not determine changed paths: {git_warning}")
    for warning in result.warnings:
        print(f"warning: {warning}", file=sys.stderr)
    if result.errors:
        print("Feature documentation matrix errors:", file=sys.stderr)
        for error in result.errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("Feature documentation matrix OK.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
