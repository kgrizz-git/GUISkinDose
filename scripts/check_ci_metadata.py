#!/usr/bin/env python3
"""Scan GitHub PR/push metadata without echoing matched values."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

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

    findings: list[MetadataFinding] = []
    for source, text in sources:
        findings.extend(
            MetadataFinding(source=source, line=finding.location, rule=finding.rule)
            for finding in text_findings(source, text)
        )
    return findings


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("event_path", type=Path, help="GitHub event JSON path")
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
    for finding in findings:
        print(f"ERROR: {finding.source}:{finding.line}: {finding.rule}", file=sys.stderr)
    if findings:
        return 1
    print("CI metadata privacy scan OK.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
