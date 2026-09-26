"""Unit tests for scripts/sync_ui_copy.py."""

from __future__ import annotations

from pathlib import Path

import pytest

import scripts.sync_ui_copy as sync_ui_copy
from scripts.sync_ui_copy import main, sync


def _write_catalog(path: Path, text: str = '{"keys": {}}') -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def test_sync_mirrors_missing_target(tmp_path: Path) -> None:
    source = _write_catalog(tmp_path / "ui_copy.json")
    target = tmp_path / "bundled" / "ui_copy.json"

    assert sync(source, target, check=False) == 0
    assert target.read_text(encoding="utf-8") == '{"keys": {}}'


def test_sync_overwrites_drifted_target(tmp_path: Path) -> None:
    source = _write_catalog(tmp_path / "canonical.json", '{"keys": {"a": 1}}')
    target = tmp_path / "bundled.json"
    target.write_text('{"keys": {}}', encoding="utf-8")

    assert sync(source, target, check=False) == 0
    assert target.read_text(encoding="utf-8") == '{"keys": {"a": 1}}'


def test_sync_leaves_matching_target_alone(tmp_path: Path) -> None:
    source = _write_catalog(tmp_path / "a.json")
    target = tmp_path / "b.json"
    target.write_bytes(source.read_bytes())
    mtime_before = target.stat().st_mtime_ns

    assert sync(source, target, check=False) == 0
    assert target.stat().st_mtime_ns == mtime_before


def test_sync_check_passes_when_in_sync(tmp_path: Path) -> None:
    source = _write_catalog(tmp_path / "a.json")
    target = tmp_path / "b.json"
    target.write_bytes(source.read_bytes())

    assert sync(source, target, check=True) == 0


def test_sync_check_reports_drift(tmp_path: Path, capsys) -> None:
    source = _write_catalog(tmp_path / "a.json", '{"keys": {"a": 1}}')
    target = tmp_path / "b.json"
    target.write_text('{"keys": {}}', encoding="utf-8")

    assert sync(source, target, check=True) == 1
    assert "out of sync" in capsys.readouterr().err
    assert target.read_text(encoding="utf-8") == '{"keys": {}}'


def test_sync_check_reports_missing_target(tmp_path: Path, capsys) -> None:
    source = _write_catalog(tmp_path / "a.json")

    assert sync(source, tmp_path / "missing.json", check=True) == 1
    assert "does not exist" in capsys.readouterr().err


def test_sync_reports_missing_source(tmp_path: Path, capsys) -> None:
    assert sync(tmp_path / "missing.json", tmp_path / "out.json", check=False) == 1
    assert "does not exist" in capsys.readouterr().err


def test_main_check_against_repo_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sync_ui_copy, "repo_root_from_script", lambda: tmp_path)
    source_dir = tmp_path / "dev-docs"
    source_dir.mkdir()
    (source_dir / "ui_copy.json").write_text('{"keys": {}}', encoding="utf-8")

    assert main(["--check"]) == 1
    assert main([]) == 0
    target = tmp_path / "src" / "guiskindose" / "gui" / "ui_copy.json"
    assert target.read_text(encoding="utf-8") == '{"keys": {}}'
    assert main(["--check"]) == 0


def test_main_refuses_repo_root_override() -> None:
    """The root is fixed to the checkout, so a CLI root override is rejected."""
    with pytest.raises(SystemExit) as excinfo:
        main(["--repo-root", "elsewhere"])
    assert excinfo.value.code == 2
