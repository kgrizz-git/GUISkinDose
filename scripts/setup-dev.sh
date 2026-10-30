#!/usr/bin/env bash
set -euo pipefail

if ! command -v uv > /dev/null 2>&1; then
    echo "ERROR: uv not found; the locked git hooks require uv."
    echo "Install uv, then run: uv sync --extra dev --extra gui --locked"
    exit 1
fi

# Verify pre-commit is available (requires pip install -e ".[dev,gui]" first)
if ! command -v pre-commit > /dev/null 2>&1; then
    echo "ERROR: pre-commit not found." >&2
    echo "Activate your venv or install dependencies first:" >&2
    echo "  pip install -e \".[dev,gui]\"" >&2
    exit 1
fi

pre-commit install
pre-commit install --hook-type pre-push
pre-commit install --hook-type commit-msg
echo "Git hooks installed (pre-commit + pre-push + commit-msg)."
echo "For routed privacy changes, run: python scripts/privacy_admission.py run --mode staged"
echo "Optional: install the privacy-scan group if the privacy hook asks for a Presidio receipt:"
echo "  uv sync --extra dev --extra gui --group privacy-scan   (or pip 25.1+: pip install --group privacy-scan)"
