"""Regression cases for complexity-gate measurement and historical metadata."""

import json
import subprocess
from pathlib import Path

import pytest

from scripts.check_complexity import canonical_document, canonicalize, check, collect_findings, ruff_version
from scripts.complexity_caps_helpers import check_cap_history


@pytest.fixture(autouse=True)
def _clear_ci_base_context(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep synthetic Git history independent of the runner's event."""
    monkeypatch.delenv("GITHUB_BASE_REF", raising=False)
    monkeypatch.delenv("COMPLEXITY_BEFORE_SHA", raising=False)


def test_ruff_suppressions_cannot_hide_complex_functions(tmp_path: Path) -> None:
    """Project per-file ignores and inline noqa must not shrink the measurement."""
    source = "def inline_noqa():  # noqa: C901\n    a = 1\n"
    source += "    if a: a += 1\n" * 11 + "    return a\n"
    source += "\ndef file_ignored():\n    a = 1\n"
    source += "    if a: a += 1\n" * 11 + "    return a\n"
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "probe.py").write_text(source, encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text(
        '[tool.ruff.lint.per-file-ignores]\n"src/probe.py" = ["C901"]\n', encoding="utf-8"
    )
    findings = collect_findings(tmp_path)
    assert {finding.function for finding in findings} == {"inline_noqa", "file_ignored"}
    caps_path = tmp_path / "dev-docs" / "complexity_caps.json"
    caps_path.parent.mkdir()
    caps_path.write_bytes(canonicalize(canonical_document(ruff_version(tmp_path), [])))
    assert sum("unlisted over-limit function" in error for error in check(tmp_path)) == 2


def test_history_accepts_new_ruff_version_with_unchanged_caps(tmp_path: Path) -> None:
    """Historical metadata belongs to its own Ruff version, not the new one."""
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "init"],
        cwd=tmp_path, check=True,
    )
    caps_path = tmp_path / "dev-docs" / "complexity_caps.json"
    caps_path.parent.mkdir()
    old = canonical_document("0.16.2", [])
    caps_path.write_bytes(canonicalize(old))
    subprocess.run(["git", "add", "dev-docs/complexity_caps.json"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "caps"],
        cwd=tmp_path, check=True,
    )
    subprocess.run(["git", "update-ref", "refs/remotes/origin/main", "HEAD"], cwd=tmp_path, check=True)
    updated = json.loads(json.dumps(old))
    updated["tool_version"] = "0.16.3"
    assert check_cap_history(tmp_path, updated, canonicalize(updated)) == []
