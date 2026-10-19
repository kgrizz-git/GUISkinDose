# Double-click desktop launchers — GUISkinDose

_Status: in progress (branch `feat/desktop-launchers`, stacked on the app-icon PR)._
_Created: 2026-10-19. Revised after review the same day._
_Related: [PORTABLE_APP_PLAN.md](PORTABLE_APP_PLAN.md) (frozen per-OS app; supersedes this when it ships)._

## Goal

A user who has cloned the repository can start the GUI by double-clicking a file in Finder, Explorer,
or a Linux file manager, and that file shows the GUISkinDose icon after the first run.

This is a stopgap for source checkouts. It reuses `run_gui.sh` / `run_gui.bat`, which already find
Python, enforce the 3.11 floor, offer to create `.venv`, install extras, and pick browser or native
mode. A frozen app from the portable-app plan gets a real bundle icon and makes this unnecessary.

## Why the icon is set on first run

Git stores contents and the executable bit only. A custom file icon (macOS extended attributes,
Windows shortcut metadata, Linux `.desktop` trust metadata) cannot travel through a clone, so the
launcher applies it locally when it runs.

## Design

### Files

| Path | Tracked | Role |
|------|---------|------|
| `GUISkinDose.command` | yes, mode 100755 | macOS double-click entry: `cd "$(dirname "$0")" \|\| exit 1`, run `./run_gui.sh "$@"`, and pause on a non-zero exit so Terminal does not close over the error. |
| `run_gui.sh` / `run_gui.bat` | yes (edited) | Call the setup step once the interpreter is validated (placement below). |
| `scripts/desktop_launchers.py` | yes | Stdlib-only, repo-only (not in the wheel). `ensure` converges the current OS's launcher. |
| `GUISkinDose.lnk` | **no** | Windows shortcut written by `ensure`: target `run_gui.bat`, icon `guiskindose_icon.ico`. |
| `GUISkinDose.desktop` | **no** | Linux desktop entry written by `ensure` in the repo root. |

Both generated files embed absolute paths (and so the user name). They get anchored `.gitignore`
lines (`/GUISkinDose.lnk`, `/GUISkinDose.desktop`) and are added to `never_track_names` in
`dev-docs/privacy_admission_policy.json` so they cannot be force-added.

### Converge, no state file

`ensure` checks the real artifact each run and writes only when it differs. There is no state file,
so nothing can go stale (a `git checkout` that rewrites `GUISkinDose.command` drops its icon
xattrs; a moved clone invalidates absolute paths) and no extra file holds path-derived data.

- **macOS:** if `xattr -p com.apple.ResourceFork GUISkinDose.command` succeeds, the icon is present;
  otherwise apply it.
- **Linux:** render the entry, compare with the bytes on disk, write only on difference. A
  matching entry that lost its executable bit is re-chmodded. GNOME trust lives outside the file,
  so `gio set` is retried quietly every run (bounded by the 10 s timeout); a missing `gio`
  (non-GNOME desktops) is not an error.
- **Windows:** a shell link stores its working directory as a counted UTF-16LE string (a 16-bit
  character count, then the text). An existing `GUISkinDose.lnk` that contains the count plus this
  checkout's root is left alone and PowerShell never starts. Matching the count as well as the text
  makes the check exact, so a checkout renamed to a prefix of its old path
  (`...\GUISkinDose-old` → `...\GUISkinDose`) is rewritten, as is any other moved clone.

Status output is one fixed line, printed only when something was created or failed. No absolute
paths, user names, exception text (`str(OSError)` carries the path), or subprocess output are
printed: every subprocess runs with stdout/stderr discarded, `shell=False`, and a 10 s timeout.
Failures are caught as `OSError`, `ValueError` (covers `UnicodeError`) and `SubprocessError`, and the
step always exits 0.

Platform branching is unavoidable here and is confined to this one script. The platform name, the
environment, the repo root, and the subprocess runner are injectable so tests never touch the real
checkout.

### macOS

- `GUISkinDose.command` opens Terminal on double-click and runs `run_gui.sh`.
- Icon: `osascript -l JavaScript -e <constant script> <icon> <target>`. The JXA `run(argv)` imports
  AppKit, loads `NSImage` from argv[0], returns early if the image is nil (a nil image would *reset*
  the icon), then checks the BOOL from `NSWorkspace.sharedWorkspace.setIconForFileOptions`.
- Image source: the existing multi-size `guiskindose_icon.ico` (ImageIO reads ICO; Finder uses the
  largest frame). If the smoke test shows it unusable, generate a PNG at runtime into `tmp/` with
  `sips` rather than adding a binary asset.
- Needs a GUI session; over ssh it fails quietly.
- The icon lives in extended attributes, which git ignores, so `git status` stays clean.
- Gatekeeper: `git clone` does not quarantine files. A browser-downloaded ZIP does, and on
  macOS 15+ right-click → Open no longer bypasses it: use System Settings → Privacy & Security →
  Open Anyway (approves just that file; recursively stripping quarantine is not recommended, since it
  disables Gatekeeper for everything in the download). The smoke test also checks that
  the GitHub ZIP keeps mode 755 on `.command` and `run_gui.sh`.

### Windows

- A `.bat` cannot carry an icon, so `ensure` writes `GUISkinDose.lnk` via `WScript.Shell`
  `CreateShortcut`: `TargetPath` = `run_gui.bat`, `WorkingDirectory` = repo root,
  `IconLocation` = `<ico>,0`.
