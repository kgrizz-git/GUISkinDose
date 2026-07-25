#!/usr/bin/env python3
"""Cross-platform wrapper for dependency auditing.

Uses 'uv audit' if available (scanning the lockfile), otherwise falls back to
'pip-audit' scanning the active environment.
"""

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path


def _load_audit_ignores(repo_root: Path) -> list[str]:
    """Return tracked advisory suppressions from ``[tool.uv.audit]`` in pyproject.toml.

    ``uv audit`` reads this section natively, but ``pip-audit`` has no pyproject
    config, so the fallback path mirrors the same IDs via ``--ignore-vuln`` to keep a
    single source of truth. Combines ``ignore`` and ``ignore-until-fixed``. Degrades to
    an empty list if tomllib is unavailable (Python < 3.11) or the file cannot be parsed.
    """
    try:
        import tomllib
    except ModuleNotFoundError:
        return []
    try:
        with open(repo_root / "pyproject.toml", "rb") as fh:
            data = tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError):
        return []
    audit = data.get("tool", {}).get("uv", {}).get("audit", {})
    ids: list[str] = []
    for key in ("ignore", "ignore-until-fixed"):
        ids.extend(str(v) for v in audit.get(key, []))
    return ids


def main():
    repo_root = Path(__file__).resolve().parent.parent
    
    # Check if uv is installed in the system PATH
    uv_bin = shutil.which("uv")
    
    # Check if uv.lock exists
    lock_file = repo_root / "uv.lock"
    if uv_bin and not lock_file.exists():
        print("INFO: 'uv.lock' not found. Falling back to active environment scan using pip-audit...")
        sys.stdout.flush()
        uv_bin = None
        
    # Check uv version and availability (requires uv >= 0.11.19, the release that unhid 'uv audit')
    if uv_bin:
        try:
            version_out = subprocess.run([uv_bin, "--version"], capture_output=True, text=True, check=True).stdout
            match = re.search(r"uv\s+(\d+)\.(\d+)\.(\d+)", version_out)
            if match:
                major, minor, patch = map(int, match.groups())
                if (major, minor, patch) < (0, 11, 19):
                    print(
                        f"INFO: 'uv' version {major}.{minor}.{patch} is too old "
                        f"(requires 0.11.19+ for 'uv audit'). Falling back to pip-audit..."
                    )
                    sys.stdout.flush()
                    uv_bin = None
            else:
                uv_bin = None
        except Exception:
            uv_bin = None

    # Probe if uv audit subcommand is available
    if uv_bin:
        try:
            probe = subprocess.run([uv_bin, "audit", "--help"], capture_output=True, text=True, cwd=repo_root)
            if probe.returncode != 0:
                print("INFO: 'uv audit' subcommand is not supported by this uv installation. Falling back to pip-audit...")
                sys.stdout.flush()
                uv_bin = None
        except Exception:
            uv_bin = None

    # Print general fallback message if uv was never found in the first place
    if not uv_bin and shutil.which("uv") is None:
        print("INFO: 'uv' not found in PATH. Auditing active Python environment instead using pip-audit...")
        sys.stdout.flush()

    # Pass any extra command line arguments (e.g. ignores) through
    extra_args = sys.argv[1:]
    
    if uv_bin:
        print("Using 'uv audit' to check locked dependencies...")
        sys.stdout.flush()
        
        # Filter out pip-audit specific flags that uv doesn't support
        uv_args = []
        i = 0
        while i < len(extra_args):
            arg = extra_args[i]
            if arg in ("--desc", "--vulnerability-service", "--format", "-f"):
                # Skip this flag and its value if it has one
                i += 1
                if i < len(extra_args) and not extra_args[i].startswith("-"):
                    i += 1
                continue
            if arg.startswith(("--desc=", "--vulnerability-service=", "--format=", "-f=")):
                i += 1
                continue
            uv_args.append(arg)
            i += 1

        # In CI, enforce --locked so a stale uv.lock fails loudly. Locally, use --frozen to audit
        # the committed lockfile as-is and avoid 'uv audit' relocking / downloading a CPython interpreter.
        if os.environ.get("CI"):
            if "--locked" not in uv_args and "--frozen" not in uv_args:
                uv_args.append("--locked")
        else:
            if "--frozen" not in uv_args and "--locked" not in uv_args:
                uv_args.append("--frozen")

        # Reject passthrough args containing shell metacharacters / newlines before
        # handing them to the (shell-less) subprocess call (Sonar S8705).
        for arg in uv_args:
            if any(ch in arg for ch in "\n\r\x00") or arg.strip() != arg:
                raise ValueError(f"unsafe audit argument: {arg!r}")
        try:
            result = subprocess.run(
                [uv_bin, "audit"] + uv_args,
                cwd=repo_root
            )
            sys.exit(result.returncode)
        except FileNotFoundError:
            # Fallback if shutil.which returned a path that is not executable
            pass
            
    # Fallback to pip-audit
    try:
        # Default to include descriptions, but allow overriding/extending via extra_args
        cmd = ["pip-audit"]
        if not any(arg.startswith("--desc") for arg in extra_args):
            cmd.extend(["--desc", "on"])
        # Mirror the tracked [tool.uv.audit] suppressions onto pip-audit (which has no
        # pyproject config) so both audit paths honor the same documented policy.
        tracked_ignores = _load_audit_ignores(repo_root)
        if tracked_ignores:
            print(f"INFO: applying tracked audit suppressions from [tool.uv.audit]: {', '.join(tracked_ignores)}")
            sys.stdout.flush()
            for vuln_id in tracked_ignores:
                cmd.extend(["--ignore-vuln", vuln_id])
        cmd.extend(extra_args)
        
        result = subprocess.run(cmd, cwd=repo_root)
        sys.exit(result.returncode)
    except FileNotFoundError:
        print("ERROR: 'pip-audit' is not installed or not found in PATH.", file=sys.stderr)
        print("Please install pip-audit or uv to run dependency auditing:", file=sys.stderr)
        print("  pip install pip-audit", file=sys.stderr)
        print("  or install development dependencies: pip install -e '.[dev]'", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
