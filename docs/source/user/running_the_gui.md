# Running the GUI

This page covers launch options, local access, logging, and platform notes for the
GUISkinDose graphical interface. Install steps are on the [Installation](install.md) page.

## Launching

After installing `guiskindose[gui]`, start the GUI:

```bash
guiskindose --mode gui            # opens in your browser
guiskindose --mode gui --native   # own window; needs guiskindose[gui-native]
```

`python -m guiskindose --mode gui [--native]` is equivalent.

### From a source checkout

The launcher scripts also set up the interpreter and dependencies.

**macOS / Linux:**

```bash
chmod +x run_gui.sh   # one-time setup, enables executing the sh script
./run_gui.sh
```

**Windows:**

```bat
run_gui.bat
```

Both scripts prompt you to run in browser mode (option 1) or native window mode
(option 2, default).

### Double-click launchers

After the first run, each OS has a file you can double-click, with the GUISkinDose icon:

| OS | Double-click | Created by |
|----|--------------|------------|
| macOS | `GUISkinDose.command` (opens Terminal) | Tracked; its icon is set on first run |
| Windows | `GUISkinDose.lnk` | The first `run_gui.bat` run |
| Linux | `GUISkinDose.desktop` (GNOME: allow launching if asked) | The first `./run_gui.sh` run |

The shortcuts stay inside the checkout and are git-ignored. On Linux, GNOME records the
"allow launching" trust flag in its own metadata store under your home folder. Set
`GUISKINDOSE_NO_LAUNCHER_SETUP=1` to skip creating them. On macOS, a checkout downloaded
as a ZIP is quarantined: allow it under System Settings → Privacy & Security → Open
Anyway. A `git clone` is not quarantined.

## Local-only access

The GUI has no user accounts and keeps the loaded study in one shared, in-process state.
It always binds to `127.0.0.1` (localhost) and refuses any other host. There is no LAN or
remote mode. Do not expose it with a proxy. Run the GUI on the machine where the data may
reside instead.

Browser mode adds three protections on top of loopback binding (see
`src/guiskindose/gui/loopback_security.py`):

- **Per-launch token.** The console prints a launch URL with a random secret, and the
  browser opens it automatically. Only that URL starts a session. Every other HTTP and
  websocket request needs the session cookie. The URL stays valid until the server
  restarts, so a second browser profile or a cleared cookie does not lock you out. After
  a restart, old tabs stop working; use the new console URL.
- **Strict Host validation.** Only the loopback address is accepted, which blocks DNS
  rebinding.
- **Origin validation.** Websocket and HTTP requests that carry a foreign `Origin` are
  rejected as cross-site.

Loopback binding is per machine, not per user. Anyone logged into the same machine who
has the launch URL or an active session sees the same state. On shared workstations, use
one operator at a time or per-operator machines. Native mode enforces the same Host and
Origin checks but has no launch token, because the embedded window is the trusted client.
The in-app help page *Loopback scope and local access* covers this in more detail.

## Logging and privacy

The CLI and GUI log to the console (stderr). Native mode has no visible terminal, so
launch it from a shell if you need to read diagnostic output. No log file is written
unless `configure_logging(log_file=...)` is wired at startup; the optional file sink in
`guiskindose.debug` supports rotation and size caps.

The app does not log file names or paths, because RDSR filenames often contain patient
identifiers. It logs only file type, size, and event counts. Verbose `DEBUG` output is
opt-in per category through a `debug.json` in the working directory:

```json
{ "GUI": true, "PROCESSING": true, "CALCULATION": true, "RENDERING": true }
```

Identifiers stay redacted with debug enabled. Still, review console output for PHI before
pasting it into an issue.

## Platform notes (Tkinter)

The GUI works fully without Tkinter. It uses Tkinter for the native **Save As** dialog
when exporting and to size the native window to your screen. Without it, you see a log
line such as `No module named '_tkinter'`. Exports then fall back to a browser download,
and the window opens at a default size.

Tkinter ships with Python but is built only when the Tcl/Tk libraries are present, so it
can be missing (commonly with `pyenv` builds). It is not a pip package. To install it:

| Platform | Command |
|---|---|
| macOS, Homebrew Python | `brew install python-tk` (or `python-tk@3.12` for a specific version) |
| macOS, pyenv Python | `brew install tcl-tk`, then reinstall the interpreter: `pyenv install 3.12.9` |
| Debian / Ubuntu | `sudo apt install python3-tk` |
| Fedora | `sudo dnf install python3-tkinter` |
| Windows | Included with the python.org installer; keep "tcl/tk and IDLE" checked |

Verify with `python -c "import tkinter; print(tkinter.TkVersion)"`.

Native window mode remembers the last window size, position, and maximized state in
`~/.guiskindose/gui.json`. The first launch opens maximized. An existing
`~/.mypyskindose/gui.json` is still read when the new file is absent.
