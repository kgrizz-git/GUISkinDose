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
    moving major tag. Quoted ``uses`` keys and a single-line flow mapping are
    recognized. A ``uses`` value that is not one scalar is a failure. This is
    not a YAML parser: block scalars and multi-line values are rejected, and
    lines inside a ``|`` or ``>`` block are not scanned.

Inputs:
    Workflow directory (default: ``.github/workflows`` in this checkout).
    Live checks call the GitHub REST API. Inject ``fetch(url, token)`` so
    tests can supply ``(status, body)`` without touching the network.

Outputs:
    Exit 0 and one OK line when every pin passes. Exit 1 with one line per
    failure (file, line, target, reason). The target is ``owner/repo`` for a
    remote action, or ``uses`` when the value cannot be read. Exit 2 when no
    token is set.
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


@dataclass(frozen=True)
class _ParsedUses:
    """One ``uses`` value.

    ``spec`` is None when the key was found but the value is not one scalar.
    """

    spec: str | None
    note: str | None


def parse_uses(line: str) -> _ParsedUses | None:
    """Return a ``uses`` entry, or None when ``line`` has no ``uses`` key.

    Recognizes a plain ``uses:`` key, a quoted ``uses`` key, and one ``uses``
    key inside a single-line ``{...}`` flow mapping. A bare ``#`` still counts
    as a uses line. The version note is the first comment token, or None when
    the comment is empty. ``spec`` is None when the value cannot be read as one
    scalar (empty, unclosed quotes, extra tokens, or a nested value).
    """
    content = _without_list_marker(line.strip())
    if content.startswith("{"):
        return _flow_uses(content, line)
    found = _mapping_key_value_at(content, 0)
    if found is None or found[0] != "uses":
        return None
    return _parsed_from_value(content[found[1] :], line)


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

    Local ``./`` references and ``docker://`` images are ignored. A ``uses``
    key whose value is not one scalar is a failure, as is an unparseable
    remote spec. Lines nested under a ``|`` or ``>`` block are ignored so a
    ``run`` script is not mistaken for an action.
    """
    found: list[ActionUse] = []
    failures: list[str] = []
    block_indent: int | None = None
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if _is_block_body(line, block_indent):
            continue
        block_indent = _block_header_indent(line)
        parsed = parse_uses(line)
        if parsed is None:
            continue
        if parsed.spec is None:
            failures.append(_failure_line(path, number, "uses", "unparseable uses value"))
            continue
        recorded = _record_use(path, number, parsed.spec, parsed.note)
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


def _is_block_body(line: str, block_indent: int | None) -> bool:
    """Return whether ``line`` is still inside a literal or folded block."""
    if block_indent is None:
        return False
    if not line.strip():
        return True
    return len(line) - len(line.lstrip(" ")) > block_indent


def _block_header_indent(line: str) -> int | None:
    """Return the indent of a ``key: |`` or ``key: >`` line, else None."""
    content = _without_list_marker(line.strip())
    _key, separator, value = content.partition(":")
    if not separator:
        return None
    indicator = value.split("#", 1)[0].strip()
    if indicator in {"|", "|-", "|+", ">", ">-", ">+"}:
        return len(line) - len(line.lstrip(" "))
    return None


def _without_list_marker(stripped: str) -> str:
    """Drop one leading sequence marker so ``- uses:`` and ``-{uses:}`` both match."""
    if stripped.startswith("- "):
        return stripped[2:].lstrip()
    if stripped.startswith(("-{", '-"', "-'")):
        return stripped[1:].lstrip()
    return stripped


def _mapping_key_value_at(text: str, index: int) -> tuple[str, int] | None:
    """Return ``(key, index after colon)`` when a mapping key starts at ``index``."""
    i = _skip_spaces(text, index)
    if i >= len(text) or text[i] in ",}#":
        return None
    key, i = _read_key(text, i)
    if key is None:
        return None
    i = _skip_spaces(text, i)
    if i >= len(text) or text[i] != ":":
        return None
    return key, i + 1


def _read_key(text: str, index: int) -> tuple[str | None, int]:
    """Return the key text and the index after it, or ``(None, index)``."""
    if text[index] in "\"'":
        end = _closing_quote(text, index)
        if end is None:
            return None, index
        return text[index + 1 : end], end + 1
    end = index
    while end < len(text) and text[end] not in ": \t,}#":
        end += 1
    if end == index:
        return None, index
    return text[index:end], end


def _flow_uses(text: str, line: str) -> _ParsedUses | None:
    """Return the ``uses`` entry in one flow mapping, or None when it has none."""
    value, unparseable = _flow_uses_value(text)
    if unparseable:
        return _ParsedUses(None, None)
    if value is None:
        return None
    return _parsed_from_value(value, line)


def _flow_uses_value(text: str) -> tuple[str | None, bool]:
    """Return ``(uses value, unparseable)`` for a ``{...}`` mapping.

    A broken mapping that never names ``uses`` is ignored. A ``uses`` key whose
    entry does not end at a comma or ``}`` is unparseable.
    """
    index = 1
    found: str | None = None
    while index < len(text):
        index = _skip_spaces(text, index)
        if index < len(text) and text[index] == "}":
            break
        step = _next_flow_entry(text, index)
        if step is None:
            return _broken_flow(text, index, found)
        key, value, index = step
        if key != "uses":
            continue
        if found is not None:
            return None, True
        found = value
    if found is None:
        return None, False
    return found, False


def _broken_flow(text: str, index: int, found: str | None) -> tuple[str | None, bool]:
    """Report a broken entry only when it is, or follows, a ``uses`` key."""
    key_here = _mapping_key_value_at(text, index)
    if found is not None or (key_here is not None and key_here[0] == "uses"):
        return None, True
    return None, False


def _next_flow_entry(text: str, index: int) -> tuple[str, str, int] | None:
    """Return ``(key, value text, index after the entry)``, or None when the entry breaks."""
    found = _mapping_key_value_at(text, index)
    if found is None:
        return None
    key, value_start = found
    value_end = _end_of_flow_value(text, value_start)
    if value_end is None:
        return None
    nxt = _skip_spaces(text, value_end)
    if nxt < len(text) and text[nxt] == ",":
        return key, text[value_start:value_end], nxt + 1
    if nxt < len(text) and text[nxt] == "}":
        return key, text[value_start:value_end], nxt
    return None


def _end_of_flow_value(text: str, start: int) -> int | None:
    """Return the index just after one flow-mapping value."""
    i = _skip_spaces(text, start)
    if i >= len(text):
        return i
    if text[i] in "\"'":
        end = _closing_quote(text, i)
        if end is None:
            return None
        return end + 1
    if text[i] in "{[":
        return _end_of_nest(text, i)
    while i < len(text) and text[i] not in ",}#":
        i += 1
    return i


def _end_of_nest(text: str, start: int) -> int | None:
    """Return the index just after a ``{}`` or ``[]`` group, respecting quotes."""
    depth = 0
    quote: str | None = None
    for i in range(start, len(text)):
        char = text[i]
        if quote is not None:
            if char == quote:
                quote = None
            continue
        if char in "\"'":
            quote = char
            continue
        if char in "{[":
            depth += 1
        elif char in "}]":
            depth -= 1
            if depth == 0:
                return i + 1
    return None


def _parsed_from_value(value_text: str, line: str) -> _ParsedUses:
    """Read one scalar and an optional ``# vX.Y.Z`` note."""
    spec, note, ok = _read_scalar(value_text)
    if not ok or not spec:
        return _ParsedUses(None, None)
    if note is None:
        note = _comment_note(line)
    return _ParsedUses(spec, note)


