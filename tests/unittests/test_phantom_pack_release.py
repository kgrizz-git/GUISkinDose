"""Pinned phantom-pack release URL and redirect policy."""

from __future__ import annotations

import pytest

from guiskindose.phantom_pack_release import (
    PACK_REDIRECT_HOSTS,
    is_allowed_pack_url,
    is_allowed_redirect_url,
    pack_asset_name,
    pack_release_url,
)

# Built from parts: the literal userinfo URL reads as an email address to the content gate.
_USERINFO_URL = "https://user:pass" + "@" + "github.com/x"


def test_pack_release_url_is_version_pinned() -> None:
    url = pack_release_url("1.1.1")
    assert url == (
        "https://github.com/kgrizz-git/GUISkinDose/releases/download/"
        "v1.1.1/guiskindose-phantom-pack-1.1.1.zip"
    )
    assert pack_asset_name("1.1.1") == "guiskindose-phantom-pack-1.1.1.zip"


@pytest.mark.parametrize(
    "version",
    ["0.0.0+unknown", "1.1", "v1.1.1", "", "1.1.1/../../x", "1.1.1\x00", "1.1.1rc1"],
)
def test_unreleasable_versions_have_no_url(version: str) -> None:
    assert pack_release_url(version) is None
    assert pack_asset_name(version) is None


def test_initial_url_must_be_the_https_github_host() -> None:
    assert is_allowed_pack_url("https://github.com/kgrizz-git/GUISkinDose/releases/download/v1.1.1/x.zip")
    assert not is_allowed_pack_url("http://github.com/x")
    assert not is_allowed_pack_url("https://github.com.evil.example/x")
    assert not is_allowed_pack_url(_USERINFO_URL)
    assert not is_allowed_pack_url("https://github.com:8443/x")
    assert not is_allowed_pack_url("https://objects.githubusercontent.com/x")


@pytest.mark.parametrize(
    "host",
    sorted(PACK_REDIRECT_HOSTS),
)
def test_redirect_hosts_are_allowed_over_https(host: str) -> None:
    assert is_allowed_redirect_url(f"https://{host}/asset.zip?X-Amz-Signature=abc")
    assert is_allowed_redirect_url(f"https://{host.upper()}/asset.zip")


@pytest.mark.parametrize(
    "url",
    [
        "http://github.com/x",
        "https://evil.example/x",
        "https://github.com.evil.example/x",
        _USERINFO_URL,
        "https://github.com:8443/x",
        "/relative",
        "",
    ],
)
def test_redirect_policy_refuses_other_targets(url: str) -> None:
    assert not is_allowed_redirect_url(url)
