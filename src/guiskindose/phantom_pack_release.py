"""Code-owned phantom-pack release location and redirect policy.

The download URL is derived from the running application version. It is never
read from settings, an environment variable, or a command-line argument, so a
user cannot point the app at another host. The allowed redirect hosts are the
GitHub release host and the asset CDN hosts GitHub redirects to.
"""

from __future__ import annotations

import re
from urllib.parse import SplitResult, urlsplit

PACK_RELEASE_REPOSITORY = "kgrizz-git/GUISkinDose"
PACK_ASSET_NAME_TEMPLATE = "guiskindose-phantom-pack-{version}.zip"
PACK_RELEASE_URL_TEMPLATE = (
    "https://github.com/{repository}/releases/download/v{version}/{asset}"
)

# GitHub redirects a /releases/download/ request to its asset CDN. These are the
# only hosts a redirect may reach; anything else is refused before a second
# request is made.
PACK_REDIRECT_HOSTS: frozenset[str] = frozenset(
    {
        "github.com",
        "release-assets.githubusercontent.com",
        "objects.githubusercontent.com",
    }
)

_PLAIN_RELEASE_VERSION = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")


def pack_asset_name(version: str) -> str | None:
    """Return the release asset name for *version*, or ``None`` when not releasable."""
    if not isinstance(version, str) or not _PLAIN_RELEASE_VERSION.fullmatch(version):
        return None
    return PACK_ASSET_NAME_TEMPLATE.format(version=version)


def pack_release_url(version: str) -> str | None:
    """Return the pinned download URL for *version*, or ``None`` when not releasable.

    Only a plain ``X.Y.Z`` version has a public release tag. A source checkout
    reporting ``0.0.0+unknown`` and a prerelease/local suffix fail closed.
    """
    asset = pack_asset_name(version)
    if asset is None:
        return None
    return PACK_RELEASE_URL_TEMPLATE.format(
        repository=PACK_RELEASE_REPOSITORY,
        version=version,
        asset=asset,
    )


def _split_secure_url(url: str) -> SplitResult | None:
    """Parse an HTTPS URL with no userinfo and the default port, else ``None``."""
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except (TypeError, ValueError):
        return None
    if parsed.scheme != "https" or not parsed.hostname:
        return None
    if parsed.username is not None or parsed.password is not None:
        return None
    if port not in (None, 443):
        return None
    return parsed


def is_allowed_pack_url(url: str) -> bool:
    """True when *url* is the HTTPS GitHub release host the app may start from."""
    parsed = _split_secure_url(url)
    return parsed is not None and parsed.hostname is not None and parsed.hostname.lower() == "github.com"


def is_allowed_redirect_url(url: str) -> bool:
    """True when a redirect target is HTTPS on an allowed GitHub asset host."""
    parsed = _split_secure_url(url)
    return parsed is not None and parsed.hostname is not None and parsed.hostname.lower() in PACK_REDIRECT_HOSTS
