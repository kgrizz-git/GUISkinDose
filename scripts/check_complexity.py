#!/usr/bin/env python3
"""Enforce per-function Ruff C901 complexity caps with a ratcheting caps file.

Metric: Ruff ``C901`` (McCabe cyclomatic complexity), threshold 10. New functions
at 11 or above fail. Grandfathered caps may only decrease or disappear.

Caps live in ``dev-docs/complexity_caps.json``; see the plan at
``dev-docs/plans/COMPLEXITY_GATES_PLAN.md``. ``--check`` (default) validates the
working tree against the caps file, ``--bootstrap`` creates the initial reviewed
baseline, ``--update`` lowers or removes caps, and ``--migrate`` records
reviewed renames. Heavy lifting lives in ``scripts/complexity_caps_helpers.py``.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.complexity_caps_helpers import (
    CAPS_PATH,
    THRESHOLD,
    Finding,
    _write_caps_atomic,
    canonical_document,
    canonicalize,
    check_cap_history,
    collect_findings,
    compare_caps_history,
    measurement_errors,
    migrate,
    over_limit,
    parse_findings,
    qualified_names_by_row,
    ruff_version,
    synthesize_findings,
    update,
    validate_caps_document,
    validate_caps_file,
)

__all__ = [
    "CAPS_PATH",
    "THRESHOLD",
    "Finding",
    "bootstrap",
    "canonical_document",
    "canonicalize",
    "check",
    "check_cap_history",
    "collect_findings",
    "compare_caps_history",
    "main",
    "measurement_errors",
    "migrate",
    "over_limit",
    "parse_findings",
    "qualified_names_by_row",
    "ruff_version",
    "synthesize_findings",
    "update",
    "validate_caps_document",
    "validate_caps_file",
]


def repo_root() -> Path:
    """Repository root inferred from this script's location."""
    return Path(__file__).resolve().parent.parent


def _ref_has_caps_file(ref: str, root: Path) -> bool | None:
    """True/False whether ``ref`` has the caps file; None when the ref is unavailable."""
    verify = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", ref],
        capture_output=True,
        text=True,
        cwd=str(root),
    )
    if verify.returncode != 0:
        return None
    result = subprocess.run(
        ["git", "ls-tree", ref, "--", CAPS_PATH.as_posix()],
        capture_output=True,
        text=True,
        cwd=str(root),
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip() != ""


def bootstrap_blocked(root: Path) -> list[str]:
    """Reasons bootstrap may not run; empty means it may proceed."""
    errors: list[str] = []
    if (root / CAPS_PATH).exists():
        errors.append("caps file already exists in the working tree")
    head = _ref_has_caps_file("HEAD", root)
    if head is True:
        errors.append("caps file already present at HEAD")
    elif head is None:
        errors.append("git HEAD unavailable; cannot verify bootstrap precondition")
    base = _ref_has_caps_file("origin/main", root)
    if base is True:
        errors.append("caps file already present at origin/main")
    elif base is None:
        errors.append("origin/main ref unavailable; cannot prove the branch base has no caps file")
    return errors


def bootstrap(root: Path) -> list[str]:
    """Write the initial canonical caps file; refuse to overwrite or re-run."""
    blocked = bootstrap_blocked(root)
    if blocked:
        return blocked
    try:
        findings = collect_findings(root)
        version = ruff_version(root)
    except (ValueError, RuntimeError) as exc:
        return [f"could not collect complexity data: {exc}"]
    over = over_limit(findings)
    document = canonical_document(version, over)
    caps_path = root / CAPS_PATH
    try:
        caps_path.parent.mkdir(parents=True, exist_ok=True)
        _write_caps_atomic(caps_path, canonicalize(document))
    except OSError as exc:
        return [f"cannot write caps file: {exc}"]
    print(f"bootstrap: wrote {CAPS_PATH} with {len(over)} caps at ruff {version}")
    return []


def check(root: Path) -> list[str]:
    """Return all gate errors for one working tree; empty list means pass."""
    try:
        findings = collect_findings(root)
        version = ruff_version(root)
    except (ValueError, RuntimeError) as exc:
        return [f"could not collect complexity data: {exc}"]
    over = over_limit(findings)
    caps_path = root / CAPS_PATH
    if not caps_path.is_file():
        return [f"caps file missing: {CAPS_PATH} (run scripts/check_complexity.py --bootstrap after review)"]
    document, errors = validate_caps_file(caps_path, version)
    if document is None:
        return errors
    errors.extend(measurement_errors(over, document))
    if errors:
        return errors
    try:
        wt_bytes = caps_path.read_bytes()
    except OSError as exc:
        return [f"cannot read caps file: {exc}"]
    return check_cap_history(root, document, wt_bytes)


def main(argv: list[str] | None = None) -> int:
    """Parse flags and dispatch the selected mode."""
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--check", action="store_true", help="validate the tree against caps (default)")
    parser.add_argument("--bootstrap", action="store_true", help="create the initial reviewed caps baseline")
    parser.add_argument("--update", action="store_true", help="lower/remove caps to current measured scores")
    parser.add_argument("--migrate", nargs=2, metavar=("OLD_PATH:OLD_FUNCTION", "NEW_PATH:NEW_FUNCTION"), help="rename a cap with a migration record")
    args = parser.parse_args(argv)
    modes = [args.check, args.bootstrap, args.update, args.migrate is not None]
    if sum(modes) > 1:
        parser.error("choose exactly one of --check/--bootstrap/--update/--migrate")
    root = repo_root()
    if args.bootstrap:
        errors = bootstrap(root)
    elif args.update:
        errors = update(root)
    elif args.migrate is not None:
        errors = migrate(root, args.migrate[0], args.migrate[1])
    else:
        errors = check(root)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print("SUCCESS: complexity gate passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
