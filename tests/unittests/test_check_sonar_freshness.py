"""Tests for the opt-in SonarQube freshness gate."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

import scripts.check_sonar_freshness as gate


def _git(args: list[str], path: Path, capture: bool = False) -> str:
    cmd = [
        "git",
        "-c",
        "core.hooksPath=/dev/null",
        "-c",
        "commit.gpgsign=false",
        "-c",
        "user.email=test@example.com",
        "-c",
        "user.name=Test",
        *args,
    ]
    env = os.environ.copy()
    for key in gate.GIT_DIR_OVERRIDE_VARS:
        env.pop(key, None)
    if capture:
        return subprocess.check_output(cmd, cwd=path, text=True, env=env).strip()
    subprocess.check_call(cmd, cwd=path, env=env)
    return ""


@pytest.fixture
def fixture_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    _git(["init", "-q"], root)
    (root / "seed.txt").write_text("seed\n", encoding="utf-8")
    _git(["add", "seed.txt"], root)
    _git(["commit", "-q", "-m", "seed"], root)
    monkeypatch.setattr(gate, "repo_root", lambda: root)
    monkeypatch.delenv("SONAR_FRESHNESS_GATE", raising=False)
    monkeypatch.delenv("SONAR_GATE_MAX_COMMITS", raising=False)
    return root


def _commit(path: Path, name: str) -> str:
    file_path = path / f"{name}.txt"
    file_path.write_text(f"{name}\n", encoding="utf-8")
    _git(["add", file_path.name], path)
    _git(["commit", "-q", "-m", f"add {name}"], path)
    return _git(["rev-parse", "HEAD"], path, capture=True)


def _write_state(state_path: Path, commit: str, issues_count: int = 3) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps(
            {
                "last_scan_commit": commit,
                "last_scan_time": "2026-09-25T12:00:00Z",
                "issues_count": issues_count,
                "issues_path": "tmp/sonar-issues/2026-09-25T120000Z.json",
                "issues_summary_path": "tmp/sonar-latest-issues.md",
            }
        )
        + "\n",
        encoding="utf-8",
    )


def test_gate_off_without_env_exits_zero(fixture_repo: Path) -> None:
    state_path = fixture_repo / "tmp" / "sonar-state.json"
    _write_state(state_path, _git(["rev-parse", "HEAD"], fixture_repo, capture=True))
    assert gate.main(["--state", str(state_path)]) == 0


@pytest.mark.parametrize("off_value", ["0", "false", "no", ""])
def test_gate_off_values_exit_zero(fixture_repo: Path, monkeypatch: pytest.MonkeyPatch, off_value: str) -> None:
    state_path = fixture_repo / "tmp" / "sonar-state.json"
    _write_state(state_path, _git(["rev-parse", "HEAD"], fixture_repo, capture=True))
    monkeypatch.setenv("SONAR_FRESHNESS_GATE", off_value)
    assert gate.main(["--state", str(state_path)]) == 0


def test_missing_state_blocks(fixture_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SONAR_FRESHNESS_GATE", "1")
    assert gate.main(["--state", str(fixture_repo / "tmp" / "sonar-state.json")]) == 1


def test_invalid_state_blocks(fixture_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    state_path = fixture_repo / "tmp" / "sonar-state.json"
    state_path.parent.mkdir(parents=True)
    state_path.write_text("{not json\n", encoding="utf-8")
    monkeypatch.setenv("SONAR_FRESHNESS_GATE", "1")
    assert gate.main(["--state", str(state_path)]) == 1


def test_dangling_scan_commit_blocks(fixture_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    state_path = fixture_repo / "tmp" / "sonar-state.json"
    _write_state(state_path, "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef")
    monkeypatch.setenv("SONAR_FRESHNESS_GATE", "1")
    assert gate.main(["--state", str(state_path)]) == 1


def test_commit_stage_within_budget_allows(fixture_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    scan_sha = _commit(fixture_repo, "a")
    state_path = fixture_repo / "tmp" / "sonar-state.json"
    _write_state(state_path, scan_sha)
    monkeypatch.setenv("SONAR_FRESHNESS_GATE", "1")
    assert gate.main(["--state", str(state_path)]) == 0


def test_commit_stage_at_budget_blocks(fixture_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    scan_sha = _commit(fixture_repo, "a")
    for i in range(9):  # 9 since scan -> pending 10 (>= default budget)
        _commit(fixture_repo, f"b{i}")
    state_path = fixture_repo / "tmp" / "sonar-state.json"
    _write_state(state_path, scan_sha)
    monkeypatch.setenv("SONAR_FRESHNESS_GATE", "1")
    assert gate.main(["--state", str(state_path)]) == 1


def test_push_stage_allows_at_scan_commit(fixture_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    scan_sha = _commit(fixture_repo, "a")
    state_path = fixture_repo / "tmp" / "sonar-state.json"
    _write_state(state_path, scan_sha)
    monkeypatch.setenv("SONAR_FRESHNESS_GATE", "1")
    assert gate.main(["--state", str(state_path), "--stage", "push"]) == 0


def test_push_stage_blocks_on_any_commit(fixture_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    scan_sha = _commit(fixture_repo, "a")
    _commit(fixture_repo, "b")
    state_path = fixture_repo / "tmp" / "sonar-state.json"
    _write_state(state_path, scan_sha)
    monkeypatch.setenv("SONAR_FRESHNESS_GATE", "1")
    assert gate.main(["--state", str(state_path), "--stage", "push"]) == 1


def test_dotenv_enables_gate(fixture_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    scan_sha = _commit(fixture_repo, "a")
    for i in range(9):
        _commit(fixture_repo, f"b{i}")
    state_path = fixture_repo / "tmp" / "sonar-state.json"
    _write_state(state_path, scan_sha)
    (fixture_repo / ".env").write_text("SONAR_FRESHNESS_GATE=1\n", encoding="utf-8")
    monkeypatch.delenv("SONAR_FRESHNESS_GATE", raising=False)
    assert gate.main(["--state", str(state_path)]) == 1


def test_exported_env_wins_over_dotenv(fixture_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    scan_sha = _commit(fixture_repo, "a")
    for i in range(9):
        _commit(fixture_repo, f"b{i}")
    state_path = fixture_repo / "tmp" / "sonar-state.json"
    _write_state(state_path, scan_sha)
    (fixture_repo / ".env").write_text("SONAR_FRESHNESS_GATE=1\n", encoding="utf-8")
    monkeypatch.setenv("SONAR_FRESHNESS_GATE", "0")
    assert gate.main(["--state", str(state_path)]) == 0
