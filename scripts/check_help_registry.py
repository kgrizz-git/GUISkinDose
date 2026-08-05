#!/usr/bin/env python3
"""Validate GUI help registry metadata and bundled help files."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REGISTRY_PATH = Path("dev-docs/help_registry.json")


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


def _entry_context(index: int, entry: object) -> str:
    if isinstance(entry, dict) and _is_non_empty_string(entry.get("id")):
        return str(entry["id"])
    return f"entry[{index}]"


def _validate_registry_shape(data: object, result: ValidationResult) -> tuple[Path, Path, list[dict[str, Any]]]:
    if not isinstance(data, dict):
        result.errors.append("registry root must be a JSON object")
        return Path(), Path(), []
    if data.get("schema_version") != 1:
        result.errors.append("schema_version must be 1")
    source_dir_raw = data.get("source_dir")
    target_dir_raw = data.get("target_dir")
    entries_raw = data.get("entries")
    if not _is_non_empty_string(source_dir_raw):
        result.errors.append("source_dir must be a non-empty string")
        source_dir_raw = ""
    if not _is_non_empty_string(target_dir_raw):
        result.errors.append("target_dir must be a non-empty string")
        target_dir_raw = ""
    if not isinstance(entries_raw, list):
        result.errors.append("entries must be a list")
        entries_raw = []

    entries: list[dict[str, Any]] = []
    for index, entry in enumerate(entries_raw):
        validated = _validate_registry_entry(index, entry, result)
        if validated is not None:
            entries.append(validated)
    return Path(str(source_dir_raw)), Path(str(target_dir_raw)), entries


def _validate_registry_entry(index: int, entry: object, result: ValidationResult) -> dict[str, Any] | None:
    """Validate one registry entry while preserving malformed-entry recovery."""
    context = _entry_context(index, entry)
    if not isinstance(entry, dict):
        result.errors.append(f"{context}: entry must be an object")
        return None
    for field_name in ("id", "title", "source"):
        if not _is_non_empty_string(entry.get(field_name)):
            result.errors.append(f"{context}: {field_name} must be a non-empty string")
    gui_files = entry.get("gui_files")
    if not isinstance(gui_files, list) or not all(_is_non_empty_string(item) for item in gui_files):
        result.errors.append(f"{context}: gui_files must be a list of non-empty strings")
    return entry


def _source_is_referenced(source: str, gui_texts: list[str]) -> bool:
    pattern = re.compile(rf"content_path\s*=\s*['\"]{re.escape(source)}['\"]")
    return any(pattern.search(text) for text in gui_texts)


def _help_id_is_referenced(help_id: str, gui_texts: list[str]) -> bool:
    pattern = re.compile(rf"help_id\s*=\s*['\"]{re.escape(help_id)}['\"]")
    return any(pattern.search(text) for text in gui_texts)


def validate_help_registry(repo_root: Path, *, strict: bool = False) -> ValidationResult:
    repo_root = repo_root.resolve()
    result = ValidationResult()
    registry_path = repo_root / REGISTRY_PATH
    if not registry_path.is_file():
        result.errors.append(f"missing help registry: {REGISTRY_PATH}")
        return result

    try:
        data = load_json(registry_path)
    except json.JSONDecodeError as exc:
        result.errors.append(f"{REGISTRY_PATH}: invalid JSON: {exc}")
        return result

    source_dir, target_dir, entries = _validate_registry_shape(data, result)
    source_root = repo_root / source_dir
    target_root = repo_root / target_dir

    seen_ids: set[str] = set()
    registered_sources: set[str] = set()
    for index, entry in enumerate(entries):
        _check_entry(
            index,
            entry,
            source_root,
            target_root,
            source_dir,
            target_dir,
            repo_root,
            result,
            strict,
            seen_ids,
            registered_sources,
        )

    if source_root.is_dir():
        _check_orphaned_sources(source_root, source_dir, registered_sources, result, strict)

    return result


def _check_entry(
    index: int,
    entry: dict[str, Any],
    source_root: Path,
    target_root: Path,
    source_dir: Path,
    target_dir: Path,
    repo_root: Path,
    result: ValidationResult,
    strict: bool,
    seen_ids: set[str],
    registered_sources: set[str],
) -> None:
    context = _entry_context(index, entry)
    help_id = str(entry.get("id", ""))
    source = str(entry.get("source", ""))

    if help_id in seen_ids:
        result.errors.append(f"{context}: duplicate help id {help_id!r}")
    seen_ids.add(help_id)
    if source:
        registered_sources.add(source)

    _check_entry_files(source, source_root, target_root, source_dir, target_dir, context, result)
    _check_gui_references(entry, repo_root, source, help_id, context, result, strict)


def _check_entry_files(
    source: str,
    source_root: Path,
    target_root: Path,
    source_dir: Path,
    target_dir: Path,
    context: str,
    result: ValidationResult,
) -> None:
    if not source:
        return
    source_path = source_root / source
    target_path = target_root / source
    if not source_path.is_file():
        result.errors.append(f"{context}: missing source help file {source_dir / source}")
    if not target_path.is_file():
        result.errors.append(
            f"{context}: missing mirrored help file {target_dir / source}; run scripts/sync_gui_help.py"
        )
    elif source_path.is_file() and source_path.read_text(encoding="utf-8") != target_path.read_text(encoding="utf-8"):
        result.errors.append(f"{context}: mirrored help file is stale; run scripts/sync_gui_help.py")


def _check_gui_references(
    entry: dict[str, Any],
    repo_root: Path,
    source: str,
    help_id: str,
    context: str,
    result: ValidationResult,
    strict: bool,
) -> None:
    if "gui_files" in entry:
        gui_files = entry["gui_files"]
        if not isinstance(gui_files, list):
            result.errors.append(f"{context}: 'gui_files' must be a list of file paths")
            return
    else:
        gui_files = []

    gui_texts: list[str] = []
    for gui_file in gui_files:
        if not isinstance(gui_file, (str, Path)):
            result.errors.append(f"{context}: GUI file paths must be strings, got {type(gui_file)}")
            continue
        gui_path = repo_root / str(gui_file)
        if not gui_path.is_file():
            result.errors.append(f"{context}: missing GUI file {gui_file}")
            continue
        gui_texts.append(gui_path.read_text(encoding="utf-8"))

    if not gui_texts:
        return
    if source and not _source_is_referenced(source, gui_texts):
        result.errors.append(f"{context}: GUI files do not reference content_path={source!r}")
    if help_id and not _help_id_is_referenced(help_id, gui_texts):
        message = f"{context}: GUI files do not reference help_id={help_id!r}"
        _append_ref_error(result, message, strict)


def _append_ref_error(result: ValidationResult, message: str, strict: bool) -> None:
    if strict:
        result.errors.append(message)
    else:
        result.warnings.append(message)


def _check_orphaned_sources(
    source_root: Path,
    source_dir: Path,
    registered_sources: set[str],
    result: ValidationResult,
    strict: bool,
) -> None:
    for source_path in sorted(source_root.glob("*.md")):
        if source_path.name in registered_sources:
            continue
        message = f"orphaned source help file {source_dir / source_path.name}"
        if strict:
            result.errors.append(message)
        else:
            result.warnings.append(message)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate GUI help registry metadata.")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=repo_root_from_script(),
        help="Repository root (default: parent of scripts/)",
    )
    parser.add_argument("--strict", action="store_true", help="Fail on advisory help-registry warnings.")
    args = parser.parse_args(argv)

    result = validate_help_registry(args.repo_root, strict=args.strict)
    for warning in result.warnings:
        print(f"warning: {warning}", file=sys.stderr)
    if result.errors:
        print("GUI help registry errors:", file=sys.stderr)
        for error in result.errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("GUI help registry OK.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
