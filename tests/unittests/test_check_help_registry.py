"""Unit tests for scripts/check_help_registry.py."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.check_help_registry import validate_help_registry


def _write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _base_registry() -> dict[str, object]:
    return {
        "schema_version": 1,
        "source_dir": "docs/source/gui_help",
        "target_dir": "src/guiskindose/gui/help",
        "entries": [
            {
                "id": "upload",
                "title": "Upload help",
                "source": "upload_workflow.md",
                "gui_files": ["src/guiskindose/gui/tabs/upload.py"],
                "required": True,
            }
        ],
    }


def _write_valid_repo(tmp_path: Path) -> None:
    _write_json(tmp_path / "dev-docs" / "help_registry.json", _base_registry())
    source = tmp_path / "docs" / "source" / "gui_help" / "upload_workflow.md"
    target = tmp_path / "src" / "guiskindose" / "gui" / "help" / "upload_workflow.md"
    gui = tmp_path / "src" / "guiskindose" / "gui" / "tabs" / "upload.py"
    source.parent.mkdir(parents=True, exist_ok=True)
    target.parent.mkdir(parents=True, exist_ok=True)
    gui.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("# Upload\n", encoding="utf-8")
    target.write_text("# Upload\n", encoding="utf-8")
    gui.write_text(
        'HelpButton(title="Upload help", content_path="upload_workflow.md", help_id="upload")\n',
        encoding="utf-8",
    )


def test_validate_help_registry_accepts_valid_registry(tmp_path: Path) -> None:
    _write_valid_repo(tmp_path)

    result = validate_help_registry(tmp_path)

    assert result.errors == []
    assert result.warnings == []


def test_validate_help_registry_reports_missing_source(tmp_path: Path) -> None:
    _write_valid_repo(tmp_path)
    (tmp_path / "docs" / "source" / "gui_help" / "upload_workflow.md").unlink()

    result = validate_help_registry(tmp_path)

    assert any("missing source help file" in error for error in result.errors)


def test_validate_help_registry_reports_missing_mirror(tmp_path: Path) -> None:
    _write_valid_repo(tmp_path)
    (tmp_path / "src" / "guiskindose" / "gui" / "help" / "upload_workflow.md").unlink()

    result = validate_help_registry(tmp_path)

    assert any("run scripts/sync_gui_help.py" in error for error in result.errors)


def test_validate_help_registry_reports_duplicate_id(tmp_path: Path) -> None:
    registry = _base_registry()
    entries = registry["entries"]
    assert isinstance(entries, list)
    entries.append(dict(entries[0]))
    _write_valid_repo(tmp_path)
    _write_json(tmp_path / "dev-docs" / "help_registry.json", registry)

    result = validate_help_registry(tmp_path)

    assert any("duplicate help id" in error for error in result.errors)


def test_validate_help_registry_reports_missing_gui_file(tmp_path: Path) -> None:
    _write_valid_repo(tmp_path)
    (tmp_path / "src" / "guiskindose" / "gui" / "tabs" / "upload.py").unlink()

    result = validate_help_registry(tmp_path)

    assert any("missing GUI file" in error for error in result.errors)


def test_validate_help_registry_reports_mismatched_gui_reference(tmp_path: Path) -> None:
    _write_valid_repo(tmp_path)
    (tmp_path / "src" / "guiskindose" / "gui" / "tabs" / "upload.py").write_text(
        'HelpButton(title="Upload help", content_path="wrong.md", help_id="wrong")\n',
        encoding="utf-8",
    )

    result = validate_help_registry(tmp_path)

    assert any("do not reference content_path" in error for error in result.errors)
    assert any("do not reference help_id" in warning for warning in result.warnings)


def test_validate_help_registry_warns_for_orphaned_help_file(tmp_path: Path) -> None:
    _write_valid_repo(tmp_path)
    orphan = tmp_path / "docs" / "source" / "gui_help" / "orphan.md"
    orphan.write_text("# Orphan\n", encoding="utf-8")

    result = validate_help_registry(tmp_path)

    assert any("orphaned source help file" in warning for warning in result.warnings)


def test_validate_help_registry_strict_fails_for_orphaned_help_file(tmp_path: Path) -> None:
    _write_valid_repo(tmp_path)
    orphan = tmp_path / "docs" / "source" / "gui_help" / "orphan.md"
    orphan.write_text("# Orphan\n", encoding="utf-8")

    result = validate_help_registry(tmp_path, strict=True)

    assert any("orphaned source help file" in error for error in result.errors)
