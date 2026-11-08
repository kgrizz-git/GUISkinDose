"""Verify Developer ID seals on a stapled or signed app bundle. Logs counts only."""

from __future__ import annotations

import os
import plistlib
import subprocess
import sys
from pathlib import Path

JIT_KEY = "com.apple.security.cs.allow-jit"
UNSIGNED_KEY = "com.apple.security.cs.allow-unsigned-executable-memory"
GET_TASK = "com.apple.security.get-task-allow"
FORBIDDEN_TEAMS_DEFAULT = "B9A88FL5XJ"


def _team_id(target: Path) -> str:
    proc = subprocess.run(["codesign", "-dv", str(target)], capture_output=True, text=True)
    text = (proc.stderr or "") + (proc.stdout or "")
    for line in text.splitlines():
        if "TeamIdentifier=" in line:
            return line.split("=", 1)[1].strip()
    return ""


def _entitlement_keys(target: Path) -> set[str]:
    proc = subprocess.run(
        ["codesign", "-d", "--entitlements", "-", str(target)],
        capture_output=True,
    )
    if proc.returncode != 0 or not proc.stdout.strip():
        return set()
    try:
        data = plistlib.loads(proc.stdout)
    except Exception:
        return set()
    return set(data) if isinstance(data, dict) else set()


def main() -> int:
    app = Path(sys.argv[1])
    expected = os.environ["GUISKINDOSE_EXPECTED_TEAM_ID"]
    forbidden = {
        part.strip()
        for part in os.environ.get("GUISKINDOSE_FORBIDDEN_TEAM_IDS", FORBIDDEN_TEAMS_DEFAULT).split(",")
        if part.strip()
    }
    chromium_main_jit = os.environ.get("GUISKINDOSE_CHROMIUM_MAIN_NEEDS_JIT", "0") == "1"
    chromium = app / "Contents/Helpers/Chromium.app"
    chromium_main = chromium / "Contents/MacOS/Chromium"
    outer_main = app / "Contents/MacOS/GUISkinDose"
    has_chromium = chromium.is_dir()

    verify_fail = 0
    team_mismatch = 0
    forbidden_hits = 0
    macho_count = 0
    bundle_count = 0
    helper_jit_missing = 0
    outer_bad_ent = 0

    if subprocess.run(["codesign", "--verify", "--deep", "--strict", str(app)], capture_output=True).returncode != 0:
        verify_fail += 1

    for path in sorted(app.joinpath("Contents").rglob("*")):
        if "_CodeSignature" in path.parts:
            continue
        if path.is_dir():
            if path.suffix in {".app", ".framework", ".xpc"}:
                bundle_count += 1
                if subprocess.run(["codesign", "--verify", "--strict", str(path)], capture_output=True).returncode != 0:
                    verify_fail += 1
                tid = _team_id(path)
                if tid and tid != expected:
                    team_mismatch += 1
                if tid in forbidden:
                    forbidden_hits += 1
            continue
        proc = subprocess.run(["file", "-b", str(path)], capture_output=True, text=True)
        if "Mach-O" not in (proc.stdout or ""):
            continue
        macho_count += 1
        if subprocess.run(["codesign", "--verify", "--strict", str(path)], capture_output=True).returncode != 0:
            verify_fail += 1
        tid = _team_id(path)
        if tid and tid != expected:
            team_mismatch += 1
        if tid in forbidden:
            forbidden_hits += 1

        if not has_chromium or path.parent.name != "MacOS":
            continue
        app_bundle = path.parent.parent
        if app_bundle.suffix != ".app" or not str(path).startswith(str(chromium)):
            continue
        keys = _entitlement_keys(path)
        if app_bundle == chromium:
            if chromium_main_jit and JIT_KEY not in keys:
                helper_jit_missing += 1
            if not chromium_main_jit and (JIT_KEY in keys or UNSIGNED_KEY in keys):
                outer_bad_ent += 1
        elif JIT_KEY not in keys:
            helper_jit_missing += 1

    if outer_main.is_file():
        keys = _entitlement_keys(outer_main)
        if GET_TASK in keys or JIT_KEY in keys or UNSIGNED_KEY in keys:
            outer_bad_ent += 1

    print(f"verify_macho_count={macho_count}")
    print(f"verify_bundle_count={bundle_count}")
    print(f"verify_failures={verify_fail}")
    print(f"team_mismatch_count={team_mismatch}")
    print(f"forbidden_team_count={forbidden_hits}")
    print(f"helper_jit_missing_count={helper_jit_missing}")
    print(f"outer_bad_entitlements_count={outer_bad_ent}")

    failed = verify_fail or team_mismatch or forbidden_hits or helper_jit_missing or outer_bad_ent
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
