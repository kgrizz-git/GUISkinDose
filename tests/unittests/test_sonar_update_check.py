"""Tests for the weekly advisory SonarQube server/scanner update check."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from scripts.sonar_update_check import (
    HUB_TAGS_URL,
    SCANNER_RELEASE_URL,
    UPDATE_STATE_PATH,
    check_due,
    fetch_text,
    latest_community_version,
    parse_version,
    run_update_check,
    scanner_version_from_output,
)

NOW = datetime(2026, 9, 26, 12, tzinfo=UTC)
HOST = "http://localhost:9000"
HUB_TAGS = {
    "results": [
        {"name": "latest", "digest": "sha256:new"},
        {"name": "community", "digest": "sha256:new"},
        {"name": "26.9.0.129388-community", "digest": "sha256:new"},
        {"name": "2026.5.0-developer", "digest": "sha256:dev"},
        {"name": "26.7.0.124771-community", "digest": "sha256:old"},
    ]
}


def fake_fetch(server: str = "26.7.0.124771", scanner: str = "8.1.0.6389"):
    responses = {
        HUB_TAGS_URL: json.dumps(HUB_TAGS),
        SCANNER_RELEASE_URL: json.dumps({"tag_name": scanner}),
        f"{HOST}/api/server/version": server,
    }
    calls: list[str] = []

    def fetch(url: str) -> str:
        calls.append(url)
        return responses[url]

    return fetch, calls


def test_parse_version_accepts_dotted_numbers_only() -> None:
    assert parse_version("26.9.0.129388") == (26, 9, 0, 129388)
    assert parse_version("8.1") == (8, 1)
    for raw in ("latest", "26", "1.2.3.4.5", "", None, "26.9-community"):
        assert parse_version(raw) is None


def test_latest_community_version_follows_community_digest() -> None:
    assert latest_community_version(HUB_TAGS) == "26.9.0.129388"


def test_latest_community_version_requires_digest_match() -> None:
    """Without a digest-matched versioned tag, report nothing rather than guess."""
    unpinned = {"results": [{"name": "25.1.0.1-community"}, {"name": "25.10.0.2-community"}]}
    assert latest_community_version(unpinned) is None
    other_digest = {
        "results": [
            {"name": "community", "digest": "sha256:new"},
            {"name": "25.10.0.2-community", "digest": "sha256:old"},
        ]
    }
    assert latest_community_version(other_digest) is None


@pytest.mark.parametrize("payload", [None, {}, {"results": "x"}, {"results": [{"name": "community"}]}])
def test_latest_community_version_rejects_unexpected_payloads(payload: object) -> None:
    assert latest_community_version(payload) is None


def test_scanner_version_parsed_without_echoing_paths() -> None:
    output = "INFO  Scanner configuration file: /somewhere/conf\nINFO  SonarScanner CLI 8.1.0.6389\n"
    assert scanner_version_from_output(output) == "8.1.0.6389"
    assert scanner_version_from_output("no version here") is None


def test_check_due_after_interval_or_bad_state(tmp_path: Path) -> None:
    state = tmp_path / "state.json"
    assert check_due(state, NOW)
    state.write_text(json.dumps({"last_checked": (NOW - timedelta(days=2)).isoformat()}), encoding="utf-8")
    assert not check_due(state, NOW)
    state.write_text(json.dumps({"last_checked": (NOW - timedelta(days=7)).isoformat()}), encoding="utf-8")
    assert check_due(state, NOW)
    state.write_text("not json", encoding="utf-8")
    assert check_due(state, NOW)


def test_reports_outdated_server_and_records_check(tmp_path: Path) -> None:
    fetch, _calls = fake_fetch()
    messages = run_update_check(
        tmp_path, HOST, "scanner", fetch=fetch, scanner_version=lambda _b: "8.1.0.6389", now=NOW
    )
    assert messages == [
        "SonarQube update available: server 26.7.0.124771 -> 26.9.0.129388. To update, back up, then bump the "
        "image pin in compose.sonarqube.yaml; see dev-docs/SONARQUBE_LOCAL.md."
    ]
    assert json.loads((tmp_path / UPDATE_STATE_PATH).read_text(encoding="utf-8"))["last_checked"] == NOW.isoformat()


def test_reports_outdated_scanner(tmp_path: Path) -> None:
    fetch, _calls = fake_fetch(server="26.9.0.129388", scanner="8.2.0.1")
    messages = run_update_check(
        tmp_path, HOST, "scanner", fetch=fetch, scanner_version=lambda _b: "8.1.0.6389", now=NOW
    )
    assert len(messages) == 1 and "sonar-scanner 8.1.0.6389 -> 8.2.0.1" in messages[0]


def test_skips_network_when_recently_checked(tmp_path: Path) -> None:
    state = tmp_path / UPDATE_STATE_PATH
    state.parent.mkdir(parents=True)
    state.write_text(json.dumps({"last_checked": (NOW - timedelta(days=1)).isoformat()}), encoding="utf-8")
    fetch, calls = fake_fetch()
    assert run_update_check(tmp_path, HOST, "scanner", fetch=fetch, scanner_version=lambda _b: "1.0", now=NOW) == []
    assert calls == []
    fetch, calls = fake_fetch()
    forced = run_update_check(
        tmp_path, HOST, "scanner", force=True, fetch=fetch, scanner_version=lambda _b: "8.1.0.6389", now=NOW
    )
    assert calls and forced


def test_offline_skips_silently_and_stays_due(tmp_path: Path) -> None:
    def offline(_url: str) -> str:
        raise OSError("offline")

    assert run_update_check(tmp_path, HOST, "scanner", fetch=offline, scanner_version=lambda _b: "1.0", now=NOW) == []
    assert not (tmp_path / UPDATE_STATE_PATH).exists()


def test_unreachable_server_does_not_record_check(tmp_path: Path) -> None:
    fetch, _calls = fake_fetch()

    def fetch_without_server(url: str) -> str:
        if url.startswith(HOST):
            raise OSError("connection refused")
        return fetch(url)

    result = run_update_check(
        tmp_path, HOST, "scanner", fetch=fetch_without_server, scanner_version=lambda _b: "8.1.0.6389", now=NOW
    )
    assert result == []
    assert not (tmp_path / UPDATE_STATE_PATH).exists()


@pytest.mark.parametrize("url", ["http://example.com/x", "file:///etc/hosts", "ftp://example.com/x"])
def test_fetch_text_refuses_non_https_public_urls(url: str) -> None:
    with pytest.raises(ValueError, match="unsupported"):
        fetch_text(url)


def test_invalid_version_does_not_record_check(tmp_path: Path) -> None:
    """A malformed version (e.g. an HTML error page) leaves the check due."""
    fetch, _calls = fake_fetch(server="<html>Service Unavailable</html>")
    result = run_update_check(tmp_path, HOST, "scanner", fetch=fetch, scanner_version=lambda _b: "8.1.0.6389", now=NOW)
    assert result == []
    assert not (tmp_path / UPDATE_STATE_PATH).exists()


def test_state_write_failure_is_advisory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """An OSError while recording the check must not stop the runner."""
    def fail_write(_path: Path, _now: datetime) -> None:
        raise OSError("read-only")

    monkeypatch.setattr("scripts.sonar_update_check.record_check", fail_write)
    fetch, _calls = fake_fetch()
    messages = run_update_check(
        tmp_path, HOST, "scanner", fetch=fetch, scanner_version=lambda _b: "8.1.0.6389", now=NOW
    )
    assert len(messages) == 1
