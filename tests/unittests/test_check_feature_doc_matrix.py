"""Unit tests for scripts/check_feature_doc_matrix.py."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.check_feature_doc_matrix import evaluate_doc_impact, validate_feature_doc_matrix


def _write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _matrix() -> dict[str, object]:
    return {
        "schema_version": 1,
        "features": {
            "tabular_input": {
                "status": "shipped",
                "code": ["src/guiskindose/gui/tabs/upload.py"],
                "tests": ["tests/unittests/test_input_adapters.py"],
                "docs": ["dev-docs/INPUT_SCHEMA_DETECTION.md"],
                "help": ["docs/source/gui_help/upload_workflow.md"],
            }
        },
    }


def _write_valid_repo(tmp_path: Path) -> None:
    _write_json(tmp_path / "dev-docs" / "feature_doc_matrix.json", _matrix())
    for rel in [
        "src/guiskindose/gui/tabs/upload.py",
        "tests/unittests/test_input_adapters.py",
        "dev-docs/INPUT_SCHEMA_DETECTION.md",
        "docs/source/gui_help/upload_workflow.md",
    ]:
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x\n", encoding="utf-8")


def test_validate_feature_doc_matrix_accepts_valid_metadata(tmp_path: Path) -> None:
    _write_valid_repo(tmp_path)

    result = validate_feature_doc_matrix(tmp_path)

    assert result.errors == []


def test_validate_feature_doc_matrix_reports_missing_path(tmp_path: Path) -> None:
    _write_valid_repo(tmp_path)
    (tmp_path / "dev-docs" / "INPUT_SCHEMA_DETECTION.md").unlink()

    result = validate_feature_doc_matrix(tmp_path)

    assert any("missing docs path" in error for error in result.errors)


def test_validate_feature_doc_matrix_rejects_unknown_status(tmp_path: Path) -> None:
    repo = _matrix()
    features = repo["features"]
    assert isinstance(features, dict)
    feature = features["tabular_input"]
    assert isinstance(feature, dict)
    feature["status"] = "unknown"
    _write_valid_repo(tmp_path)
    _write_json(tmp_path / "dev-docs" / "feature_doc_matrix.json", repo)

    result = validate_feature_doc_matrix(tmp_path)

    assert any("unknown status" in error for error in result.errors)


def test_evaluate_doc_impact_warns_for_changed_code_without_docs(tmp_path: Path) -> None:
    _write_valid_repo(tmp_path)

    result = evaluate_doc_impact(
        tmp_path,
        changed_paths=["src/guiskindose/gui/tabs/upload.py", "tests/unittests/test_input_adapters.py"],
    )

    assert any("tabular_input" in warning for warning in result.warnings)
    assert result.errors == []


def test_evaluate_doc_impact_strict_fails_without_doc_or_help_change(tmp_path: Path) -> None:
    _write_valid_repo(tmp_path)

    result = evaluate_doc_impact(
        tmp_path,
        changed_paths=["src/guiskindose/gui/tabs/upload.py"],
        strict_impact=True,
    )

    assert any("requires linked doc/help review" in error for error in result.errors)


def test_evaluate_doc_impact_strict_passes_with_doc_change(tmp_path: Path) -> None:
    _write_valid_repo(tmp_path)

    result = evaluate_doc_impact(
        tmp_path,
        changed_paths=["src/guiskindose/gui/tabs/upload.py", "dev-docs/INPUT_SCHEMA_DETECTION.md"],
        strict_impact=True,
    )

    assert result.errors == []
