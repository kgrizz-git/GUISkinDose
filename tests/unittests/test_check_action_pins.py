"""Unit tests for scripts/check_action_pins.py. No network."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.check_action_pins import check_workflows, resolve_token

PIN = "a" * 40
OTHER = "b" * 40
TAG_OBJECT = "c" * 40


def _write(directory: Path, text: str) -> None:
    (directory / "workflow.yml").write_text(text, encoding="utf-8")


def _forbid_fetch(url: str, token: str) -> tuple[int, str]:
    raise AssertionError(f"fetch should not be called for {url} with token length {len(token)}")


def test_local_uses_is_ignored(tmp_path: Path) -> None:
    _write(tmp_path, "jobs:\n  call:\n    uses: ./.github/workflows/privacy-gates.yml\n")
    assert check_workflows(tmp_path, _forbid_fetch, "token") == []


def test_full_sha_commit_200_passes(tmp_path: Path) -> None:
    _write(tmp_path, f"steps:\n  - uses: actions/checkout@{PIN}\n")

    def fetch(url: str, token: str) -> tuple[int, str]:
        assert token == "token"
        assert url.endswith(f"/commits/{PIN}")
        return 200, "{}"

    assert check_workflows(tmp_path, fetch, "token") == []


def test_tag_ref_fails_before_fetch(tmp_path: Path) -> None:
    _write(tmp_path, "steps:\n  - uses: actions/checkout@v4\n")
    failures = check_workflows(tmp_path, _forbid_fetch, "token")
    assert len(failures) == 1
    assert "actions/checkout" in failures[0]
    assert "not a full commit sha" in failures[0]


def test_commit_404_fails(tmp_path: Path) -> None:
    _write(tmp_path, f"steps:\n  - uses: actions/checkout@{PIN}\n")

    def fetch(url: str, token: str) -> tuple[int, str]:
        assert url.endswith(f"/commits/{PIN}")
        assert token
        return 404, "missing"

    failures = check_workflows(tmp_path, fetch, "token")
    assert len(failures) == 1
    assert "commit not found" in failures[0]


def test_semver_comment_matching_peeled_tag_passes(tmp_path: Path) -> None:
    _write(tmp_path, f"steps:\n  - uses: actions/checkout@{PIN}  # v1.2.3\n")
    seen: list[str] = []

    def fetch(url: str, token: str) -> tuple[int, str]:
        assert token == "token"
        seen.append(url)
        if url.endswith(f"/commits/{PIN}"):
            return 200, "{}"
        if url.endswith("/git/ref/tags/v1.2.3"):
            body = json.dumps({"object": {"type": "tag", "sha": TAG_OBJECT}})
            return 200, body
        if url.endswith(f"/git/tags/{TAG_OBJECT}"):
            body = json.dumps({"object": {"type": "commit", "sha": PIN}})
            return 200, body
        raise AssertionError(url)

    assert check_workflows(tmp_path, fetch, "token") == []
    assert any(url.endswith("/git/ref/tags/v1.2.3") for url in seen)
    assert any(url.endswith(f"/git/tags/{TAG_OBJECT}") for url in seen)


def test_semver_comment_pointing_elsewhere_fails(tmp_path: Path) -> None:
    _write(tmp_path, f"steps:\n  - uses: actions/checkout@{PIN}  # v1.2.3\n")

    def fetch(url: str, token: str) -> tuple[int, str]:
        assert token
        if url.endswith(f"/commits/{PIN}"):
            return 200, "{}"
        if url.endswith("/git/ref/tags/v1.2.3"):
            body = json.dumps({"object": {"type": "commit", "sha": OTHER}})
            return 200, body
        raise AssertionError(url)

    failures = check_workflows(tmp_path, fetch, "token")
    assert len(failures) == 1
    assert failures[0].endswith(f"workflow.yml:2: actions/checkout: tag v1.2.3 points at {OTHER}")


def test_major_only_comment_does_not_request_tag(tmp_path: Path) -> None:
    _write(tmp_path, f"steps:\n  - uses: actions/github-script@{PIN}  # v9\n")
    seen: list[str] = []

    def fetch(url: str, token: str) -> tuple[int, str]:
        assert token
        seen.append(url)
        return 200, "{}"

    assert check_workflows(tmp_path, fetch, "token") == []
    assert seen
    assert all("/git/ref/tags/v9" not in url for url in seen)


def test_missing_token_exits_2(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    with pytest.raises(SystemExit) as caught:
        resolve_token()
    assert caught.value.code == 2
