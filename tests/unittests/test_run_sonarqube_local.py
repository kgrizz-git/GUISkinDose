"""Tests for the local-only SonarQube runner."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.run_sonarqube_local import (
    build_scanner_command,
    classify_failure,
    sanitize_host_url,
    validate_host,
    validate_scanner_binary,
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
