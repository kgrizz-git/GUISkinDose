"""
Structural tests for MyPySkinDose package layer dependency rules (Harness Phase 4).

Scans import statements via AST (no import-linter dependency). Fails CI when
high-value layer boundaries are violated.

Inputs: Python sources under src/mypyskindose/
Outputs: pytest pass/fail with module:line messages on violation
"""

from __future__ import annotations

import ast
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[2] / "src" / "mypyskindose"

# Settings may only depend on shared utilities — not runtime/orchestration/presentation.
SETTINGS_FORBIDDEN_PREFIXES = (
    "mypyskindose.calculate_dose",
    "mypyskindose.plotting",
    "mypyskindose.gui",
    "mypyskindose.analyze_data",
    "mypyskindose.main",
    "mypyskindose.format_export_data",
    "mypyskindose.beam_class",
    "mypyskindose.phantom_class",
    "mypyskindose.geom_calc",
    "mypyskindose.corrections",
    "mypyskindose.db_connect",
    "mypyskindose.rdsr_parser",
    "mypyskindose.rdsr_normalizer",
)

CALCULATE_DOSE_FORBIDDEN_PREFIXES = (
    "mypyskindose.gui",
    "mypyskindose.plotting",
)

GUI_FORBIDDEN_PREFIXES = (
    "mypyskindose.calculate_dose",
)

# input_adapters is L2 — must not reach into domain, dose, GUI, or orchestration.
INPUT_ADAPTERS_FORBIDDEN_PREFIXES = (
    "mypyskindose.calculate_dose",
    "mypyskindose.plotting",
    "mypyskindose.gui",
    "mypyskindose.analyze_data",
    "mypyskindose.main",
    "mypyskindose.format_export_data",
    "mypyskindose.beam_class",
    "mypyskindose.phantom_class",
    "mypyskindose.geom_calc",
    "mypyskindose.corrections",
    "mypyskindose.db_connect",
)


def _python_files_under(relative_dir: str) -> list[Path]:
    root = PACKAGE_ROOT / relative_dir
    if not root.is_dir():
        return []
    return sorted(root.rglob("*.py"))


def _iter_imports(py_file: Path) -> list[tuple[int, str]]:
    """Return (line_number, module_name) for each import in the file."""
    source = py_file.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(py_file))
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.append((node.lineno, alias.name))
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.append((node.lineno, node.module))
    return found


def _matches_prefix(module: str, prefix: str) -> bool:
    return module == prefix or module.startswith(prefix + ".")


def _violations(py_files: list[Path], forbidden_prefixes: tuple[str, ...]) -> list[str]:
    messages: list[str] = []
    for py_file in py_files:
        rel = py_file.relative_to(PACKAGE_ROOT.parent)
        for line_no, module in _iter_imports(py_file):
            for prefix in forbidden_prefixes:
                if _matches_prefix(module, prefix):
                    messages.append(f"{rel}:{line_no}: forbidden import {module!r} (layer rule)")
    return messages


def test_settings_layer_does_not_import_runtime_modules() -> None:
    """L1 settings must stay independent of dose, plotting, GUI, and orchestration."""
    violations = _violations(_python_files_under("settings"), SETTINGS_FORBIDDEN_PREFIXES)
    assert not violations, "Settings layer imports violate architecture:\n" + "\n".join(violations)


def test_gui_does_not_import_calculate_dose_directly() -> None:
    """L8 GUI must call analyze_data orchestration, not dose pipeline internals."""
    violations = _violations(_python_files_under("gui"), GUI_FORBIDDEN_PREFIXES)
    assert not violations, "GUI layer imports violate architecture:\n" + "\n".join(violations)


def test_input_adapters_does_not_import_domain_or_higher() -> None:
    """L2 input_adapters must not depend on domain models, dose pipeline, or presentation."""
    violations = _violations(_python_files_under("input_adapters"), INPUT_ADAPTERS_FORBIDDEN_PREFIXES)
    assert not violations, "input_adapters layer imports violate architecture:\n" + "\n".join(violations)


def test_calculate_dose_does_not_import_presentation_layers() -> None:
    """L4 dose pipeline must not depend on GUI or plotting."""
    violations = _violations(_python_files_under("calculate_dose"), CALCULATE_DOSE_FORBIDDEN_PREFIXES)
    assert not violations, "calculate_dose imports violate architecture:\n" + "\n".join(violations)
