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
#   3. Env file: read only if it is a regular file (not a symlink), owned by the current
#      user, and mode 600 or stricter. It is parsed, never sourced: blank lines and #
#      comments are skipped, and each other line must be [export ]NAME=VALUE for one of
#      the three variables, the value optionally single- or double-quoted. Only a leading
#      $HOME/, ${HOME}/ or ~/ in GUISKINDOSE_NOTARY_KEY is expanded. Any other $, $( or
#      backtick, an unknown name, a line without =, or <...> placeholder text is refused.
#      All three must be set. Then API-key mode is used.
#   4. Otherwise the script fails and explains how to restore options 2 or 3.
#   Values, the key path, and the env file contents are never printed. Do not run with set -x.
#
# Every nested Mach-O is signed inside-out with the hardened runtime and a secure
# timestamp, deepest paths first, then each nested bundle, then the app. No --deep.
# The output directory receives GUISkinDose-macos-<arch>.zip (stapled app, ditto zip).
set -euo pipefail
set +x

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

# True when a value still holds template text such as <KEY_ID> or <IssuerID>.
is_placeholder() {
    [[ "$1" == *"<"*">"* ]]
}

use_api_key() {
    local key="$GUISKINDOSE_NOTARY_KEY" value
    for value in "$GUISKINDOSE_NOTARY_KEY" "$GUISKINDOSE_NOTARY_KEY_ID" "$GUISKINDOSE_NOTARY_ISSUER"; do
        if is_placeholder "$value"; then
            echo "a GUISKINDOSE_NOTARY_* value still contains <...> placeholder text" >&2
            exit 1
        fi
    done
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

env_fail() {
    echo "refusing GUISKINDOSE_NOTARY_ENV file: $1" >&2
    exit 1
}

# Open the env file once on fd 3, check that open file, and parse from it, so the
# checks and the parse see the same content. Values are never printed.
load_env_file() {
    local file="$1" line name value lineno=0 mode
    [[ -L "$file" ]] && env_fail "it is a symlink"
    exec 3<"$file" || env_fail "cannot open it"
    [[ -f /dev/fd/3 ]] || env_fail "not a regular file"
    [[ "$(stat -L -f %u /dev/fd/3)" == "$(id -u)" ]] || env_fail "not owned by the current user"
    mode="$(stat -L -f %Lp /dev/fd/3)"
    (( (8#$mode & 8#077) == 0 )) || env_fail "group or world access; chmod 600 it"
    while IFS= read -r line <&3 || [[ -n "$line" ]]; do
        lineno=$((lineno + 1))
        line="${line#"${line%%[![:space:]]*}"}"
        line="${line%"${line##*[![:space:]]}"}"
        [[ -z "$line" || "$line" == "#"* ]] && continue
        if [[ "$line" == "export "* ]]; then
            line="${line#export }"
            line="${line#"${line%%[![:space:]]*}"}"
        fi
        [[ "$line" == *=* ]] || env_fail "line $lineno is not NAME=VALUE"
        name="${line%%=*}"
        value="${line#*=}"
        case "$name" in
            GUISKINDOSE_NOTARY_KEY | GUISKINDOSE_NOTARY_KEY_ID | GUISKINDOSE_NOTARY_ISSUER) ;;
            *) env_fail "line $lineno sets an unsupported name" ;;
        esac
        local quoted=""
        if [[ ${#value} -ge 2 && "$value" == \"*\" ]]; then
            value="${value:1:${#value}-2}"
            quoted="double"
        elif [[ ${#value} -ge 2 && "$value" == \'*\' ]]; then
            value="${value:1:${#value}-2}"
            quoted="single"
        fi
        # shellcheck disable=SC2016  # literal text to refuse, not an expansion
        [[ "$value" == *'`'* || "$value" == *'$('* ]] && env_fail "line $lineno contains command substitution"
        if [[ "$name" == GUISKINDOSE_NOTARY_KEY && "$quoted" != single ]]; then
            # shellcheck disable=SC2016,SC2088  # literal prefixes matched, then expanded by hand
            case "$value" in
                '$HOME/'*) value="$HOME/${value#\$HOME/}" ;;
                '${HOME}/'*) value="$HOME/${value#\$\{HOME\}/}" ;;
                '~/'*) value="$HOME/${value#\~/}" ;;
            esac
        fi
        if [[ "$quoted" != single ]]; then
            local rest="$value"
            [[ "$name" == GUISKINDOSE_NOTARY_KEY ]] && rest="${value#"$HOME"}"
            [[ "$rest" == *'$'* ]] && env_fail "line $lineno contains a \$ expansion"
        fi
        is_placeholder "$value" && env_fail "line $lineno still contains <...> placeholder text"
        printf -v "$name" '%s' "$value"
    done
    exec 3<&-
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
        load_env_file "$NOTARY_ENV"
        if [[ "$(count_key_vars)" != 3 ]]; then
            env_fail "it must set all three GUISKINDOSE_NOTARY_* variables"
        fi
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
# notarytool output can carry account identifiers, so it goes to mode-600 files only.
SUBMIT_ERR="$OUT/notary-submit.stderr"
( umask 077; xcrun notarytool submit "$SUBMIT_ZIP" "${NOTARY_AUTH[@]}" --wait \
    --output-format plist > "$RESULT" 2> "$SUBMIT_ERR" ) || true
echo "notarization took $(( $(date +%s) - start )) s"
STATUS="$(/usr/libexec/PlistBuddy -c 'Print :status' "$RESULT" 2>/dev/null || echo unknown)"
SUB_ID="$(/usr/libexec/PlistBuddy -c 'Print :id' "$RESULT" 2>/dev/null || echo)"
echo "notary status: $STATUS"
if [[ "$STATUS" == unknown ]]; then
    echo "notarytool submit failed; see notary-submit.stderr in the output directory" >&2
fi
rm -f "$SUBMIT_ZIP"
if [[ "$STATUS" != "Accepted" ]]; then
    if [[ -n "$SUB_ID" ]]; then
        LOG="$OUT/notary-log.json"
        ( umask 077; xcrun notarytool log "$SUB_ID" "${NOTARY_AUTH[@]}" "$LOG" \
            > "$OUT/notary-log.stdout" 2> "$OUT/notary-log.stderr" ) \
            || echo "notarytool log failed; see notary-log.stderr in the output directory" >&2
        # Print bundle-relative paths only.
        /usr/bin/python3 -I -c '
import json, sys
log = json.load(open(sys.argv[1]))
for issue in log.get("issues") or []:
    severity = issue.get("severity")
    message = issue.get("message")
    path = issue.get("path") or ""
    path = path.split(".app/", 1)[-1] if ".app/" in path else path.rsplit("/", 1)[-1]
    print("%s: %s: %s" % (severity, path, message))
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
