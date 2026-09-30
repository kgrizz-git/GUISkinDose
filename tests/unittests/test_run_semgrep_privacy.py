"""Tests for the blocking privacy Semgrep runner.

This gate decides whether a push is allowed, so the cases that matter are the
ones where it must *refuse*: scanner missing, scanner crashed, scanner reported
its own errors, or malformed output. Any of those returning 0 would turn a
blocking privacy control into decoration.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any, ClassVar

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _load(name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


runner = _load("run_semgrep_privacy")


class _Completed:
    def __init__(self, returncode: int, stdout: str) -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = ""


def _stub_scan(monkeypatch: pytest.MonkeyPatch, returncode: int, payload: object) -> dict[str, Any]:
    captured: dict[str, Any] = {}

    def _fake_run(command: list[str], **kwargs: Any) -> _Completed:
        captured["command"] = command
        captured["kwargs"] = kwargs
        text = payload if isinstance(payload, str) else json.dumps(payload)
        return _Completed(returncode, text)

    monkeypatch.setattr(runner, "semgrep_argv", lambda args, root=None: ["SEMGREP", *args])
    monkeypatch.setattr(runner.subprocess, "run", _fake_run)
    return captured


class TestCleanScan:
    def test_no_findings_passes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _stub_scan(monkeypatch, 0, {"results": [], "errors": []})
        assert runner.main([]) == 0

    def test_uses_the_project_ruleset_and_code_paths(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured = _stub_scan(monkeypatch, 0, {"results": [], "errors": []})
        runner.main([])
        command = captured["command"]
        assert any(part.endswith("mypyskindose-privacy.yml") for part in command)
        for target in ("src", "scripts", "tests"):
            assert target in command
        assert "--json" in command

    def test_project_interpreter_pin_is_not_passed_through(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("UV_PYTHON", "3.14")
        captured = _stub_scan(monkeypatch, 0, {"results": [], "errors": []})
        runner.main([])
        assert "UV_PYTHON" not in captured["kwargs"]["env"]


class TestRefusals:
    def test_unresolvable_semgrep_returns_two(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A silent privacy gate is worse than a broken one."""

        def _raise(_args: list[str], root: Path | None = None) -> list[str]:
            raise runner.SemgrepUnavailableError("no uvx, no semgrep")

        monkeypatch.setattr(runner, "semgrep_argv", _raise)
        assert runner.main([]) == 2

    def test_scanner_that_cannot_start_returns_two(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(runner, "semgrep_argv", lambda args, root=None: ["SEMGREP", *args])

        def _raise(_command: list[str], **_kwargs: Any) -> None:
            raise OSError("exec format error")

        monkeypatch.setattr(runner.subprocess, "run", _raise)
        assert runner.main([]) == 2

    def test_unparseable_output_returns_two(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _stub_scan(monkeypatch, 0, "not json at all")
        assert runner.main([]) == 2

    def test_scanner_reported_errors_return_two(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Semgrep can exit 0 while reporting rule/parse errors; that is not a pass."""
        _stub_scan(monkeypatch, 0, {"results": [], "errors": [{"message": "rule failed"}]})
        assert runner.main([]) == 2

    @pytest.mark.parametrize("code", [2, 7])
    def test_unexpected_exit_code_returns_two(self, monkeypatch: pytest.MonkeyPatch, code: int) -> None:
        _stub_scan(monkeypatch, code, {"results": [], "errors": []})
        assert runner.main([]) == 2

    def test_non_list_results_return_two(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _stub_scan(monkeypatch, 0, {"results": "nope", "errors": []})
        assert runner.main([]) == 2


class TestFindings:
    _FINDING: ClassVar[dict[str, Any]] = {
        # Deliberately not a real rule id: the runner only splits on "." and prints the
        # tail, and a real id would carry the pre-rename brand past the stale-brand gate.
        "check_id": "rules.example-leaky-filename-rule",
        "path": "src/guiskindose/leaky.py",
        "start": {"line": 12},
    }

    def test_findings_fail_the_gate(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _stub_scan(monkeypatch, 1, {"results": [self._FINDING], "errors": []})
        assert runner.main([]) == 1

    def test_default_output_uses_a_path_token_not_the_path(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Default output must stay value-safe for shared logs."""
        _stub_scan(monkeypatch, 1, {"results": [self._FINDING], "errors": []})
        runner.main([])
        err = capsys.readouterr().err
        assert "path_token=" in err
        assert "leaky.py" not in err

    def test_verbose_paths_shows_the_path_for_local_debugging(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _stub_scan(monkeypatch, 1, {"results": [self._FINDING], "errors": []})
        runner.main(["--verbose-paths"])
        assert "src/guiskindose/leaky.py" in capsys.readouterr().err
