#!/usr/bin/env python3
"""
Enforce CHANGELOG.md updates when src/ or tests/ files change.

In CI (pull_request):  compares PR head against origin/$GITHUB_BASE_REF.
Local (pre-push):      compares HEAD against the merge-base with origin/main.

Exit 0 (pass) when:
  - No src/ or tests/ files changed.
  - CHANGELOG.md is among the changed files.
  - The only non-test changes are to comments or blank lines, and MAINTENANCE_LOG.md is updated.
  - Base ref cannot be determined (fail-open to avoid blocking offline work).
Exit 1 (fail) when src/ or tests/ files changed but CHANGELOG.md was not updated.
"""

from __future__ import annotations

import io
import os
import subprocess
import sys
import tokenize


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], capture_output=True, text=True)


def changed_files(base: str) -> list[str]:
    """Files changed between base and HEAD using a three-dot merge-base diff."""
    result = _git("diff", "--name-only", f"{base}...HEAD")
    if result.returncode != 0:
        return []
    return [f for f in result.stdout.splitlines() if f]


def _file_at(ref: str, path: str) -> str | None:
    """Contents of ``path`` at ``ref``, or None when it is absent or unreadable.

    The decode happens inside ``subprocess.run(text=True)``, so a file with non-UTF-8 bytes
    raises before the lexer is reached and outside its ``try``. Caught here so the result is
    a refusal like every other unreadable case, rather than a traceback from the hook.
    """
    try:
        result = _git("show", f"{ref}:{path}")
    except (UnicodeDecodeError, OSError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout


def _code_tokens(source: str) -> list[tuple[int, str]] | None:
    """Token stream with comments and non-logical newlines removed, or None if unlexable.

    Returning None on a lexical failure is deliberate: an unparseable file must not be
    exempted just because the comparison could not be made.
    """
    kept: list[tuple[int, str]] = []
    try:
        for token in tokenize.generate_tokens(io.StringIO(source).readline):
            if token.type in (tokenize.COMMENT, tokenize.NL):
                continue
            kept.append((token.type, token.string))
    # TokenError derives from Exception, not SyntaxError, so it must be named; IndentationError
    # does derive from SyntaxError and would be redundant here. The source is already `str` by
    # this point, so nothing in this arm concerns decoding — that is handled in _file_at.
    #
    # RecursionError and MemoryError are deliberately not caught. generate_tokens over a str is
    # iterative regex matching with no parse tree, so neither is reachable in practice; and if
    # one ever were, propagating exits the hook non-zero and blocks the push with a traceback,
    # which is fail-closed and self-announcing rather than a silent exemption.
    except (tokenize.TokenError, SyntaxError, ValueError):
        return None
    return kept


def is_comment_only(base: str, path: str) -> bool:
    """Whether a Python file changed in comments and blank lines only.

    Decided by lexing the whole file before and after and comparing the token streams with
    comments and blank-line newlines dropped. Equal streams mean nothing but commentary
    moved, which is exactly what the exemption is for.

    Two line-based versions preceded this one and both were wrong in ways their tests did
    not reach. The first allowed any added line lacking a statement-like marker, so a bare
    ``return None`` slipped through. The second held added and removed lines to the same
    rule but still parsed the diff by prefix, so a genuine ``++i`` arrived as ``+++i``, got
    mistaken for a file header, and a real statement went unseen beside an added comment.
    Comparing token streams removes the whole class: there is no line classification left to
    get wrong, a ``#`` inside a string literal is a STRING token rather than a comment, and
    a docstring edit changes the stream and is correctly refused.

    A new or deleted file is never comment-only, and neither is a file that will not lex. An
    unexpected failure is not silently exempted either: it propagates, the hook exits non-zero
    and the push is blocked.
    Only ``.py`` files qualify at all: a comment-only edit to JSON or Markdown under ``src/``
    still demands a changelog entry, as it did before this exemption existed.

    Comment directives that tools act on — ``# type: ignore``, ``# noqa``, ``# pragma``,
    encoding cookies — are COMMENT tokens and so are exempt. That is deliberate: they change
    linter, type-checker and coverage outcomes rather than what the program computes, and the
    exemption still requires a MAINTENANCE_LOG entry, so the change is recorded either way.

    If this classifier is ever wrong again, delete the exemption rather than writing a fourth
    one; a single changelog line costs less than a classifier debugged four times.
    """
    if not path.endswith(".py"):
        return False
    before = _file_at(base, path)
    after = _file_at("HEAD", path)
    if before is None or after is None or before == after:
        return False
    before_tokens = _code_tokens(before)
    after_tokens = _code_tokens(after)
    if before_tokens is None or after_tokens is None:
        return False
    return before_tokens == after_tokens


def resolve_base() -> str | None:
    """Return a git ref to diff against, or None if undetermined."""
    base_ref = os.environ.get("GITHUB_BASE_REF")
    if base_ref:
        return f"origin/{base_ref}"

    r = _git("merge-base", "HEAD", "origin/main")
    if r.returncode == 0:
        sha = r.stdout.strip()
        if sha:
            return sha

    return None


def main() -> int:
    base = resolve_base()
    if base is None:
        print("check_changelog: base ref undetermined — skipping check.", file=sys.stderr)
        return 0

    changed = changed_files(base)
    if not changed:
        return 0

    substantive = [f for f in changed if f.startswith(("src/", "tests/"))]
    if not substantive:
        return 0

    # Process-only exemption: when the only src/tests changes are test files
    # and the PR also touches MAINTENANCE_LOG.md (the maintainer-facing log),
    # the entry belongs there, not in the user-facing CHANGELOG. Backlog
    # cleanups (TO_DO item removals with test pinning) are the recurring case.
    non_test = [f for f in substantive if not f.startswith("tests/")]
    if not non_test and "dev-docs/MAINTENANCE_LOG.md" in changed:
        return 0

    # Same exemption, extended to src changes that touch only comments and blank lines.
    # CHANGELOG.md documents its own scope as notable *user-facing* changes and points
    # maintainer-facing work at MAINTENANCE_LOG.md, so a comment has no honest entry in it;
    # demanding one there trains readers to skim the file. Any behavioural change still
    # requires CHANGELOG.md, because is_comment_only() compares the file's whole token stream
    # before and after: anything that moves a real token, including commenting code out,
    # fails — as does a file that cannot be lexed.
    if "dev-docs/MAINTENANCE_LOG.md" in changed and all(is_comment_only(base, f) for f in non_test):
        return 0

    if "CHANGELOG.md" in changed:
        return 0

    print("check_changelog: CHANGELOG.md not updated.", file=sys.stderr)
    print(
        f"  {len(substantive)} source/test file(s) changed but CHANGELOG.md was not.",
        file=sys.stderr,
    )
    print("  Add a changelog entry before pushing.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
