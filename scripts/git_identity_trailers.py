#!/usr/bin/env python3
"""Allowlisted Git identity trailers for commit-message privacy scans.

Dependabot and GitHub merge tooling append ``Signed-off-by`` /
``Co-authored-by`` trailers that use GitHub automation or noreply addresses.
Those are not patient or institutional contacts, but they match the generic
``EMAIL_ADDRESS`` rule used by the sensitive-content gate.

This module decides which trailer lines may be ignored when scanning commit
messages and CI push metadata. Tracked file content must not use this
allowlist — callers keep ``allow_git_identity_trailers=False`` for docs and
source.

Inputs: a single text line from a commit message.
Outputs: a boolean; never echoes the email value.
"""

from __future__ import annotations

import re

# Git identity trailers used by Dependabot / GitHub merge UI / Cursor co-authors.
# Display-name text must not contain "@" so an institutional address cannot hide
# behind an allowlisted bracketed noreply address on the same trailer line.
_GIT_IDENTITY_TRAILER_LINE = re.compile(
    r"(?i)^\s*(Signed-off-by|Co-authored-by|Reviewed-by|Acked-by):\s+"
    r"[^@<>\n]+<(?P<email>[^<>\s]+)>\s*$"
)
_ALLOWED_GIT_TRAILER_EMAIL = re.compile(
    r"(?i)^(?:support@github\.com|noreply@github\.com|[^@\s]+@users\.noreply\.github\.com)$"
)


def is_allowlisted_git_identity_trailer(line: str) -> bool:
    """Return True for allowlisted Git identity trailers with noreply/bot emails.

    Real institutional emails in the same trailers still return False so the
    ``EMAIL_ADDRESS`` rule continues to block them.
    """
    match = _GIT_IDENTITY_TRAILER_LINE.match(line)
    if match is None:
        return False
    return _ALLOWED_GIT_TRAILER_EMAIL.match(match.group("email")) is not None
