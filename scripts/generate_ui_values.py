#!/usr/bin/env python3
"""Regenerate dev-docs/UI_values.md from GUI CSS tokens in styles.py.

Purpose:
    Extract design tokens from the MODERN_CSS constant so UI_values.md cannot
    drift from the implementation.

Inputs:
    Repository root (auto-detected as parent of ``scripts/``, or ``--repo-root``).
    Reads ``src/mypyskindose/gui/styles.py``.

Outputs:
    Writes ``dev-docs/UI_values.md`` (or ``--check`` to verify without writing).

Usage:
    python scripts/generate_ui_values.py
    python scripts/generate_ui_values.py --check
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

APP_REL_PATH = Path("src/mypyskindose/gui/styles.py")
OUTPUT_REL_PATH = Path("dev-docs/UI_values.md")

MODERN_CSS_RE = re.compile(
    r'MODERN_CSS\s*=\s*r"""(.*?)"""',
    re.DOTALL,
)
CSS_VAR_RE = re.compile(r"^\s*(--[\w-]+)\s*:\s*([^;]+);", re.MULTILINE)
RADIAL_GRADIENT_RE = re.compile(
    r"radial-gradient\(\s*at\s+([^,]+),\s*rgba\(([^)]+)\)\s+([^,]+),\s*transparent\s+([^)]+)\)",
    re.IGNORECASE,
)


def repo_root_from_script() -> Path:
    return Path(__file__).resolve().parent.parent


def extract_modern_css(app_path: Path) -> str:
    text = app_path.read_text(encoding="utf-8")
    match = MODERN_CSS_RE.search(text)
    if not match:
        raise ValueError(f"MODERN_CSS not found in {app_path}")
    return match.group(1)


def parse_css_variables(css: str) -> list[tuple[str, str]]:
    return [(name, value.strip()) for name, value in CSS_VAR_RE.findall(css)]


def parse_radial_gradients(css: str) -> list[tuple[str, str, str, str]]:
    return RADIAL_GRADIENT_RE.findall(css)


def variable_purpose(name: str) -> str:
    purposes = {
        "--bg-primary": "Main background",
        "--bg-secondary": "Secondary background (panels, drawer)",
        "--aurora-purple": "Navigation, primary actions, sidebar glow",
        "--aurora-teal": "Input and load accents",
        "--aurora-pink": "Status and highlights",
        "--text-main": "Primary text",
        "--text-muted": "Secondary text",
        "--glass-bg": "Card background",
        "--glass-bg-hover": "Card hover background",
        "--glass-border": "Glass border color",
        "--shadow-soft": "Default card shadow",
        "--shadow-hover": "Card hover shadow",
        "--glow-blue": "Blue glow for hover effects",
        "--glow-purple": "Purple glow for secondary buttons",
    }
    return purposes.get(name, "Design token")


def render_markdown(
    variables: list[tuple[str, str]],
    gradients: list[tuple[str, str, str, str]],
) -> str:
    lines = [
        "# UI Values — MyPySkinDose",
        "",
        "> **Auto-generated** — do not edit by hand. Regenerate with:",
        "> `python scripts/generate_ui_values.py`",
        "",
        "Design tokens extracted from `MODERN_CSS` in "
        "[src/mypyskindose/gui/styles.py](../src/mypyskindose/gui/styles.py). "
        "Aesthetic intent lives in [DESIGN.md](../DESIGN.md); "
        "implementation plan in [GUI_PLAN.md](GUI_PLAN.md).",
        "",
        "## Color palette (CSS variables)",
        "",
        "| Variable | Value | Purpose |",
        "| :--- | :--- | :--- |",
    ]
    for name, value in variables:
        lines.append(f"| `{name}` | `{value}` | {variable_purpose(name)} |")

    lines.extend(
        [
            "",
            "## Aurora effects (radial gradients)",
            "",
            "Extracted from `body` and `.q-drawer` background rules.",
            "",
        ]
    )
    if gradients:
        for position, rgba, _start, radius in gradients:
            lines.append(f"- **{position.strip()}:** `rgba({rgba})` ({radius.strip()} radius)")
    else:
        lines.append("_No radial gradients matched the extraction pattern._")

    lines.extend(["", f"_Generated from `{APP_REL_PATH.as_posix()}`._", ""])
    return "\n".join(lines)


def generate(repo_root: Path) -> str:
    app_path = repo_root / APP_REL_PATH
    if not app_path.is_file():
        raise FileNotFoundError(app_path)
    css = extract_modern_css(app_path)
    return render_markdown(parse_css_variables(css), parse_radial_gradients(css))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Regenerate dev-docs/UI_values.md from app.py CSS.")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=repo_root_from_script(),
        help="Repository root (default: parent of scripts/)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit 1 if UI_values.md would change (for CI/pre-commit)",
    )
    args = parser.parse_args(argv)

    repo_root = args.repo_root.resolve()
    output_path = repo_root / OUTPUT_REL_PATH
    new_content = generate(repo_root)

    if args.check:
        if not output_path.is_file():
            print(f"{OUTPUT_REL_PATH} missing; run generate_ui_values.py", file=sys.stderr)
            return 1
        existing = output_path.read_text(encoding="utf-8")
        if existing != new_content:
            print(f"{OUTPUT_REL_PATH} is stale; run: python scripts/generate_ui_values.py", file=sys.stderr)
            return 1
        print(f"{OUTPUT_REL_PATH} is up to date.")
        return 0

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(new_content, encoding="utf-8")
    print(f"Wrote {OUTPUT_REL_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
