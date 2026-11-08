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


class EntitlementsParseError(RuntimeError):
    pass


def _team_identifier(target: Path) -> tuple[str | None, bool]:
    """Return (team id or None, True when codesign -dv succeeded)."""
    proc = subprocess.run(["codesign", "-dv", str(target)], capture_output=True, text=True)
    if proc.returncode != 0:
        return None, False
    text = (proc.stderr or "") + (proc.stdout or "")
    for line in text.splitlines():
        if "TeamIdentifier=" in line:
            tid = line.split("=", 1)[1].strip()
            return (tid or None), True
    return None, False


def _entitlement_plist(target: Path) -> dict:
    """Read entitlements via --xml; without it codesign prints a non-plist [Dict] dump."""
    proc = subprocess.run(
        ["codesign", "-d", "--entitlements", "-", "--xml", str(target)],
        capture_output=True,
    )
    if proc.returncode != 0:
        raise EntitlementsParseError("codesign entitlements dump failed")
    raw = proc.stdout.strip()
    if not raw:
        return {}
    try:
        data = plistlib.loads(proc.stdout)
    except Exception as exc:
        raise EntitlementsParseError("entitlements xml parse failed") from exc
    return data if isinstance(data, dict) else {}


def _jit_required(ent: dict) -> bool:
    return ent.get(JIT_KEY) is True


def _record_team(
    team_mismatch: int,
    forbidden_hits: int,
    *,
    expected: str,
    forbidden: set[str],
    tid: str | None,
    dv_ok: bool,
) -> tuple[int, int]:
    """Count a failed display or a missing Team ID as a mismatch, not as unknown."""
    if not dv_ok or tid is None or tid != expected:
        team_mismatch += 1
    if tid in forbidden:
        forbidden_hits += 1
    return team_mismatch, forbidden_hits


def main() -> int:
    app = Path(sys.argv[1])
    expected = os.environ["GUISKINDOSE_EXPECTED_TEAM_ID"]
    forbidden = {
        part.strip()
        for part in os.environ.get("GUISKINDOSE_FORBIDDEN_TEAM_IDS", FORBIDDEN_TEAMS_DEFAULT).split(",")
        if part.strip()
    }
    chromium_main_jit = os.environ.get("GUISKINDOSE_CHROMIUM_MAIN_NEEDS_JIT", "0") == "1"
    edition_full = os.environ.get("GUISKINDOSE_PORTABLE_EDITION", "").lower() == "full"
    chromium = app / "Contents/Helpers/Chromium.app"
    outer_main = app / "Contents/MacOS/GUISkinDose"
    has_chromium = chromium.is_dir()

    verify_fail = 0
    team_mismatch = 0
    forbidden_hits = 0
    macho_count = 0
    bundle_count = 0
    helper_jit_missing = 0
    outer_bad_ent = 0
    entitlements_parse_fail = 0
    chromium_missing = 0

    if edition_full and not has_chromium:
        chromium_missing = 1

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
                tid, dv_ok = _team_identifier(path)
                team_mismatch, forbidden_hits = _record_team(
                    team_mismatch,
                    forbidden_hits,
                    expected=expected,
                    forbidden=forbidden,
                    tid=tid,
                    dv_ok=dv_ok,
                )
            continue
        proc = subprocess.run(["file", "-b", str(path)], capture_output=True, text=True)
        if "Mach-O" not in (proc.stdout or ""):
            continue
        macho_count += 1
        if subprocess.run(["codesign", "--verify", "--strict", str(path)], capture_output=True).returncode != 0:
            verify_fail += 1
        tid, dv_ok = _team_identifier(path)
        team_mismatch, forbidden_hits = _record_team(
            team_mismatch,
            forbidden_hits,
            expected=expected,
            forbidden=forbidden,
            tid=tid,
            dv_ok=dv_ok,
        )

        if not has_chromium or path.parent.name != "MacOS":
            continue
        app_bundle = path.parent.parent
        if app_bundle.name == "Contents":
            app_bundle = app_bundle.parent
        if app_bundle.suffix != ".app" or not str(path).startswith(str(chromium)):
            continue
        try:
            ent = _entitlement_plist(path)
        except EntitlementsParseError:
            entitlements_parse_fail += 1
            continue
        ent_keys = set(ent)
        if app_bundle == chromium:
            if chromium_main_jit and not _jit_required(ent):
                helper_jit_missing += 1
            if not chromium_main_jit and (JIT_KEY in ent_keys or UNSIGNED_KEY in ent_keys):
                outer_bad_ent += 1
        elif not _jit_required(ent):
            helper_jit_missing += 1

    if outer_main.is_file():
        try:
            ent = _entitlement_plist(outer_main)
        except EntitlementsParseError:
            entitlements_parse_fail += 1
            ent = {}
        ent_keys = set(ent)
        if GET_TASK in ent_keys or JIT_KEY in ent_keys or UNSIGNED_KEY in ent_keys:
            outer_bad_ent += 1

    print(f"verify_macho_count={macho_count}")
    print(f"verify_bundle_count={bundle_count}")
    print(f"verify_failures={verify_fail}")
    print(f"team_mismatch_count={team_mismatch}")
    print(f"forbidden_team_count={forbidden_hits}")
    print(f"helper_jit_missing_count={helper_jit_missing}")
    print(f"outer_bad_entitlements_count={outer_bad_ent}")
    print(f"entitlements_parse_fail_count={entitlements_parse_fail}")
    print(f"chromium_missing_count={chromium_missing}")

    macho_empty = 1 if macho_count == 0 else 0
    print(f"macho_empty_count={macho_empty}")

    failed = (
        verify_fail
        or team_mismatch
        or forbidden_hits
        or helper_jit_missing
        or outer_bad_ent
        or entitlements_parse_fail
        or chromium_missing
        or macho_empty
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
