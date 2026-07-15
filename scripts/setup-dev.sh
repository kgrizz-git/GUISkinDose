#!/usr/bin/env bash
set -euo pipefail

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
