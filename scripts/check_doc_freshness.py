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
BACKTICK_SPAN_RE = re.compile(r"`([^`\n]+)`")
PROSE_PATH_RE = re.compile(
    r"(?<![A-Za-z0-9_./-])"
    r"(?P<path>"
    r"(?:AGENTS|CHANGELOG|DESIGN|README)\.md"
    r"|(?:dev-docs|docs/source|src|tests|scripts)/[A-Za-z0-9_./#-]+"
    r")"
)
PATH_TRAILING_CHARS = ".,;:)"
AGENTS_FILENAME = "AGENTS.md"
README_FILENAME = "README.md"
CHANGELOG_FILENAME = "CHANGELOG.md"
DESIGN_FILENAME = "DESIGN.md"
ROOT_DOC_FILENAMES = frozenset({AGENTS_FILENAME, README_FILENAME, CHANGELOG_FILENAME, DESIGN_FILENAME})
PATH_REFERENCE_EXTENSIONS = (
    ".bat",
    ".cfg",
    ".css",
    ".csv",
    ".dcm",
    ".html",
    ".ini",
    ".ipynb",
    ".json",
    ".md",
    ".py",
    ".sh",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
)
PATH_REFERENCE_PREFIXES = (
    "dev-docs/",
    "docs/source/",
    "src/",
    "tests/",
    "scripts/",
)
ABSOLUTE_DOC_PATH_RES = (
    re.compile(r"file:///[^\s)>`]+"),
    re.compile(r"(?<![A-Za-z0-9_])(?:/Users|/home|/private|/tmp|/var|/path/to)/[^\s)>`]+"),
    re.compile(r"(?<![A-Za-z0-9_])[A-Za-z]:\\[^\s)>`]+"),
)

STALE_PATTERN_RE = re.compile(
    r"\b(not implemented|not wired|planned)\b",
    re.IGNORECASE,
)

