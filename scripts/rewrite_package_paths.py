#!/usr/bin/env python3
"""Rewrite approved-asset inventory ``path`` prefixes and scan for leftover brand strings.

Two related helpers for the GUISkinDose rename (PR 0 of the mechanical rename plan):

1. **Inventory rewrite** — a pure function plus small CLI that rewrites ``path`` strings
   starting with ``src/mypyskindose/`` to ``src/guiskindose/`` in the approved-asset
   inventory, leaving ``sha256``, ``kind``, ``purpose``, ``review``, ``dicom_review`` and
   any other metadata untouched. It recurses into nested objects/lists that happen to
   contain ``path`` keys. Semgrep rule IDs, ``# nosemgrep: mypyskindose-*`` comments,
   GitHub URLs, and any other non-path string are **not** touched (the rewrite is keyed
   on the JSON ``path`` member, not a blanket string substitution).

2. **Leftover scan** — report-only scan of ``src``, ``tests``, ``scripts``,
   ``pyproject.toml``, ``MANIFEST.in``, and ``.github`` for the tokens
   ``mypyskindose``, ``MyPySkinDose``, and ``MYPYSKINDOSE_``, minus an explicit allowlist.
   It always exits 0: this is a report, not a gate (another agent owns
   ``check_stale_brand.py``).

Inputs: the JSON inventory on disk (``--inventory``) and/or the scan roots.
Outputs: rewritten JSON (``--apply``) or a dry-run listing of planned changes;
         leftover hits printed to stdout.
"""

from __future__ import annotations

import argparse
import json
import re
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any

PACKAGE_OLD = "mypyskindose"
PACKAGE_NEW = "guiskindose"
BRAND_OLD = "MyPySkinDose"
ENV_OLD_PREFIX = "MYPYSKINDOSE_"
SRC_PREFIX_OLD = f"src/{PACKAGE_OLD}/"
SRC_PREFIX_NEW = f"src/{PACKAGE_NEW}/"

# Files skipped entirely by the leftover scan.
_SCAN_SKIP_FILENAMES = {"CHANGELOG.md"}

# Token patterns reported by the leftover scan.
_SCAN_TOKENS = (PACKAGE_OLD, BRAND_OLD, ENV_OLD_PREFIX)

# Allowlist entries matched against the *file path* (repo-relative string). Any file
# whose path contains one of these fragments is skipped entirely.
_ALLOWLIST_FILE_PATHS: tuple[str, ...] = (
    "dev-docs/plans/archive/",
    "dev-docs/assessments/",
    "dev-docs/plans/GUISKINDOSE_RENAME_PLAN.md",
    "dev-docs/plans/GUISKINDOSE_PRIVACY_REPUBLICATION_PLAN.md",
    "dev-docs/COORD_TRANSFORM_COMPARISON.md",
    "CHANGELOG.md",
    "GUISKINDOSE_MIGRATION_STATUS.md",
    "scripts/check_stale_brand.py",
    "tests/unittests/test_check_stale_brand.py",
    "scripts/rewrite_package_paths.py",
    "tests/unittests/test_rewrite_package_paths.py",
)

# Compiled line-content allowlist patterns. A line matching any of these is subtracted
# from the report even though it contains a brand token.
_ALLOWLIST_NOSEMGREP = re.compile(r"#\s*nosemgrep:\s*mypyskindose-[\w-]+\b")
_ALLOWLIST_SONAR = re.compile(r"\bmypyskindose\b(?=.*(?:projectKey|projectName|sonar))", re.IGNORECASE)
_ALLOWLIST_LINE_PATTERNS: tuple[re.Pattern[str], ...] = (
    _ALLOWLIST_NOSEMGREP,  # "# nosemgrep: mypyskindose-*"
    re.compile(r"\bid:\s*mypyskindose-[\w-]+\b"),  # YAML rule id:
    re.compile(r"github\.com/kgrizz-git/MyPySkinDose"),  # upstream GitHub URL
    _ALLOWLIST_SONAR,  # Sonar projectKey/projectName
)


def _is_file_allowlisted(repo_rel: str) -> bool:
    """Return True when *repo_rel* is an allowlisted file or under an allowlisted directory.

    Directory entries end with ``/`` and match as a prefix. File entries match
    exactly so a suffix such as ``CHANGELOG.md.bak`` is not exempt.
    """
    posix = repo_rel.replace("\\", "/")
    return any(
        posix.startswith(allowed) if allowed.endswith("/") else posix == allowed
        for allowed in _ALLOWLIST_FILE_PATHS
    )


def _is_line_allowlisted(line: str) -> bool:
    return any(pattern.search(line) is not None for pattern in _ALLOWLIST_LINE_PATTERNS)


def repo_root_from_script() -> Path:
    return Path(__file__).resolve().parent.parent


def rewrite_path_prefix(path: str) -> str:
    """Return *path* with the ``src/mypyskindose/`` prefix rewritten to ``src/guiskindose/``.

    Only the leading package path prefix is rewritten. Any other string (Semgrep rule
    IDs, URLs, logger names) is returned unchanged — callers key on the JSON ``path``
    member so non-path strings never reach this function.
    """
    if path.startswith(SRC_PREFIX_OLD):
        return SRC_PREFIX_NEW + path[len(SRC_PREFIX_OLD) :]
    return path


