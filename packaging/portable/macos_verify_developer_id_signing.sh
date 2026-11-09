#!/usr/bin/env bash
# Deep verification of Developer ID seals (Team ID, forbidden teams, entitlements).
# Requires GUISKINDOSE_EXPECTED_TEAM_ID. Optional GUISKINDOSE_FORBIDDEN_TEAM_IDS,
# GUISKINDOSE_CHROMIUM_MAIN_NEEDS_JIT. Prints counts only from the Python helper.
set -euo pipefail

if [[ $# -ne 1 ]]; then
    echo "usage: $0 <GUISkinDose.app>" >&2
    exit 2
fi
[[ -n "${GUISKINDOSE_EXPECTED_TEAM_ID:-}" ]] || {
    echo "GUISKINDOSE_EXPECTED_TEAM_ID is required" >&2
    exit 2
}
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 -I "${HERE}/macos_verify_developer_id_signing.py" "$1"