def _read_scalar(value_text: str) -> tuple[str | None, str | None, bool]:
    """Return ``(spec, note, ok)``. ``ok`` is false when the value is not one scalar."""
    text = value_text.strip()
    if not text or text[0] in "{[|>*!&":
        return None, None, False
    if text[0] in "\"'":
        quoted = _quoted_body(text)
        if quoted is None:
            return None, None, False
        body, rest = quoted
        if not body or "\\" in body or "''" in body:
            return None, None, False
        return _finish_scalar(body, rest)
    end = 0
    while end < len(text) and text[end] not in " \t#":
        end += 1
    if end == 0:
        return None, None, False
    return _finish_scalar(text[:end], text[end:])


def _quoted_body(text: str) -> tuple[str, str] | None:
    """Return ``(body, rest)`` for a matching pair of quotes, without unescaping."""
    end = _closing_quote(text, 0)
    if end is None:
        return None
    return text[1:end], text[end + 1 :]


def _finish_scalar(body: str, rest: str) -> tuple[str | None, str | None, bool]:
    """Accept ``body`` only when ``rest`` is empty or a ``#`` comment."""
    remainder = rest.strip()
    if not remainder:
        return body, None, True
    if not remainder.startswith("#"):
        return None, None, False
    comment = remainder[1:].strip()
    if not comment:
        return body, None, True
    return body, comment.split()[0], True


def _comment_note(line: str) -> str | None:
    """Return the first comment token on ``line`` that is outside quotes."""
    quote: str | None = None
    for index, char in enumerate(line):
        if quote is not None:
            if char == quote:
                quote = None
            continue
        if char in "\"'":
            quote = char
            continue
        if char == "#":
            comment = line[index + 1 :].strip()
            return comment.split()[0] if comment else None
    return None


def _closing_quote(text: str, start: int) -> int | None:
    """Return the index of the closing quote that matches ``text[start]``."""
    quote = text[start]
    for index in range(start + 1, len(text)):
        if text[index] == quote:
            return index
    return None


def _skip_spaces(text: str, index: int) -> int:
    while index < len(text) and text[index] in " \t":
        index += 1
    return index


def _record_use(path: Path, number: int, spec: str, note: str | None) -> ActionUse | str | None:
    """Return an action use, a failure line, or None when the spec is skipped."""
    if spec.startswith(("./", "docker://")):
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
    # GitHub returns 422, not 404, when the repo exists and the SHA does not.
    if status == 422:
        return "commit not found (github api status 422)"
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
    return _peel(fetch_url, token, owner, repo, payload.get("object"), 0)


def _peel(
    fetch_url: Fetch,
    token: str,
    owner: str,
    repo: str,
    obj: object,
    depth: int,
) -> tuple[str | None, str | None]:
    """Return ``(commit sha, error)`` while following an annotated tag."""
    if depth > _MAX_PEEL_DEPTH:
        return None, None
    peeled = _object_sha(obj)
    if peeled is None:
        return None, None
    kind, sha = peeled
    if kind == "commit":
        return sha, None
    if kind != "tag":
        return None, None
    status, body = fetch_url(_api("repos", owner, repo, "git", "tags", sha), token)
    if status == 404:
        return None, None
    if status != 200:
        return None, f"github api status {status}"
    payload = _json_object(body)
    if payload is None:
        return None, None
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
