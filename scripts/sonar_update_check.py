#!/usr/bin/env python3
"""Weekly advisory check for a newer local SonarQube server or scanner.

Stdlib-only helper for ``scripts/run_sonarqube_local.py``. At most once per
``CHECK_INTERVAL`` it compares:

* the running server's version (``/api/server/version`` on the loopback host,
  no token sent) against the newest ``<version>-community`` tag on Docker Hub
  that shares the ``community`` tag's digest; and
* the local ``sonar-scanner --version`` against the latest GitHub release of
  ``SonarSource/sonar-scanner-cli``.

The check is advisory: it never updates anything, never changes the runner's
exit code, and only reads public release metadata (nothing about this
repository is sent). Offline or unexpected responses skip silently and leave
the check due, so it retries on the next run. Rules ship inside the server's
bundled analyzers, so a current server means current rule definitions.
"""

from __future__ import annotations

import json
import re
import subprocess
from collections.abc import Callable
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import ProxyHandler, Request, build_opener

UPDATE_STATE_PATH = Path("tmp/sonar-update-check.json")
CHECK_INTERVAL = timedelta(days=7)
REQUEST_TIMEOUT = 5
HUB_TAGS_URL = (
    "https://hub.docker.com/v2/namespaces/library/repositories/sonarqube/tags?page_size=100&ordering=last_updated"
)
SCANNER_RELEASE_URL = "https://api.github.com/repos/SonarSource/sonar-scanner-cli/releases/latest"
SERVER_UPDATE_HINT = "back up, then bump the image pin in compose.sonarqube.yaml; see dev-docs/SONARQUBE_LOCAL.md"
SCANNER_UPDATE_HINT = "run brew upgrade sonar-scanner, or download it from SonarSource"
_LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}
_VERSION_RE = re.compile(r"^\d+(?:\.\d+){1,3}$")
_COMMUNITY_TAG_RE = re.compile(r"^(\d+(?:\.\d+){1,3})-community$")
_SCANNER_VERSION_RE = re.compile(r"SonarScanner CLI (\d+(?:\.\d+){1,3})\b")
# The server-version request carries no credentials, but it still must not
# leave the machine through an HTTP(S)_PROXY.
_LOOPBACK_OPENER = build_opener(ProxyHandler({}))
_PUBLIC_OPENER = build_opener()

FetchText = Callable[[str], str]


def parse_version(raw: object) -> tuple[int, ...] | None:
    """Return a numeric version tuple, or None for anything unexpected."""
    if not isinstance(raw, str) or not _VERSION_RE.match(raw.strip()):
        return None
    return tuple(int(part) for part in raw.strip().split("."))


def latest_community_version(tags_payload: object) -> str | None:
    """Return the ``<version>-community`` tag that shares the ``community`` tag's digest.

    Returns None when no versioned tag on the fetched page matches, rather than
    guessing from the highest tag and printing a spurious advisory.
    """
    results = tags_payload.get("results") if isinstance(tags_payload, dict) else None
    if not isinstance(results, list):
        return None
    tags = [tag for tag in results if isinstance(tag, dict) and isinstance(tag.get("name"), str)]
    community_digest = next((tag.get("digest") for tag in tags if tag["name"] == "community"), None)
    versioned: list[tuple[tuple[int, ...], str, object]] = []
    for tag in tags:
        match = _COMMUNITY_TAG_RE.match(tag["name"])
        parsed = parse_version(match.group(1)) if match else None
        if match and parsed:
            versioned.append((parsed, match.group(1), tag.get("digest")))
    pinned = [entry for entry in versioned if community_digest and entry[2] == community_digest]
    return max(pinned)[1] if pinned else None


def scanner_version_from_output(output: str) -> str | None:
    match = _SCANNER_VERSION_RE.search(output)
    return match.group(1) if match else None


def local_scanner_version(binary: str) -> str | None:
    try:
        completed = subprocess.run(
            [binary, "--version"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False, timeout=60
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return scanner_version_from_output(completed.stdout[:8192].decode("utf-8", errors="replace"))


def fetch_text(url: str) -> str:
    """GET a fixed https URL or a loopback server URL; raise OSError/ValueError on trouble."""
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower()
    if hostname in _LOOPBACK_HOSTS and parsed.scheme in {"http", "https"}:
        opener = _LOOPBACK_OPENER
    elif parsed.scheme == "https":
        opener = _PUBLIC_OPENER
    else:
        raise ValueError("unsupported update-check URL")
    request = Request(url, headers={"Accept": "application/json", "User-Agent": "guiskindose-sonar-update-check"})
    with opener.open(request, timeout=REQUEST_TIMEOUT) as response:  # nosec B310 - scheme checked above
        return response.read(1_000_000).decode("utf-8", errors="replace")


def check_due(state_path: Path, now: datetime) -> bool:
    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
        last = datetime.fromisoformat(payload["last_checked"])
    except (OSError, ValueError, KeyError, TypeError):
        return True
    if last.tzinfo is None:
        return True
    return now - last >= CHECK_INTERVAL


def record_check(state_path: Path, now: datetime) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps({"last_checked": now.isoformat()}, indent=2) + "\n", encoding="utf-8")


def _compare(label: str, local: str | None, latest: str | None, hint: str) -> str | None:
    local_v, latest_v = parse_version(local), parse_version(latest)
    if local_v is None or latest_v is None or local_v >= latest_v:
        return None
    return f"SonarQube update available: {label} {local} -> {latest}. To update, {hint}."


def run_update_check(
    root: Path,
    host_url: str,
    scanner_binary: str,
    *,
    force: bool = False,
    fetch: FetchText = fetch_text,
    scanner_version: Callable[[str], str | None] = local_scanner_version,
    now: datetime | None = None,
) -> list[str]:
    """Return advisory update messages; record the check only when it completed."""
    current = now or datetime.now(UTC)
    state_path = root / UPDATE_STATE_PATH
    if not force and not check_due(state_path, current):
        return []
    try:
        hub_tags = json.loads(fetch(HUB_TAGS_URL))
        release = json.loads(fetch(SCANNER_RELEASE_URL))
    except (OSError, ValueError):
        return []
    latest_server = latest_community_version(hub_tags)
    tag_name = release.get("tag_name") if isinstance(release, dict) else None
    latest_scanner = tag_name if isinstance(tag_name, str) else None
    try:
        local_server: str | None = fetch(f"{host_url}/api/server/version").strip()
    except (OSError, ValueError):
        local_server = None
    local_scanner = scanner_version(scanner_binary)
    versions = (latest_server, latest_scanner, local_server, local_scanner)
    if any(parse_version(version) is None for version in versions):
        return []
    # Advisory only: a failed state write leaves the check due and lets the analysis run.
    with suppress(OSError):
        record_check(state_path, current)
    messages = [
        _compare("server", local_server, latest_server, SERVER_UPDATE_HINT),
        _compare("sonar-scanner", local_scanner, latest_scanner, SCANNER_UPDATE_HINT),
    ]
    return [message for message in messages if message]
