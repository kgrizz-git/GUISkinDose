#!/usr/bin/env python3
"""Give the source-checkout launchers the GUISkinDose icon.

What it does:
    ``ensure`` converges the double-click launcher for the current OS. It
    checks the real artifact each run and writes only what is missing:

    - macOS: sets the app icon on ``GUISkinDose.command`` (Finder custom icon).
    - Windows: writes ``GUISkinDose.lnk`` (target ``run_gui.bat``, app icon)
      unless the existing shortcut already names this checkout.
    - Linux: writes ``GUISkinDose.desktop``, keeps it executable, and marks it
      trusted for GNOME (``gio`` metadata lives outside the checkout).

    There is no state file. Git cannot carry a file icon, so ``run_gui.sh`` and
    ``run_gui.bat`` call this on every launch; repeat runs are quiet.

Inputs:
    Platform, environment, repo root, and subprocess runner are injectable for
    tests. ``GUISKINDOSE_NO_LAUNCHER_SETUP`` (any non-empty value) skips it.

Outputs:
    At most one fixed status line. No absolute paths, user names, exception
    text, or subprocess output are printed. Always exits 0: launcher setup must
    never block the GUI.
"""

from __future__ import annotations

import argparse
import base64
import os
import platform
import subprocess
import sys
from collections.abc import Callable, Mapping
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OPT_OUT = "GUISKINDOSE_NO_LAUNCHER_SETUP"
TIMEOUT_S = 10
COMMAND_NAME = "GUISkinDose.command"
LNK_NAME = "GUISkinDose.lnk"
DESKTOP_NAME = "GUISkinDose.desktop"
# Characters a root path may contain for the .desktop entry. None of them needs
# escaping inside a quoted Exec argument or a Desktop Entry string value.
_DESKTOP_SAFE_PUNCTUATION = frozenset(" _./+@~-")

Runner = Callable[..., subprocess.CompletedProcess[bytes]]

# JXA: argv[0] is the image, argv[1] the target. A nil image would reset the
# icon, so it is checked before setIcon.
_MACOS_SET_ICON = """
ObjC.import('AppKit');
function run(argv) {
  const image = $.NSImage.alloc.initWithContentsOfFile(argv[0]);
  if (image.isNil()) { return 'no-image'; }
  return $.NSWorkspace.sharedWorkspace.setIconForFileOptions(image, argv[1], 0) ? 'ok' : 'failed';
}
"""

# PowerShell: every path arrives as an environment variable, never as script text.
_WINDOWS_SHORTCUT = """
$s = (New-Object -ComObject WScript.Shell).CreateShortcut($env:GSD_LNK)
$s.TargetPath = $env:GSD_TARGET
$s.WorkingDirectory = $env:GSD_ROOT
$s.IconLocation = $env:GSD_ICON + ',0'
$s.Save()
"""


def icon_path(root: Path, suffix: str) -> Path:
    """Return the shipped app icon with ``suffix`` (``.svg`` or ``.ico``)."""
    return root / "src" / "guiskindose" / "gui" / "static" / f"guiskindose_icon{suffix}"


def ensure(
    root: Path = ROOT,
    system: str | None = None,
    env: Mapping[str, str] | None = None,
    run: Runner = subprocess.run,
) -> str:
    """Converge the launcher for ``system`` and return a status line, or ``""``."""
    environ = os.environ if env is None else env
    if environ.get(OPT_OUT):
        return ""
    handlers: dict[str, Callable[[Path, Mapping[str, str], Runner], str]] = {
        "Darwin": _ensure_macos,
        "Windows": _ensure_windows,
        "Linux": _ensure_linux,
    }
    handler = handlers.get(system or platform.system())
    if handler is None:
        return ""
    try:
        return handler(root, environ, run)
    except (OSError, ValueError, subprocess.SubprocessError):
        # ValueError covers UnicodeError. The message is fixed: exception text carries paths.
        return "Launcher setup skipped."


def main(argv: list[str] | None = None) -> int:
    """Run ``ensure`` and print its status line. Always returns 0."""
    parser = argparse.ArgumentParser(description="Set up the double-click GUISkinDose launcher.")
    parser.add_argument("command", choices=["ensure"])
    parser.parse_args(argv)
    status = ensure()
    if status:
        print(status)
    return 0


