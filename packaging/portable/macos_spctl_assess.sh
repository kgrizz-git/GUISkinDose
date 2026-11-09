#!/usr/bin/env bash
# Assess stapled/notarized app with spctl; on failure log sanitized lines (no absolute paths).
#
# Source this file; do not execute directly.
set -euo pipefail

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    echo "source macos_spctl_assess.sh instead of executing it" >&2
    exit 2
fi

# Replace the assessed path, absolute or relative, with <app>.
_macos_spctl_sanitize_output() {
    local raw="$1"
    local app="$2"
    local line
    while IFS= read -r line || [[ -n "$line" ]]; do
        line="${line//"$app"/<app>}"
        printf '%s\n' "$line"
    done <<<"$raw"
}

_macos_spctl_report_failure() {
    local raw="$1"
    local app="$2"
    local context="${3:-spctl}"
    local sanitized
    sanitized="$(_macos_spctl_sanitize_output "$raw" "$app")"
    echo "${context}: assessment did not report Notarized Developer ID" >&2
    printf '%s\n' "$sanitized" >&2
    if [[ -n "${GITHUB_STEP_SUMMARY:-}" ]]; then
        {
            echo "### ${context}"
            echo '```'
            printf '%s\n' "$sanitized"
            echo '```'
        } >>"$GITHUB_STEP_SUMMARY"
    fi
}

# Returns 0 when spctl reports Notarized Developer ID. When echo_accepted=1, prints spctl: accepted.
macos_spctl_assert_notarized() {
    local app="$1"
    local context="${2:-spctl}"
    local echo_accepted="${3:-0}"
    local spctl_out
    spctl_out="$(spctl -a -t exec -vv "$app" 2>&1)" || true
    if grep -q 'source=Notarized Developer ID' <<<"$spctl_out"; then
        if [[ "$echo_accepted" == 1 ]]; then
            echo "spctl: accepted"
        fi
        return 0
    fi
    _macos_spctl_report_failure "$spctl_out" "$app" "$context"
    return 1
}
