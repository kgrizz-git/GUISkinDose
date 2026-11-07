#!/usr/bin/env bash
# Bundle ungoogled-chromium into a frozen GUISkinDose.app (CI spike, ad-hoc only).
#
# Required environment:
#   APP_BUNDLE          Path to GUISkinDose.app (under the repo)
#   APP_EXE             Contents/MacOS/GUISkinDose inside that bundle
#   CHROMIUM_URL        Pinned .dmg URL
#   CHROMIUM_SHA256     Lowercase hex digest of the .dmg
#   CHROMIUM_VERSION    Version label for logs (no paths)
#   SC_SUB              Self-check/pngcheck owned subdir name
#
# Optional:
#   GUISKINDOSE_CI_OUT  Directory for copied reports (default: out)
#
# Writes counts and relative browser path names to stdout and appends CI env keys
# to GITHUB_ENV when set. Never prints absolute paths.
# Post-resign ``--png-check`` runs from CI on the unzipped artifact (see portable-spike.yml).
set -euo pipefail

if [[ -z "${APP_BUNDLE:-}" || -z "${APP_EXE:-}" || -z "${CHROMIUM_URL:-}" || -z "${CHROMIUM_SHA256:-}" ]]; then
    echo "missing required environment for macOS Chromium bundle" >&2
    exit 2
fi

SC_SUB="${SC_SUB:-guiskindose-selfcheck}"
CI_OUT="${GUISKINDOSE_CI_OUT:-out}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PORTABLE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export BROWSER_REL="Helpers/Chromium.app/Contents/MacOS/Chromium"
NESTED_REL="Contents/Helpers/Chromium.app"

append_env() {
    [[ -n "${GITHUB_ENV:-}" ]] || return 0
    printf '%s\n' "$1" >>"$GITHUB_ENV"
}

is_macho() {
    [[ "$(file -b "$1")" == *Mach-O* ]]
}

adhoc_sign() {
    codesign --force --sign - "$1"
}

adhoc_resign_app() {
    local app="$1"
    local count=0
    while IFS= read -r -d '' path; do
        if is_macho "$path"; then
            adhoc_sign "$path"
            count=$((count + 1))
        fi
    done < <(find "$app/Contents" -type f ! -path '*/_CodeSignature/*' -print0)
    echo "signed_macho_files=${count}"
    while IFS= read -r -d '' bundle; do
        adhoc_sign "$bundle"
    done < <(find "$app/Contents" -depth -type d \( -name '*.framework' -o -name '*.app' -o -name '*.xpc' \) -print0)
    adhoc_sign "$app"
}

helpers="${APP_BUNDLE}/Contents/Helpers/Chromium.app"
notices="${APP_BUNDLE}/Contents/Resources/chromium"
browser="${helpers}/Contents/MacOS/Chromium"

dl="$(mktemp -d)"
dmg="${dl}/chromium.dmg"
curl -fsSL -o "$dmg" "$CHROMIUM_URL"
actual="$(shasum -a 256 "$dmg" | awk '{print $1}')"
if [[ "$actual" != "$CHROMIUM_SHA256" ]]; then
    echo "Chromium sha256 mismatch" >&2
    echo "expected_digest=${CHROMIUM_SHA256}" >&2
    echo "actual_digest=${actual}" >&2
    exit 1
fi
echo "chromium_version=${CHROMIUM_VERSION:-unknown} sha256_verified=true"

mount_dir="$(mktemp -d)"
hdiutil attach "$dmg" -nobrowse -readonly -mountpoint "$mount_dir" >/dev/null
ditto --norsrc --noextattr --noacl "${mount_dir}/Chromium.app" "$helpers"
hdiutil detach "$mount_dir" >/dev/null
xattr -cr "$helpers"
codesign --verify --strict "$helpers"
echo "nested_verify=passed nested_path=${NESTED_REL}"
append_env "NESTED_VERIFY=passed"

mkdir -p "$notices"
cp "${PORTABLE_DIR}/chromium/LICENSE.chromium.txt" "${PORTABLE_DIR}/chromium/LICENSE.ungoogled-chromium-macos.txt" "$notices"
if ! line="$(cd "$REPO_ROOT" && uv run --no-sync python -I packaging/portable/dump_chromium_credits.py "$browser" "${notices}/CREDITS.html")"; then
    exit 1
fi
libs="${line#*product_entries=}"
libs="${libs%% *}"
echo "credits_product_entries=${libs}"
append_env "CREDITS_PRODUCTS=${libs}"

rm -rf "$dl" "$mount_dir"

mkdir -p "$CI_OUT"
export PNG_CHECK_LABEL=pre_resign
"${PORTABLE_DIR}/macos_frozen_png_check.sh"
echo "wrapper_fds=implied_free"
append_env "WRAPPER_FDS=implied_free"

adhoc_resign_app "$APP_BUNDLE"
codesign --verify --deep --strict "$APP_BUNDLE"
echo "outer_verify=passed browser_path=${BROWSER_REL}"
append_env "OUTER_VERIFY=passed"