def rewrite_inventory_paths(data: Any) -> tuple[Any, list[tuple[str, str]]]:
    """Recursively rewrite ``path`` members in an inventory-like structure.

    Returns ``(rewritten, changes)`` where *changes* is a list of ``(old, new)`` path
    pairs actually rewritten. Nested dicts/lists are traversed; only keys literally
    named ``path`` with a string value are considered.
    """
    changes: list[tuple[str, str]] = []
    rewritten = _rewrite_inventory_recursive(data, changes)
    return rewritten, changes


def _rewrite_inventory_recursive(data: Any, changes: list[tuple[str, str]]) -> Any:
    if isinstance(data, dict):
        new_dict: dict[str, Any] = {}
        for key, value in data.items():
            if key == "path" and isinstance(value, str):
                new_value = rewrite_path_prefix(value)
                if new_value != value:
                    changes.append((value, new_value))
                new_dict[key] = new_value
            else:
                new_dict[key] = _rewrite_inventory_recursive(value, changes)
        return new_dict
    if isinstance(data, list):
        return [_rewrite_inventory_recursive(item, changes) for item in data]
    return data


def scan_leftover_brand(
    repo_root: Path,
    roots: Sequence[Path],
    tokens: tuple[str, ...] = _SCAN_TOKENS,
) -> list[tuple[Path, int, str]]:
    """Return ``(file, line_number, line_text)`` hits for brand tokens minus the allowlist.

    Files in ``_SCAN_SKIP_FILENAMES`` are skipped. Lines matching the allowlist are
    subtracted. The returned hits are sorted by file then line number.
    """
    hits: list[tuple[Path, int, str]] = []
    for root in roots:
        root_abs = repo_root / root
        if root_abs.is_file():
            files = [root_abs]
        elif root_abs.is_dir():
            files = [p for p in sorted(root_abs.rglob("*")) if p.is_file()]
        else:
            continue
        for path in files:
            if path.name in _SCAN_SKIP_FILENAMES:
                continue
            try:
                repo_rel = str(path.relative_to(repo_root))
            except ValueError:
                repo_rel = str(path)
            if _is_file_allowlisted(repo_rel):
                continue
            if not _is_text_file(path):
                continue
            try:
                with path.open("r", encoding="utf-8") as handle:
                    for number, raw_line in enumerate(handle, start=1):
                        line = raw_line.rstrip("\r\n")
                        lower = line.lower()
                        if not any(token.lower() in lower for token in tokens):
                            continue
                        if _is_line_allowlisted(line):
                            continue
                        hits.append((path, number, line))
            except (OSError, UnicodeDecodeError):
                continue
    hits.sort(key=lambda hit: (hit[0], hit[1]))
    return hits


def _is_text_file(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            sample = handle.read(4096)
    except OSError:
        return False
    if b"\x00" in sample:
        return False
    try:
        sample.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


def _load_inventory(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _dump_inventory(data: Any, path: Path) -> None:
    """Atomically write inventory JSON (indent 2, trailing newline)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            delete=False,
            suffix=".tmp",
        ) as tmp:
            tmp_path = Path(tmp.name)
            tmp.write(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
        tmp_path.replace(path)
    except Exception:
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)
        raise


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    rewrite = subparsers.add_parser(
        "rewrite",
        help="Rewrite src/mypyskindose/ path prefixes in the asset inventory.",
    )
    rewrite.add_argument(
        "--inventory",
        type=Path,
        default=None,
        help="Path to the inventory JSON (default: dev-docs/approved_asset_inventory.json).",
    )
    rewrite.add_argument(
        "--apply",
        action="store_true",
        default=False,
        help="Write the rewritten inventory back. Without this, runs dry-run.",
    )

    scan = subparsers.add_parser(
        "scan",
        help="Scan for leftover mypyskindose/MyPySkinDose/MYPYSKINDOSE_ hits (report only).",
    )
    scan.add_argument(
        "--roots",
        nargs="+",
        type=Path,
        default=None,
        help="Scan roots (default: src tests scripts pyproject.toml MANIFEST.in .github).",
    )

    args = parser.parse_args(argv)
    repo_root = repo_root_from_script()

    if args.command == "rewrite":
        inventory_path = args.inventory
        if inventory_path is None:
            inventory_path = repo_root / "dev-docs" / "approved_asset_inventory.json"
        inventory_path = inventory_path.resolve()
        data = _load_inventory(inventory_path)
        rewritten, changes = rewrite_inventory_paths(data)
        if not changes:
            print(f"No {SRC_PREFIX_OLD} paths to rewrite in {inventory_path}.")
            return 0
        if not args.apply:
            print(f"DRY RUN: {len(changes)} path(s) would be rewritten in {inventory_path}:")
            for old, new in changes:
                print(f"  {old} -> {new}")
            return 0
        _dump_inventory(rewritten, inventory_path)
        print(f"Rewrote {len(changes)} path(s) in {inventory_path}.")
        print("Re-run: python scripts/render_asset_inventory.py --write")
        print("Stage both the JSON and generated Markdown together.")
        return 0

    # scan
    roots = args.roots
    if roots is None:
        roots = [Path("src"), Path("tests"), Path("scripts"), Path("pyproject.toml"), Path("MANIFEST.in"), Path(".github")]
    hits = scan_leftover_brand(repo_root, roots)
    if not hits:
        print("No leftover brand hits found (after allowlist).")
        return 0
    print(f"Leftover brand hits: {len(hits)} (after allowlist):")
    try:
        for path, number, line in hits:
            rel = path.relative_to(repo_root) if path.is_absolute() else path
            print(f"  {rel}:{number}: {line}")
    except BrokenPipeError:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
