#!/usr/bin/env python3
"""Advisory checks for repository agent guidance.

This script warns about guidance drift without blocking normal commits. Use
``--strict`` for release or doc-gardening runs that should fail on warnings.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

TODO_SOFT_LINE_LIMIT = 200
TODO_COMPLETED_SOFT_LIMIT = 10

AGENT_POINTER_FILES = (
    "CLAUDE.md",
    "GEMINI.md",
    "QWEN.md",
    ".github/copilot-instructions.md",
)

UNDOCUMENTED_AGENT_FILES = (
    "KIMI.md",
    "GPT.md",
    "CURSOR.md",
    "DEEPSEEK.md",
)

CHECKED_ITEM_RE = re.compile(r"^\s*-\s*\[[xX]\]\s+")
CHECKLIST_ITEM_RE = re.compile(r"^\s*-\s*\[[ xX]\]\s+")


@dataclass(frozen=True)
class AgentGuidanceWarning:
    path: Path
    message: str


def repo_root_from_script() -> Path:
    return Path(__file__).resolve().parent.parent


def _read_lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines()


def _relative(path: Path, repo_root: Path) -> Path:
    return path.relative_to(repo_root)


def warn_for_pointer_files(repo_root: Path) -> list[AgentGuidanceWarning]:
    warnings: list[AgentGuidanceWarning] = []
    for relative in AGENT_POINTER_FILES:
        path = repo_root / relative
        if not path.is_file():
            continue

        text = path.read_text(encoding="utf-8")
        if "AGENTS.md" not in text:
            warnings.append(
                AgentGuidanceWarning(
                    path=Path(relative),
                    message="agent-specific guidance file does not mention AGENTS.md",
                )
            )
        if len(text.splitlines()) > 60 and "dev-docs/AGENT_PLAYBOOK.md" not in text:
            warnings.append(
                AgentGuidanceWarning(
                    path=Path(relative),
                    message="agent-specific guidance is long; prefer a short pointer to dev-docs/AGENT_PLAYBOOK.md",
                )
            )

    for relative in UNDOCUMENTED_AGENT_FILES:
        path = repo_root / relative
        if path.is_file():
            warnings.append(
                AgentGuidanceWarning(
                    path=Path(relative),
                    message="undocumented agent guidance filename; verify the tool loads this file before committing it",
                )
            )

    return warnings


def warn_for_todo(repo_root: Path) -> list[AgentGuidanceWarning]:
    todo = repo_root / "dev-docs" / "TO_DO.md"
    if not todo.is_file():
        return []

    lines = _read_lines(todo)
    warnings: list[AgentGuidanceWarning] = []
    relative = _relative(todo, repo_root)

    if len(lines) > TODO_SOFT_LINE_LIMIT:
        warnings.append(
            AgentGuidanceWarning(
                path=relative,
                message=f"TO_DO.md is {len(lines)} lines; keep it near {TODO_SOFT_LINE_LIMIT} lines by moving history to archived plans or CHANGELOG.md",
            )
        )

    completed_items = sum(1 for line in lines if CHECKED_ITEM_RE.match(line))
    if completed_items > TODO_COMPLETED_SOFT_LIMIT:
        warnings.append(
            AgentGuidanceWarning(
                path=relative,
                message=f"TO_DO.md has {completed_items} completed checklist items; keep only recent completions",
            )
        )

    return warnings


def warn_for_completed_active_plans(repo_root: Path) -> list[AgentGuidanceWarning]:
    plans_dir = repo_root / "dev-docs" / "plans"
    if not plans_dir.is_dir():
        return []

    warnings: list[AgentGuidanceWarning] = []
    for path in sorted(plans_dir.glob("*.md")):
        if path.name.endswith("_PLAN.md"):
            continue

        lines = _read_lines(path)
        checklist_lines = [line for line in lines if CHECKLIST_ITEM_RE.match(line)]
        if not checklist_lines:
            continue
        checked_lines = [line for line in checklist_lines if CHECKED_ITEM_RE.match(line)]
        if len(checked_lines) != len(checklist_lines):
            continue

        warnings.append(
            AgentGuidanceWarning(
                path=_relative(path, repo_root),
                message="active execution plan appears complete; archive under dev-docs/plans/archive/ if done or superseded",
            )
        )

    return warnings


def collect_agent_guidance_warnings(repo_root: Path) -> list[AgentGuidanceWarning]:
    root = repo_root.resolve()
    warnings: list[AgentGuidanceWarning] = []
    warnings.extend(warn_for_pointer_files(root))
    warnings.extend(warn_for_todo(root))
    warnings.extend(warn_for_completed_active_plans(root))
    return warnings


def format_warning(warning: AgentGuidanceWarning) -> str:
    return f"warning {warning.path}: {warning.message}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Warn about stale or duplicated agent guidance.")
    parser.add_argument("--repo-root", type=Path, default=repo_root_from_script())
    parser.add_argument("--strict", action="store_true", help="Exit 1 when warnings are found.")
    args = parser.parse_args(argv)

    warnings = collect_agent_guidance_warnings(args.repo_root)
    for warning in warnings:
        print(format_warning(warning), file=sys.stderr)

    if warnings:
        print(
            f"Agent guidance check found {len(warnings)} warning(s). This is advisory unless --strict is used.",
            file=sys.stderr,
        )
        return 1 if args.strict else 0

    print("Agent guidance OK.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
