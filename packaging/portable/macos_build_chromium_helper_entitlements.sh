#!/usr/bin/env bash
# Build a minimal Chromium helper entitlements plist from upstream Mach-O signatures.
#
# Usage (repository root):
#   packaging/portable/macos_build_chromium_helper_entitlements.sh <GUISkinDose.app> <out.plist>
#
# Writes <out.plist>.chromium_main_jit with 0 or 1. Logs upstream key names per role only.
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
main = chromium / "Contents/MacOS/Chromium"
targets: list[tuple[str, Path]] = []
if main.is_file():
    targets.append(("chromium_main", main))
for helper_app in chromium.rglob("*.app"):
    if helper_app == chromium:
        continue
    macos = helper_app / "Contents/MacOS"
    if not macos.is_dir():
        continue
    for exe in sorted(macos.iterdir()):
        if exe.is_file() and not exe.name.startswith("."):
            targets.append(("chromium_helper", exe))
            break

def dump_keys(exe: Path) -> set[str]:
    proc = subprocess.run(
        ["codesign", "-d", "--entitlements", "-", str(exe)],
        capture_output=True,
    )
    if proc.returncode != 0 or not proc.stdout.strip():
        return set()
    try:
        data = plistlib.loads(proc.stdout)
    except Exception:
        return set()
    return set(data) if isinstance(data, dict) else set()

jit = "com.apple.security.cs.allow-jit"
unsigned = "com.apple.security.cs.allow-unsigned-executable-memory"
seen_unsigned = False
main_has_jit = False
for role, exe in targets:
    keys = dump_keys(exe)
    print(f"upstream_entitlement_keys_role={role} count={len(keys)}")
    for key in sorted(keys):
        print(f"upstream_entitlement_key={key}")
    if role == "chromium_main" and jit in keys:
        main_has_jit = True
    if unsigned in keys:
        seen_unsigned = True

ent: dict[str, bool] = {jit: True}
if seen_unsigned:
    ent[unsigned] = True

out.parent.mkdir(parents=True, exist_ok=True)
out.write_bytes(plistlib.dumps(ent))
Path(f"{out}.chromium_main_jit").write_text("1" if main_has_jit else "0", encoding="utf-8")
PY

chmod 600 "$OUT" "${OUT}.chromium_main_jit"
echo "chromium_helper_entitlements=built"
