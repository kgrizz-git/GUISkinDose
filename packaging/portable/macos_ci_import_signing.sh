#!/usr/bin/env bash
# Import Developer ID and notary API material on an ephemeral GitHub Actions macOS runner.
#
# Required environment (typically from macos-release secrets):
#   DEVELOPER_ID_P12_BASE64, DEVELOPER_ID_P12_PASSWORD
#   NOTARY_KEY_P8, NOTARY_KEY_ID, NOTARY_ISSUER
# Optional: GITHUB_ENV, GITHUB_OUTPUT for CI wiring.
#
# Never prints secret values or absolute paths.
set -euo pipefail
set +x

for var in DEVELOPER_ID_P12_BASE64 DEVELOPER_ID_P12_PASSWORD NOTARY_KEY_P8 NOTARY_KEY_ID NOTARY_ISSUER; do
    if [[ -z "${!var:-}" ]]; then
        echo "missing signing environment: set $var" >&2
        exit 1
    fi
done

mask_notary_p8() {
    local line
    if [[ "$NOTARY_KEY_P8" != *BEGIN* ]]; then
        echo "::add-mask::${NOTARY_KEY_P8}"
        return
    fi
    while IFS= read -r line || [[ -n "$line" ]]; do
        case "$line" in
            "-----BEGIN"* | "-----END"*) ;;
            "") ;;
            *) echo "::add-mask::${line}" ;;
        esac
    done <<<"$NOTARY_KEY_P8"
}

echo "::add-mask::${DEVELOPER_ID_P12_PASSWORD}"
mask_notary_p8
echo "::add-mask::${NOTARY_KEY_ID}"
echo "::add-mask::${NOTARY_ISSUER}"

KEYCHAIN="${RUNNER_TEMP}/guiskindose-signing.keychain-db"
P12="${RUNNER_TEMP}/developer-id.p12"
P8="${RUNNER_TEMP}/AuthKey.p8"
KEYCHAIN_PASSWORD="$(openssl rand -base64 32)"
echo "::add-mask::${KEYCHAIN_PASSWORD}"

[[ -n "${GITHUB_OUTPUT:-}" ]] && echo "KEYCHAIN_PATH=${KEYCHAIN}" >>"$GITHUB_OUTPUT"
PREV_KEYCHAINS="$(security list-keychains -d user | tr -d '"')"
if [[ -n "${GITHUB_OUTPUT:-}" ]]; then
    {
        echo "PREV_KEYCHAINS<<EOF"
        echo "$PREV_KEYCHAINS"
        echo "EOF"
    } >>"$GITHUB_OUTPUT"
fi

python3 -I "${BASH_SOURCE%/*}/macos_ci_decode_signing_material.py" p12 \
    || { echo "p12 decode failed" >&2; exit 1; }
python3 -I "${BASH_SOURCE%/*}/macos_ci_decode_signing_material.py" notary \
    || { echo "notary key file is not a private key PEM" >&2; exit 1; }

security create-keychain -p "$KEYCHAIN_PASSWORD" "$KEYCHAIN"
security set-keychain-settings -lut 21600 "$KEYCHAIN"
security unlock-keychain -p "$KEYCHAIN_PASSWORD" "$KEYCHAIN"
security import "$P12" -k "$KEYCHAIN" -P "$DEVELOPER_ID_P12_PASSWORD" \
    -T /usr/bin/codesign -T /usr/bin/security
rm -f "$P12"
security set-key-partition-list -S apple-tool:,apple:,codesign: -s -k "$KEYCHAIN_PASSWORD" "$KEYCHAIN"
# shellcheck disable=SC2086
security list-keychains -d user -s "$KEYCHAIN" $PREV_KEYCHAINS
security default-keychain -s "$KEYCHAIN"

ID_LINES="$(security find-identity -v -p codesigning)"
COUNT="$(printf '%s\n' "$ID_LINES" | grep -c 'Developer ID Application:' || true)"
if [[ "$COUNT" != 1 ]]; then
    echo "expected exactly one Developer ID Application identity, found ${COUNT}" >&2
    exit 1
fi
IDENTITY="$(printf '%s\n' "$ID_LINES" | sed -n 's/.*"\(Developer ID Application: [^"]*\)".*/\1/p' | head -n 1)"
[[ -n "$IDENTITY" ]] || { echo "could not resolve signing identity" >&2; exit 1; }

if [[ -n "${GITHUB_ENV:-}" ]]; then
    {
        echo "GUISKINDOSE_SIGN_IDENTITY=${IDENTITY}"
        echo "GUISKINDOSE_NOTARY_KEY=${P8}"
        echo "GUISKINDOSE_NOTARY_KEY_ID=${NOTARY_KEY_ID}"
        echo "GUISKINDOSE_NOTARY_ISSUER=${NOTARY_ISSUER}"
    } >>"$GITHUB_ENV"
fi
echo "signing_import=ok"
