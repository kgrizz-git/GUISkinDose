#!/usr/bin/env python3
"""Report public symbols under ``src/`` missing docstrings.

This check is advisory by default: it prints per-file inventories of undocumented
public modules, classes, functions, and methods, but exits 0 unless ``--strict``
is passed. It uses only the standard library (``ast``) and never imports the
package, so it stays fast and side-effect free.

Visibility rule: a name is public when it does not start with an underscore
(dunder and private names are skipped, including ``__init__``). Module-level
symbols nested under ``if``/``try``/``with``/``match`` guards (for example
``if TYPE_CHECKING:``) are included; definitions nested inside function bodies
are out of scope for the inventory. Files whose stem starts with a single
underscore (for example ``_helpers.py``) are omitted; package entry points such
as ``__init__.py`` and ``__main__.py`` are included. Files that fail to parse
are reported on stderr and skipped.
"""

from __future__ import annotations

import argparse
import ast
import sys
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class FileInventory:
    path: Path
    skipped: bool = False
    missing: list[str] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)


def qualified_name(stack: list[str]) -> str:
    return ".".join(stack)


def plural(count: int, singular: str, plural_form: str) -> str:
    return f"{count} {singular if count == 1 else plural_form}"


def is_public(name: str) -> bool:
    return not name.startswith("_")


def is_public_module(stem: str) -> bool:
    """Return whether a ``.py`` file stem should be included in the inventory."""
    return not stem.startswith("_") or stem.startswith("__")


def iter_module_scope(body: list[ast.stmt]) -> Iterator[ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef]:
    """Yield module-level classes/functions, descending into guard blocks."""
    for node in body:
        if isinstance(node, ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            yield node
        elif isinstance(node, ast.If):
            yield from iter_module_scope(node.body)
            yield from iter_module_scope(node.orelse)
        elif isinstance(node, ast.Try | ast.TryStar):
            yield from iter_module_scope(node.body)
            for handler in node.handlers:
                yield from iter_module_scope(handler.body)
            yield from iter_module_scope(node.orelse)
            yield from iter_module_scope(node.finalbody)
        elif isinstance(node, ast.With):
            yield from iter_module_scope(node.body)
        elif isinstance(node, ast.Match):
            for case in node.cases:
                yield from iter_module_scope(case.body)


def collect_missing(tree: ast.Module) -> tuple[list[str], dict[str, int]]:
    """Return ``(missing qualified names, totals per kind)`` for one module."""
    missing: list[str] = []
    totals = {"module": 1, "class": 0, "function": 0, "method": 0}

    if ast.get_docstring(tree) is None:
        missing.append("<module>")

    def visit_class(node: ast.ClassDef, stack: list[str]) -> None:
        totals["class"] += 1
        if ast.get_docstring(node) is None:
            missing.append(qualified_name(stack))
        for child in node.body:
            if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef):
                if not is_public(child.name):
                    continue
                totals["method"] += 1
                if ast.get_docstring(child) is None:
                    missing.append(qualified_name([*stack, child.name]))
            elif isinstance(child, ast.ClassDef) and is_public(child.name):
                visit_class(child, [*stack, child.name])

    for node in iter_module_scope(tree.body):
        if isinstance(node, ast.ClassDef) and is_public(node.name):
            visit_class(node, [node.name])
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and is_public(node.name):
            totals["function"] += 1
            if ast.get_docstring(node) is None:
                missing.append(node.name)

    return missing, totals


def iter_source_files(src_dir: Path) -> list[Path]:
    return sorted(p for p in src_dir.rglob("*.py") if p.is_file() and is_public_module(p.stem))


def inventory_file(path: Path) -> FileInventory:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, SyntaxError, ValueError) as exc:
        print(f"warning {path}: skipped ({exc.__class__.__name__})", file=sys.stderr)
        return FileInventory(path=path, skipped=True)
    missing, counts = collect_missing(tree)
    return FileInventory(path=path, missing=missing, counts=counts)


def repo_root_from_script() -> Path:
    return Path(__file__).resolve().parent.parent


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Report public symbols under src/ missing docstrings.")
    parser.add_argument("--repo-root", type=Path, default=repo_root_from_script())
    parser.add_argument("--src-dir", type=Path, default=Path("src") / "guiskindose")
    parser.add_argument("--strict", action="store_true", help="Exit 1 when any docstring is missing.")
    args = parser.parse_args(argv)

    repo_root = args.repo_root.resolve()
    src_dir = repo_root / args.src_dir if not args.src_dir.is_absolute() else args.src_dir
    src_dir = src_dir.resolve()
    if not src_dir.is_dir():
        parser.error(f"src dir not found: {src_dir}")

    files = iter_source_files(src_dir)
    inventories = [inventory_file(p) for p in files]

    with_gaps = [inv for inv in inventories if inv.missing]
    for inv in with_gaps:
        try:
            rel = inv.path.relative_to(repo_root).as_posix()
        except ValueError:
            rel = inv.path.as_posix()
        print(f"missing {rel}: {', '.join(inv.missing)}", file=sys.stderr)

    totals = {"module": 0, "class": 0, "function": 0, "method": 0}
    missing_total = 0
    skipped_total = 0
    for inv in inventories:
        for kind, count in inv.counts.items():
            totals[kind] += count
        missing_total += len(inv.missing)
        skipped_total += 1 if inv.skipped else 0

    summary = (
        f"Docstring inventory: {plural(len(files), 'file', 'files')}, "
        + ", ".join(
            plural(totals[kind], kind, form)
            for kind, form in (
                ("module", "modules"),
                ("class", "classes"),
                ("function", "functions"),
                ("method", "methods"),
            )
        )
        + f"; {plural(missing_total, 'missing docstring', 'missing docstrings')} "
        + f"in {plural(len(with_gaps), 'file', 'files')}"
        + (f"; {plural(skipped_total, 'file', 'files')} skipped." if skipped_total else ".")
    )
    print(summary)

    if with_gaps:
        print("This is advisory unless --strict is used.", file=sys.stderr)
        return 1 if args.strict else 0

    print("Docstring inventory OK.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