INVENTORY_NOT_IMPLEMENTED_RE = re.compile(  # NOSONAR: S8786 false positive — capture bounded by literal |.
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


@dataclass(frozen=True)
class PathReference:
    source: Path
    line_number: int
    target: str
    context: str
    message: str


def repo_root_from_script() -> Path:
    return Path(__file__).resolve().parent.parent


def collect_markdown_files(repo_root: Path) -> list[Path]:
    """Return markdown files under the harness doc scan roots."""
    candidates: list[Path] = [
        repo_root / AGENTS_FILENAME,
        repo_root / "CLAUDE.md",
        repo_root / "GEMINI.md",
        repo_root / "QWEN.md",
        repo_root / README_FILENAME,
        repo_root / CHANGELOG_FILENAME,
        repo_root / DESIGN_FILENAME,
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
    # Match by scheme prefix without embedding a clear-text "http://" literal (Sonar S5332).
    return any(lowered.startswith(f"{scheme}:") for scheme in ("http", "https", "mailto", "file"))


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
        for line_number, line in enumerate(md_file.read_text(encoding="utf-8").splitlines(), start=1):
            broken.extend(_broken_links_in_line(md_file, rel_source, line_number, line, repo_root))
    return broken


def _broken_links_in_line(
    source_file: Path,
    relative_source: Path,
    line_number: int,
    line: str,
    repo_root: Path,
) -> list[BrokenLink]:
    """Return missing local Markdown targets from one line in stable source order."""
    broken: list[BrokenLink] = []
    for match in MARKDOWN_LINK_RE.finditer(line):
        raw_target = match.group(1).strip()
        if not raw_target or is_external_link(raw_target):
            continue
        path_part, _anchor = split_link_target(raw_target)
        if not path_part:
            continue
        resolved = resolve_relative_link(source_file, path_part, repo_root)
        if not link_target_exists(resolved):
            broken.append(
                BrokenLink(
                    source=relative_source,
                    line_number=line_number,
                    target=raw_target,
                    message=f"broken link [{raw_target}] -> {resolved}",
                )
            )
    return broken


def markdown_link_spans(line: str) -> list[tuple[int, int]]:
    return [match.span() for match in MARKDOWN_LINK_RE.finditer(line)]


def span_overlaps(span: tuple[int, int], blocked_spans: list[tuple[int, int]]) -> bool:
    start, end = span
    return any(start < blocked_end and end > blocked_start for blocked_start, blocked_end in blocked_spans)


def clean_path_reference(raw: str) -> str:
    target = raw.strip().strip(PATH_TRAILING_CHARS)
    return re.sub(r":\d+$", "", target)


def looks_like_repo_path(raw: str) -> bool:
    target = clean_path_reference(raw)
    if (
        not target
        or "://" in target
        or any(char.isspace() for char in target)
        or any(char in target for char in "*{}<>")
        or target.startswith(("/", "#", "~"))
    ):
        return False
    if target in ROOT_DOC_FILENAMES:
        return True
    if target.startswith(PATH_REFERENCE_PREFIXES):
        return True
    return False


def resolve_path_reference(source_file: Path, path_part: str, repo_root: Path) -> Path:
    if path_part in ROOT_DOC_FILENAMES:
        return (repo_root / path_part).resolve()
    if path_part.startswith(PATH_REFERENCE_PREFIXES):
        return (repo_root / path_part).resolve()
    return resolve_relative_link(source_file, path_part, repo_root)


def extract_path_references(line: str) -> list[tuple[str, str, tuple[int, int]]]:
    blocked_spans = markdown_link_spans(line)
    references: list[tuple[str, str, tuple[int, int]]] = []
    seen_spans: set[tuple[int, int]] = set()

    for match in BACKTICK_SPAN_RE.finditer(line):
        if span_overlaps(match.span(), blocked_spans):
            continue
        target = clean_path_reference(match.group(1))
        if looks_like_repo_path(target):
            references.append((target, "backtick", match.span()))
            seen_spans.add(match.span())

    for match in PROSE_PATH_RE.finditer(line):
        if span_overlaps(match.span(), blocked_spans) or span_overlaps(match.span(), list(seen_spans)):
            continue
        if match.end() < len(line) and line[match.end()] in "*{}<>":
            continue
        target = clean_path_reference(match.group("path"))
        if looks_like_repo_path(target):
            references.append((target, "prose", match.span()))

    return references


def skip_path_reference_scan(rel_source: Path) -> bool:
    return rel_source == Path(CHANGELOG_FILENAME) or "plans" in rel_source.parts


def archive_candidate_for_path(target: str, repo_root: Path) -> str | None:
    path_part, _anchor = split_link_target(target)
    prefix = "dev-docs/plans/"
    archive_prefix = "dev-docs/plans/archive/"
    if not path_part.startswith(prefix) or path_part.startswith(archive_prefix):
        return None
    candidate = f"{archive_prefix}{path_part.removeprefix(prefix)}"
    if (repo_root / candidate).exists():
        return candidate
    return None


def _iter_non_fenced_lines(md_file: Path):
    """Yield ``(line_number, line)`` for ``md_file``, skipping fenced code blocks."""
    in_fenced_block = False
    for line_number, line in enumerate(md_file.read_text(encoding="utf-8").splitlines(), start=1):
        if line.lstrip().startswith("```"):
            in_fenced_block = not in_fenced_block
            continue
        if in_fenced_block:
            continue
        yield line_number, line


def _build_path_reference_hit(
    raw_target: str,
    context: str,
    md_file: Path,
    rel_source: Path,
    line_number: int,
    repo_root: Path,
) -> PathReference | None:
    """Resolve a single path reference; return a ``PathReference`` hit if it is broken."""
    if is_external_link(raw_target):
        return None
    path_part, _anchor = split_link_target(raw_target)
    if not path_part:
        return None
    resolved = resolve_path_reference(md_file, path_part, repo_root)
    if resolved.exists():
        return None
    archive_candidate = archive_candidate_for_path(raw_target, repo_root)
    message = f"stale path `{raw_target}`"
    if archive_candidate:
        message += f"; archived candidate: {archive_candidate}"
    else:
        message += f" -> {resolved}"
    return PathReference(
        source=rel_source,
        line_number=line_number,
        target=raw_target,
        context=context,
        message=message,
    )


def find_broken_path_references(markdown_files: list[Path], repo_root: Path) -> list[PathReference]:
    broken: list[PathReference] = []
    for md_file in markdown_files:
        rel_source = md_file.relative_to(repo_root)
        if skip_path_reference_scan(rel_source):
            continue
        for line_number, line in _iter_non_fenced_lines(md_file):
            for raw_target, context, _span in extract_path_references(line):
                hit = _build_path_reference_hit(
                    raw_target, context, md_file, rel_source, line_number, repo_root
                )
                if hit is not None:
                    broken.append(hit)
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


INVENTORY_CHECK_SOURCES = (AGENTS_FILENAME, CHANGELOG_FILENAME)


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


def format_path_reference(item: PathReference) -> str:
    return f"{item.source}:{item.line_number}: {item.message}"


def run_checks(
    repo_root: Path,
    *,
    report_stale_patterns: bool = True,
    scan_path_references: bool = True,
) -> tuple[
    list[BrokenLink],
    list[PathReference],
    list[AbsolutePathHit],
    list[StaleHit],
    list[InventoryContradiction],
]:
    markdown_files = collect_markdown_files(repo_root)
    broken = find_broken_links(markdown_files, repo_root)
    path_references: list[PathReference] = []
    if scan_path_references:
        path_references = find_broken_path_references(markdown_files, repo_root)
    absolute = find_absolute_path_hits(markdown_files, repo_root)
    stale: list[StaleHit] = []
    if report_stale_patterns:
        stale = find_stale_pattern_hits(markdown_files, repo_root)
    contradictions = find_inventory_contradictions(repo_root)
    return broken, path_references, absolute, stale, contradictions


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
    parser.add_argument(
        "--no-path-reference-scan",
        action="store_true",
        help="Skip stale path scan for backtick/prose path references",
    )
    args = parser.parse_args(argv)

    repo_root = args.repo_root.resolve()
    broken, path_references, absolute, stale, contradictions = run_checks(
        repo_root,
        report_stale_patterns=not args.no_stale_warnings,
        scan_path_references=not args.no_path_reference_scan,
    )
    has_errors = _report_blocking_findings(broken, path_references, absolute, contradictions)
    _report_stale_findings(stale)
    if not has_errors:
        scanned = len(collect_markdown_files(repo_root))
        print(f"Doc freshness OK ({scanned} markdown files scanned).")
    return int(has_errors)


def _report_blocking_findings(
    broken: list[BrokenLink],
    path_references: list[PathReference],
    absolute: list[AbsolutePathHit],
    contradictions: list[InventoryContradiction],
) -> bool:
    """Render all blocking finding groups and report whether any were present."""
    groups = (
        ("Broken relative links:", [format_broken_link(item) for item in broken]),
        ("Broken path references:", [format_path_reference(item) for item in path_references]),
        ("Forbidden absolute filesystem paths in docs:", [format_absolute_path_hit(item) for item in absolute]),
        ("FEATURE_INVENTORY contradictions:", [format_inventory_contradiction(item) for item in contradictions]),
    )
    has_errors = False
    for heading, messages in groups:
        if messages:
            print(heading, file=sys.stderr)
            for message in messages:
                print(message, file=sys.stderr)
            has_errors = True
    return has_errors


def _report_stale_findings(stale: list[StaleHit]) -> None:
    """Render advisory stale-pattern findings without changing the exit status."""
    if not stale:
        return
    print("Advisory stale-pattern hits (does not fail CI):", file=sys.stderr)
    for item in stale:
        print(format_stale_hit(item), file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
