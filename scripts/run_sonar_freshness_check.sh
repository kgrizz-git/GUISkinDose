#!/usr/bin/env bash
# Pre-commit wrapper for the local SonarQube freshness gate.
# Resolves the project venv interpreter so the hook does not depend on the
# application being importable. Forwards all arguments to the Python gate script.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Each candidate must actually start and import sys; a stale venv symlink or
# a Windows Store alias can be "executable" yet unusable.
usable() { [[ -n "$1" ]] && "$1" -c 'import sys' >/dev/null 2>&1; }

PYTHON_SELECTED=""
for candidate in \
  "${PYTHON:-}" \
  "$ROOT_DIR/.venv/bin/python" \
  "$ROOT_DIR/.venv/Scripts/python.exe" \
  "$(command -v python3 || true)" \
  "$(command -v python || true)"; do
  if usable "$candidate"; then
    PYTHON_SELECTED="$candidate"
    break
  fi
done
if [[ -z "$PYTHON_SELECTED" ]]; then
  echo "run_sonar_freshness_check: no working Python interpreter found; skipping Sonar freshness gate." >&2
  exit 0
fi

exec "$PYTHON_SELECTED" "$ROOT_DIR/scripts/check_sonar_freshness.py" "$@"
