"""Tests for the pinned, isolated Semgrep resolution.

The point of this module is that a security gate either runs the *pinned*
scanner or fails loudly — it must never silently run nothing, and it must never
silently run an unexpected version.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _load_module() -> Any:
    """Load scripts/semgrep_tool.py by path.

    Matches tests/unittests/test_audit_dependencies.py: `scripts/` is not an
    importable package, and a sys.path insert does not resolve for basedpyright.
    """
    spec = importlib.util.spec_from_file_location("semgrep_tool", ROOT / "scripts" / "semgrep_tool.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


semgrep_tool = _load_module()
UNPINNED_ENV: str = semgrep_tool.UNPINNED_ENV
SemgrepUnavailableError: type[Exception] = semgrep_tool.SemgrepUnavailableError
pinned_version = semgrep_tool.pinned_version
semgrep_argv = semgrep_tool.semgrep_argv


def _inventory(tmp_path: Path, tools: list[dict[str, object]]) -> Path:
    target = tmp_path / semgrep_tool.INVENTORY_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({"version": 1, "tools": tools}), encoding="utf-8")
    return tmp_path


class TestPinnedVersion:
    def test_reads_the_real_inventory(self) -> None:
        version = pinned_version()
        assert version
        assert version[0].isdigit(), "expected a semver-ish pin"

    def test_reads_a_supplied_root(self, tmp_path: Path) -> None:
        root = _inventory(tmp_path, [{"id": "semgrep", "version": "9.9.9"}])
        assert pinned_version(root) == "9.9.9"

    def test_missing_entry_raises(self, tmp_path: Path) -> None:
        root = _inventory(tmp_path, [{"id": "bandit", "version": "1.0.0"}])
        with pytest.raises(SemgrepUnavailableError, match="no semgrep entry"):
            pinned_version(root)

    @pytest.mark.parametrize("version", ["", "   ", None, 42])
    def test_unusable_version_raises(self, tmp_path: Path, version: object) -> None:
        root = _inventory(tmp_path, [{"id": "semgrep", "version": version}])
        with pytest.raises(SemgrepUnavailableError, match="no version"):
            pinned_version(root)


class TestSemgrepArgv:
    def test_prefers_a_pinned_isolated_run(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        root = _inventory(tmp_path, [{"id": "semgrep", "version": "1.2.3"}])
        monkeypatch.delenv(UNPINNED_ENV, raising=False)
        monkeypatch.setattr(semgrep_tool.shutil, "which", lambda name: "/bin/uvx" if name == "uvx" else None)
        argv = semgrep_argv(["--version"], root=root)
        assert argv == ["/bin/uvx", "--from", "semgrep==1.2.3", "semgrep", "--version"]

    def test_falls_back_to_path_semgrep_with_a_warning(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """An unpinned local binary is usable but must announce itself."""
        root = _inventory(tmp_path, [{"id": "semgrep", "version": "1.2.3"}])
        monkeypatch.delenv(UNPINNED_ENV, raising=False)
        monkeypatch.setattr(
            semgrep_tool.shutil, "which", lambda name: "/usr/bin/semgrep" if name == "semgrep" else None
        )
        argv = semgrep_argv(["--version"], root=root)
        assert argv == ["/usr/bin/semgrep", "--version"]
        assert "not pinned" in capsys.readouterr().err

    def test_raises_when_nothing_can_run_it(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Never degrade to "skip the scan"."""
        root = _inventory(tmp_path, [{"id": "semgrep", "version": "1.2.3"}])
        monkeypatch.delenv(UNPINNED_ENV, raising=False)
        monkeypatch.setattr(semgrep_tool.shutil, "which", lambda _name: None)
        with pytest.raises(SemgrepUnavailableError):
            semgrep_argv(["--version"], root=root)

    @pytest.mark.parametrize("truthy", ["1", "true", "YES", "on"])
    def test_unpinned_probe_drops_the_version(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, truthy: str
    ) -> None:
        root = _inventory(tmp_path, [{"id": "semgrep", "version": "1.2.3"}])
        monkeypatch.setenv(UNPINNED_ENV, truthy)
        monkeypatch.setattr(semgrep_tool.shutil, "which", lambda name: "/bin/uvx" if name == "uvx" else None)
        assert semgrep_argv(["--version"], root=root) == ["/bin/uvx", "semgrep", "--version"]

    @pytest.mark.parametrize("falsy", ["", "0", "false", "no"])
    def test_falsy_probe_flag_keeps_the_pin(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, falsy: str) -> None:
        """Only an explicit opt-in may unpin the gate."""
        root = _inventory(tmp_path, [{"id": "semgrep", "version": "1.2.3"}])
        monkeypatch.setenv(UNPINNED_ENV, falsy)
        monkeypatch.setattr(semgrep_tool.shutil, "which", lambda name: "/bin/uvx" if name == "uvx" else None)
        assert "semgrep==1.2.3" in semgrep_argv(["--version"], root=root)


class TestInventoryIsTheSingleSourceOfTruth:
    def test_semgrep_is_not_a_project_dependency(self) -> None:
        """Re-adding it to `dev` would restore the four advisory suppressions."""
        pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        dependency_section = pyproject.split("[tool.")[0]
        assert "semgrep" not in dependency_section

    def test_no_call_site_hardcodes_a_version(self) -> None:
        """A second copy of the pin is how the hook and CI drift apart."""
        root = ROOT
        for relative in (
            ".pre-commit-config.yaml",
            ".github/workflows/ci.yml",
            ".github/workflows/ci-latest.yml",
            "scripts/run_semgrep_owasp.py",
            "scripts/run_semgrep_privacy.py",
        ):
            text = (root / relative).read_text(encoding="utf-8")
            assert "semgrep==" not in text, f"{relative} hardcodes a semgrep version"
