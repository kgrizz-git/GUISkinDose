"""Tests for the local-only SonarQube runner."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from scripts.run_sonarqube_local import (
    build_scanner_command,
    classify_failure,
    load_env_defaults,
    project_version_from_pyproject,
    sanitize_host_url,
    validate_host,
    validate_scanner_binary,
    write_freshness_state,
)


@pytest.mark.parametrize(
    "url",
    ["http://localhost:9000", "http://127.0.0.1:9000", "http://[::1]:9000"],
)
def test_loopback_sonarqube_hosts_are_allowed(url: str) -> None:
    validate_host(url, allow_remote=False)


def test_remote_sonarqube_host_requires_explicit_override() -> None:
    with pytest.raises(ValueError, match="non-loopback"):
        validate_host("https://sonar.example.com", allow_remote=False)

    validate_host("https://sonar.example.com", allow_remote=True)


def test_failure_classification_suppresses_raw_scanner_detail(tmp_path: Path) -> None:
    log = tmp_path / "scanner.log"
    log.write_text("Analysis failed: Not authorized. Check sonar.token for /private/path", encoding="utf-8")

    assert classify_failure(log) == "authentication_required"


def test_scanner_binary_must_be_absolute_known_name(tmp_path: Path) -> None:
    binary = tmp_path / "sonar-scanner"
    binary.write_text("#!/bin/sh\n", encoding="utf-8")
    binary.chmod(0o755)

    assert validate_scanner_binary(str(binary.resolve())) == binary.resolve()
    with pytest.raises(ValueError, match="absolute"):
        validate_scanner_binary("sonar-scanner")
    other = tmp_path / "other-tool"
    other.write_text("#!/bin/sh\n", encoding="utf-8")
    with pytest.raises(ValueError, match="unexpected"):
        validate_scanner_binary(str(other.resolve()))


def test_scanner_command_rejects_control_characters_in_host(tmp_path: Path) -> None:
    binary = tmp_path / "sonar-scanner"
    binary.write_text("#!/bin/sh\n", encoding="utf-8")
    resolved = binary.resolve()

    safe_url = sanitize_host_url("http://localhost:9000", allow_remote=False)
    command = build_scanner_command(resolved, safe_url, wait_for_quality_gate=True)
    assert command[0] == str(resolved)
    assert command[1] == "-Dsonar.host.url=http://localhost:9000"
    with pytest.raises(ValueError, match="invalid SonarQube host URL"):
        sanitize_host_url("http://localhost:9000\n-Dsonar.extra=1", allow_remote=False)


def test_sanitize_host_url_emits_loopback_literals() -> None:
    assert sanitize_host_url("http://127.0.0.1:9000", allow_remote=False) == "http://127.0.0.1:9000"
    assert sanitize_host_url("http://[::1]:9000", allow_remote=False) == "http://[::1]:9000"


def test_scanner_command_passes_project_version(tmp_path: Path) -> None:
    binary = tmp_path / "sonar-scanner"
    binary.write_text("#!/bin/sh\n", encoding="utf-8")
    resolved = binary.resolve()

    command = build_scanner_command(resolved, "http://localhost:9000", wait_for_quality_gate=True)
    assert not any(part.startswith("-Dsonar.projectVersion=") for part in command)

    versioned = build_scanner_command(
        resolved, "http://localhost:9000", wait_for_quality_gate=True, project_version="1.0.0"
    )
    assert "-Dsonar.projectVersion=1.0.0" in versioned

    with pytest.raises(ValueError, match="invalid project version"):
        build_scanner_command(
            resolved,
            "http://localhost:9000",
            wait_for_quality_gate=True,
            project_version="1.0\n-Dsonar.extra=1",
        )


def test_project_version_from_pyproject(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "x"\nversion = "1.2.3"\n', encoding="utf-8")
    assert project_version_from_pyproject(tmp_path) == "1.2.3"
    assert project_version_from_pyproject(tmp_path / "missing") is None


def test_project_version_ignores_other_tables_and_comments(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[tool.example]\ntool_version = "9.9.9"\n[project]\nname = "x"\nversion = "1.2.3"  # release\n',
        encoding="utf-8",
    )
    assert project_version_from_pyproject(tmp_path) == "1.2.3"


def test_project_version_invalid_toml_returns_none(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project\nversion = \n", encoding="utf-8")
    assert project_version_from_pyproject(tmp_path) is None
    (tmp_path / "pyproject.toml").write_text("[tool.example]\nname = \"x\"\n", encoding="utf-8")
    assert project_version_from_pyproject(tmp_path) is None


def test_write_freshness_state_round_trips(tmp_path: Path) -> None:
    import json

    from scripts.run_sonarqube_local import FRESHNESS_STATE_PATH

    write_freshness_state(tmp_path, {"last_scan_commit": "abc123", "issues_count": None})
    payload = json.loads((tmp_path / FRESHNESS_STATE_PATH).read_text(encoding="utf-8"))
    assert payload["last_scan_commit"] == "abc123"


def test_load_env_defaults_from_dotenv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SONAR_TOKEN", raising=False)
    monkeypatch.delenv("SONAR_HOST_URL", raising=False)
    (tmp_path / ".env").write_text(
        'SONAR_TOKEN="squ_test" # local token\nSONAR_HOST_URL=http://localhost:9000\nOTHER=ignored\n',
        encoding="utf-8",
    )
    load_env_defaults(tmp_path)
    assert os.environ["SONAR_TOKEN"] == "squ_test"
    assert os.environ["SONAR_HOST_URL"] == "http://localhost:9000"
    assert "OTHER" not in os.environ


def test_load_env_defaults_exported_wins(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SONAR_TOKEN", "exported")
    monkeypatch.delenv("SONAR_HOST_URL", raising=False)
    (tmp_path / ".env").write_text("SONAR_TOKEN=file-token\n", encoding="utf-8")
    load_env_defaults(tmp_path)
    assert os.environ["SONAR_TOKEN"] == "exported"
