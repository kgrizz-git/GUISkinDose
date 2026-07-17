"""Tests for the local-only SonarQube runner."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.run_sonarqube_local import classify_failure, validate_host


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
