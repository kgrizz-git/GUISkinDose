#!/usr/bin/env python3
"""Documentation freshness checker for MyPySkinDose.

Purpose:
    Scan tracked markdown for broken relative links, forbidden absolute
    filesystem paths, advisory stale-language patterns, and checkable
    contradictions against FEATURE_INVENTORY.md (in AGENTS.md and
    CHANGELOG.md).

Inputs:
    Repository root (auto-detected as parent of ``scripts/``, or ``--repo-root``).

Outputs:
    Prints broken links / forbidden absolute paths as ``file:line: message``,
    warnings for stale patterns and inventory checks. Exit code 0 when clean;
    1 when broken links, forbidden absolute paths, or inventory contradictions
    are found (stale-pattern warnings never fail CI).

Usage:
    python scripts/check_doc_freshness.py
    python scripts/check_doc_freshness.py --repo-root /path/to/MyPySkinDose
    python scripts/check_doc_freshness.py --no-stale-warnings
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

MARKDOWN_LINK_RE = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
ABSOLUTE_DOC_PATH_RES = (
    re.compile(r"file:///[^\s)>`]+"),
    re.compile(r"(?<![A-Za-z0-9_])(?:/Users|/home|/private|/tmp|/var|/path/to)/[^\s)>`]+"),
    re.compile(r"(?<![A-Za-z0-9_])[A-Za-z]:\\[^\s)>`]+"),
)

STALE_PATTERN_RE = re.compile(
    r"\b(not implemented|not wired|planned)\b",
    re.IGNORECASE,
)

INVENTORY_NOT_IMPLEMENTED_RE = re.compile(
    r"\|\s*(?P<feature>[^|]+?)\s*\|\s*Planned,\s*not implemented\s*\|",
    re.IGNORECASE,
)

# Minimal guard: tabular input is not implemented per FEATURE_INVENTORY.md.
TABULAR_FEATURE_KEY = "csv/tsv/xlsx event-table input"
TABULAR_FALSE_CLAIM_RES = (
    re.compile(
        r"(?i)(tabular|event[- ]table).{0,60}\b(implemented|now available|fully supported)\b"
    ),
    re.compile(
        r"(?i)\b(csv|tsv|xlsx)\b.{0,40}\binput\b.{0,40}\b(implemented|works|available)\b"
    ),
)
TABULAR_EXCLUDE_RES = (
    re.compile(r"(?i)\b(plan|planned|not implemented|next input focus)\b"),
)


@dataclass(frozen=True)
class BrokenLink:
    source: Path
    line_number: int
    target: str
    message: str


@dataclass(frozen=True)
class AbsolutePathHit:
    source: Path
    line_number: int
    match_text: str
    line: str


@dataclass(frozen=True)
class StaleHit:
    source: Path
    line_number: int
    line: str


@dataclass(frozen=True)
class InventoryContradiction:
    source: Path
    line_number: int
    feature: str
    line: str


def repo_root_from_script() -> Path:
    return Path(__file__).resolve().parent.parent


def collect_markdown_files(repo_root: Path) -> list[Path]:
    """Return markdown files under the harness doc scan roots."""
    candidates: list[Path] = [
        repo_root / "AGENTS.md",
        repo_root / "CLAUDE.md",
        repo_root / "GEMINI.md",
        repo_root / "QWEN.md",
        repo_root / "README.md",
        repo_root / "CHANGELOG.md",
        repo_root / "DESIGN.md",
    ]
    dev_docs = repo_root / "dev-docs"
    if dev_docs.is_dir():
        candidates.extend(sorted(dev_docs.rglob("*.md")))
    gui_help = repo_root / "docs" / "source" / "gui_help"
    if gui_help.is_dir():
        candidates.extend(sorted(gui_help.rglob("*.md")))

    return [path for path in candidates if path.is_file()]


def is_external_link(target: str) -> bool:
    lowered = target.strip().lower()
    return lowered.startswith(("http://", "https://", "mailto:", "file://"))


def split_link_target(target: str) -> tuple[str, str | None]:
    """Split ``path#anchor`` into path and optional anchor."""
    stripped = target.strip()
    if stripped.startswith("#"):
        return "", stripped.lstrip("#") or None
    path_part, sep, anchor = stripped.partition("#")
    if not sep:
        return stripped, None
    return path_part, anchor or None


def resolve_relative_link(source_file: Path, path_part: str, repo_root: Path) -> Path:
    """Resolve a relative markdown link target to an absolute path."""
    if path_part.startswith("/"):
        return (repo_root / path_part.lstrip("/")).resolve()
    return (source_file.parent / path_part).resolve()


def link_target_exists(resolved: Path) -> bool:
    return resolved.exists()


def find_broken_links(markdown_files: list[Path], repo_root: Path) -> list[BrokenLink]:
    broken: list[BrokenLink] = []
    for md_file in markdown_files:
        rel_source = md_file.relative_to(repo_root)
        lines = md_file.read_text(encoding="utf-8").splitlines()
        for line_number, line in enumerate(lines, start=1):
            for match in MARKDOWN_LINK_RE.finditer(line):
                raw_target = match.group(1).strip()
                if not raw_target or is_external_link(raw_target):
                    continue

                path_part, _anchor = split_link_target(raw_target)
                if not path_part:
                    continue

                resolved = resolve_relative_link(md_file, path_part, repo_root)
                if link_target_exists(resolved):
                    continue

                broken.append(
                    BrokenLink(
                        source=rel_source,
                        line_number=line_number,
                        target=raw_target,
                        message=f"broken link [{raw_target}] -> {resolved}",
                    )
                )
    return broken


