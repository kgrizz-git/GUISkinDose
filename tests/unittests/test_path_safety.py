"""Unit tests for scripts/phantom_gen/path_safety.py (Sonar S8707 path rebuild)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# The repository root must be importable before loading this non-installed script module.
from scripts.phantom_gen.path_safety import (
    resolve_under_roots,
    trusted_path_under_roots,
    write_text_under_roots,
)


def test_resolve_under_roots_rejects_escape(tmp_path: Path) -> None:
    """Paths outside the allowlisted roots must raise ValueError."""
    outside = tmp_path / "escape.txt"
    outside.write_text("nope", encoding="utf-8")
    with pytest.raises(ValueError, match="escaped"):
        resolve_under_roots(outside, roots=(ROOT,))


def test_trusted_path_under_roots_rebuilds_from_root(tmp_path: Path) -> None:
    """Trusted rebuild returns a path under the matched root with the same parts."""
    report = tmp_path / "out" / "report.json"
    report.parent.mkdir(parents=True)
    trusted = trusted_path_under_roots(report, roots=(tmp_path,))
    assert trusted == (tmp_path / "out" / "report.json").resolve()
    assert trusted.is_relative_to(tmp_path.resolve())
    # Identity with resolve_under_roots for on-root paths, but rebuilt via joinpath.
    resolved = resolve_under_roots(report, roots=(tmp_path,))
    assert trusted == resolved


def test_trusted_path_under_roots_rejects_escape(tmp_path: Path) -> None:
    """Escape attempts fail before any write path is returned."""
    outside = tmp_path / "escape.json"
    outside.write_text("{}", encoding="utf-8")
    other_root = tmp_path / "allowed"
    other_root.mkdir()
    with pytest.raises(ValueError, match="escaped"):
        trusted_path_under_roots(outside, roots=(other_root,))


def test_trusted_path_under_roots_repo_relative() -> None:
    """Relative paths under the repo root rebuild safely for report writes."""
    rel = Path("tmp") / "catalog_report.json"
    trusted = trusted_path_under_roots(rel, roots=(ROOT,))
    assert trusted == (ROOT / "tmp" / "catalog_report.json").resolve()
    assert trusted.parts[-2:] == ("tmp", "catalog_report.json")


def test_write_text_under_roots_writes_payload(tmp_path: Path) -> None:
    """write_text_under_roots confines the path then writes via open().write."""
    target = tmp_path / "reports" / "out.json"
    written = write_text_under_roots(target, '{"ok": true}', roots=(tmp_path,))
    assert written == (tmp_path / "reports" / "out.json").resolve()
    assert written.read_text(encoding="utf-8") == '{"ok": true}'


def test_write_text_under_roots_rejects_escape(tmp_path: Path) -> None:
    """Escape attempts fail before any file is created."""
    outside = tmp_path / "escape.json"
    other_root = tmp_path / "allowed"
    other_root.mkdir()
    with pytest.raises(ValueError, match="escaped"):
        write_text_under_roots(outside, "{}", roots=(other_root,))
    assert not outside.exists()
