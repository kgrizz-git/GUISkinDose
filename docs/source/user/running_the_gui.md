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

After the first run, each OS usually has a file you can double-click, with the GUISkinDose icon.
Setup is best effort; if it cannot finish, the launcher script still works.

| OS | Double-click | Created by |
|----|--------------|------------|
| macOS | `GUISkinDose.command` (opens Terminal) | Tracked; its icon is set on first run |
| Windows | `GUISkinDose.lnk` | The first `run_gui.bat` run |
| Linux | `GUISkinDose.desktop` (GNOME: allow launching if asked) | The first `./run_gui.sh` run, if setup succeeds |

The shortcuts stay inside the checkout and are git-ignored. On Linux, setup is skipped under
WSL, when the checkout path contains characters a desktop file cannot hold, and when
`GUISkinDose.desktop` is a symlink. On Linux, GNOME records the
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
  browser opens it automatically. An HTTP request that carries the token in its query
  string starts a session, on any path. All other HTTP and websocket requests need the
  session cookie. The token stays valid until the server
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
Another local user can therefore still reach its port.
The in-app help page *Loopback scope and local access* covers this in more detail.

## Logging and privacy

The CLI and GUI log to the console (stderr). Native mode has no visible terminal, so
launch it from a shell if you need to read diagnostic output. No log file is written
unless `configure_logging(log_file=...)` is wired at startup; the optional file sink in
`guiskindose.debug` supports rotation and size caps.

The app's default logging does not record file names or paths, because RDSR filenames
often contain patient identifiers. It logs progress and warning messages. File type, size,
and event counts appear only in the opt-in category-tagged output described below. This
guarantee does not cover module-level `DEBUG` output, described below. Extra
category-tagged `DEBUG` output is opt-in through a `debug.json` in the working directory:

```json
{ "GUI": true, "PROCESSING": true, "CALCULATION": true, "RENDERING": true }
```

Some module-level debug lines print without that file. The app's own error logging
redacts identifiers, but debug output may not. Review console output for PHI before
pasting it into an issue.

## PNG export

PNG dose maps, and the dose-map images embedded in XLSX, PDF, HTML, and DOCX reports, are
rendered by Kaleido.
Kaleido needs a Chromium-family browser such as Chrome or Edge installed on the machine.
Without one, PNG export reports an error, and reports show "Image unavailable" in place of
the images. HTML dose maps, JSON, CSV, and the report text and tables still work.

## Platform notes (Tkinter)

Tkinter is optional. Native mode asks pywebview for your screen size, and uses Tkinter only if
pywebview cannot report it. If neither works, the window opens at a default size. The failure
is logged at `DEBUG` level only.

The native **Save As** dialog comes from pywebview, not Tkinter. In native mode, cancelling
that dialog skips the export. Browser-mode exports always go through a normal browser download.

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
