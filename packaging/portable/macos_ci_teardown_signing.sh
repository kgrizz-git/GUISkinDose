#!/usr/bin/env bash
# Delete throwaway signing keychain and notary key file; restore prior keychain list.
set -euo pipefail
set +x

rm -f "${RUNNER_TEMP}/AuthKey.p8" "${RUNNER_TEMP}/developer-id.p12" 2>/dev/null || true
if [[ -n "${KEYCHAIN_PATH:-}" && -f "$KEYCHAIN_PATH" ]]; then
    security delete-keychain "$KEYCHAIN_PATH" || true
fi
if [[ -n "${PREV_KEYCHAINS:-}" ]]; then
    # shellcheck disable=SC2086
    security list-keychains -d user -s $PREV_KEYCHAINS
fi
