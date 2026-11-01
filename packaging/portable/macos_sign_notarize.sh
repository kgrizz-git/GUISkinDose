#!/usr/bin/env bash
# Sign, notarize, and staple a frozen GUISkinDose.app (PORTABLE_APP_PLAN.md Phase 0b).
#
# Usage (from the repository root, after the PyInstaller freeze):
#   packaging/portable/macos_sign_notarize.sh tmp/portable/dist/GUISkinDose.app tmp/portable/release
#
# Environment:
#   GUISKINDOSE_SIGN_IDENTITY    codesign identity (default: the first "Developer ID Application" one)
#   GUISKINDOSE_NOTARY_PROFILE   notarytool keychain profile (default: guiskindose-notary)
#   GUISKINDOSE_NOTARY_KEY       App Store Connect API key file (.p8)    } set all three for
#   GUISKINDOSE_NOTARY_KEY_ID    its key ID                              } API-key auth; set
#   GUISKINDOSE_NOTARY_ISSUER    its issuer ID                           } none for the profile
#   GUISKINDOSE_SKIP_NOTARIZE=1  sign and verify only
#   GUISKINDOSE_NOTARY_DRY_RUN=1 print the auth mode and redacted notarytool arguments, then exit
#
# Notary auth modes:
#   1. API key: when all three GUISKINDOSE_NOTARY_KEY* variables are set, notarytool gets
#      --key/--key-id/--issuer for submit and log. CI will supply these from a protected
#      GitHub Environment, with the Developer ID .p12 imported into a temporary keychain.
#   2. Keychain profile (local default): --keychain-profile. Recreate a lost profile with
#      xcrun notarytool store-credentials <profile> --key <AuthKey.p8> --key-id <ID> --issuer <ID>
#   Setting only some of the three variables is an error. Values are never printed.
#
# Every nested Mach-O is signed inside-out with the hardened runtime and a secure
# timestamp, deepest paths first, then each nested bundle, then the app. No --deep.
# The output directory receives GUISkinDose-macos-<arch>.zip (stapled app, ditto zip).
set -euo pipefail

