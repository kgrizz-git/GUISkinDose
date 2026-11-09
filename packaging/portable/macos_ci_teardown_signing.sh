#!/usr/bin/env bash
# Delete throwaway signing keychain and secret files; restore prior keychain list.
set +e
set +x

FAILED=0
RT="${RUNNER_TEMP:-}"

run_cleanup() {
    local name="$1"
    shift
    if ! "$@"; then
        echo "cleanup failed: $name" >&2
        FAILED=1
    fi
}

# The import step records the path before creating the keychain, so it may not exist.
if [[ -n "${KEYCHAIN_PATH:-}" && -f "$KEYCHAIN_PATH" ]]; then
    run_cleanup delete-keychain security delete-keychain "$KEYCHAIN_PATH"
fi
run_cleanup remove-signing-artifacts rm -f "${RT}/AuthKey.p8" "${RT}/developer-id.p12"
if [[ -n "${PREV_KEYCHAINS:-}" ]]; then
    # shellcheck disable=SC2086
    run_cleanup restore-keychains security list-keychains -d user -s $PREV_KEYCHAINS
fi

exit "$FAILED"
