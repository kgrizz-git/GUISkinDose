"""Tests for the isolated privacy-scan tool project and its launcher."""

from __future__ import annotations

import tomllib
from pathlib import Path
from unittest import mock

import pytest
from packaging.requirements import Requirement
from packaging.version import Version

from scripts import privacy_admission, privacy_scan_tool

ROOT = Path(__file__).resolve().parents[2]


def test_tool_environment_redirects_uv_settings(tmp_path: Path) -> None:
    env = privacy_scan_tool.tool_environment(
        {"UV_PYTHON": "3.14", "VIRTUAL_ENV": "/x", "UV_PROJECT_ENVIRONMENT": "/root/.venv", "KEEP": "1"},
        root=tmp_path,
    )
    assert "UV_PYTHON" not in env
    assert "VIRTUAL_ENV" not in env
    assert env["UV_PROJECT_ENVIRONMENT"] == str(tmp_path / "tools/privacy-scan/.venv")
    assert env["KEEP"] == "1"


def test_script_argv_uses_tool_project(tmp_path: Path) -> None:
    assert privacy_scan_tool.script_argv("s.py", ["--a"], root=tmp_path) == [
        "uv", "run", "--project", str(tmp_path / "tools/privacy-scan"), "--no-sync", "python", "s.py", "--a",
    ]


def _run_scanner_capture(scanner_id: str, tmp_path: Path) -> mock.Mock:
    rule = privacy_admission.ScannerRule(
        scanner_id=scanner_id, version="v", trigger_extensions=frozenset(), trigger_prefixes=(),
        input_extensions=frozenset(), input_prefixes=(), scope="all_matching", config_paths=(),
        diff_regex=None,
    )
    completed = mock.Mock(returncode=0, stdout="", stderr="")
    (tmp_path / "tools/privacy-scan/.venv").mkdir(parents=True)
    (tmp_path / "tools/privacy-scan/.venv/pyvenv.cfg").write_text("home = x\n", encoding="utf-8")
    with (
        mock.patch.object(privacy_admission, "git_path_directory", return_value=tmp_path / "cache"),
        mock.patch.object(privacy_admission.subprocess, "run", return_value=completed) as run,
        mock.patch.dict("os.environ", {"UV_PYTHON": "3.14", "VIRTUAL_ENV": "/x"}),
    ):
        privacy_admission.run_scanner(tmp_path, tmp_path / "snap", rule, ["a.png"] if scanner_id == "image-ocr" else ["a.md"])
    return run


def test_run_scanner_presidio_uses_tool_project(tmp_path: Path) -> None:
    run = _run_scanner_capture("presidio", tmp_path)
    argv = run.call_args.args[0]
    assert argv[:5] == ["uv", "run", "--project", str(tmp_path / "tools/privacy-scan"), "--no-sync"]
    assert "--fail-on-findings" in argv
    env = run.call_args.kwargs["env"]
    assert env["UV_PROJECT_ENVIRONMENT"] == str(tmp_path / "tools/privacy-scan/.venv")
    assert "UV_PYTHON" not in env
    assert "UV_CACHE_DIR" in env


def test_run_scanner_image_ocr_uses_tool_project(tmp_path: Path) -> None:
    run = _run_scanner_capture("image-ocr", tmp_path)
    assert str(tmp_path / "tools/privacy-scan") in run.call_args.args[0]
    assert run.call_args.kwargs["env"]["UV_PROJECT_ENVIRONMENT"] == str(tmp_path / "tools/privacy-scan/.venv")


def _floors(path: Path) -> dict[str, Version]:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    deps = list(data.get("project", {}).get("dependencies", []))
    floors: dict[str, Version] = {}
    for spec in deps:
        req = Requirement(spec)
        for item in req.specifier:
            if item.operator == ">=":
                floors[req.name.lower()] = Version(item.version)
    return floors


def test_tool_project_floors_not_below_root() -> None:
    root_floors = _floors(ROOT / "pyproject.toml")
    tool_floors = _floors(ROOT / "tools/privacy-scan/pyproject.toml")
    for name in ("pillow", "pypdf", "pydicom"):
        assert tool_floors[name] >= root_floors[name], name


def test_environment_missing_reflects_pyvenv_cfg(tmp_path: Path) -> None:
    assert privacy_scan_tool.environment_missing(tmp_path)
    venv = tmp_path / "tools/privacy-scan/.venv"
    venv.mkdir(parents=True)
    (venv / "pyvenv.cfg").write_text("home = x\n", encoding="utf-8")
    assert not privacy_scan_tool.environment_missing(tmp_path)


def test_run_scanner_refuses_missing_env_without_paths(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    rule = privacy_admission.ScannerRule(
        scanner_id="presidio", version="v", trigger_extensions=frozenset(), trigger_prefixes=(),
        input_extensions=frozenset(), input_prefixes=(), scope="all_matching", config_paths=(), diff_regex=None,
    )
    with mock.patch.object(privacy_admission.subprocess, "run") as run:
        code = privacy_admission.run_scanner(tmp_path, tmp_path / "snap", rule, ["a.md"])
    err = capsys.readouterr().err
    assert code == 1
    run.assert_not_called()
    assert privacy_scan_tool.SYNC_COMMAND in err
    assert privacy_scan_tool.WINDOWS_SYNC_COMMAND in err
    assert str(tmp_path) not in err
    assert not (tmp_path / "tools").exists()
