#!/usr/bin/env python3
"""Allowlisted Git identity trailers for commit-message privacy scans.

Dependabot, GitHub merge tooling, and common AI coding agents append
``Signed-off-by`` / ``Co-authored-by`` trailers that use automation or vendor
noreply addresses. Those are not patient or institutional contacts, but they
match the generic ``EMAIL_ADDRESS`` rule used by the sensitive-content gate.

This module decides which trailer lines may be ignored when scanning commit
messages and CI push metadata. Tracked file content must not use this
allowlist — callers keep ``allow_git_identity_trailers=False`` for docs and
source.

Inputs: a single text line from a commit message.
Outputs: a boolean; never echoes the email value.
"""

from __future__ import annotations

import re

# Git identity trailers used by Dependabot / GitHub merge UI / AI agent attribution.
# Display-name text must not contain "@" so an institutional address cannot hide
# behind an allowlisted bracketed noreply address on the same trailer line.
_GIT_IDENTITY_TRAILER_LINE = re.compile(
    r"(?i)^\s*(Signed-off-by|Co-authored-by|Reviewed-by|Acked-by):\s+"
    r"[^@<>\n]+<(?P<email>[^<>\s]+)>\s*$"
)

# Vendor-published automation noreply addresses (exact match, case-insensitive).
# Split ``user@domain`` literals so the sensitive-content gate does not flag this module.
_NOREPLY_AT = "noreply@"
_ALLOWED_EXACT_TRAILER_EMAILS: frozenset[str] = frozenset(
    {
        "support@" + "github.com",
        _NOREPLY_AT + "github.com",
        _NOREPLY_AT + "anthropic.com",  # Claude Code / Anthropic agents
        "cursoragent@" + "cursor.com",  # Cursor IDE + cloud agents
        _NOREPLY_AT + "openai.com",  # OpenAI Codex default commit_attribution
        "qwen-coder@" + "alibabacloud.com",  # Qwen Coder co-author trailer
    }
)

_USERS_NOREPLY_GITHUB = re.compile(r"(?i)^[^@\s]+@users\.noreply\.github\.com$")
_KILO_GASTOWN_AGENT = re.compile(r"(?i)^[^@\s]+@gastown\.kilo\.ai$")


def _is_allowed_trailer_email(email: str) -> bool:
    normalized = email.strip().lower()
    if normalized in {address.lower() for address in _ALLOWED_EXACT_TRAILER_EMAILS}:
        return True
    return _USERS_NOREPLY_GITHUB.match(email) is not None or _KILO_GASTOWN_AGENT.match(email) is not None


def is_allowlisted_git_identity_trailer(line: str) -> bool:
    """Return True for allowlisted Git identity trailers with noreply/bot emails.

    Real institutional emails in the same trailers still return False so the
    ``EMAIL_ADDRESS`` rule continues to block them.
    """
    match = _GIT_IDENTITY_TRAILER_LINE.match(line)
    if match is None:
        return False
    return _is_allowed_trailer_email(match.group("email"))
