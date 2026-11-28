"""Tests for the pinned, isolated phi-scan resolution.

The point of this module is that a privacy gate either runs the *pinned* scanner or
fails loudly — it must never silently run nothing, never silently run an unexpected
version, and never use the unverified ``uvx`` fallback in CI.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path
from typing import Any
from unittest import mock

import pytest

import scripts.phi_scan_tool as package_phi_scan_tool
from scripts import run_phi_scan

ROOT = Path(__file__).resolve().parents[2]


def _load_module() -> Any:
    """Load scripts/phi_scan_tool.py by path.

    Matches tests/unittests/test_semgrep_tool.py: `scripts/` is not an importable
    target for a sys.path insert under basedpyright, so the file is loaded directly.
    """
    spec = importlib.util.spec_from_file_location("phi_scan_tool", ROOT / "scripts" / "phi_scan_tool.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


phi_scan_tool = _load_module()
PhiScanUnavailableError: type[Exception] = phi_scan_tool.PhiScanUnavailableError
pinned_version = phi_scan_tool.pinned_version
phi_scan_argv = phi_scan_tool.phi_scan_argv
TOOL_PROJECT: Path = phi_scan_tool.TOOL_PROJECT


def _inventory(tmp_path: Path, tools: list[dict[str, object]]) -> Path:
    target = tmp_path / phi_scan_tool.INVENTORY_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({"version": 1, "tools": tools}), encoding="utf-8")
    return tmp_path


def _locked_project(root: Path, version: str = "1.2.3") -> Path:
    """Give a fake root a tool project that looks hash-locked at ``version``."""
    project = root / TOOL_PROJECT
    project.mkdir(parents=True, exist_ok=True)
    (project / "pyproject.toml").write_text(
        f'[project]\nname = "x"\ndependencies = ["phi-scan=={version}"]\n', encoding="utf-8"
    )
    (project / "uv.lock").write_text("version = 1\n", encoding="utf-8")
    return project


def _which(**found: str) -> Any:
    """shutil.which stub: only the named tools resolve."""
    return lambda name: found.get(name)


@pytest.fixture(autouse=True)
def _neutral_ci_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make every test state the CI-ness it means, instead of inheriting the runner's."""
    for name in ("CI", "GITHUB_ACTIONS"):
        monkeypatch.delenv(name, raising=False)


class TestPinnedVersion:
    def test_reads_the_real_inventory(self) -> None:
        version = pinned_version()
        assert version
        assert version[0].isdigit(), "expected a semver-ish pin"

    def test_reads_a_supplied_root(self, tmp_path: Path) -> None:
        root = _inventory(tmp_path, [{"id": "phi-scan", "version": "9.9.9"}])
        assert pinned_version(root) == "9.9.9"

    def test_missing_entry_raises(self, tmp_path: Path) -> None:
        root = _inventory(tmp_path, [{"id": "semgrep", "version": "1.0.0"}])
        with pytest.raises(PhiScanUnavailableError, match="no phi-scan entry"):
            pinned_version(root)

    @pytest.mark.parametrize("version", ["", "   ", None, 42])
    def test_unusable_version_raises(self, tmp_path: Path, version: object) -> None:
        root = _inventory(tmp_path, [{"id": "phi-scan", "version": version}])
        with pytest.raises(PhiScanUnavailableError, match="no version"):
            pinned_version(root)