def _quiet(run: Runner, argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
    """Run ``argv`` with output discarded, no shell, and a timeout."""
    return run(
        argv,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=TIMEOUT_S,
        check=False,
        **kwargs,
    )


def _ensure_macos(root: Path, env: Mapping[str, str], run: Runner) -> str:
    """Set the app icon on ``GUISkinDose.command`` unless it already has one."""
    target = root / COMMAND_NAME
    if not target.is_file():
        return ""
    if _quiet(run, ["xattr", "-p", "com.apple.ResourceFork", str(target)]).returncode == 0:
        return ""
    result = run(
        ["osascript", "-l", "JavaScript", "-e", _MACOS_SET_ICON, str(icon_path(root, ".ico")), str(target)],
        capture_output=True,
        timeout=TIMEOUT_S,
        check=False,
    )
    if result.returncode == 0 and result.stdout.strip() == b"ok":
        return "Launcher icon set."
    # Expected symptom if NSImage cannot read the ICO, or when there is no GUI session (ssh).
    return "Launcher icon not applied."


def _ensure_windows(root: Path, env: Mapping[str, str], run: Runner) -> str:
    """Write ``GUISkinDose.lnk`` pointing at ``run_gui.bat`` with the app icon.

    Skips PowerShell when the shortcut already names this checkout, so a normal
    launch pays nothing; a moved clone gets a fresh shortcut.
    """
    lnk = root / LNK_NAME
    existed = lnk.is_file()
    if existed and shortcut_names_root(lnk, root):
        return ""
    _quiet(run, _powershell_argv(env), cwd=str(root), env=_shortcut_env(root, env))
    # A stale shortcut left by a moved clone must not count as success if PowerShell was blocked.
    if lnk.is_file() and shortcut_names_root(lnk, root):
        return "Launcher shortcut updated." if existed else "Launcher shortcut created: GUISkinDose.lnk"
    return "Launcher shortcut not created."


def shortcut_names_root(lnk: Path, root: Path) -> bool:
    """Return whether ``lnk`` stores ``root`` as its working directory.

    Shell links keep the working directory as UTF-16LE text, so a byte search is
    enough to tell a current shortcut from one left by a moved checkout.
    """
    return str(root).encode("utf-16-le") in lnk.read_bytes()


def _powershell_argv(env: Mapping[str, str]) -> list[str]:
    """Return the constant PowerShell argv; it never contains a path from the checkout."""
    system_root = Path(env.get("SystemRoot") or env.get("SYSTEMROOT") or r"C:\Windows")
    exe = system_root / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    encoded = base64.b64encode(_WINDOWS_SHORTCUT.encode("utf-16-le")).decode("ascii")
    return [str(exe), "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded]


def _shortcut_env(root: Path, env: Mapping[str, str]) -> dict[str, str]:
    """Return the parent environment plus the shortcut paths as ``GSD_*`` variables."""
    return {
        **env,
        "GSD_LNK": str(root / LNK_NAME),
        "GSD_TARGET": str(root / "run_gui.bat"),
        "GSD_ROOT": str(root),
        "GSD_ICON": str(icon_path(root, ".ico")),
    }


def _ensure_linux(root: Path, env: Mapping[str, str], run: Runner) -> str:
    """Write ``GUISkinDose.desktop`` when it is missing or differs."""
    if env.get("WSL_DISTRO_NAME"):
        return ""
    if not desktop_path_is_safe(root):
        return "Launcher shortcut skipped: the checkout path has unsupported characters."
    target = root / DESKTOP_NAME
    if target.is_symlink():
        return "Launcher shortcut skipped."
    content = render_desktop_entry(root).encode("utf-8")
    current = target.is_file() and target.read_bytes() == content
    if current and os.access(target, os.X_OK):
        return ""
    if not current:
        _atomic_write(target, content)
    # A lost executable bit (or a first run where gio failed) is repaired here too.
    target.chmod(0o755)
    _quiet(run, ["gio", "set", str(target), "metadata::trusted", "true"])
    return "" if current else "Launcher shortcut created: GUISkinDose.desktop"


def desktop_path_is_safe(root: Path) -> bool:
    """Return whether every character of ``root`` is safe in a Desktop Entry unescaped."""
    return all(char.isalnum() or char in _DESKTOP_SAFE_PUNCTUATION for char in str(root))


def render_desktop_entry(root: Path) -> str:
    """Return the ``.desktop`` text for a root that passed ``desktop_path_is_safe``."""
    return (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=GUISkinDose\n"
        "Comment=Peak skin dose and 3D skin dose maps\n"
        f'Exec="{root / "run_gui.sh"}"\n'
        f"Path={root}\n"
        f"Icon={icon_path(root, '.svg')}\n"
        "Terminal=true\n"
        "Categories=Science;MedicalSoftware;\n"
    )


def _atomic_write(target: Path, content: bytes) -> None:
    """Write ``content`` to a sibling temp file, then replace ``target``."""
    temp = target.with_name(f".{target.name}.tmp")
    temp.unlink(missing_ok=True)
    try:
        temp.write_bytes(content)
        temp.replace(target)
    finally:
        temp.unlink(missing_ok=True)


if __name__ == "__main__":
    sys.exit(main())
