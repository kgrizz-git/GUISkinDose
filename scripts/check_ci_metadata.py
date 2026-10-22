#!/usr/bin/env python3
"""Scan GitHub PR/push metadata without echoing matched values."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

if __package__:
    from .check_sensitive_content import text_findings
else:  # pragma: no cover - GitHub Actions invokes this file directly.
    from check_sensitive_content import text_findings


@dataclass(frozen=True)
class MetadataFinding:
    source: str
    line: str
    rule: str


def scan_event_payload(payload: dict[str, object]) -> list[MetadataFinding]:
    sources: list[tuple[str, str]] = []
    pull_request = payload.get("pull_request")
    if isinstance(pull_request, dict):
        for field in ("title", "body"):
            value = pull_request.get(field)
            if isinstance(value, str):
                sources.append((f"pull_request_{field}", value))

    commits = payload.get("commits")
    if isinstance(commits, list):
        for index, commit in enumerate(commits, start=1):
            if isinstance(commit, dict) and isinstance(commit.get("message"), str):
                sources.append((f"push_commit_{index}", str(commit["message"])))

    return _scan_sources(sources)


def scan_commit_messages(commits: Sequence[tuple[str, str]]) -> list[MetadataFinding]:
    """Scan ``(short_sha, message)`` pairs, such as a pull request's own commits."""
    return _scan_sources([(f"pr_commit_{sha}", message) for sha, message in commits])


def read_commit_messages(commit_range: str) -> list[tuple[str, str]]:
    """Return ``(short_sha, message)`` for each commit in a ``base..head`` range."""
    output = subprocess.run(
        ["git", "log", "--format=%h%x00%B%x1e", commit_range],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    commits: list[tuple[str, str]] = []
    for record in output.split("\x1e"):
        sha, sep, message = record.lstrip("\n").partition("\x00")
        if sep:
            commits.append((sha, message))
    return commits


def _scan_sources(sources: Sequence[tuple[str, str]]) -> list[MetadataFinding]:
    findings: list[MetadataFinding] = []
    for source, text in sources:
        # Commit messages may include Dependabot Signed-off-by /
        # Co-authored-by noreply trailers; PR title/body stay strict.
        allow_trailers = source.startswith(("push_commit_", "pr_commit_"))
        findings.extend(
            MetadataFinding(source=source, line=finding.location, rule=finding.rule)
            for finding in text_findings(source, text, allow_git_identity_trailers=allow_trailers)
        )
    return findings


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("event_path", type=Path, help="GitHub event JSON path")
    parser.add_argument(
        "--commit-range",
        help="Also scan the commit messages in this git range (base..head), e.g. a pull request's commits",
    )
    args = parser.parse_args(argv)
    try:
        payload = json.loads(args.event_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: CI metadata scan did not run ({type(exc).__name__}).", file=sys.stderr)
        return 2
    if not isinstance(payload, dict):
        print("ERROR: CI metadata scan did not run (invalid_event).", file=sys.stderr)
        return 2
    findings = scan_event_payload(payload)
    if args.commit_range:
        try:
            findings.extend(scan_commit_messages(read_commit_messages(args.commit_range)))
        except (OSError, subprocess.CalledProcessError) as exc:
            print(f"ERROR: CI metadata scan did not run ({type(exc).__name__}).", file=sys.stderr)
            return 2
    for finding in findings:
        print(f"ERROR: {finding.source}:{finding.line}: {finding.rule}", file=sys.stderr)
    if findings:
        return 1
    print("CI metadata privacy scan OK.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
