#!/usr/bin/env bash
# Build a minimal Chromium helper entitlements plist from upstream Mach-O signatures.
#
# Usage (repository root):
#   packaging/portable/macos_build_chromium_helper_entitlements.sh <GUISkinDose.app> <out.plist>
#
# Logs upstream entitlement key names only (never values). The output plist keeps
# com.apple.security.cs.allow-jit and optionally allow-unsigned-executable-memory per
# PORTABLE_MACOS_RELEASE_SIGNING_PLAN.md.
set -euo pipefail
set +x

if [[ $# -ne 2 ]]; then
    echo "usage: $0 <GUISkinDose.app> <out.plist>" >&2
    exit 2
fi
APP="${1%/}"
OUT="$2"
CHROMIUM="${APP}/Contents/Helpers/Chromium.app"
[[ -d "${CHROMIUM}/Contents/MacOS" ]] || {
    echo "Chromium.app missing under Contents/Helpers" >&2
    exit 1
}

python3 -I - "$APP" "$OUT" <<'PY'
import plistlib
import subprocess
import sys
from pathlib import Path

app = Path(sys.argv[1])
out = Path(sys.argv[2])
chromium = app / "Contents/Helpers/Chromium.app"
targets: list[Path] = []
main = chromium / "Contents/MacOS/Chromium"
if main.is_file():
    targets.append(main)
for helper_app in chromium.rglob("*.app"):
    macos = helper_app / "Contents/MacOS"
    if not macos.is_dir():
        continue
    for exe in sorted(macos.iterdir()):
        if exe.is_file() and not exe.name.startswith("."):
            targets.append(exe)
            break

seen_jit = False
seen_unsigned = False
for exe in targets:
    proc = subprocess.run(
        ["codesign", "-d", "--entitlements", "-", str(exe)],
        capture_output=True,
    )
    if proc.returncode != 0 or not proc.stdout.strip():
        continue
    try:
        data = plistlib.loads(proc.stdout)
    except Exception:
        continue
    for key in data:
        print(f"upstream_entitlement_key={key}")
        if key == "com.apple.security.cs.allow-jit":
            seen_jit = True
        if key == "com.apple.security.cs.allow-unsigned-executable-memory":
            seen_unsigned = True

ent: dict[str, bool] = {"com.apple.security.cs.allow-jit": True}
if seen_unsigned:
    ent["com.apple.security.cs.allow-unsigned-executable-memory"] = True
if not seen_jit and not seen_unsigned:
    # Renderer hardened-runtime failure without a JIT key; allow-jit already set.
    pass

out.parent.mkdir(parents=True, exist_ok=True)
out.write_bytes(plistlib.dumps(ent))
PY

chmod 600 "$OUT"
echo "chromium_helper_entitlements=built"
