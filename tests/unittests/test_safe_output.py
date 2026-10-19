"""Tests for atomic, private, Git-aware export writes."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from unittest import mock

import pytest

from guiskindose.safe_output import _GIT_LOCATION_ENV, UnsafeOutputPathError, atomic_write_private


def _git(args: list[str]) -> None:
    """Run git for a temporary repository without this process's checkout variables."""
    env = os.environ.copy()
    for name in _GIT_LOCATION_ENV:
        env.pop(name, None)
    subprocess.run(args, check=True, env=env)


def _record_git_env(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, str]]:
    """Capture the environment of later git spawns, then run the real command."""
    real_run = subprocess.run
    seen: list[dict[str, str]] = []

    def spy(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        command = args[0] if args else None
        env = kwargs.get("env")
        if isinstance(command, list) and command and command[0] == "git" and isinstance(env, dict):
            seen.append({str(key): str(value) for key, value in env.items()})
        return real_run(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(subprocess, "run", spy)
    return seen


def test_atomic_write_is_private_and_requires_force_to_overwrite(tmp_path: Path) -> None:
    target = tmp_path / "report.bin"
    atomic_write_private(target, b"first")
    assert target.read_bytes() == b"first"
    if os.name == "posix":
        assert target.stat().st_mode & 0o777 == 0o600

    with pytest.raises(UnsafeOutputPathError, match="export_destination_exists"):
        atomic_write_private(target, b"second")
    atomic_write_private(target, b"second", force=True)
    assert target.read_bytes() == b"second"


def test_checkout_writes_require_an_explicit_ignored_root(tmp_path: Path) -> None:
    _git(["git", "init", "-q", str(tmp_path)])
    (tmp_path / ".gitignore").write_text("private-output/\n", encoding="utf-8")
    ignored = tmp_path / "private-output"
    ignored.mkdir()
    target = ignored / "report.json"

    with pytest.raises(UnsafeOutputPathError, match="export_checkout_path_forbidden"):
        atomic_write_private(target, b"{}")
    atomic_write_private(target, b"{}", allow_ignored_checkout=True)
    assert target.read_bytes() == b"{}"


def test_tracked_checkout_path_is_forbidden(tmp_path: Path) -> None:
    """A path still in the index is rejected after the working tree file is removed."""
    _git(["git", "init", "-q", str(tmp_path)])
    tracked = tmp_path / "report.json"
    tracked.write_text("seed", encoding="utf-8")
    _git(["git", "-C", str(tmp_path), "add", "--", "report.json"])
    tracked.unlink()

    with pytest.raises(UnsafeOutputPathError, match="export_tracked_path_forbidden"):
        atomic_write_private(tracked, b"{}")
    assert not tracked.exists()


def test_non_ignored_checkout_path_is_forbidden(tmp_path: Path) -> None:
    """A new file inside a checkout is rejected when it is not gitignored."""
    _git(["git", "init", "-q", str(tmp_path)])
    target = tmp_path / "report.json"

    with pytest.raises(UnsafeOutputPathError, match="export_checkout_path_forbidden"):
        atomic_write_private(target, b"{}")
    assert not target.exists()


def test_checkout_guard_ignores_inherited_git_location(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Validation uses the destination checkout, not GIT_DIR from the parent process."""
    _git(["git", "init", "-q", str(tmp_path)])
    repo_root = Path(__file__).resolve().parents[2]
    monkeypatch.setenv("GIT_DIR", str(repo_root / ".git"))
    monkeypatch.setenv("GIT_WORK_TREE", str(repo_root))
    monkeypatch.setenv("GIT_INDEX_FILE", str(tmp_path / "not-the-index"))
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    seen = _record_git_env(monkeypatch)
    target = tmp_path / "report.json"

    with pytest.raises(UnsafeOutputPathError, match="export_checkout_path_forbidden"):
        atomic_write_private(target, b"{}")
    assert not target.exists()
    assert seen
    for env in seen:
        assert set(env).isdisjoint(_GIT_LOCATION_ENV)


def test_checkout_guard_finds_repo_below_an_inherited_ceiling(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A ceiling on a parent directory must not hide the destination checkout."""
    _git(["git", "init", "-q", str(tmp_path)])
    nested = tmp_path / "nested"
    nested.mkdir()
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    target = nested / "report.json"

    with pytest.raises(UnsafeOutputPathError, match="export_checkout_path_forbidden"):
        atomic_write_private(target, b"{}")
    assert not target.exists()


def test_rejection_message_never_echoes_sensitive_destination(tmp_path: Path) -> None:
    sentinel = "PATIENT-SENTINEL-12345.json"
    target = tmp_path / sentinel
    target.write_bytes(b"existing")
    with pytest.raises(UnsafeOutputPathError) as caught:
        atomic_write_private(target, b"replacement")
    assert sentinel not in str(caught.value)


def _git_argv(args: tuple[object, ...]) -> list[str] | None:
    command = args[0] if args else None
    if not isinstance(command, list) or not command or command[0] != "git":
        return None
    return [part for part in command if isinstance(part, str)]


def test_checkout_guard_allows_write_when_git_disappears_after_root(tmp_path: Path) -> None:
    """A spawn failure after the root is known fails open instead of blocking the export."""
    target = tmp_path / "report.json"
    root = str(tmp_path.resolve())

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        del kwargs
        argv = _git_argv(args)
        if argv is None:
            raise AssertionError("unexpected subprocess")
        if "rev-parse" in argv:
            return subprocess.CompletedProcess(argv, 0, root + "\n", "")
        raise FileNotFoundError("git")

    with mock.patch.object(subprocess, "run", side_effect=fake_run):
        written = atomic_write_private(target, b"payload")
    assert written == target
    assert target.read_bytes() == b"payload"


def test_checkout_guard_allows_write_when_ignore_check_cannot_spawn(tmp_path: Path) -> None:
    """A spawn failure on the ignore check, after an untracked result, still allows the write."""
    target = tmp_path / "report.json"
    root = str(tmp_path.resolve())

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        del kwargs
        argv = _git_argv(args)
        if argv is None:
            raise AssertionError("unexpected subprocess")
        if "rev-parse" in argv:
            return subprocess.CompletedProcess(argv, 0, root + "\n", "")
        if "ls-files" in argv:
            return subprocess.CompletedProcess(argv, 1, "", "")
        raise FileNotFoundError("git")

    with mock.patch.object(subprocess, "run", side_effect=fake_run):
        written = atomic_write_private(target, b"payload")
    assert written == target
    assert target.read_bytes() == b"payload"


def test_atomic_write_succeeds_when_git_is_missing(tmp_path: Path) -> None:
    target = tmp_path / "export.bin"

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        del kwargs
        command = args[0] if args else None
        if isinstance(command, list) and command and command[0] == "git":
            raise FileNotFoundError("git")
        raise AssertionError("unexpected subprocess")

    with mock.patch.object(subprocess, "run", side_effect=fake_run):
        written = atomic_write_private(target, b"payload")
    assert written == target
    assert target.read_bytes() == b"payload"


def test_frozen_build_skips_git_checkout_guard(tmp_path: Path) -> None:
    _git(["git", "init", "-q", str(tmp_path)])
    target = tmp_path / "inside-repo.bin"
    git_calls: list[list[str]] = []

    def record_git_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        del kwargs
        command = args[0] if args else None
        if not isinstance(command, list):
            raise AssertionError("unexpected subprocess")
        argv = [part for part in command if isinstance(part, str)]
        if argv and argv[0] == "git":
            git_calls.append(argv)
            return subprocess.CompletedProcess(argv, 0, "", "")
        raise AssertionError("unexpected subprocess")

    with (
        mock.patch.object(subprocess, "run", side_effect=record_git_run),
        mock.patch.object(sys, "frozen", True, create=True),
    ):
        atomic_write_private(target, b"frozen-export")
    assert target.read_bytes() == b"frozen-export"
    assert git_calls == []


def test_git_spawn_uses_create_no_window_when_available(monkeypatch: pytest.MonkeyPatch) -> None:
    flag = 0x08000000
    monkeypatch.setattr(subprocess, "CREATE_NO_WINDOW", flag, raising=False)
    captured: dict[str, object] = {}

    def capture_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        command = args[0] if args else None
        if not isinstance(command, list):
            raise AssertionError("unexpected subprocess")
        argv = [part for part in command if isinstance(part, str)]
        captured["creationflags"] = kwargs.get("creationflags")
        return subprocess.CompletedProcess(argv, 1, "", "")

    monkeypatch.setattr(subprocess, "run", capture_run)
    from guiskindose import safe_output

    safe_output._git_root(Path("/nonexistent"))

    assert captured.get("creationflags") == flag
