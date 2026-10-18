"""Tests for atomic, private, Git-aware export writes."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from unittest import mock

import pytest

from guiskindose.safe_output import UnsafeOutputPathError, atomic_write_private


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
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / ".gitignore").write_text("private-output/\n", encoding="utf-8")
    ignored = tmp_path / "private-output"
    ignored.mkdir()
    target = ignored / "report.json"

    with pytest.raises(UnsafeOutputPathError, match="export_checkout_path_forbidden"):
        atomic_write_private(target, b"{}")
    atomic_write_private(target, b"{}", allow_ignored_checkout=True)
    assert target.read_bytes() == b"{}"


def test_rejection_message_never_echoes_sensitive_destination(tmp_path: Path) -> None:
    sentinel = "PATIENT-SENTINEL-12345.json"
    target = tmp_path / sentinel
    target.write_bytes(b"existing")
    with pytest.raises(UnsafeOutputPathError) as caught:
        atomic_write_private(target, b"replacement")
    assert sentinel not in str(caught.value)


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
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
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
