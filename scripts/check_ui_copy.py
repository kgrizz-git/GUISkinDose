#!/usr/bin/env python3
"""Validate GUI UI-copy and glossary metadata."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

UI_COPY_PATH = Path("dev-docs/ui_copy.json")
GLOSSARY_PATH = Path("dev-docs/glossary.json")
COPY_TEXT_RE = re.compile(r"copy_text\(\s*['\"]([^'\"]+)['\"]\s*\)")
SOURCE_SCAN_ROOT = Path("src/mypyskindose/gui")

TERMINOLOGY_RULES = (
    (re.compile(r"\bmaximum skin dose\b", re.IGNORECASE), "use 'peak skin dose'"),
    (re.compile(r"\bhalf value layer\b", re.IGNORECASE), "use 'half-value layer'"),
    (re.compile(r"\bsubfloor\b", re.IGNORECASE), "use 'below-floor'"),
)


@dataclass
class ValidationResult:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def repo_root_from_script() -> Path:
    return Path(__file__).resolve().parent.parent


def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    seen: set[str] = set()
    duplicates: list[str] = []
    for key, value in pairs:
        if key in seen:
            duplicates.append(key)
        seen.add(key)
        result[key] = value
    if duplicates:
        joined = ", ".join(sorted(set(duplicates)))
        raise ValueError(f"duplicate JSON key(s): {joined}")
    return result


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=reject_duplicate_keys)


def _is_non_empty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _load_metadata(path: Path, result: ValidationResult) -> Any:
    if not path.is_file():
        result.errors.append(f"missing metadata file {path}")
        return None
    try:
        return load_json(path)
    except (json.JSONDecodeError, ValueError) as exc:
        result.errors.append(f"{path}: invalid JSON: {exc}")
        return None


def _resolve_owner(repo_root: Path, owner: str) -> Path:
    if owner.startswith("src/"):
        return repo_root / owner
    return repo_root / "src" / "mypyskindose" / owner


def _collect_copy_text_uses(repo_root: Path) -> dict[str, list[Path]]:
    uses: dict[str, list[Path]] = {}
    scan_root = repo_root / SOURCE_SCAN_ROOT
    if not scan_root.is_dir():
        return uses
    for path in sorted(scan_root.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        for match in COPY_TEXT_RE.finditer(text):
            uses.setdefault(match.group(1), []).append(path.relative_to(repo_root))
    return uses


def validate_ui_copy(repo_root: Path, *, strict: bool = False) -> ValidationResult:
    repo_root = repo_root.resolve()
    result = ValidationResult()
    data = _load_metadata(repo_root / UI_COPY_PATH, result)
    if not isinstance(data, dict):
        if data is not None:
            result.errors.append(f"{UI_COPY_PATH}: root must be an object")
        return result
    if data.get("schema_version") != 1:
        result.errors.append(f"{UI_COPY_PATH}: schema_version must be 1")
    keys = data.get("keys")
    if not isinstance(keys, dict):
        result.errors.append(f"{UI_COPY_PATH}: keys must be an object")
        return result

    used_keys = _collect_copy_text_uses(repo_root)
    for key, files in used_keys.items():
        if key not in keys:
            joined = ", ".join(str(path) for path in files)
            result.errors.append(f"{joined}: copy_text key is not in catalog: {key}")

    for key, item in keys.items():
        if not isinstance(item, dict):
            result.errors.append(f"{key}: catalog entry must be an object")
            continue
        text = item.get("text")
        owner = item.get("owner")
        if not _is_non_empty_string(text):
            result.errors.append(f"{key}: text must be a non-empty string")
        if not _is_non_empty_string(owner):
            result.errors.append(f"{key}: owner must be a non-empty string")
            continue
        owner_path = _resolve_owner(repo_root, str(owner))
        if not owner_path.is_file():
            result.errors.append(f"{key}: owner file does not exist: {owner}")
            continue
        owner_text = owner_path.read_text(encoding="utf-8")
        if key not in used_keys:
            message = f"{key}: unused UI copy key"
            if strict:
                result.errors.append(message)
            else:
                result.warnings.append(message)
        if isinstance(text, str) and text and text in owner_text:
            result.errors.append(f"{key}: literal catalog text remains in {owner}")

    return result


def validate_glossary(repo_root: Path, *, strict: bool = False) -> ValidationResult:
    repo_root = repo_root.resolve()
    result = ValidationResult()
    data = _load_metadata(repo_root / GLOSSARY_PATH, result)
    if not isinstance(data, dict):
        if data is not None:
            result.errors.append(f"{GLOSSARY_PATH}: root must be an object")
        return result
    if data.get("schema_version") != 1:
        result.errors.append(f"{GLOSSARY_PATH}: schema_version must be 1")

    terms = data.get("terms")
    if not isinstance(terms, dict):
        result.errors.append(f"{GLOSSARY_PATH}: terms must be an object")
        return result

    collected_aliases: dict[str, str] = {}
    for term, item in terms.items():
        _validate_glossary_entry(term, item, collected_aliases, result, strict)

    warnings = _scan_terminology(repo_root)
    result.errors.extend(warnings if strict else [])
    result.warnings.extend(warnings if not strict else [])
    return result


def _validate_glossary_entry(
    term: str,
    item: dict,
    aliases: dict[str, str],
    result: ValidationResult,
    strict: bool,
) -> None:
    if not isinstance(item, dict):
        result.errors.append(f"{term}: glossary entry must be an object")
        return

    _check_mandatory_text_field(term, item, "preferred", result)
    _check_definition(term, item, result)
    _check_alias_duplicates(term, item, aliases, result)


def _check_mandatory_text_field(
    term: str, item: dict, field: str, result: ValidationResult
) -> None:
    if not _is_non_empty_string(item.get(field)):
        result.errors.append(f"{term}: {field} must be a non-empty string")


def _check_definition(term: str, item: dict, result: ValidationResult) -> None:
    definition = item.get("definition")
    if not isinstance(definition, str) or not definition:
        result.errors.append(f"{term}: definition must be a non-empty string")
        return
    if not definition.endswith("."):
        result.errors.append(f"{term}: definition must end with a period")
    if len(definition) > 240:
        result.errors.append(f"{term}: definition must be 240 characters or fewer")


def _check_alias_duplicates(
    term: str, item: dict, aliases: dict[str, str], result: ValidationResult
) -> None:
    raw_aliases = item.get("aliases")
    if not isinstance(raw_aliases, list) or not all(_is_non_empty_string(a) for a in raw_aliases):
        result.errors.append(f"{term}: aliases must be a list of non-empty strings")
        return
    for alias in raw_aliases:
        lowered = str(alias).lower()
        if lowered in aliases:
            result.errors.append(f"{term}: duplicate glossary alias {alias!r} also used by {aliases[lowered]}")
        aliases[lowered] = str(term)


def _terminology_scan_files(repo_root: Path) -> list[Path]:
    files: list[Path] = []
    help_dir = repo_root / "docs" / "source" / "gui_help"
    if help_dir.is_dir():
        files.extend(sorted(help_dir.glob("*.md")))
    dev_docs = repo_root / "dev-docs"
    if dev_docs.is_dir():
        files.extend(path for path in sorted(dev_docs.glob("*.md")) if path.name != GLOSSARY_PATH.name)
    agents = repo_root / "AGENTS.md"
    if agents.is_file():
        files.append(agents)
    ui_copy = repo_root / UI_COPY_PATH
    if ui_copy.is_file():
        files.append(ui_copy)
    return files


def _scan_terminology(repo_root: Path) -> list[str]:
    warnings: list[str] = []
    for path in _terminology_scan_files(repo_root):
        rel = path.relative_to(repo_root)
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            for pattern, suggestion in TERMINOLOGY_RULES:
                if pattern.search(line):
                    warnings.append(f"{rel}:{line_number}: {suggestion}")
    return warnings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate UI copy and glossary metadata.")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=repo_root_from_script(),
        help="Repository root (default: parent of scripts/)",
    )
    parser.add_argument("--strict", action="store_true", help="Fail on advisory unused/terminology warnings.")
    args = parser.parse_args(argv)

    copy_result = validate_ui_copy(args.repo_root, strict=args.strict)
    glossary_result = validate_glossary(args.repo_root, strict=args.strict)
    errors = copy_result.errors + glossary_result.errors
    warnings = copy_result.warnings + glossary_result.warnings
    for warning in warnings:
        print(f"warning: {warning}", file=sys.stderr)
    if errors:
        print("UI copy/glossary errors:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("UI copy and glossary OK.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
