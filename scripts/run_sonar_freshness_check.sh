#!/usr/bin/env bash
# Pre-commit wrapper for the local SonarQube freshness gate.
# Resolves the project venv interpreter so the hook does not depend on the
# application being importable. Forwards all arguments to the Python gate script.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

PYTHON="${PYTHON:-$ROOT_DIR/.venv/bin/python}"
if [[ ! -x "$PYTHON" ]]; then
  PYTHON="$(command -v python3)"
fi

exec "$PYTHON" "$ROOT_DIR/scripts/check_sonar_freshness.py" "$@"
