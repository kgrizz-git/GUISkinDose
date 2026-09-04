"""Unit tests for scripts/check_ui_copy.py."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.check_ui_copy import validate_glossary, validate_ui_copy


def _write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _write_catalog(repo_root: Path, data: object | None = None) -> None:
    catalog = data or {
        "schema_version": 1,
        "keys": {
            "sample.tooltip": {
                "text": "Sample tooltip",
                "owner": "gui/tabs/sample.py",
            }
        },
    }
    _write_json(repo_root / "dev-docs" / "ui_copy.json", catalog)


def _write_glossary(repo_root: Path, data: object | None = None) -> None:
    glossary = data or {
        "schema_version": 1,
        "terms": {
            "PSD": {
                "preferred": "peak skin dose",
                "definition": "Maximum accumulated dose on any modeled skin cell.",
                "aliases": ["peak skin dose"],
            }
        },
    }
    _write_json(repo_root / "dev-docs" / "glossary.json", glossary)


def _write_owner(repo_root: Path, text: str = 'copy_text("sample.tooltip")\n') -> None:
    path = repo_root / "src" / "guiskindose" / "gui" / "tabs" / "sample.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_validate_ui_copy_accepts_valid_catalog(tmp_path: Path) -> None:
    _write_catalog(tmp_path)
    _write_owner(tmp_path)

    result = validate_ui_copy(tmp_path)

    assert result.errors == []
    assert result.warnings == []


def test_validate_ui_copy_rejects_empty_text(tmp_path: Path) -> None:
    _write_catalog(
        tmp_path,
        {
            "schema_version": 1,
            "keys": {"sample.tooltip": {"text": "", "owner": "gui/tabs/sample.py"}},
        },
    )
    _write_owner(tmp_path)

    result = validate_ui_copy(tmp_path)

    assert any("text must be a non-empty string" in error for error in result.errors)


def test_validate_ui_copy_rejects_missing_owner(tmp_path: Path) -> None:
    _write_catalog(tmp_path)

    result = validate_ui_copy(tmp_path)

    assert any("owner file does not exist" in error for error in result.errors)


def test_validate_ui_copy_reports_missing_key_used_in_code(tmp_path: Path) -> None:
    _write_catalog(tmp_path)
    _write_owner(tmp_path, 'copy_text("missing.tooltip")\n')

    result = validate_ui_copy(tmp_path)

    assert any("copy_text key is not in catalog" in error for error in result.errors)


def test_validate_ui_copy_warns_and_strict_fails_for_unused_key(tmp_path: Path) -> None:
    _write_catalog(tmp_path)
    _write_owner(tmp_path, "print('no catalog use')\n")

    default_result = validate_ui_copy(tmp_path)
    strict_result = validate_ui_copy(tmp_path, strict=True)

    assert any("unused UI copy key" in warning for warning in default_result.warnings)
    assert any("unused UI copy key" in error for error in strict_result.errors)


def test_validate_ui_copy_reports_literal_catalog_text_left_in_owner(tmp_path: Path) -> None:
    _write_catalog(tmp_path)
    _write_owner(tmp_path, '"Sample tooltip"\ncopy_text("sample.tooltip")\n')

    result = validate_ui_copy(tmp_path)

    assert any("literal catalog text remains" in error for error in result.errors)


def test_validate_glossary_rejects_duplicate_aliases(tmp_path: Path) -> None:
    _write_glossary(
        tmp_path,
        {
            "schema_version": 1,
            "terms": {
                "A": {"preferred": "alpha", "definition": "Alpha term.", "aliases": ["same"]},
                "B": {"preferred": "beta", "definition": "Beta term.", "aliases": ["same"]},
            },
        },
    )

    result = validate_glossary(tmp_path)

    assert any("duplicate glossary alias" in error for error in result.errors)


def test_validate_glossary_warns_for_banned_terms(tmp_path: Path) -> None:
    _write_glossary(tmp_path)
    help_dir = tmp_path / "docs" / "source" / "gui_help"
    help_dir.mkdir(parents=True)
    (help_dir / "topic.md").write_text("This mentions maximum skin dose.\n", encoding="utf-8")

    result = validate_glossary(tmp_path)

    assert any("use 'peak skin dose'" in warning for warning in result.warnings)
