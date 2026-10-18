#!/usr/bin/env python3
"""Verify every third-party GitHub Action ``uses:`` pin is a real commit.

What it does:
    Parses every ``*.yml`` and ``*.yaml`` file under ``.github/workflows``.
    Local ``./`` references and ``docker://`` images are skipped. A remote
    action (``owner/repo@ref`` or ``owner/repo/subpath@ref``) must be pinned
    to a full 40-hex commit SHA. The GitHub repository is ``owner/repo``; the
    subpath is not a separate repo. When the line comment is a full semver
    (``# vX.Y.Z``), that tag is resolved and peeled to a commit, which must
    equal the pin. A major-only comment (``# v9``) is not compared to the
    moving major tag.

Inputs:
    Workflow directory (default: ``.github/workflows`` in this checkout).
    Live checks call the GitHub REST API. Inject ``fetch(url, token)`` so
    tests can supply ``(status, body)`` without touching the network.

Outputs:
    Exit 0 and one OK line when every pin passes. Exit 1 with one line per
    failure (file, line, owner/repo, reason). Exit 2 when no token is set.
    Expected API failures are reported as pin failures, not tracebacks.

The live check needs a GitHub token in ``GH_TOKEN`` or ``GITHUB_TOKEN``.
The token and the Authorization header are never printed.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from email.message import Message
from pathlib import Path
from typing import IO

API = "https://api.github.com"
SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")
FULL_SEMVER_RE = re.compile(r"^v\d+\.\d+\.\d+$")
MAJOR_ONLY_RE = re.compile(r"^v\d+$")
USES_RE = re.compile(r"""^(?:-\s*)?uses:\s*['"]?(?P<spec>[^'"\s#]+)['"]?(?:\s*#\s*(?P<note>\S+).*)?\s*$""")
REMOTE_RE = re.compile(r"^(?P<owner>[A-Za-z0-9_.-]+)/(?P<repo>[A-Za-z0-9_.-]+)(?:/[^@]+)?@(?P<ref>.+)$")
OK_LINE = "Action pin check OK."
Fetch = Callable[[str, str], tuple[int, str]]
_MAX_PEEL_DEPTH = 5


class _RefuseRedirects(urllib.request.HTTPRedirectHandler):
    """Fail on 3xx so the Authorization header is never forwarded."""

    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: IO[bytes],
        code: int,
        msg: str,
        headers: Message,
        newurl: str,
    ) -> urllib.request.Request | None:
        raise urllib.error.HTTPError(req.full_url, code, "redirect refused for credentialed request", headers, fp)


_OPENER = urllib.request.build_opener(_RefuseRedirects)


@dataclass(frozen=True)
class ActionUse:
    """One remote ``uses:`` line."""

    path: Path
    line: int
    owner: str
    repo: str
    ref: str
    semver: str | None


def fetch(url: str, token: str) -> tuple[int, str]:
    """GET ``url`` with a bearer token.

    Returns ``(status, body)``. HTTP error statuses are returned to the caller.
    The token and Authorization header are never printed.
    """
    request = urllib.request.Request(url, headers=_request_headers(token))
    try:
        with _OPENER.open(request, timeout=30) as response:
            body = response.read().decode("utf-8", errors="replace")
            return int(response.status), body
    except urllib.error.HTTPError as exc:
        return exc.code, _error_body(exc)
    except OSError:
        return 0, ""


def resolve_token(env: Mapping[str, str] | None = None) -> str:
    """Return ``GH_TOKEN`` or ``GITHUB_TOKEN``.

    Exits 2 when neither is set. Does not print the token.
    """
    source = os.environ if env is None else env
    token = source.get("GH_TOKEN") or source.get("GITHUB_TOKEN")
    if token:
        return token
    print("Set GH_TOKEN or GITHUB_TOKEN for the live action-pin check.", file=sys.stderr)
    raise SystemExit(2)


def workflow_files(directory: Path) -> list[Path]:
    """Return workflow YAML files under ``directory``, sorted."""
    files = [path for pattern in ("*.yml", "*.yaml") for path in directory.rglob(pattern) if path.is_file()]
    return sorted(files)


def parse_uses(line: str) -> tuple[str, str | None] | None:
    """Return ``(spec, version note)`` when ``line`` is a single-line ``uses:``."""
    match = USES_RE.match(line.strip())
    if match is None:
        return None
    return match.group("spec"), match.group("note")


