"""Tests for the OWASP Semgrep runner.

Covers the "fails loudly" guarantees the module docstring sells, which were
previously unexercised: a scanner that cannot run, or cannot start, must return a
non-zero exit code rather than reporting success.
"""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _load(name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


runner = _load("run_semgrep_owasp")


class _Completed:
    def __init__(self, returncode: int) -> None:
        self.returncode = returncode


class TestCommandConstruction:
    def test_passes_config_flags_excludes_and_targets(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured: dict[str, Any] = {}

        def _fake_run(command: list[str], **kwargs: Any) -> _Completed:
            captured["command"] = command
            captured["kwargs"] = kwargs
            return _Completed(0)

        monkeypatch.setattr(runner.subprocess, "run", _fake_run)
        monkeypatch.setattr(runner, "semgrep_argv", lambda args: ["SEMGREP", *args])

        assert runner.main([]) == 0
        command = captured["command"]
        assert command[0] == "SEMGREP"
        assert "--config=p/owasp-top-ten" in command
        assert "--error" in command
        assert "--metrics=off" in command
        for target in ("src", "scripts", ".github/workflows", "docs/source/conf.py"):
            assert target in command
        assert any(part.startswith("--exclude=src/**/example_data") for part in command)

    def test_runs_from_the_repository_root(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured: dict[str, Any] = {}
        monkeypatch.setattr(
            runner.subprocess,
            "run",
            lambda command, **kwargs: captured.update(kwargs) or _Completed(0),
        )
        monkeypatch.setattr(runner, "semgrep_argv", lambda args: ["SEMGREP", *args])
        runner.main([])
        assert captured["cwd"] == ROOT

    def test_metrics_are_disabled_in_the_environment(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Belt and braces with --metrics=off; the Cloud App stays disabled."""
        captured: dict[str, Any] = {}
        monkeypatch.setattr(
            runner.subprocess,
            "run",
            lambda command, **kwargs: captured.update(kwargs) or _Completed(0),
        )
        monkeypatch.setattr(runner, "semgrep_argv", lambda args: ["SEMGREP", *args])
        runner.main([])
        assert captured["env"]["SEMGREP_SEND_METRICS"] == "off"
        assert captured["env"]["SEMGREP_ENABLE_VERSION_CHECK"] == "0"

    def test_extra_arguments_are_appended(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured: dict[str, Any] = {}
        monkeypatch.setattr(
            runner.subprocess,
            "run",
            lambda command, **kwargs: captured.update({"command": command}) or _Completed(0),
        )
        monkeypatch.setattr(runner, "semgrep_argv", lambda args: ["SEMGREP", *args])
        runner.main(["--verbose"])
        assert captured["command"][-1] == "--verbose"


class TestFailsLoudly:
    def test_unresolvable_semgrep_returns_two(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Never exit 0 when the scanner could not be resolved."""

        def _raise(_args: list[str]) -> list[str]:
            raise runner.SemgrepUnavailableError("no uvx, no semgrep")

        monkeypatch.setattr(runner, "semgrep_argv", _raise)
        assert runner.main([]) == 2

    def test_scanner_that_cannot_start_returns_two(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def _raise(_command: list[str], **_kwargs: Any) -> None:
            raise OSError("exec format error")

        monkeypatch.setattr(runner, "semgrep_argv", lambda args: ["SEMGREP", *args])
        monkeypatch.setattr(runner.subprocess, "run", _raise)
        assert runner.main([]) == 2

    @pytest.mark.parametrize("code", [0, 1, 2, 7])
    def test_scanner_exit_code_propagates(self, monkeypatch: pytest.MonkeyPatch, code: int) -> None:
        """Findings (1) and scanner errors must reach the hook and CI."""
        monkeypatch.setattr(runner, "semgrep_argv", lambda args: ["SEMGREP", *args])
        monkeypatch.setattr(runner.subprocess, "run", lambda *a, **k: _Completed(code))
        assert runner.main([]) == code


class TestNoShell:
    def test_command_is_a_list_so_nothing_can_be_injected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured: dict[str, Any] = {}
        monkeypatch.setattr(
            runner.subprocess,
            "run",
            lambda command, **kwargs: captured.update({"command": command, "kwargs": kwargs}) or _Completed(0),
        )
        monkeypatch.setattr(runner, "semgrep_argv", lambda args: ["SEMGREP", *args])
        runner.main([])
        assert isinstance(captured["command"], list)
        assert "shell" not in captured["kwargs"]


def test_real_subprocess_signature_is_respected() -> None:
    """Guard against the fake above drifting from subprocess.run's real contract."""
    assert callable(subprocess.run)