class TestPhiScanArgv:
    def test_prefers_the_hash_locked_tool_project(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        root = _inventory(tmp_path, [{"id": "phi-scan", "version": "1.2.3"}])
        project = _locked_project(root)
        monkeypatch.setattr(phi_scan_tool.shutil, "which", _which(uv="/bin/uv", uvx="/bin/uvx"))
        argv = phi_scan_argv(["scan", "."], root=root)
        assert argv == ["/bin/uv", "run", "--locked", "--project", str(project), "phi-scan", "scan", "."]

    def test_locked_run_refuses_a_stale_manifest(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """--locked compares the manifest to its own lock and never reads the inventory."""
        root = _inventory(tmp_path, [{"id": "phi-scan", "version": "9.9.9"}])
        _locked_project(root, version="1.2.3")
        monkeypatch.setattr(phi_scan_tool.shutil, "which", _which(uv="/bin/uv"))
        with pytest.raises(PhiScanUnavailableError, match=r"inventory pins phi-scan 9\.9\.9"):
            phi_scan_argv(["scan", "."], root=root)

    def test_manifest_without_a_pin_is_refused(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        root = _inventory(tmp_path, [{"id": "phi-scan", "version": "1.2.3"}])
        project = _locked_project(root)
        (project / "pyproject.toml").write_text("[project]\nname = 'x'\n", encoding="utf-8")
        monkeypatch.setattr(phi_scan_tool.shutil, "which", _which(uv="/bin/uv"))
        with pytest.raises(PhiScanUnavailableError, match="declares no version"):
            phi_scan_argv(["scan", "."], root=root)

    def test_uvx_is_a_local_fallback_and_says_so(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = _inventory(tmp_path, [{"id": "phi-scan", "version": "1.2.3"}])
        monkeypatch.setattr(phi_scan_tool.shutil, "which", _which(uv="/bin/uv", uvx="/bin/uvx"))
        argv = phi_scan_argv(["scan", "."], root=root)
        assert argv == ["/bin/uvx", "--from", "phi-scan==1.2.3", "phi-scan", "scan", "."]
        assert "hash-verified" in capsys.readouterr().err

    def test_uvx_is_refused_in_ci_when_the_lock_is_missing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A green CI log would hide an unverified dependency tree."""
        root = _inventory(tmp_path, [{"id": "phi-scan", "version": "1.2.3"}])
        monkeypatch.setenv("CI", "true")
        monkeypatch.setattr(phi_scan_tool.shutil, "which", _which(uv="/bin/uv", uvx="/bin/uvx"))
        with pytest.raises(PhiScanUnavailableError, match="CI checkout must include it"):
            phi_scan_argv(["scan", "."], root=root)

    @pytest.mark.parametrize("fallback", ["uvx", "path"])
    def test_ci_refuses_every_non_locked_route_even_with_a_lock_present(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fallback: str
    ) -> None:
        """The lock is only load-bearing if CI cannot reach around it when uv is missing."""
        root = _inventory(tmp_path, [{"id": "phi-scan", "version": "1.2.3"}])
        _locked_project(root)
        monkeypatch.setenv("CI", "true")
        tools = {"uvx": "/bin/uvx"} if fallback == "uvx" else {"phi-scan": "/usr/bin/phi-scan"}
        monkeypatch.setattr(phi_scan_tool.shutil, "which", _which(**tools))
        monkeypatch.setattr(phi_scan_tool, "installed_version", lambda _exe: "1.2.3")
        with pytest.raises(PhiScanUnavailableError, match="CI checkout must include it"):
            phi_scan_argv(["scan", "."], root=root)

    def test_path_phi_scan_is_accepted_only_at_the_pinned_version(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = _inventory(tmp_path, [{"id": "phi-scan", "version": "1.2.3"}])
        monkeypatch.setattr(phi_scan_tool.shutil, "which", _which(**{"phi-scan": "/usr/bin/phi-scan"}))
        monkeypatch.setattr(phi_scan_tool, "installed_version", lambda _exe: "1.2.3")
        assert phi_scan_argv(["scan", "."], root=root) == ["/usr/bin/phi-scan", "scan", "."]
        assert "not the hash-locked ones" in capsys.readouterr().err

    @pytest.mark.parametrize("reported", ["1.2.4", "0.9.0", None])
    def test_path_phi_scan_at_the_wrong_version_is_refused(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, reported: str | None
    ) -> None:
        root = _inventory(tmp_path, [{"id": "phi-scan", "version": "1.2.3"}])
        monkeypatch.setattr(phi_scan_tool.shutil, "which", _which(**{"phi-scan": "/usr/bin/phi-scan"}))
        monkeypatch.setattr(phi_scan_tool, "installed_version", lambda _exe: reported)
        with pytest.raises(PhiScanUnavailableError, match=r"pinned to 1\.2\.3"):
            phi_scan_argv(["scan", "."], root=root)

    def test_a_phi_scan_inside_the_project_venv_is_refused(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root = _inventory(tmp_path, [{"id": "phi-scan", "version": "1.2.3"}])
        leaked = root / ".venv" / "bin" / "phi-scan"
        leaked.parent.mkdir(parents=True)
        leaked.write_text("#!/bin/sh\n", encoding="utf-8")
        monkeypatch.setattr(phi_scan_tool.shutil, "which", _which(**{"phi-scan": str(leaked)}))
        monkeypatch.setattr(phi_scan_tool, "installed_version", lambda _exe: "1.2.3")
        with pytest.raises(PhiScanUnavailableError, match="leaked into it"):
            phi_scan_argv(["scan", "."], root=root)

    def test_raises_when_nothing_can_run_it(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Never degrade to "skip the scan"."""
        root = _inventory(tmp_path, [{"id": "phi-scan", "version": "1.2.3"}])
        monkeypatch.setattr(phi_scan_tool.shutil, "which", lambda _name: None)
        with pytest.raises(PhiScanUnavailableError):
            phi_scan_argv(["scan", "."], root=root)


class TestRunner:
    def test_runner_fails_loudly_in_ci_without_uv(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """The runner must not start a scanner when CI has no hash-locked route.

        The error is value-free: it names the missing capability, not a filesystem path.
        """
        root = _inventory(tmp_path, [{"id": "phi-scan", "version": "1.2.3"}])
        _locked_project(root)
        monkeypatch.setenv("CI", "true")
        monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
        # Pull the lock present but uv unavailable: the CI guard must reject it before
        # considering the uvx or PATH fallbacks.
        monkeypatch.setattr(package_phi_scan_tool.shutil, "which", lambda _name: None)
        monkeypatch.setattr(
            run_phi_scan, "phi_scan_argv", lambda args: package_phi_scan_tool.phi_scan_argv(args, root=root)
        )
        with mock.patch.object(run_phi_scan.subprocess, "run") as run:
            code = run_phi_scan.main(["--version"])
        run.assert_not_called()
        err = capsys.readouterr().err
        assert code == 1
        assert "ERROR:" in err
        assert "CI checkout must include it" in err
        assert str(tmp_path) not in err


class TestInstalledVersion:
    def test_reads_the_name_prefixed_first_line(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            phi_scan_tool.subprocess,
            "run",
            lambda *_a, **_k: subprocess.CompletedProcess([], 0, "phi-scan 1.2.3\n", ""),
        )
        assert phi_scan_tool.installed_version("/usr/bin/phi-scan") == "1.2.3"

    @pytest.mark.parametrize(
        "outcome",
        [subprocess.CompletedProcess([], 2, "", "boom"), subprocess.CompletedProcess([], 0, "  \n", ""), OSError("nope")],
    )
    def test_unreadable_versions_are_none_not_an_exception(
        self, monkeypatch: pytest.MonkeyPatch, outcome: object
    ) -> None:
        """A failed probe must be reported as a mismatch, not crash the gate."""

        def fake_run(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
            if isinstance(outcome, BaseException):
                raise outcome
            assert isinstance(outcome, subprocess.CompletedProcess)
            return outcome

        monkeypatch.setattr(phi_scan_tool.subprocess, "run", fake_run)
        assert phi_scan_tool.installed_version("/usr/bin/phi-scan") is None


class TestToolEnvironment:
    def test_project_interpreter_pin_is_not_passed_to_the_tool(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("UV_PYTHON", "3.14")
        assert "UV_PYTHON" not in phi_scan_tool.tool_environment()

    def test_other_variables_survive(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("UV_CACHE_DIR", "/x/cache")
        assert phi_scan_tool.tool_environment()["UV_CACHE_DIR"] == "/x/cache"

    def test_the_tool_never_installs_into_the_project_environment(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("UV_PROJECT_ENVIRONMENT", str(ROOT / ".venv"))
        monkeypatch.setenv("VIRTUAL_ENV", str(ROOT / ".venv"))
        environment = phi_scan_tool.tool_environment()
        assert Path(environment["UV_PROJECT_ENVIRONMENT"]) == ROOT / TOOL_PROJECT / ".venv"
        assert "VIRTUAL_ENV" not in environment

    def test_the_tool_environment_follows_a_supplied_root(self, tmp_path: Path) -> None:
        environment = phi_scan_tool.tool_environment(root=tmp_path)
        assert Path(environment["UV_PROJECT_ENVIRONMENT"]) == tmp_path / TOOL_PROJECT / ".venv"


class TestHashLockedToolProject:
    def test_the_real_checkout_has_a_locked_tool_project(self) -> None:
        assert phi_scan_tool.locked_tool_project() == ROOT / TOOL_PROJECT

    def test_the_tool_pin_matches_the_inventory(self) -> None:
        """uv needs a literal requirement, so the pin exists twice; it must not drift."""
        manifest = (ROOT / TOOL_PROJECT / "pyproject.toml").read_text(encoding="utf-8")
        assert f'"phi-scan=={pinned_version()}"' in manifest

    def test_every_transitive_package_is_hash_pinned(self) -> None:
        """The reason this project exists: uvx records no hashes."""
        lock = (ROOT / TOOL_PROJECT / "uv.lock").read_text(encoding="utf-8")
        assert lock.count('hash = "sha256:') > 100
        assert f'name = "phi-scan"\nversion = "{pinned_version()}"' in lock

    def test_the_tool_project_is_not_in_the_root_resolution(self) -> None:
        """Isolation is the point; a workspace member would merge it back in."""
        assert "phi-scan" not in (ROOT / "uv.lock").read_text(encoding="utf-8")
        assert "[tool.uv.workspace]" not in (ROOT / "pyproject.toml").read_text(encoding="utf-8")

    def test_phi_scan_is_not_a_project_dependency(self) -> None:
        dependency_section = (ROOT / "pyproject.toml").read_text(encoding="utf-8").split("[tool.")[0]
        assert "phi-scan" not in dependency_section

    def test_the_resolved_command_actually_reports_the_pinned_version(self) -> None:
        """Assert the version that runs, not just the one requested.

        Deliberately no skip: a privacy gate that quietly does nothing is worse than one
        that fails.
        """
        completed = subprocess.run(
            phi_scan_argv(["--version"]),
            cwd=ROOT,
            env=phi_scan_tool.tool_environment(),
            check=False,
            capture_output=True,
            text=True,
            timeout=600,
        )
        assert completed.returncode == 0, completed.stderr[-2000:]
        assert completed.stdout.strip().splitlines()[0].strip().split()[-1] == pinned_version()

    def test_no_call_site_hardcodes_a_version(self) -> None:
        """A second copy of the pin is how the hook and CI drift apart."""
        for relative in (
            ".github/workflows/phi-scan.yml",
            "scripts/privacy_admission.py",
            "scripts/run_phi_scan.py",
        ):
            text = (ROOT / relative).read_text(encoding="utf-8")
            assert "phi-scan==" not in text, f"{relative} hardcodes a phi-scan version"

    def test_workflows_and_admission_go_through_the_resolver(self) -> None:
        """No direct `uvx --from phi-scan` anywhere outside the resolver's fallback."""
        workflow = (ROOT / ".github/workflows/phi-scan.yml").read_text(encoding="utf-8")
        admission = (ROOT / "scripts/privacy_admission.py").read_text(encoding="utf-8")
        runner = (ROOT / "scripts/run_phi_scan.py").read_text(encoding="utf-8")
        assert "scripts/run_phi_scan.py" in workflow
        assert "uvx" not in workflow
        assert "phi_scan_tool.phi_scan_argv" in admission
        assert "uvx" not in admission
        assert "phi_scan_argv" in runner
        # The only place the unverified fallback may be constructed is the resolver.
        resolver = (ROOT / "scripts/phi_scan_tool.py").read_text(encoding="utf-8")
        assert '"--from"' in resolver
        for relative in (".github/workflows/phi-scan.yml", "scripts/privacy_admission.py", "scripts/run_phi_scan.py"):
            assert "--from" not in (ROOT / relative).read_text(encoding="utf-8"), relative

    def test_no_workflow_or_script_invokes_uvx_for_phi_scan(self) -> None:
        """Every call site resolves through the hash-locked tool project instead."""
        offenders: list[str] = []
        for pattern in (".github/workflows/*.yml", "scripts/*.py"):
            for path in ROOT.glob(pattern):
                if path.name == "phi_scan_tool.py":
                    continue
                text = path.read_text(encoding="utf-8")
                if "--from phi-scan" in text or "uvx --from phi-scan" in text:
                    offenders.append(path.relative_to(ROOT).as_posix())
        assert offenders == []
