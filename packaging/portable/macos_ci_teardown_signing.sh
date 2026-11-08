#!/usr/bin/env bash
# Delete throwaway signing keychain and secret files; restore prior keychain list.
set +e
set +x

RT="${RUNNER_TEMP:-}"
if [[ -n "${KEYCHAIN_PATH:-}" ]]; then
    security delete-keychain "$KEYCHAIN_PATH" 2>/dev/null
fi
rm -f "${RT}/AuthKey.p8" "${RT}/developer-id.p12" 2>/dev/null
if [[ -n "${PREV_KEYCHAINS:-}" ]]; then
    # shellcheck disable=SC2086
    security list-keychains -d user -s $PREV_KEYCHAINS 2>/dev/null
fi
exit 0
