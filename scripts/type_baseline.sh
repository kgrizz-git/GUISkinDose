#!/usr/bin/env bash
# Manage the optional basedpyright baseline (.basedpyright/baseline.json).
#
# Usage:
#   ./scripts/type_baseline.sh shrink   # default — auto-remove fixed errors (local baselinemode=auto)
#   ./scripts/type_baseline.sh write    # add current errors to baseline (accept new debt)
#
# After shrink, commit the updated baseline if basedpyright reports changes.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BASELINE="${BASELINE_FILE:-$ROOT/.basedpyright/baseline.json}"
ACTION="${1:-shrink}"

cd "$ROOT"

case "$ACTION" in
  shrink)
    if [[ ! -f "$BASELINE" ]]; then
      echo "No baseline at $BASELINE — nothing to shrink." >&2
      echo "Create one with: $0 write" >&2
      exit 1
    fi
    basedpyright --baselinefile "$BASELINE"
    echo "If basedpyright updated the baseline, commit: ${BASELINE#"$ROOT"/}"
    ;;
  write)
    mkdir -p "$(dirname "$BASELINE")"
    basedpyright --baselinefile "$BASELINE" --writebaseline
    echo "Wrote baseline to ${BASELINE#"$ROOT"/}. Review and commit if intentional."
    ;;
  *)
    echo "Usage: $0 [shrink|write]" >&2
    exit 2
    ;;
esac
