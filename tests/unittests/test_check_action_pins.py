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
    """Write ``text`` as the only workflow file in ``directory``."""
    (directory / "workflow.yml").write_text(text, encoding="utf-8")


def _forbid_fetch(url: str, token: str) -> tuple[int, str]:
    """Fail the test if the checker reaches the network."""
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


def test_commit_422_is_a_missing_commit(tmp_path: Path) -> None:
    _write(tmp_path, f"steps:\n  - uses: actions/checkout@{PIN}\n")

    def fetch(url: str, token: str) -> tuple[int, str]:
        assert url.endswith(f"/commits/{PIN}")
        assert token
        return 422, "No commit found for SHA"

    failures = check_workflows(tmp_path, fetch, "token")
    assert len(failures) == 1
    assert failures[0].endswith("actions/checkout: commit not found (github api status 422)")


def test_bare_hash_comment_still_checks_the_pin(tmp_path: Path) -> None:
    _write(tmp_path, f"steps:\n  - uses: actions/checkout@{PIN}  #\n")

    def fetch(url: str, token: str) -> tuple[int, str]:
        assert url.endswith(f"/commits/{PIN}")
        assert token
        return 404, "missing"

    failures = check_workflows(tmp_path, fetch, "token")
    assert len(failures) == 1
    assert failures[0].endswith("actions/checkout: commit not found")


def test_annotated_tag_peel_api_error_is_not_a_missing_tag(tmp_path: Path) -> None:
    _write(tmp_path, f"steps:\n  - uses: actions/checkout@{PIN}  # v1.2.3\n")

    def fetch(url: str, token: str) -> tuple[int, str]:
        assert token
        if url.endswith(f"/commits/{PIN}"):
            return 200, "{}"
        if url.endswith("/git/ref/tags/v1.2.3"):
            return 200, json.dumps({"object": {"type": "tag", "sha": TAG_OBJECT}})
        if url.endswith(f"/git/tags/{TAG_OBJECT}"):
            return 503, ""
        raise AssertionError(url)

    failures = check_workflows(tmp_path, fetch, "token")
    assert len(failures) == 1
    assert failures[0].endswith("actions/checkout: github api status 503")
    assert "tag v1.2.3 not found" not in failures[0]


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


def test_semver_comment_with_trailing_words_still_checks_tag(tmp_path: Path) -> None:
    _write(tmp_path, f"steps:\n  - uses: actions/checkout@{PIN}  # v1.2.3 release pin\n")

    def fetch(url: str, token: str) -> tuple[int, str]:
        assert token
        if url.endswith(f"/commits/{PIN}"):
            return 200, "{}"
        if url.endswith("/git/ref/tags/v1.2.3"):
            return 200, json.dumps({"object": {"type": "commit", "sha": PIN}})
        raise AssertionError(url)

    assert check_workflows(tmp_path, fetch, "token") == []


def test_github_api_error_is_not_reported_as_a_missing_commit(tmp_path: Path) -> None:
    _write(tmp_path, f"steps:\n  - uses: actions/checkout@{PIN}\n")

    def fetch(url: str, token: str) -> tuple[int, str]:
        assert token
        assert url.endswith(f"/commits/{PIN}")
        return 503, ""

    failures = check_workflows(tmp_path, fetch, "token")
    assert len(failures) == 1
    assert failures[0].endswith("workflow.yml:2: actions/checkout: github api status 503")


def test_quoted_uses_key_is_checked(tmp_path: Path) -> None:
    _write(tmp_path, f'steps:\n  - "uses": actions/checkout@{PIN}\n')
    seen: list[str] = []

    def fetch(url: str, token: str) -> tuple[int, str]:
        assert token
        seen.append(url)
        return 200, "{}"

    assert check_workflows(tmp_path, fetch, "token") == []
    assert any(url.endswith(f"/commits/{PIN}") for url in seen)


def test_single_quoted_uses_key_is_checked(tmp_path: Path) -> None:
    _write(tmp_path, "steps:\n  - 'uses': actions/checkout@v4\n")
    failures = check_workflows(tmp_path, _forbid_fetch, "token")
    assert len(failures) == 1
    assert failures[0].endswith("workflow.yml:2: actions/checkout: not a full commit sha")


