#!/usr/bin/env python3
"""Reject commit messages containing sensitive-content admission patterns.

The hook accepts the commit-message file supplied by git. It reports only the
line and rule identifier; it never writes the commit-message content to output.
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path

if __package__:
    from .check_sensitive_content import Finding, text_findings
else:  # pragma: no cover - exercised by git invoking this file directly.
    from check_sensitive_content import Finding, text_findings


def resolve_commit_message_path(
    path: Path,
    *,
    allowed_roots: Sequence[Path] | None = None,
) -> Path:
    """Resolve and confine a git commit-message path before reading it.

    Git normally passes `.git/COMMIT_EDITMSG` (or an equivalent under `GIT_DIR`).
    Reject path escapes so faulty/automation-supplied CLI arguments cannot read
    arbitrary filesystem locations through this hook. Tests may pass an explicit
    `allowed_roots` override; the default also permits the process temp directory
    used by pytest's `tmp_path`.
    """
    resolved = path.expanduser().resolve()
    roots = (
        [root.resolve() for root in allowed_roots]
        if allowed_roots is not None
        else [
            Path.cwd().resolve(),
            (Path.cwd() / ".git").resolve(),
            Path(tempfile.gettempdir()).resolve(),
        ]
    )
    if not any(resolved == root or resolved.is_relative_to(root) for root in roots):
        raise ValueError("commit-message path escapes repository")
    if not resolved.is_file():
        raise ValueError("commit-message path is not a file")
    return resolved


def scan_commit_message(path: Path, *, allowed_roots: Sequence[Path] | None = None) -> list[Finding]:
    """Scan a UTF-8 git commit-message file without allowing exemptions."""
    confined = resolve_commit_message_path(path, allowed_roots=allowed_roots)
    try:
        message = confined.read_text(encoding="utf-8")
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
