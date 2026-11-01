#!/usr/bin/env bash
# Sign, notarize, and staple a frozen GUISkinDose.app (PORTABLE_APP_PLAN.md Phase 0b).
#
# Usage (from the repository root, after the PyInstaller freeze):
#   packaging/portable/macos_sign_notarize.sh tmp/portable/dist/GUISkinDose.app tmp/portable/release
#
# Environment:
#   GUISKINDOSE_SIGN_IDENTITY    codesign identity (default: the first "Developer ID Application" one)
#   GUISKINDOSE_NOTARY_PROFILE   notarytool keychain profile (default: guiskindose-notary)
#   GUISKINDOSE_NOTARY_KEY       App Store Connect API key file (.p8)    } API-key auth when
#   GUISKINDOSE_NOTARY_KEY_ID    its key ID                              } all three are set;
#   GUISKINDOSE_NOTARY_ISSUER    its issuer ID                           } a partial set fails
#   GUISKINDOSE_NOTARY_ENV       env file for fallback 3 (default: $HOME/.appstoreconnect/notary.env)
#   GUISKINDOSE_SKIP_NOTARIZE=1  sign and verify only; no notary auth is resolved
#   GUISKINDOSE_NOTARY_DRY_RUN=1 resolve auth, print the mode and redacted arguments, then exit
#
# Notary auth order (resolved before signing, so a bad setup fails fast):
#   1. API key: all three GUISKINDOSE_NOTARY_* variables already set. notarytool gets
#      --key/--key-id/--issuer for submit and log. CI will supply these from a protected
#      GitHub Environment, with the Developer ID .p12 imported into a temporary keychain.
#   2. Keychain profile: used when `notarytool history` accepts it (output discarded).
#      Recreate a lost profile with
#      xcrun notarytool store-credentials <profile> --key <AuthKey.p8> --key-id <ID> --issuer <ID>
#   3. Env file: sourced only if it is a regular file (not a symlink), owned by the current
#      user, and mode 600 or stricter. It must set all three variables, with no
#      <KeyID>/<IssuerID> placeholder text. Then API-key mode is used.
#   4. Otherwise the script fails and explains how to restore options 2 or 3.
#   Values, the key path, and the env file contents are never printed. Do not run with set -x.
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

NOTARY_ENV="${GUISKINDOSE_NOTARY_ENV:-$HOME/.appstoreconnect/notary.env}"

count_key_vars() {
    local count=0 value
    for value in "${GUISKINDOSE_NOTARY_KEY:-}" "${GUISKINDOSE_NOTARY_KEY_ID:-}" "${GUISKINDOSE_NOTARY_ISSUER:-}"; do
        [[ -n "$value" ]] && count=$((count + 1))
    done
    echo "$count"
}

use_api_key() {
    local key="$GUISKINDOSE_NOTARY_KEY"
    if [[ ! -f "$key" || ! -r "$key" ]]; then
        echo "GUISKINDOSE_NOTARY_KEY does not name a readable file" >&2
        exit 1
    fi
    if [[ -n "$(find "$key" -perm -g+r -o -perm -o+r 2>/dev/null)" ]]; then
        echo "warning: the GUISKINDOSE_NOTARY_KEY file is group- or world-readable; chmod 600 it" >&2
    fi
    NOTARY_AUTH=(--key "$key" --key-id "$GUISKINDOSE_NOTARY_KEY_ID" --issuer "$GUISKINDOSE_NOTARY_ISSUER")
    REDACTED_AUTH="--key <GUISKINDOSE_NOTARY_KEY> --key-id <GUISKINDOSE_NOTARY_KEY_ID> --issuer <GUISKINDOSE_NOTARY_ISSUER>"
}

# Refuse an env file that another user could have written or can read.
check_env_file() {
    local file="$1" mode
    if [[ -L "$file" || ! -f "$file" ]]; then
        echo "refusing GUISKINDOSE_NOTARY_ENV file: not a regular file (or a symlink)" >&2
        exit 1
    fi
    if [[ "$(stat -f %u "$file")" != "$(id -u)" ]]; then
        echo "refusing GUISKINDOSE_NOTARY_ENV file: not owned by the current user" >&2
        exit 1
    fi
    mode="$(stat -f %Lp "$file")"
    if (( (8#$mode & 8#077) != 0 )); then
        echo "refusing GUISKINDOSE_NOTARY_ENV file: group or world access; chmod 600 it" >&2
        exit 1
    fi
}

no_auth_message() {
    cat >&2 <<EOF
No usable notary credentials.
Either recreate the keychain profile "$PROFILE" (interactive; the key file stays outside the repository):
  xcrun notarytool store-credentials "$PROFILE" --key <AuthKey.p8> --key-id <KEY_ID> --issuer <ISSUER_ID>
or create a mode-600 env file at GUISKINDOSE_NOTARY_ENV (default ~/.appstoreconnect/notary.env) that sets
GUISKINDOSE_NOTARY_KEY, GUISKINDOSE_NOTARY_KEY_ID and GUISKINDOSE_NOTARY_ISSUER.
Set GUISKINDOSE_SKIP_NOTARIZE=1 to sign without notarizing.
EOF
}

resolve_notary_auth() {
    case "$(count_key_vars)" in
        3)
            AUTH_MODE="api-key (environment)"
            use_api_key
            return
            ;;
        0) ;;
        *)
            echo "set all of GUISKINDOSE_NOTARY_KEY, GUISKINDOSE_NOTARY_KEY_ID and GUISKINDOSE_NOTARY_ISSUER, or none" >&2
            exit 1
            ;;
    esac
    # Output is discarded because it can carry account identifiers.
    if xcrun notarytool history --keychain-profile "$PROFILE" >/dev/null 2>&1; then
        AUTH_MODE="keychain-profile"
        NOTARY_AUTH=(--keychain-profile "$PROFILE")
        REDACTED_AUTH="--keychain-profile <GUISKINDOSE_NOTARY_PROFILE>"
        return
    fi
    if [[ -e "$NOTARY_ENV" || -L "$NOTARY_ENV" ]]; then
        check_env_file "$NOTARY_ENV"
        # shellcheck disable=SC1090  # the path is chosen at runtime and checked above
        source "$NOTARY_ENV"
        if [[ "$(count_key_vars)" != 3 ]]; then
            echo "GUISKINDOSE_NOTARY_ENV file must set all three GUISKINDOSE_NOTARY_* variables" >&2
            exit 1
        fi
        local value
        for value in "$GUISKINDOSE_NOTARY_KEY" "$GUISKINDOSE_NOTARY_KEY_ID" "$GUISKINDOSE_NOTARY_ISSUER"; do
            if [[ "$value" == *"<KeyID>"* || "$value" == *"<IssuerID>"* ]]; then
                echo "GUISKINDOSE_NOTARY_ENV file still contains placeholder text" >&2
                exit 1
            fi
        done
        AUTH_MODE="api-key (env file)"
        use_api_key
        return
    fi
    no_auth_message
    exit 1
}

NOTARY_AUTH=()
AUTH_MODE="none"
REDACTED_AUTH=""
if [[ "${GUISKINDOSE_SKIP_NOTARIZE:-0}" != "1" ]]; then
    resolve_notary_auth
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