- PowerShell is resolved under `%SystemRoot%\System32\WindowsPowerShell\v1.0\` and run with
  `-NoProfile -NonInteractive -EncodedCommand <constant script>`. Paths reach it only as
  `GSD_*` environment variables merged into the full parent environment (PowerShell needs
  `SystemRoot`). No `-ExecutionPolicy Bypass`: execution policy does not govern `-EncodedCommand`,
  and the flag alarms endpoint security on clinical PCs.
- Constrained Language Mode / AppLocker can block `New-Object -ComObject`; that is reported as
  "shortcut not created" and the launcher carries on.

### Linux

- File managers open `.sh` in an editor, so the first launch is `./run_gui.sh` from a terminal.
  That run writes `GUISkinDose.desktop`: `Type=Application`, `Name=GUISkinDose`,
  `Exec="<root>/run_gui.sh"`, `Path=<root>`, `Icon=<root>/…/guiskindose_icon.svg`, `Terminal=true`.
- Quoting: rather than implement both Desktop Entry escaping layers, the entry is written only when
  every character of the root path is a letter, digit, or one of `` _./+@~-`` (space included).
  Those need no escaping inside a quoted `Exec` argument or in string values. Any other path skips
  with one status line.
- Atomic write (temp file + `Path.replace()`, temp removed on failure and git-ignored); an existing
  symlink at the target is never followed.
  `chmod 755`, then best-effort `gio set … metadata::trusted true`.
- Not offered under WSL (`WSL_DISTRO_NAME` set).

### Calling the step

- `run_gui.sh`: right after the final `check_python_version` / "Selected interpreter" line and before
  `setup_dependencies`, so it also runs when the user declines the venv or skips installing (the
  script is stdlib-only and needs no `guiskindose`):
  `if [ -z "${GUISKINDOSE_NO_LAUNCHER_SETUP:-}" ] && [ -f scripts/desktop_launchers.py ]; then "$PYTHON" scripts/desktop_launchers.py ensure || true; fi`
  (`|| true` is required under `set -e`).
- `run_gui.bat`: just before `%PYTHON_CMD% -c "import guiskindose"`, which resets `ERRORLEVEL` for the
  checks that follow. The path is relative (`scripts\desktop_launchers.py`), like the bat's `.venv`
  handling: `%~dp0` would be mangled by delayed expansion when the checkout path contains `!`.
  Guarded by `if exist` and `if not defined GUISKINDOSE_NO_LAUNCHER_SETUP`; stderr to `nul`, no pipe.
  No new `!choice!` / `!install_choice!` tokens (counted by `test_launcher_parity`).
- Opt-out: `GUISKINDOSE_NO_LAUNCHER_SETUP=1`.

### Write containment

Writes go to the repo root (`GUISkinDose.lnk`, `GUISkinDose.desktop`, xattrs on
`GUISkinDose.command`). One exception: GNOME's `gio set` records trust in
`~/.local/share/gvfs-metadata`, outside the checkout; it is best-effort and keyed by path.

## Tests

`tests/unittests/test_desktop_launchers.py` (injected platform, env, root under `tmp_path`, fake runner):

- Dispatch by platform; unknown platform and the opt-out env var are no-ops; WSL is skipped.
- macOS: script text is constant and paths are only argv; xattr present → no osascript call;
  osascript failure / "nil image" → "not applied" line, exit 0.
- Windows: PowerShell argv is constant across roots; paths only in `GSD_*`; parent env (`SystemRoot`)
  kept; no `-ExecutionPolicy`; failure → "not created".
- Windows: a shortcut naming this root skips PowerShell; a stale one is rewritten ("updated").
- Linux (POSIX-only tests; Windows CI runners skip them): exact rendering for a root with a space and a non-ASCII letter; unsafe roots (`%`, `"`, `$`,
  backslash, newline) skip; second run writes nothing; a lost executable bit is repaired; symlink
  target skipped; mode is 755; no temp file left. Test directory names stay valid on Windows.
- Output never contains the root path; exceptions (including `UnicodeEncodeError`) → exit 0.
- `GUISkinDose.command` is 100755 in the git index.
- Launcher static checks: the call sits between the final interpreter check and
  `setup_dependencies` in `run_gui.sh`, carries `|| true`, and both launchers honour the opt-out.

Existing launcher tests set `GUISKINDOSE_NO_LAUNCHER_SETUP=1` (the copied `run_gui.bat` has no
`scripts/` beside it anyway). CI: add `GUISkinDose.command` to the literal `shellcheck` list.
The new script stays under the C901 ≤ 10 and 800-line gates.

## Docs

`README.md` Quick launch, `CHANGELOG.md` (Unreleased → Added), `dev-docs/branding/README.md`,
`dev-docs/index.md`, and a pointer from `PORTABLE_APP_PLAN.md` "What exists today".

## Manual smoke (required before merge)

| OS | Check |
|----|-------|
| macOS (Apple silicon, 15+) | Fresh clone: double-click `.command` starts the GUI; icon shows in Finder; `git status` clean; second run prints nothing. GitHub ZIP: quarantine wording and mode 755. |
| Windows 11 | Double-click `run_gui.bat`: `GUISkinDose.lnk` appears with the icon and launches; clone path with spaces. |
| Ubuntu (GNOME) | `./run_gui.sh` once: `.desktop` appears with the icon and launches after trust. |

## Non-goals

- Desktop, Start Menu, Dock, or `~/.local/share/applications` entries (could be a later opt-in flag).
- Hiding the console/Terminal window; code signing or notarization.
- The running process's Dock icon on macOS (still Python's).

## Open question

Is the ICO usable by `NSImage` on current macOS? Settled by the macOS smoke test.