def test_flow_mapping_uses_key_is_checked(tmp_path: Path) -> None:
    _write(tmp_path, f"steps:\n  - {{name: checkout, uses: actions/checkout@{PIN}}}\n")
    seen: list[str] = []

    def fetch(url: str, token: str) -> tuple[int, str]:
        assert token
        seen.append(url)
        return 200, "{}"

    assert check_workflows(tmp_path, fetch, "token") == []
    assert any(url.endswith(f"/commits/{PIN}") for url in seen)


def test_quoted_uses_key_inside_flow_mapping_is_checked(tmp_path: Path) -> None:
    _write(tmp_path, 'steps:\n  - { "uses": actions/checkout@v4 }\n')
    failures = check_workflows(tmp_path, _forbid_fetch, "token")
    assert len(failures) == 1
    assert "not a full commit sha" in failures[0]


def test_quoted_uses_value_with_spaces_is_reported(tmp_path: Path) -> None:
    _write(tmp_path, 'uses: "actions/checkout@not a pin"\n')
    failures = check_workflows(tmp_path, _forbid_fetch, "token")
    assert len(failures) == 1
    assert "not a full commit sha" in failures[0]


@pytest.mark.parametrize(
    "text",
    [
        '"uses":\n',
        "uses:\n",
        "- uses:\n",
        "uses: |\n",
        "- {uses: actions/checkout@v4 extra}\n",
        '- {"uses": "actions/checkout@v4" trailing}\n',
    ],
)
def test_unparseable_uses_value_is_reported(tmp_path: Path, text: str) -> None:
    _write(tmp_path, text)
    failures = check_workflows(tmp_path, _forbid_fetch, "token")
    assert len(failures) == 1
    assert "unparseable uses value" in failures[0]


def test_run_line_that_mentions_uses_is_ignored(tmp_path: Path) -> None:
    _write(tmp_path, "steps:\n  - run: echo uses: actions/checkout@v4\n")
    assert check_workflows(tmp_path, _forbid_fetch, "token") == []


def test_flow_mapping_keeps_uses_after_an_escaped_quote(tmp_path: Path) -> None:
    """A doubled single quote in an earlier field must not hide the uses key."""
    _write(tmp_path, "- {name: 'it''s checkout', uses: actions/checkout@v4}\n")
    failures = check_workflows(tmp_path, _forbid_fetch, "token")
    assert len(failures) == 1
    assert "actions/checkout: not a full commit sha" in failures[0]


def test_flow_mapping_keeps_uses_after_an_escaped_double_quote(tmp_path: Path) -> None:
    _write(tmp_path, '- {name: "say \\"hi\\"", uses: actions/checkout@v4}\n')
    failures = check_workflows(tmp_path, _forbid_fetch, "token")
    assert len(failures) == 1
    assert "actions/checkout: not a full commit sha" in failures[0]


@pytest.mark.parametrize("header", ["|2", ">2-"])
def test_explicit_block_indent_is_not_scanned(tmp_path: Path, header: str) -> None:
    _write(tmp_path, f"steps:\n  - run: {header}\n      uses: actions/checkout@v4\n")
    assert check_workflows(tmp_path, _forbid_fetch, "token") == []


def test_uses_after_folded_first_key_is_checked(tmp_path: Path) -> None:
    """A sibling uses key is not part of the folded value of the first key."""
    _write(
        tmp_path,
        "steps:\n  - if: >-\n      github.event_name == 'push'\n    uses: actions/checkout@v4\n",
    )
    failures = check_workflows(tmp_path, _forbid_fetch, "token")
    assert len(failures) == 1
    assert "workflow.yml:4:" in failures[0]
    assert "not a full commit sha" in failures[0]


def test_comment_that_looks_like_a_block_header_is_ignored(tmp_path: Path) -> None:
    _write(tmp_path, "steps:\n  # note: |\n    uses: actions/checkout@v4\n")
    failures = check_workflows(tmp_path, _forbid_fetch, "token")
    assert len(failures) == 1
    assert "workflow.yml:3:" in failures[0]


def test_uses_inside_run_block_is_ignored(tmp_path: Path) -> None:
    """A script body is not an action, and the next step still is."""
    _write(
        tmp_path,
        "steps:\n"
        "  - run: |\n"
        '      {"uses": "actions/checkout@v4"}\n'
        "      uses: actions/checkout@v4\n"
        "  - uses: actions/checkout@v4\n",
    )
    failures = check_workflows(tmp_path, _forbid_fetch, "token")
    assert len(failures) == 1
    assert "workflow.yml:5:" in failures[0]
    assert "not a full commit sha" in failures[0]