def semver_comment(note: str | None) -> str | None:
    """Return a ``vX.Y.Z`` comment, or None for major-only and other notes.

    A major-only note such as ``# v9`` names a moving tag. Existence of the
    pinned commit is enough; do not resolve that tag.
    """
    if note is None or MAJOR_ONLY_RE.fullmatch(note):
        return None
    if FULL_SEMVER_RE.fullmatch(note):
        return note
    return None


def uses_in_file(path: Path) -> tuple[list[ActionUse], list[str]]:
    """Collect remote action uses from one workflow file.

    Local ``./`` references and ``docker://`` images are ignored. An
    unparseable remote spec is a failure.
    """
    found: list[ActionUse] = []
    failures: list[str] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        parsed = parse_uses(line)
        if parsed is None:
            continue
        recorded = _record_use(path, number, parsed[0], parsed[1])
        if isinstance(recorded, ActionUse):
            found.append(recorded)
        elif recorded is not None:
            failures.append(recorded)
    return found, failures


def check_workflows(directory: Path, fetch_url: Fetch, token: str) -> list[str]:
    """Check every remote action pin under ``directory``.

    Commit lookups are deduped by owner, repo, and SHA. Tag lookups are
    deduped by owner, repo, and tag name.
    """
    commits: dict[tuple[str, str, str], int] = {}
    tags: dict[tuple[str, str, str], tuple[str | None, str | None]] = {}
    failures: list[str] = []
    for path in workflow_files(directory):
        uses, parse_failures = uses_in_file(path)
        failures.extend(parse_failures)
        failures.extend(_pin_failures(uses, fetch_url, token, commits, tags))
    return failures


def main(argv: list[str] | None = None) -> int:
    """Scan workflow pins and return the process exit code."""
    parser = argparse.ArgumentParser(description="Verify pinned GitHub Actions are real commits.")
    parser.add_argument(
        "--workflows",
        type=Path,
        default=_default_workflows(),
        help="Directory of workflow YAML files (default: this repo's .github/workflows).",
    )
    args = parser.parse_args(argv)
    token = resolve_token()
    if not args.workflows.is_dir():
        print(f"Workflow directory not found: {args.workflows}", file=sys.stderr)
        return 1
    failures = check_workflows(args.workflows, fetch, token)
    if failures:
        for line in failures:
            print(line)
        return 1
    print(OK_LINE)
    return 0


