#!/usr/bin/env python3
"""Reject commit messages containing sensitive-content admission patterns.

The hook accepts the commit-message file supplied by git. It reports only the
line and rule identifier; it never writes the commit-message content to output.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

if __package__:
    from .check_sensitive_content import Finding, text_findings
else:  # pragma: no cover - exercised by git invoking this file directly.
    from check_sensitive_content import Finding, text_findings


def scan_commit_message(path: Path) -> list[Finding]:
    """Scan a UTF-8 git commit-message file without allowing exemptions."""
    try:
        message = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ValueError(f"cannot read commit-message file: {exc}") from exc
    return text_findings("COMMIT_MESSAGE", message)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("commit_message", type=Path, help="file created by git for the commit message")
    args = parser.parse_args(argv)
    try:
        findings = scan_commit_message(args.commit_message)
    except ValueError as exc:
        print(f"check_commit_message: failed ({type(exc).__name__})", file=sys.stderr)
        return 2
    for finding in findings:
        print(finding.render(), file=sys.stderr)
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
