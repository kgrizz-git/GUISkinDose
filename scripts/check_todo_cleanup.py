#!/usr/bin/env python3
"""Remind when open TO_DO items touch files changed on this branch.

A ``dev-docs/TO_DO.md`` item that names files changed between base and HEAD
may be complete: per the backlog lifecycle (see ``dev-docs/AGENT_PLAYBOOK.md``),
completed items must be removed in the same PR once the planned work lands —
not checked off in place, and not deferred to post-merge.

Advisory by default (exit 0): only a human (or reviewing agent) can judge
whether the work actually landed. Pass ``--strict`` to fail on matches.

Exit 0 (pass) when:
  - No open items reference changed files.
  - Base ref cannot be determined (fail-open to avoid blocking offline work).
Exit 1 (fail) only with ``--strict`` and at least one match.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TODO_PATH = REPO_ROOT / "dev-docs" / "TO_DO.md"

# File-ish tokens worth matching: backticked spans and bare repo paths.
_BACKTICKED_RE = re.compile(r"`([^`]+)`")
_BARE_PATH_RE = re.compile(r"(?:src|tests|dev-docs|scripts|docs)/[\w\-.]+(?:/[\w\-.]+)*")
_BARE_SHORT_RE = re.compile(r"\b[\w\-.]+/[\w\-.]+(?:/[\w\-.]+)*\.\w+\b")
_KNOWN_EXTENSIONS = (".py", ".md", ".toml", ".yaml", ".yml", ".json", ".sh", ".bat", ".txt", ".ipynb")


@dataclass(frozen=True)
class OpenItem:
    title: str
    text: str


def parse_open_items(text: str) -> list[OpenItem]:
    """Collect ``- [ ]`` items (with continuation lines) from TO_DO markdown."""
    items: list[OpenItem] = []
    current: list[str] = []

    def flush() -> None:
        if current:
            first = current[0]
            title = re.sub(r"^-\s*\[[ xX]\]\s*", "", first).strip()
            items.append(OpenItem(title=title[:100], text="\n".join(current)))
            current.clear()

    for line in text.splitlines():
        if re.match(r"^-\s*\[[ xX]\]\s+", line):
            flush()
            if line.lstrip().startswith("- [ ]"):
                current.append(line)
        elif re.match(r"^#{1,6}\s+", line):
            flush()
        elif current and (line.startswith((" ", "\t")) or not line.strip()):
            current.append(line)
        else:
            flush()
    flush()
    return items


def _clean_candidate(token: str) -> str | None:
    token = token.strip().rstrip(").,;:!?\"'")
    if not token or " " in token or "\n" in token:
        return None
    if "/" in token or token.endswith(_KNOWN_EXTENSIONS):
        return token
    return None


def extract_paths(item_text: str) -> set[str]:
    """File references inside one item: backticked spans plus bare repo paths."""
    found: set[str] = set()
    for match in _BACKTICKED_RE.findall(item_text):
        cleaned = _clean_candidate(match)
        if cleaned:
            found.add(cleaned)
    for match in _BARE_PATH_RE.findall(item_text):
        cleaned = _clean_candidate(match)
        if cleaned:
            found.add(cleaned)
    for match in _BARE_SHORT_RE.findall(item_text):
        cleaned = _clean_candidate(match)
        if cleaned:
            found.add(cleaned)
    return found


def match_items(items: list[OpenItem], changed: list[str]) -> list[tuple[OpenItem, set[str]]]:
    """Items whose referenced paths overlap the changed files (suffix match).

    Suffix matching lets items cite short forms (``gui/tabs/data.py``) while
    the diff carries repo-relative paths (``src/guiskindose/gui/tabs/data.py``).
    """
    hits: list[tuple[OpenItem, set[str]]] = []
    for item in items:
        matched = {
            ref
            for ref in extract_paths(item.text)
            for path in changed
            if path.endswith(ref) or ref.endswith(path)
        }
        if matched:
            hits.append((item, matched))
    return hits


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], capture_output=True, text=True, cwd=REPO_ROOT)


def resolve_base() -> str | None:
    """Return a git ref to diff against, or None if undetermined."""
    base_ref = os.environ.get("GITHUB_BASE_REF")
    if base_ref:
        return f"origin/{base_ref}"

    result = _git("merge-base", "HEAD", "origin/main")
    if result.returncode == 0:
        sha = result.stdout.strip()
        if sha:
            return sha
    return None


def changed_files(base: str) -> list[str]:
    """Files changed between base and HEAD using a three-dot merge-base diff."""
    result = _git("diff", "--name-only", f"{base}...HEAD")
    if result.returncode != 0:
        return []
    return [f for f in result.stdout.splitlines() if f]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strict", action="store_true", help="exit 1 on any match")
    args = parser.parse_args(argv)

    base = resolve_base()
    if base is None:
        print("check_todo_cleanup: base ref undetermined — skipping check.", file=sys.stderr)
        return 0

    if not TODO_PATH.is_file():
        return 0

    items = parse_open_items(TODO_PATH.read_text(encoding="utf-8"))
    hits = match_items(items, changed_files(base))
    if not hits:
        return 0

    print("check_todo_cleanup: open TO_DO.md items reference files changed on this branch.")
    print("If the planned work landed here, remove the item (impact logged first) — same PR, not post-merge.\n")
    for item, matched in hits:
        refs = ", ".join(sorted(matched))
        print(f"- {item.title}\n    touches: {refs}")
    return 1 if args.strict else 0


if __name__ == "__main__":
    sys.exit(main())
