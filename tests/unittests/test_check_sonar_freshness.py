"""Tests for the opt-in SonarQube freshness gate."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

import scripts.check_sonar_freshness as gate


def _git(args: list[str], path: Path, capture: bool = False) -> str:
    # Point hooks at a guaranteed-empty dir (portable, unlike /dev/null): fresh
    # tmp repos carry only sample hooks, but a global core.hooksPath could
    # otherwise inject a developer machine's hooks into fixture commits.
    hooks_dir = path / "empty-hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        "git",
        "-c",
        f"core.hooksPath={hooks_dir}",
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


def _write_state(state_path: Path, commit: str, issues_count: int | None = 3) -> None:
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


def test_non_utf8_state_blocks_with_hint(
    fixture_repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    state_path = fixture_repo / "tmp" / "sonar-state.json"
    state_path.parent.mkdir(parents=True)
    state_path.write_bytes(b"\xff\xfe{\x00not-utf8")
    monkeypatch.setenv("SONAR_FRESHNESS_GATE", "1")
    assert gate.main(["--state", str(state_path)]) == 1
    assert "Re-run the scan to regenerate it" in capsys.readouterr().err


def test_dangling_scan_commit_blocks(fixture_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    state_path = fixture_repo / "tmp" / "sonar-state.json"
    _write_state(state_path, "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef")
    monkeypatch.setenv("SONAR_FRESHNESS_GATE", "1")
    assert gate.main(["--state", str(state_path)]) == 1


@pytest.mark.parametrize("bad_commit", ["--help", "HEAD", "deadbeef"])
def test_non_sha_scan_commit_blocks_before_git(
    fixture_repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], bad_commit: str
) -> None:
    state_path = fixture_repo / "tmp" / "sonar-state.json"
    _write_state(state_path, bad_commit)
    monkeypatch.setenv("SONAR_FRESHNESS_GATE", "1")
    assert gate.main(["--state", str(state_path)]) == 1
    assert "no valid last_scan_commit" in capsys.readouterr().err


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


def test_commit_stage_warns_but_allows_near_budget(
    fixture_repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    scan_sha = _commit(fixture_repo, "a")
    for i in range(7):  # 7 since scan -> pending 8 (>= 80% warn threshold, < 10 budget)
        _commit(fixture_repo, f"b{i}")
    state_path = fixture_repo / "tmp" / "sonar-state.json"
    _write_state(state_path, scan_sha)
    monkeypatch.setenv("SONAR_FRESHNESS_GATE", "1")
    assert gate.main(["--state", str(state_path)]) == 0
    assert "WARNING" in capsys.readouterr().err


def test_missing_last_scan_commit_blocks(fixture_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    state_path = fixture_repo / "tmp" / "sonar-state.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps({"last_scan_time": "2026-09-25T12:00:00Z", "issues_count": 3}), encoding="utf-8"
    )
    monkeypatch.setenv("SONAR_FRESHNESS_GATE", "1")
    assert gate.main(["--state", str(state_path)]) == 1


def test_block_message_renders_unknown_issue_count(
    fixture_repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    scan_sha = _commit(fixture_repo, "a")
    for i in range(9):
        _commit(fixture_repo, f"b{i}")
    state_path = fixture_repo / "tmp" / "sonar-state.json"
    _write_state(state_path, scan_sha, issues_count=None)
    monkeypatch.setenv("SONAR_FRESHNESS_GATE", "1")
    assert gate.main(["--state", str(state_path)]) == 1
    assert "Issues on record: unknown" in capsys.readouterr().err


@pytest.mark.parametrize(("raw", "expected"), [("abc", 10), ("0", 10), ("-3", 10), ("", 10), ("7", 7)])
def test_resolve_max_commits_fallbacks(monkeypatch: pytest.MonkeyPatch, raw: str, expected: int) -> None:
    if raw == "":
        monkeypatch.delenv("SONAR_GATE_MAX_COMMITS", raising=False)
    else:
        monkeypatch.setenv("SONAR_GATE_MAX_COMMITS", raw)
    assert gate.resolve_max_commits() == expected


@pytest.mark.parametrize("quoted", ['"1"', "'1'", '"1" # enabled', "1 # enabled"])
def test_dotenv_tolerates_quotes_and_comments(
    fixture_repo: Path, monkeypatch: pytest.MonkeyPatch, quoted: str
) -> None:
    scan_sha = _commit(fixture_repo, "a")
    for i in range(9):
        _commit(fixture_repo, f"b{i}")
    state_path = fixture_repo / "tmp" / "sonar-state.json"
    _write_state(state_path, scan_sha)
    (fixture_repo / ".env").write_text(f"SONAR_FRESHNESS_GATE={quoted}\n", encoding="utf-8")
    monkeypatch.delenv("SONAR_FRESHNESS_GATE", raising=False)
    assert gate.main(["--state", str(state_path)]) == 1


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("1", "1"), ('"1"', "1"), ("'1'", "1"), ('"1" # on', "1"), ("  1  ", "1"), ("squ_abc", "squ_abc")],
)
def test_clean_env_value(raw: str, expected: str) -> None:
    assert gate.clean_env_value(raw) == expected


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


def test_non_utf8_dotenv_is_ignored_not_fatal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # load_env_file runs before the opt-in check; a crash here would block every commit.
    monkeypatch.delenv("SONAR_FRESHNESS_GATE", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_bytes(b"SONAR_FRESHNESS_GATE=\xff\xfe\n")
    gate.load_env_file(env_file)
    assert "SONAR_FRESHNESS_GATE" not in os.environ


def test_state_outside_repo_is_refused(
    fixture_repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    outside = tmp_path / "outside" / "sonar-state.json"
    _write_state(outside, _git(["rev-parse", "HEAD"], fixture_repo, capture=True))
    monkeypatch.setenv("SONAR_FRESHNESS_GATE", "1")
    assert gate.main(["--state", str(outside)]) == 1
    assert "inside the repository" in capsys.readouterr().err


def test_state_traversal_is_refused(fixture_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SONAR_FRESHNESS_GATE", "1")
    assert gate.main(["--state", "../sonar-state.json"]) == 1


def test_contained_path_resolves_relative_under_root(fixture_repo: Path) -> None:
    resolved = gate.contained_path("tmp/sonar-state.json", fixture_repo)
    assert resolved == Path(os.path.realpath(fixture_repo)) / "tmp" / "sonar-state.json"
    with pytest.raises(ValueError, match="outside the repository root"):
        gate.contained_path(str(fixture_repo), fixture_repo)