def test_missing_token_exits_2(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    with pytest.raises(SystemExit) as caught:
        resolve_token()
    assert caught.value.code == 2


@pytest.mark.parametrize("body", ["not json", "[]"])
def test_unreadable_tag_response_is_not_a_missing_tag(tmp_path: Path, body: str) -> None:
    """A 200 tag lookup with a body that is not a JSON object is an API error."""
    _write(tmp_path, f"steps:\n  - uses: actions/checkout@{PIN}  # v1.2.3\n")

    def fetch(url: str, token: str) -> tuple[int, str]:
        assert token
        if url.endswith(f"/commits/{PIN}"):
            return 200, "{}"
        if url.endswith("/git/ref/tags/v1.2.3"):
            return 200, body
        raise AssertionError(url)

    failures = check_workflows(tmp_path, fetch, "token")
    assert len(failures) == 1
    assert failures[0].endswith("actions/checkout: unreadable github api response")


def test_unreadable_annotated_tag_response_is_not_a_missing_tag(tmp_path: Path) -> None:
    _write(tmp_path, f"steps:\n  - uses: actions/checkout@{PIN}  # v1.2.3\n")

    def fetch(url: str, token: str) -> tuple[int, str]:
        assert token
        if url.endswith(f"/commits/{PIN}"):
            return 200, "{}"
        if url.endswith("/git/ref/tags/v1.2.3"):
            return 200, json.dumps({"object": {"type": "tag", "sha": TAG_OBJECT}})
        if url.endswith(f"/git/tags/{TAG_OBJECT}"):
            return 200, "not json"
        raise AssertionError(url)

    failures = check_workflows(tmp_path, fetch, "token")
    assert failures[0].endswith("actions/checkout: unreadable github api response")


@pytest.mark.parametrize(
    "line",
    [
        f"  - uses: actions/checkout@{PIN}#frag\n",
        f"  - {{uses: actions/checkout@{PIN}#frag}}\n",
    ],
)
def test_hash_without_leading_space_is_part_of_the_ref(tmp_path: Path, line: str) -> None:
    """YAML opens a comment only after whitespace, so ``@sha#frag`` is not a bare SHA."""
    _write(tmp_path, "steps:\n" + line)
    failures = check_workflows(tmp_path, _forbid_fetch, "token")
    assert len(failures) == 1
    assert "actions/checkout: not a full commit sha" in failures[0]


def test_flow_mapping_comment_after_space_is_still_a_comment(tmp_path: Path) -> None:
    _write(tmp_path, f"steps:\n  - {{uses: actions/checkout@{PIN} }} # v9\n")

    def fetch(url: str, token: str) -> tuple[int, str]:
        assert token
        assert url.endswith(f"/commits/{PIN}"), url
        return 200, "{}"

    assert check_workflows(tmp_path, fetch, "token") == []


def test_uses_after_block_in_nested_sequence_is_checked(tmp_path: Path) -> None:
    """Every leading ``-`` is stripped, so the block ends at the key column."""
    _write(tmp_path, "steps:\n  - - if: >-\n        x\n      uses: actions/checkout@v4\n")
    failures = check_workflows(tmp_path, _forbid_fetch, "token")
    assert len(failures) == 1
    assert "workflow.yml:4:" in failures[0]


@pytest.mark.parametrize("text", [f"- uses: #actions/checkout@{PIN}\n", f"- uses: 'actions/checkout@{PIN}'#v1.2.3\n"])
def test_hash_comment_rules_fail_closed(tmp_path: Path, text: str) -> None:
    """A value that is only a comment, or a quote glued to ``#``, is not one scalar."""
    _write(tmp_path, text)
    failures = check_workflows(tmp_path, _forbid_fetch, "token")
    assert len(failures) == 1
    assert "unparseable uses value" in failures[0]


def test_tab_before_comment_keeps_the_semver_note(tmp_path: Path) -> None:
    _write(tmp_path, f"steps:\n  - uses: actions/checkout@{PIN}\t# v1.2.3\n")
    seen: list[str] = []

    def fetch(url: str, token: str) -> tuple[int, str]:
        assert token
        seen.append(url)
        if url.endswith(f"/commits/{PIN}"):
            return 200, "{}"
        return 200, json.dumps({"object": {"type": "commit", "sha": PIN}})

    assert check_workflows(tmp_path, fetch, "token") == []
    assert any(url.endswith("/git/ref/tags/v1.2.3") for url in seen)
