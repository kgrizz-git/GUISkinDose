#!/usr/bin/env bash
# Run ``GUISkinDose --png-check`` on a frozen macOS bundle and assert the PNG report.
#
# Required environment:
#   APP_EXE         Frozen Mach-O (Contents/MacOS/GUISkinDose)
#   PNG_CHECK_LABEL pre_resign | post_resign (basename for the copied report)
#   BROWSER_REL     Relative path under Contents expected in launched_from_onedir
#   SC_SUB          Self-check/pngcheck owned subdir name
#   GUISKINDOSE_CI_OUT Directory for copied reports (default: out)
#
# Optional: GITHUB_ENV for PRE_/POST_ timing keys.
set -euo pipefail

_PORTABLE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./strip_git_from_path.sh disable=SC1091
source "${_PORTABLE_DIR}/strip_git_from_path.sh"

if [[ -z "${APP_EXE:-}" || -z "${PNG_CHECK_LABEL:-}" || -z "${BROWSER_REL:-}" ]]; then
    echo "missing APP_EXE, PNG_CHECK_LABEL, or BROWSER_REL" >&2
    exit 2
fi

SC_SUB="${SC_SUB:-guiskindose-selfcheck}"
CI_OUT="${GUISKINDOSE_CI_OUT:-out}"

append_env() {
    [[ -n "${GITHUB_ENV:-}" ]] || return 0
    printf '%s\n' "$1" >>"$GITHUB_ENV"
}

png_assert() {
    python3 - "$1" "$BROWSER_REL" <<'PY'
import json, sys

data = json.load(open(sys.argv[1]))
render = data["render"]
page = data["page"]
assert data.get("passed"), "png-check did not pass"
assert page["http_script_refs"] == 0
assert render["launched_outside_onedir"] == 0
assert render["png_images"] >= 2
assert render["png_images"] == render["images"]
assert render["png_bytes_total"] > 0
paths = render["launched_from_onedir"]
assert sys.argv[2] in paths, paths
PY
}

run_frozen_png_check() {
    local label="$1"
    local out decoy report wall images rc=0
    out="$(mktemp -d)"
    decoy="$(mktemp -d)"
    trap 'rm -rf "$out" "$decoy"' RETURN

    export BROWSER_PATH="${decoy}/Chromium"
    strip_git_from_path || return 1

    local start=$SECONDS
    set +e
    "$APP_EXE" --png-check "$out"
    rc=$?
    set -e
    wall=$((SECONDS - start))

    report="${out}/${SC_SUB}/pngcheck_report.json"
    if [[ $rc -eq 0 ]] && [[ ! -f "$report" ]]; then
        echo "png-check wrote no report (label=${label})" >&2
        rc=1
    fi
    if [[ $rc -eq 0 ]]; then
        set +e
        png_assert "$report"
        rc=$?
        set -e
    fi
    if [[ $rc -eq 0 ]]; then
        mkdir -p "$CI_OUT"
        set +e
        cp "$report" "${CI_OUT}/pngcheck_report_${label}.json"
        rc=$?
        set -e
    fi
    if [[ $rc -eq 0 ]]; then
        images="$(python3 -c "import json; print(json.load(open('${report}'))['render']['png_images'])")"
        echo "${label}_png_wall_s=${wall} ${label}_png_images=${images}"
        case "$label" in
            pre_resign)
                append_env "PRE_PNG_WALL=${wall}"
                append_env "PRE_PNG_IMAGES=${images}"
                ;;
            post_resign)
                append_env "POST_PNG_WALL=${wall}"
                append_env "POST_PNG_IMAGES=${images}"
                ;;
        esac
    else
        echo "frozen png-check failed label=${label} exit=${rc}" >&2
    fi
    return "$rc"
}

run_frozen_png_check "$PNG_CHECK_LABEL"
