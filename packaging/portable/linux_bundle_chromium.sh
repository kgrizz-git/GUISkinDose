#!/usr/bin/env bash
# Bundle ungoogled-chromium portablelinux into a frozen onedir and record ldd sonames.
#
# Required environment:
#   APP_DIR             PyInstaller onedir (GUISkinDose/)
#   CHROMIUM_URL        Pinned .tar.xz URL
#   CHROMIUM_SHA256     Lowercase hex digest
#   CHROMIUM_BYTES      Expected archive size in bytes
#
# Prints soname lists and counts only (no resolved library paths).
set -euo pipefail

if [[ -z "${APP_DIR:-}" || -z "${CHROMIUM_URL:-}" || -z "${CHROMIUM_SHA256:-}" || -z "${CHROMIUM_BYTES:-}" ]]; then
    echo "missing required environment for Linux Chromium bundle" >&2
    exit 2
fi

append_env() {
    [[ -n "${GITHUB_ENV:-}" ]] || return 0
    printf '%s\n' "$1" >>"$GITHUB_ENV"
}

PORTABLE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$PORTABLE_DIR/../.." && pwd)"

dl="$(mktemp -d)"
archive="${dl}/chromium.tar.xz"
curl -fsSL -o "$archive" "$CHROMIUM_URL"
actual="$(sha256sum "$archive" | awk '{print $1}')"
bytes="$(stat -c%s "$archive")"
if [[ "$actual" != "$CHROMIUM_SHA256" ]]; then
    echo "Chromium sha256 mismatch" >&2
    echo "expected_digest=${CHROMIUM_SHA256}" >&2
    echo "actual_digest=${actual}" >&2
    exit 1
fi
if [[ "$bytes" != "$CHROMIUM_BYTES" ]]; then
    echo "Chromium size mismatch expected_bytes=${CHROMIUM_BYTES} actual_bytes=${bytes}" >&2
    exit 1
fi
echo "chromium_sha256_verified=true archive_bytes=${bytes}"

tar -xJf "$archive" -C "$dl"
tops=( "$dl"/* )
if [[ "${#tops[@]}" -ne 1 || ! -d "${tops[0]}" ]]; then
    echo "expected one top-level directory in the Chromium tarball" >&2
    exit 1
fi

dest="${APP_DIR}/chromium"
mkdir -p "$dest"
cp -a "${tops[0]}/." "$dest/"
test -f "${dest}/chrome"
echo "browser_path=chromium/chrome"

cp "${PORTABLE_DIR}/chromium/LICENSE.chromium.txt" "${PORTABLE_DIR}/chromium/LICENSE.ungoogled-chromium-portablelinux.txt" "$dest"
if ! line="$(cd "$REPO_ROOT" && uv run --no-sync python -I packaging/portable/dump_chromium_credits.py "${dest}/chrome" "${dest}/CREDITS.html")"; then
    exit 1
fi
libs="${line#*product_entries=}"
libs="${libs%% *}"
echo "credits_product_entries=${libs}"
append_env "CREDITS_PRODUCTS=${libs}"
rm -rf "$dl"

chrome="${dest}/chrome"
export LD_LIBRARY_PATH="${dest}${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}"
CHROME="$chrome" CHROMIUM_DIR="$dest" python3 <<'PY'
import os, re, subprocess

chrome = os.environ["CHROME"]
chromium = os.path.abspath(os.environ["CHROMIUM_DIR"])
out = subprocess.run(["ldd", chrome], capture_output=True, text=True, check=True).stdout.splitlines()
bundled, system, missing = [], [], []
for line in out:
    line = line.strip()
    if "not found" in line:
        missing.append(line.split()[0])
        continue
    m = re.match(r"(\S+)\s+=>\s+(\S+)", line)
    if not m:
        continue
    soname, resolved = m.group(1), m.group(2)
    if resolved.startswith(chromium + os.sep) or resolved == chromium:
        bundled.append(soname)
    else:
        system.append(soname)
print(f"bundled_sonames={','.join(bundled)}")
print(f"system_sonames={','.join(system)}")
print(f"not_found_sonames={','.join(missing)}")
print(f"bundled_soname_count={len(bundled)}")
print(f"system_soname_count={len(system)}")
print(f"not_found_soname_count={len(missing)}")
env_path = os.environ.get("GITHUB_ENV")
if env_path:
    with open(env_path, "a", encoding="utf-8") as fh:
        fh.write(f"BUNDLED_SONAMES={','.join(bundled)}\n")
        fh.write(f"SYSTEM_SONAMES={','.join(system)}\n")
        fh.write(f"NOT_FOUND_SONAMES={','.join(missing)}\n")
        fh.write(f"LINUX_BUNDLED_COUNT={len(bundled)}\n")
        fh.write(f"LINUX_SYSTEM_COUNT={len(system)}\n")
        fh.write(f"LINUX_NOT_FOUND_COUNT={len(missing)}\n")
PY
