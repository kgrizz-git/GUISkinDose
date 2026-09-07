#!/usr/bin/env python3
"""Reject stored execution state in the canonical getting-started notebook."""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CANONICAL_NOTEBOOK = REPO_ROOT / "docs" / "source" / "getting_started" / "getting_started.ipynb"


def notebook_cleanliness_issues(path: Path) -> list[str]:
    """Return stored-output or execution-count findings for a notebook path."""
    try:
        notebook = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return [f"could not read valid notebook JSON ({error})"]

    if not isinstance(notebook, dict):
        return ["invalid notebook JSON structure (not an object)"]

    cells = notebook.get("cells")
    if not isinstance(cells, list):
        return ["missing a list of cells"]

    issues: list[str] = []
    for index, cell in enumerate(cells):
        if not isinstance(cell, dict):
            issues.append(f"cell {index} is not an object")
            continue
        if cell.get("cell_type") != "code":
            continue
        if cell.get("execution_count") is not None:
            issues.append(f"code cell {index} has an execution count")
        outputs = cell.get("outputs")
        if not isinstance(outputs, list):
            issues.append(f"code cell {index} has malformed outputs")
        elif outputs:
            issues.append(f"code cell {index} has {len(outputs)} stored output(s)")
    return issues


def check_canonical_notebook(path: Path = CANONICAL_NOTEBOOK) -> bool:
    """Print a value-safe failure report and return whether the notebook is clean."""
    issues = notebook_cleanliness_issues(path)
    if not issues:
        print(f"Notebook cleanliness OK: {path.relative_to(REPO_ROOT)}")
        return True

    print("Canonical getting-started notebook must not store execution counts or outputs:", file=sys.stderr)
    for issue in issues:
        print(f"  - {issue}", file=sys.stderr)
    print("Run `python scripts/open_getting_started_notebook.py` for an ignored local copy.", file=sys.stderr)
    return False


def main() -> int:
    """Run the canonical getting-started notebook cleanliness guard."""
    return 0 if check_canonical_notebook() else 1


if __name__ == "__main__":
    raise SystemExit(main())