def find_absolute_path_hits(markdown_files: list[Path], repo_root: Path) -> list[AbsolutePathHit]:
    hits: list[AbsolutePathHit] = []
    for md_file in markdown_files:
        rel_source = md_file.relative_to(repo_root)
        for line_number, line in enumerate(md_file.read_text(encoding="utf-8").splitlines(), start=1):
            for pattern in ABSOLUTE_DOC_PATH_RES:
                match = pattern.search(line)
                if not match:
                    continue
                hits.append(
                    AbsolutePathHit(
                        source=rel_source,
                        line_number=line_number,
                        match_text=match.group(0),
                        line=line.rstrip(),
                    )
                )
                break
    return hits


def find_stale_pattern_hits(markdown_files: list[Path], repo_root: Path) -> list[StaleHit]:
    hits: list[StaleHit] = []
    for md_file in markdown_files:
        rel_source = md_file.relative_to(repo_root)
        for line_number, line in enumerate(md_file.read_text(encoding="utf-8").splitlines(), start=1):
            if STALE_PATTERN_RE.search(line):
                hits.append(
                    StaleHit(
                        source=rel_source,
                        line_number=line_number,
                        line=line.rstrip(),
                    )
                )
    return hits


def parse_not_implemented_features(feature_inventory: Path) -> list[str]:
    features: list[str] = []
    for line in feature_inventory.read_text(encoding="utf-8").splitlines():
        match = INVENTORY_NOT_IMPLEMENTED_RE.search(line)
        if match:
            features.append(match.group("feature").strip().lower())
    return features


def tabular_line_is_false_claim(line: str) -> bool:
    if any(pattern.search(line) for pattern in TABULAR_EXCLUDE_RES):
        return False
    return any(pattern.search(line) for pattern in TABULAR_FALSE_CLAIM_RES)


INVENTORY_CHECK_SOURCES = ("AGENTS.md", "CHANGELOG.md")


def find_inventory_contradictions(repo_root: Path) -> list[InventoryContradiction]:
    """Check AGENTS.md and CHANGELOG.md against FEATURE_INVENTORY 'Planned, not implemented' rows."""
    feature_inventory = repo_root / "dev-docs" / "FEATURE_INVENTORY.md"
    if not feature_inventory.is_file():
        return []

    not_implemented = parse_not_implemented_features(feature_inventory)
    if TABULAR_FEATURE_KEY not in not_implemented:
        return []

    contradictions: list[InventoryContradiction] = []
    for rel_source in INVENTORY_CHECK_SOURCES:
        source_path = repo_root / rel_source
        if not source_path.is_file():
            continue
        for line_number, line in enumerate(
            source_path.read_text(encoding="utf-8").splitlines(),
            start=1,
        ):
            if tabular_line_is_false_claim(line):
                contradictions.append(
                    InventoryContradiction(
                        source=Path(rel_source),
                        line_number=line_number,
                        feature=TABULAR_FEATURE_KEY,
                        line=line.rstrip(),
                    )
                )
    return contradictions


def format_broken_link(item: BrokenLink) -> str:
    return f"{item.source}:{item.line_number}: {item.message}"


def format_absolute_path_hit(item: AbsolutePathHit) -> str:
    return (
        f"{item.source}:{item.line_number}: forbidden absolute path {item.match_text!r} — "
        f"{item.line}"
    )


def format_stale_hit(item: StaleHit) -> str:
    return f"warning {item.source}:{item.line_number}: stale pattern — {item.line}"


def format_inventory_contradiction(item: InventoryContradiction) -> str:
    return (
        f"{item.source}:{item.line_number}: contradicts FEATURE_INVENTORY "
        f"({item.feature!r}) — {item.line}"
    )


def run_checks(
    repo_root: Path,
    *,
    report_stale_patterns: bool = True,
) -> tuple[list[BrokenLink], list[AbsolutePathHit], list[StaleHit], list[InventoryContradiction]]:
    markdown_files = collect_markdown_files(repo_root)
    broken = find_broken_links(markdown_files, repo_root)
    absolute = find_absolute_path_hits(markdown_files, repo_root)
    stale: list[StaleHit] = []
    if report_stale_patterns:
        stale = find_stale_pattern_hits(markdown_files, repo_root)
    contradictions = find_inventory_contradictions(repo_root)
    return broken, absolute, stale, contradictions


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate MyPySkinDose documentation freshness.")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=repo_root_from_script(),
        help="Repository root (default: parent of scripts/)",
    )
    parser.add_argument(
        "--no-stale-warnings",
        action="store_true",
        help="Skip advisory stale-pattern scan",
    )
    args = parser.parse_args(argv)

    repo_root = args.repo_root.resolve()
    broken, absolute, stale, contradictions = run_checks(
        repo_root,
        report_stale_patterns=not args.no_stale_warnings,
    )

    exit_code = 0

    if broken:
        print("Broken relative links:", file=sys.stderr)
        for item in broken:
            print(format_broken_link(item), file=sys.stderr)
        exit_code = 1

    if absolute:
        print("Forbidden absolute filesystem paths in docs:", file=sys.stderr)
        for item in absolute:
            print(format_absolute_path_hit(item), file=sys.stderr)
        exit_code = 1

    if contradictions:
        print("FEATURE_INVENTORY contradictions:", file=sys.stderr)
        for item in contradictions:
            print(format_inventory_contradiction(item), file=sys.stderr)
        exit_code = 1

    if stale:
        print("Advisory stale-pattern hits (does not fail CI):", file=sys.stderr)
        for item in stale:
            print(format_stale_hit(item), file=sys.stderr)

    if exit_code == 0:
        scanned = len(collect_markdown_files(repo_root))
        print(f"Doc freshness OK ({scanned} markdown files scanned).")

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