def _request_headers(token: str) -> dict[str, str]:
    """Headers for a credentialed GitHub API call. Callers must not log these."""
    return {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "User-Agent": "guiskindose-check-action-pins",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _error_body(exc: urllib.error.HTTPError) -> str:
    try:
        raw = exc.read()
    except OSError:
        return ""
    return raw.decode("utf-8", errors="replace")


def _default_workflows() -> Path:
    return Path(__file__).resolve().parents[1] / ".github" / "workflows"


def _display_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(Path.cwd().resolve()).as_posix()
    except (OSError, ValueError):
        return path.as_posix()


def _failure_line(path: Path, line: int, target: str, reason: str) -> str:
    return f"{_display_path(path)}:{line}: {target}: {reason}"


def _record_use(path: Path, number: int, spec: str, note: str | None) -> ActionUse | str | None:
    """Return an action use, a failure line, or None when the spec is skipped."""
    if spec.startswith("./") or spec.startswith("docker://"):
        return None
    match = REMOTE_RE.fullmatch(spec)
    if match is None:
        return _failure_line(path, number, spec, "not a full commit sha")
    return ActionUse(
        path=path,
        line=number,
        owner=match.group("owner"),
        repo=match.group("repo"),
        ref=match.group("ref"),
        semver=semver_comment(note),
    )


def _pin_failures(
    uses: list[ActionUse],
    fetch_url: Fetch,
    token: str,
    commits: dict[tuple[str, str, str], int],
    tags: dict[tuple[str, str, str], tuple[str | None, str | None]],
) -> list[str]:
    failures: list[str] = []
    for use in uses:
        reason = _pin_reason(use, fetch_url, token, commits, tags)
        if reason is not None:
            failures.append(_failure_line(use.path, use.line, f"{use.owner}/{use.repo}", reason))
    return failures


def _pin_reason(
    use: ActionUse,
    fetch_url: Fetch,
    token: str,
    commits: dict[tuple[str, str, str], int],
    tags: dict[tuple[str, str, str], tuple[str | None, str | None]],
) -> str | None:
    if not SHA_RE.fullmatch(use.ref):
        return "not a full commit sha"
    sha = use.ref.lower()
    status = _commit_status(fetch_url, token, use.owner, use.repo, sha, commits)
    if status == 404:
        return "commit not found"
    if status != 200:
        return f"github api status {status}"
    # A major-only note such as `# v9` names a moving tag. Existence of the
    # pinned commit is enough; do not compare the pin to that tag.
    if use.semver is None:
        return None
    return _tag_reason(use, sha, fetch_url, token, tags)


def _tag_reason(
    use: ActionUse,
    sha: str,
    fetch_url: Fetch,
    token: str,
    tags: dict[tuple[str, str, str], tuple[str | None, str | None]],
) -> str | None:
    tag = use.semver or ""
    pointed, error = _cached_tag_commit(fetch_url, token, use.owner, use.repo, tag, tags)
    if error is not None:
        return error
    if pointed is None:
        return f"tag {tag} not found"
    if pointed != sha:
        return f"tag {tag} points at {pointed}"
    return None


def _commit_status(
    fetch_url: Fetch,
    token: str,
    owner: str,
    repo: str,
    sha: str,
    cache: dict[tuple[str, str, str], int],
) -> int:
    """Return the GitHub status for this commit, using ``cache`` for repeats."""
    key = (owner, repo, sha)
    if key not in cache:
        status, _body = fetch_url(_api("repos", owner, repo, "commits", sha), token)
        cache[key] = status
    return cache[key]


def _cached_tag_commit(
    fetch_url: Fetch,
    token: str,
    owner: str,
    repo: str,
    tag: str,
    cache: dict[tuple[str, str, str], tuple[str | None, str | None]],
) -> tuple[str | None, str | None]:
    """Return ``(commit sha, error)``. A missing tag is ``(None, None)``."""
    key = (owner, repo, tag)
    if key not in cache:
        cache[key] = _peel_tag(fetch_url, token, owner, repo, tag)
    return cache[key]


def _peel_tag(fetch_url: Fetch, token: str, owner: str, repo: str, tag: str) -> tuple[str | None, str | None]:
    """Return the commit a tag points at.

    Annotated tags are followed to the commit. Lightweight tags already name it.
    ``(None, None)`` means the tag is missing. A non-404 failure is the error string.
    """
    status, body = fetch_url(_api("repos", owner, repo, "git", "ref", "tags", tag), token)
    if status == 404:
        return None, None
    if status != 200:
        return None, f"github api status {status}"
    payload = _json_object(body)
    if payload is None:
        return None, None
    return _peel(fetch_url, token, owner, repo, payload.get("object"), 0), None


def _peel(
    fetch_url: Fetch,
    token: str,
    owner: str,
    repo: str,
    obj: object,
    depth: int,
) -> str | None:
    if depth > _MAX_PEEL_DEPTH:
        return None
    peeled = _object_sha(obj)
    if peeled is None:
        return None
    kind, sha = peeled
    if kind == "commit":
        return sha
    if kind != "tag":
        return None
    status, body = fetch_url(_api("repos", owner, repo, "git", "tags", sha), token)
    if status != 200:
        return None
    payload = _json_object(body)
    if payload is None:
        return None
    return _peel(fetch_url, token, owner, repo, payload.get("object"), depth + 1)


def _json_object(body: str) -> dict[str, object] | None:
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return None
    if isinstance(payload, dict):
        return payload
    return None


def _object_sha(obj: object) -> tuple[str, str] | None:
    if not isinstance(obj, dict):
        return None
    kind = obj.get("type")
    sha = obj.get("sha")
    if isinstance(kind, str) and isinstance(sha, str) and SHA_RE.fullmatch(sha):
        return kind, sha.lower()
    return None


def _api(*parts: str) -> str:
    encoded = "/".join(urllib.parse.quote(part, safe="") for part in parts)
    return f"{API}/{encoded}"


if __name__ == "__main__":
    sys.exit(main())
