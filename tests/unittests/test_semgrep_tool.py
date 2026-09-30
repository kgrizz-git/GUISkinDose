"""Tests for the pinned, isolated Semgrep resolution.

The point of this module is that a security gate either runs the *pinned*
scanner or fails loudly — it must never silently run nothing, and it must never
silently run an unexpected version.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
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
TOOL_PROJECT: Path = semgrep_tool.TOOL_PROJECT


def _locked_project(root: Path) -> Path:
    """Give a fake root a tool project that looks hash-locked."""
    project = root / TOOL_PROJECT
    project.mkdir(parents=True, exist_ok=True)
    (project / "pyproject.toml").write_text("[project]\nname = 'x'\n", encoding="utf-8")
    (project / "uv.lock").write_text("version = 1\n", encoding="utf-8")
    return project


def _which(**found: str) -> Any:
    """shutil.which stub: only the named tools resolve."""
    return lambda name: found.get(name)


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

    def test_prefers_the_hash_locked_tool_project(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """A version pin alone leaves ~68 transitive packages re-resolved per run."""
        root = _inventory(tmp_path, [{"id": "semgrep", "version": "1.2.3"}])
        project = _locked_project(root)
        monkeypatch.delenv(UNPINNED_ENV, raising=False)
        monkeypatch.setattr(semgrep_tool.shutil, "which", _which(uv="/bin/uv", uvx="/bin/uvx"))
        argv = semgrep_argv(["--version"], root=root)
        assert argv == ["/bin/uv", "run", "--locked", "--project", str(project), "semgrep", "--version"]

    def test_locked_run_refuses_a_stale_lock(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """--locked is what makes the lock load-bearing instead of decorative."""
        root = _inventory(tmp_path, [{"id": "semgrep", "version": "1.2.3"}])
        _locked_project(root)
        monkeypatch.delenv(UNPINNED_ENV, raising=False)
        monkeypatch.setattr(semgrep_tool.shutil, "which", _which(uv="/bin/uv"))
        assert "--locked" in semgrep_argv(["--version"], root=root)

    def test_uvx_is_used_when_the_lock_is_absent(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Degrading to version-only isolation is allowed, but must say so."""
        root = _inventory(tmp_path, [{"id": "semgrep", "version": "1.2.3"}])
        monkeypatch.delenv(UNPINNED_ENV, raising=False)
        monkeypatch.setattr(semgrep_tool.shutil, "which", _which(uv="/bin/uv", uvx="/bin/uvx"))
        argv = semgrep_argv(["--version"], root=root)
        assert argv == ["/bin/uvx", "--from", "semgrep==1.2.3", "semgrep", "--version"]
        assert "hash-locked" in capsys.readouterr().err

    def test_path_semgrep_is_accepted_only_at_the_pinned_version(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = _inventory(tmp_path, [{"id": "semgrep", "version": "1.2.3"}])
        monkeypatch.delenv(UNPINNED_ENV, raising=False)
        monkeypatch.setattr(semgrep_tool.shutil, "which", _which(semgrep="/usr/bin/semgrep"))
        monkeypatch.setattr(semgrep_tool, "installed_version", lambda _exe: "1.2.3")
        assert semgrep_argv(["--version"], root=root) == ["/usr/bin/semgrep", "--version"]
        assert "not the hash-locked ones" in capsys.readouterr().err

    @pytest.mark.parametrize("reported", ["1.2.4", "0.9.0", None])
    def test_path_semgrep_at_the_wrong_version_is_refused(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, reported: str | None
    ) -> None:
        """Otherwise the gate silently becomes advisory: it passes locally, fails in CI."""
        root = _inventory(tmp_path, [{"id": "semgrep", "version": "1.2.3"}])
        monkeypatch.delenv(UNPINNED_ENV, raising=False)
        monkeypatch.setattr(semgrep_tool.shutil, "which", _which(semgrep="/usr/bin/semgrep"))
        monkeypatch.setattr(semgrep_tool, "installed_version", lambda _exe: reported)
        with pytest.raises(SemgrepUnavailableError, match=r"pinned to 1\.2\.3"):
            semgrep_argv(["--version"], root=root)

    def test_raises_when_nothing_can_run_it(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Never degrade to "skip the scan"."""
        root = _inventory(tmp_path, [{"id": "semgrep", "version": "1.2.3"}])
        monkeypatch.delenv(UNPINNED_ENV, raising=False)
        monkeypatch.setattr(semgrep_tool.shutil, "which", lambda _name: None)
        with pytest.raises(SemgrepUnavailableError):
            semgrep_argv(["--version"], root=root)

    @pytest.mark.parametrize("truthy", ["1", "true", "YES", "on"])
    @pytest.mark.parametrize("ci_var", ["CI", "GITHUB_ACTIONS"])
    def test_unpinned_probe_drops_the_version_in_ci(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, truthy: str, ci_var: str
    ) -> None:
        root = _inventory(tmp_path, [{"id": "semgrep", "version": "1.2.3"}])
        monkeypatch.setenv(UNPINNED_ENV, truthy)
        monkeypatch.setenv(ci_var, "true")
        monkeypatch.setattr(semgrep_tool.shutil, "which", lambda name: "/bin/uvx" if name == "uvx" else None)
        assert semgrep_argv(["--version"], root=root) == ["/bin/uvx", "semgrep", "--version"]

    def test_unpinned_probe_is_refused_outside_ci(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """The hatch must not let a local `.env` unpin the *blocking* gates.

        `.envrc` runs `dotenv_if_exists .env`, so without this an unaudited line in a
        gitignored file would silently convert the privacy gate to an arbitrary version.
        """
        root = _inventory(tmp_path, [{"id": "semgrep", "version": "1.2.3"}])
        monkeypatch.setenv(UNPINNED_ENV, "1")
        monkeypatch.delenv("CI", raising=False)
        monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
        monkeypatch.setattr(semgrep_tool.shutil, "which", lambda name: "/bin/uvx" if name == "uvx" else None)
        assert "semgrep==1.2.3" in semgrep_argv(["--version"], root=root)
        assert "ignoring" in capsys.readouterr().err

    @pytest.mark.parametrize("falsy", ["", "0", "false", "no"])
    def test_falsy_probe_flag_keeps_the_pin(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, falsy: str) -> None:
        """Only an explicit opt-in, in CI, may unpin the gate."""
        root = _inventory(tmp_path, [{"id": "semgrep", "version": "1.2.3"}])
        monkeypatch.setenv(UNPINNED_ENV, falsy)
        monkeypatch.setenv("CI", "true")
        monkeypatch.setattr(semgrep_tool.shutil, "which", lambda name: "/bin/uvx" if name == "uvx" else None)
        assert "semgrep==1.2.3" in semgrep_argv(["--version"], root=root)


class TestToolEnvironment:
    def test_project_interpreter_pin_is_not_passed_to_the_tool(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """`.envrc` pins UV_PYTHON for the project; uvx would honour it otherwise.

        Left in place, the local gate would run Semgrep on the project's interpreter
        while CI used the runner default — so a release dropping that version would
        break every direnv developer's pre-push gate with CI still green.
        """
        monkeypatch.setenv("UV_PYTHON", "3.14")
        assert "UV_PYTHON" not in semgrep_tool.tool_environment()

    def test_other_variables_survive(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SEMGREP_ENABLE_VERSION_CHECK", "0")
        assert semgrep_tool.tool_environment()["SEMGREP_ENABLE_VERSION_CHECK"] == "0"

    def test_the_tool_never_installs_into_the_project_environment(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """`.envrc` exports UV_PROJECT_ENVIRONMENT=.venv, and `uv run` honours it.

        Left in place, the hash-locked run would install Semgrep and its pinned
        dependencies into the very environment this design keeps them out of.
        """
        monkeypatch.setenv("UV_PROJECT_ENVIRONMENT", str(ROOT / ".venv"))
        monkeypatch.setenv("VIRTUAL_ENV", str(ROOT / ".venv"))
        environment = semgrep_tool.tool_environment()
        assert Path(environment["UV_PROJECT_ENVIRONMENT"]) == ROOT / TOOL_PROJECT / ".venv"
        assert "VIRTUAL_ENV" not in environment

    def test_the_tool_environment_follows_a_supplied_root(self, tmp_path: Path) -> None:
        environment = semgrep_tool.tool_environment(root=tmp_path)
        assert Path(environment["UV_PROJECT_ENVIRONMENT"]) == tmp_path / TOOL_PROJECT / ".venv"


class TestInstalledVersion:
    def test_reads_the_first_output_line(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            semgrep_tool.subprocess,
            "run",
            lambda *_a, **_k: subprocess.CompletedProcess([], 0, "1.2.3\nextra\n", ""),
        )
        assert semgrep_tool.installed_version("/usr/bin/semgrep") == "1.2.3"

    @pytest.mark.parametrize("outcome", [subprocess.CompletedProcess([], 2, "", "boom"), OSError("nope")])
    def test_unreadable_versions_are_none_not_an_exception(
        self, monkeypatch: pytest.MonkeyPatch, outcome: object
    ) -> None:
        """A failed probe must be reported as a mismatch, not crash the gate."""

        def fake_run(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
            if isinstance(outcome, BaseException):
                raise outcome
            assert isinstance(outcome, subprocess.CompletedProcess)
            return outcome

        monkeypatch.setattr(semgrep_tool.subprocess, "run", fake_run)
        assert semgrep_tool.installed_version("/usr/bin/semgrep") is None


class TestHashLockedToolProject:
    def test_the_real_checkout_has_a_locked_tool_project(self) -> None:
        assert semgrep_tool.locked_tool_project() == ROOT / TOOL_PROJECT

    def test_the_tool_pin_matches_the_inventory(self) -> None:
        """uv needs a literal requirement, so the pin exists twice; it must not drift."""
        manifest = (ROOT / TOOL_PROJECT / "pyproject.toml").read_text(encoding="utf-8")
        assert f'"semgrep=={pinned_version()}"' in manifest

    def test_every_transitive_package_is_hash_pinned(self) -> None:
        """The reason this project exists: uvx records no hashes."""
        lock = (ROOT / TOOL_PROJECT / "uv.lock").read_text(encoding="utf-8")
        assert lock.count('hash = "sha256:') > 100
        assert f'name = "semgrep"\nversion = "{pinned_version()}"' in lock

    def test_the_tool_project_is_not_in_the_root_resolution(self) -> None:
        """Isolation is the point; a workspace member would merge it back in."""
        assert "semgrep" not in (ROOT / "uv.lock").read_text(encoding="utf-8")
        assert "[tool.uv.workspace]" not in (ROOT / "pyproject.toml").read_text(encoding="utf-8")

    def test_the_resolved_command_actually_reports_the_pinned_version(self) -> None:
        """Assert the version that runs, not just the one requested.

        Deliberately no skip: as with tests/unittests/test_privacy_semgrep_rules.py, a
        security gate that quietly does nothing is worse than one that fails.
        """
        command = semgrep_argv(["--version"])
        completed = subprocess.run(
            command,
            cwd=ROOT,
            env=semgrep_tool.tool_environment(),
            check=False,
            capture_output=True,
            text=True,
            timeout=600,
        )
        assert completed.returncode == 0, completed.stderr[-2000:]
        assert completed.stdout.strip().splitlines()[0].strip() == pinned_version()


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