if [[ $# -ne 2 ]]; then
    echo "usage: $0 <path/to/GUISkinDose.app> <output-dir>" >&2
    exit 2
fi
APP="${1%/}"
OUT="$2"
[[ -d "$APP/Contents/MacOS" ]] || { echo "not an app bundle: $APP" >&2; exit 2; }
mkdir -p "$OUT"

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENTITLEMENTS="$HERE/macos_entitlements.plist"
PROFILE="${GUISKINDOSE_NOTARY_PROFILE:-guiskindose-notary}"

# Resolve notary auth before any signing, so a bad configuration fails fast.
KEY="${GUISKINDOSE_NOTARY_KEY:-}"
KEY_ID="${GUISKINDOSE_NOTARY_KEY_ID:-}"
ISSUER="${GUISKINDOSE_NOTARY_ISSUER:-}"
set_count=0
for value in "$KEY" "$KEY_ID" "$ISSUER"; do
    [[ -n "$value" ]] && set_count=$((set_count + 1))
done
if [[ $set_count -eq 3 ]]; then
    AUTH_MODE="api-key"
    if [[ ! -f "$KEY" || ! -r "$KEY" ]]; then
        echo "GUISKINDOSE_NOTARY_KEY does not name a readable file" >&2
        exit 1
    fi
    if [[ -n "$(find "$KEY" -perm -g+r -o -perm -o+r 2>/dev/null)" ]]; then
        echo "warning: the GUISKINDOSE_NOTARY_KEY file is group- or world-readable; chmod 600 it" >&2
    fi
    NOTARY_AUTH=(--key "$KEY" --key-id "$KEY_ID" --issuer "$ISSUER")
    REDACTED_AUTH="--key <GUISKINDOSE_NOTARY_KEY> --key-id <GUISKINDOSE_NOTARY_KEY_ID> --issuer <GUISKINDOSE_NOTARY_ISSUER>"
elif [[ $set_count -eq 0 ]]; then
    AUTH_MODE="keychain-profile"
    NOTARY_AUTH=(--keychain-profile "$PROFILE")
    REDACTED_AUTH="--keychain-profile <GUISKINDOSE_NOTARY_PROFILE>"
else
    echo "set all of GUISKINDOSE_NOTARY_KEY, GUISKINDOSE_NOTARY_KEY_ID and GUISKINDOSE_NOTARY_ISSUER, or none" >&2
    exit 1
fi
if [[ "${GUISKINDOSE_NOTARY_DRY_RUN:-0}" == "1" ]]; then
    echo "notary auth: $AUTH_MODE"
    echo "submit: xcrun notarytool submit <zip> $REDACTED_AUTH --wait --output-format plist"
    echo "log:    xcrun notarytool log <id> $REDACTED_AUTH <file>"
    echo "auth argument count: ${#NOTARY_AUTH[@]}"
    exit 0
fi
IDENTITY="${GUISKINDOSE_SIGN_IDENTITY:-}"
if [[ -z "$IDENTITY" ]]; then
    IDENTITY="$(security find-identity -v -p codesigning \
        | sed -n 's/.*"\(Developer ID Application: [^"]*\)".*/\1/p' | head -n 1)"
fi
[[ -n "$IDENTITY" ]] || { echo "no Developer ID Application identity found" >&2; exit 1; }

sign() {
    codesign --force --timestamp --options runtime --entitlements "$ENTITLEMENTS" \
        --sign "$IDENTITY" "$1"
}

is_macho() {
    file -b "$1" | grep -q 'Mach-O'
}

start=$(date +%s)
# 1. Loose Mach-O files (dylibs, .so extensions, executables). Order does not matter
#    here; only the bundle seals in step 2 depend on what these files contain.
count=0
while IFS= read -r -d '' path; do
    if is_macho "$path"; then
        sign "$path" >/dev/null 2>&1 || { echo "codesign failed on a nested file" >&2; sign "$path"; }
        count=$((count + 1))
    fi
done < <(find "$APP/Contents" -type f ! -path '*/_CodeSignature/*' -print0)
echo "signed $count Mach-O files"

# 2. Nested bundles (frameworks, helper apps). find -depth lists children before
#    parents, so inner seals exist before an outer bundle is sealed.
while IFS= read -r -d '' bundle; do
    sign "$bundle" >/dev/null
done < <(find "$APP/Contents" -depth -type d \( -name '*.framework' -o -name '*.app' -o -name '*.xpc' \) -print0)

# 3. The app itself.
sign "$APP"
echo "signing took $(( $(date +%s) - start )) s"

codesign --verify --deep --strict "$APP"
echo "codesign --verify --deep --strict: ok"

ZIP="$OUT/GUISkinDose-macos-$(uname -m).zip"
if [[ "${GUISKINDOSE_SKIP_NOTARIZE:-0}" == "1" ]]; then
    ditto -c -k --keepParent "$APP" "$ZIP"
    echo "notarization skipped; unstapled zip written"
    exit 0
fi

# Fail before uploading when the keychain profile is missing or unusable. Its output
# is discarded because it can carry account identifiers.
if [[ "$AUTH_MODE" == "keychain-profile" ]] \
    && ! xcrun notarytool history "${NOTARY_AUTH[@]}" >/dev/null 2>&1; then
    cat >&2 <<EOF
notarytool keychain profile "$PROFILE" is missing or unusable.
Recreate it (interactive; the key file stays outside the repository):
  xcrun notarytool store-credentials "$PROFILE" --key <AuthKey.p8> --key-id <KEY_ID> --issuer <ISSUER_ID>
The app is signed; re-run this script to notarize, or set GUISKINDOSE_SKIP_NOTARIZE=1.
EOF
    exit 1
fi

SUBMIT_ZIP="$OUT/notary-submit.zip"
rm -f "$SUBMIT_ZIP"
ditto -c -k --keepParent "$APP" "$SUBMIT_ZIP"
start=$(date +%s)
RESULT="$OUT/notary-result.plist"
xcrun notarytool submit "$SUBMIT_ZIP" "${NOTARY_AUTH[@]}" --wait \
    --output-format plist > "$RESULT" || true
echo "notarization took $(( $(date +%s) - start )) s"
STATUS="$(/usr/libexec/PlistBuddy -c 'Print :status' "$RESULT" 2>/dev/null || echo unknown)"
SUB_ID="$(/usr/libexec/PlistBuddy -c 'Print :id' "$RESULT" 2>/dev/null || echo)"
echo "notary status: $STATUS"
rm -f "$SUBMIT_ZIP"
if [[ "$STATUS" != "Accepted" ]]; then
    if [[ -n "$SUB_ID" ]]; then
        LOG="$OUT/notary-log.json"
        xcrun notarytool log "$SUB_ID" "${NOTARY_AUTH[@]}" "$LOG" || true
        # Print bundle-relative paths only.
        /usr/bin/python3 -I -c '
import json, sys
log = json.load(open(sys.argv[1]))
for issue in log.get("issues") or []:
    path = issue.get("path", "")
    path = path.split(".app/", 1)[-1] if ".app/" in path else path
    print(f"{issue.get(\"severity\")}: {path}: {issue.get(\"message\")}")
' "$LOG" || true
    fi
    exit 1
fi

xcrun stapler staple "$APP"
xcrun stapler validate "$APP"
rm -f "$ZIP"
ditto -c -k --keepParent "$APP" "$ZIP"
spctl -a -t exec -vv "$APP"
echo "release zip: $ZIP"
