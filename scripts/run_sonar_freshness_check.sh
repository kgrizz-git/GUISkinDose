#!/usr/bin/env bash
# Pre-commit wrapper for the local SonarQube freshness gate.
# Resolves the project venv interpreter so the hook does not depend on the
# application being importable. Forwards all arguments to the Python gate script.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

PYTHON="${PYTHON:-$ROOT_DIR/.venv/bin/python}"
if [[ ! -x "$PYTHON" ]]; then
  PYTHON="$ROOT_DIR/.venv/Scripts/python.exe"
fi
if [[ ! -x "$PYTHON" ]]; then
  PYTHON="$(command -v python3 || true)"
fi
if [[ -z "$PYTHON" ]]; then
  PYTHON="$(command -v python || true)"
fi
if [[ -z "$PYTHON" ]]; then
  echo "run_sonar_freshness_check: no Python interpreter found; skipping Sonar freshness gate." >&2
  exit 0
fi

exec "$PYTHON" "$ROOT_DIR/scripts/check_sonar_freshness.py" "$@"
