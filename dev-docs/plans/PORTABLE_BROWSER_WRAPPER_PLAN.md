# Portable Full: Unix Chromium pipe wrapper in the frozen bootloader

_Status: in progress (code complete 2026-11-05; frozen macOS and Linux `--png-check` proof still open)._
_Child of [PORTABLE_APP_PLAN.md](PORTABLE_APP_PLAN.md) (Freeze bullet, Phase 0b "Export PNG offline", and the Phase 1 note that frozen macOS and Linux Full builds fail PNG closed)._
_Parent of the shipped Windows path: [archive/PORTABLE_PNG_BUNDLED_BROWSER_PLAN.md](archive/PORTABLE_PNG_BUNDLED_BROWSER_PLAN.md)._

Versions cited below are the lockfile pins: choreographer **1.4.0**, kaleido **1.5.0**, PyInstaller **6.22.3** (`uv.lock`). Line numbers are from those installed trees. A bump of any of the three re-checks the drift test in chunk 1 before the code is assumed still valid.

## Problem

`figure_to_png` passes the bundled browser to Kaleido explicitly (`kopts["path"]`). On macOS and Linux that is not enough. choreographer does not exec Chromium. It execs the frozen bootloader and asks it to run a Python wrapper the bootloader cannot run.

`Chromium.get_cli` (`choreographer/browsers/chromium.py`, lines 239–246) builds, when `platform.system() != "Windows"`:

```text
[sys.executable, <...>/_unix_pipe_chromium_wrapper.py, <browser path>, ...flags]
```

`_chromium_wrapper_path` is `Path(__file__).parent / "_unix_pipe_chromium_wrapper.py"` (lines 34–36). `Browser.open` then `Popen`s that list with the pipe ends on stdin and stdout and a logger pipe on stderr (`choreographer/browser_async.py`, lines 142–153), plus `close_fds=True` and `start_new_session=True` (`chromium.py`, `get_popen_args`, lines 229–234).

In a PyInstaller app `sys.executable` is the bootloader (`packaging/portable/guiskindose.spec` sets `console=False`, line 221). The bootloader runs `packaging/portable/entry.py`. It does not run the wrapper script. `bundled_browser_for_render` therefore returns `None` on frozen macOS and Linux (`src/guiskindose/export/png_browser.py`, lines 87–98), and Full PNG fails closed. Windows never inserts the wrapper (`chromium.py`, lines 247–250), which is why a green Windows `--png-check` says nothing about the other two.

There is no environment variable, launch flag, or Kaleido option that skips the wrapper. The env vars that do exist are unrelated: `CHOREO_ENABLE_DEBUG` (`choreographer/__init__.py`, line 13), `CHOREO_PROXY_SERVER` (`chromium.py`, lines 169–171), and `BROWSER_PATH` (search path and the Kaleido error string at `kaleido/kaleido.py`, lines 195–198). `Browser.__init__` does accept `browser_cls` (`browser_async.py`, lines 88–94 and 120), and `Kaleido.__init__` forwards unknown kwargs (`kaleido/kaleido.py`, line 186), so a subclass could replace `get_cli`. That hook is the wrong place to fix this. See below.

## Why the wrapper exists

Chromium's `--remote-debugging-pipe` reads fd 3 and writes fd 4. The GUI process already has those fds open, so choreographer cannot `dup2` them in-process. The wrapper is a fresh process whose stdin and stdout *are* the pipes. Before any import it does (`choreographer/browsers/_unix_pipe_chromium_wrapper.py`):

| Lines | What |
|------:|------|
| 18–23 | `os.dup2(0, 3)`, `os.dup2(1, 4)`, then `os.set_inheritable` on 3 and 4 |
| 39 | `cli = sys.argv[1:]` |
| 41 | `print` the CLI to stderr (absolute browser path; do not copy this) |
| 43 | `subprocess.Popen(cli, pass_fds=(3, 4))` |
| 46–53 | SIGTERM and SIGINT call `terminate()`, then `wait(5)`, then `kill()`. `wait(5)` raises `subprocess.TimeoutExpired` on expiry, so `kill()` never runs. The gate catches that and then `kill()`s and `wait()`s. |
| 60–66 | `process.wait()`, then `print("{bye}")` |

`{bye}` is required. The wrapper keeps fd 1 open, so Chromium exiting does not EOF the pipe choreographer reads. `channels/pipe.py` line 195 treats `b"{bye}\n"` as channel close. `os.execv` of Chromium would drop that write. The reimplementation must `Popen`, wait, then write the sentinel to fd 1.

The spec collects pure modules into the PYZ (`noarchive=False`, `guiskindose.spec` line 207). The wrapper `.py` is not a loose file in the onedir, and `runpy` of `argv[1:]` would also try to exec the script path as the browser (`cli = sys.argv[1:]`). Reimplement the body. Do not `runpy` the shipped file.

## Chosen fix

Teach the frozen entry to recognize this re-exec, the way `multiprocessing.freeze_support` recognizes `--multiprocessing-fork`, and perform the wrapper body itself.

On `sys.platform != "win32"`, and only when `len(sys.argv) >= 3`, the entry checks whether `sys.argv[1]` ends with `_unix_pipe_chromium_wrapper.py`. A shorter argv is not a wrapper launch: do not read `argv[1]` or `argv[2]`. When it matches, the entry:

1. Runs before `_route_missing_streams()` and before `multiprocessing.freeze_support()` (`entry.py`, lines 128–129). A later gate is too late: `freeze_support` must not run in this child, and nothing may write fd 1. The debugging pipe is fd 1.
2. Treats `sys.argv[2:]` as the Chromium argument vector. Before any `dup2`, the first token must resolve inside `<exe dir>/chromium/` (`Path.resolve` plus `os.path.commonpath`, same idea as `pngcheck._inside`). Any other target, including a path that does not resolve, exits 1 with no write to stdout or stderr and without calling `dup2` or `Popen`. stderr is choreographer's logger pipe (`browser_async.py`, lines 145–149); a message there can carry a path into logistro.
3. Only after that check passes, `dup2`s stdin/stdout onto fds 3 and 4 and marks them inheritable.
4. `Popen`s that vector with `pass_fds=(3, 4)` and no shell. On SIGTERM and SIGINT, `terminate()`, then `wait(5)`. Catch `subprocess.TimeoutExpired`, then `kill()` and `wait()`. Do not copy the wrapper's bare `wait(5)` (`_unix_pipe_chromium_wrapper.py`, lines 51–53): a timeout there raises and skips `kill()`.
5. After `wait`, `os.write(1, b"{bye}\n")` and `SystemExit` with the child return code. `os.write` on fd 1, not `print`, so a replaced `sys.stdout` cannot swallow the sentinel or send it somewhere else.
6. Does not import `guiskindose`, kaleido, or choreographer on this path. The stdlib imports already at the top of `entry.py` stay above the gate; they must not write stdout. Do not add a project import above the gate.

Windows never enters the gate, including when a test or a stray argv contains the suffix. choreographer does not build this argv on Windows (`get_cli`, lines 241–250). `pass_fds` is not called there.

`bootloader_ignore_signals` stays `False` (`guiskindose.spec`, line 218) so the child can install those handlers. Do not set `argv_emulation` on the macOS `BUNDLE` (it is unset today, lines 235–254). The onedir windowed bootloader still filters a `-psn_*` argument; the wrapper argv is not one of those.

### Why this is the least fragile option

| Option | Why it loses |
|--------|----------------|
| Bypass the wrapper and exec Chromium from the parent with `preexec_fn` | `preexec_fn` runs in the forked child of a multithreaded NiceGUI process and can deadlock. It is also skipped when CPython uses `posix_spawn`. |
| Bypass and put the pipes only on stdin/stdout | Chromium ignores those for `--remote-debugging-pipe`. Windows passes handles with `--remote-debugging-io-pipes` (`chromium.py`, lines 291–303). Unix does not. |
| `browser_cls` that rewrites `get_cli` | Kaleido would forward it, but the subclass must copy the flag list at `chromium.py` lines 252–289 or call `super` and splice argv. A choreographer flag change then ships a silent behavior drift. The parent still has to re-exec something that can `dup2` onto 3 and 4, so this is the same bootloader trick plus a second copy of the CLI. |
| `runpy` the wrapper module | The `.py` is inside the PYZ, and `sys.argv[1:]` includes the script path. |
| Ship a second real interpreter | Rejected with Briefcase in Phase 0b. The freeze stays PyInstaller. |

Letting `get_cli` build the command, and making the bootloader honor the one argv shape it already emits, moves with choreographer's flags. The only protocol we copy is the fd handoff and the `{bye}` byte string.

### What breaks when choreographer changes

A unit test reads the installed sources and fails the upgrade when any of these move (chunk 1). Until that test is updated on purpose, do not loosen it.

| Change | Result |
|--------|--------|
| Wrapper filename changes, or another token is inserted before it | The gate does not run. The child falls through toward the GUI with the debug pipe on stdout. PNG fails closed (`BrowserFailedError` → `BundledBrowserUnavailableError`). Same user outcome as today. |
| Fds stop being 3 and 4, or `pass_fds` changes | Chromium starts and the DevTools pipe never connects. The render times out and is classified as a browser failure. |
| `{bye}` sentinel changes (`pipe.py` line 195 or the wrapper `print`) | The parent may not see a clean close (`ChannelClosedError`). Still a browser failure, no path in the message. |
| Wrapper removed and Chromium launched with fds already arranged | The gate does not run. PNG may start working with no entry change. The drift test fails until someone deletes the dead gate. |
| `get_cli` stops putting `sys.executable` first | Same as a rename: the gate never sees the argv. |

No fallback browser is added to paper over a mismatch.

### Bootloader stdout

The develop `pyi_main.c` does not `freopen` stdout in the onedir child. Debug lines go to stderr, and only when bootloader debug is on. The windowed subprocess runtime hook (PyInstaller PR 6364, still the documented windowed behavior) replaces stdin, stdout, or stderr only when the caller left them unset. choreographer sets all three. PyInstaller is not installed in the default `.venv` (it is the `portable` group), so chunk 1 confirms both claims against the 6.22.3 tag before the gate is trusted: the onedir bootloader must not replace an inherited stdout, and the runtime hook must leave an explicit pipe alone.

The gate still has to be first. A write to fd 1 before `dup2` corrupts the DevTools stream, and `--png-check` then fails closed. That failure is the signal to stop and re-plan. It is not a reason to fall back to a system browser.

#### PyInstaller 6.22.3 evidence (Chunk 1, recorded 2026-11-05)

Against tag `v6.22.3`: `bootloader/src/pyi_main.c` does not `freopen` stdout or stdin in the onedir child. `PyInstaller/hooks/rthooks.dat` lists no `pyi_rth_subprocess.py` (PR 6364's Windows-only hook is absent in this release), so Unix child processes inherit explicit stdin/stdout/stderr from choreographer's `Popen`. Frozen archive reads open the file per read (`PyInstaller/loader/pyimod01_archive.py`, lines 59 and 119).

## Browser path

`bundled_browser()` today is `<base>/chromium/chrome.exe` on Windows and `<base>/chromium/chrome` elsewhere (`png_browser.py`, lines 76–80). `base` defaults to `Path(sys.executable).resolve().parent`. On a macOS `.app` that parent is `Contents/MacOS`.

Those names match Windows and Linux. They do not match the macOS build.

| OS | Artifact | Executable `bundled_browser()` must return |
|----|----------|-----------------------------------------------|
| Windows | ungoogled-chromium zip, already pinned | `<exe dir>/chromium/chrome.exe` (unchanged) |
| Linux | ungoogled-chromium-portablelinux `.tar.xz`, not the AppImage | `<exe dir>/chromium/chrome`. The unpack is a directory whose main binary is `chrome`, with the shared libraries beside it (portablelinux packaging; a distro ebuild `doexe`s `chrome`). Copy the directory contents into `chromium/`, not the `chrome` file alone. |
| macOS | ungoogled-chromium-macos `.dmg` | `<exe dir>/chromium/Chromium.app/Contents/MacOS/Chromium`. The dmg contains `Chromium.app`; the Mach-O is `Contents/MacOS/Chromium` (the same path choreographer searches under `/Applications`, `_chrome_constants.py` line 83). **Record-only layout today:** copy with `ditto` into `GUISkinDose.app/Contents/MacOS/chromium/Chromium.app` (sibling of the GUISkinDose Mach-O). Before the first signed Full build, decide whether that stays under `Contents/MacOS/chromium/` or moves to `Contents/Frameworks/chromium/`, then verify with `codesign --verify --deep --strict`, `spctl -a -t exec -vv`, and the notary log. Do not change code paths until that decision is recorded. |

`bundled_browser_for_render()` returns `bundled_browser()` whenever the process is frozen, on every OS. It returns `None` only when not frozen. The macOS and Linux `None` branch and its comment go away in the same change as the gate (chunk 1 lands first; see commits).

Notices stay in the `chromium/` directory, which is `chrome.exe`'s parent on Windows and `chrome`'s parent on Linux. On macOS the Mach-O's parent is `Contents/MacOS`, so `pngcheck._check_bundle` must not use `browser.parent` for notices (`pngcheck.py`, lines 58–61). Resolve the ancestor whose name is `chromium`. Windows then looks at the same directory it looks at today.

`selfcheck._bundled_browser_present` keeps checking for a `chromium/` directory beside the executable. A nested `Chromium.app` still satisfies that.

This plan does not pin macOS or Linux sha256 values, download the artifacts, or sign the nested app. Those stay in [PORTABLE_APP_PLAN.md](PORTABLE_APP_PLAN.md) Phase 0b and Phase 1, and in [references/PORTABLE_CHROMIUM_ARTIFACT.md](../references/PORTABLE_CHROMIUM_ARTIFACT.md).

## Guarantees that stay

Unchanged from the shipped Windows design:

- The bundled path is the Kaleido `path`. `figure_to_png` keeps passing `kopts={"path": str(browser), "mathjax": False}` through `kaleido.calc_fig` on a fresh thread (`kaleido/__init__.py`, `calc_fig`, lines 81–108, `Kaleido(**kopts)`).
- Nothing calls `kaleido.start_sync_server` or `calc_fig_sync`. A running global server drops `kopts` (`kaleido/_sync_server.py`, lines 114–116).
- Missing file, launch failure, timeout, `ChromeNotFoundError`, `BrowserFailedError`, `BrowserClosedError`, `ChannelClosedError`, and `OSError` stay `BundledBrowserUnavailableError`. Anything else stays `PngRenderError`. Kaleido's missing-browser text embeds the absolute path (`kaleido.py`, lines 195–196); callers still log with `safe_error_event` (exception class only).
- No second browser. `BROWSER_PATH` remains a decoy the check sets and the render ignores.
- The wrapper gate writes no log line and no report field. A rejected Chromium argv exits silently. `_quiet_browser_loggers` (`entry.py`, lines 140–151) stays as it is, so choreographer's `Found chromium path:` (`chromium.py`, line 196) cannot reach the file log if the root logger is configured.
- Light still raises `PngExportUnavailableError` before Kaleido is imported. An unfrozen install still calls `fig.to_image`.

## Windows behavior that must not change

- `get_cli` is not patched. Windows still launches `chrome.exe` directly, with no wrapper process and no second bootloader.
- `bundled_browser()` stays `<exe dir>/chromium/chrome.exe`.
- Frozen Windows `figure_to_png` still passes that path, `mathjax=False`, and never the sync server.
- `--self-check`, `--network-probe`, `--png-check`, and `run_gui(native=True)` are unchanged. The wrapper gate returns immediately on `win32`.
- `.github/workflows/portable-spike.yml` is not edited. The Full Windows job's decoy `BROWSER_PATH`, firewall rule, and `chromium/chrome.exe` assertion stay the proof for Windows.
- Notice files stay beside `chrome.exe`. The notice-directory helper must return that same directory.

## Tests

Unit tests run unfrozen. They must not `dup2` the pytest process's real fds 3 and 4. Monkeypatch `os.dup2`, `os.set_inheritable`, `subprocess.Popen`, `os.write`, and `signal.signal`.

| Test | Asserts |
|------|---------|
| Drift | Installed `_unix_pipe_chromium_wrapper.py` still `dup2`s 0→3 and 1→4, `Popen`s with `pass_fds=(3, 4)`, and prints `{bye}`. `pipe.py` still compares `b"{bye}\n"`. `get_cli` source still names `sys.executable` and `_unix_pipe_chromium_wrapper.py` off Windows. |
| Gate, matching argv | `Popen` receives `argv[2:]` and `pass_fds=(3, 4)`. Sentinel write is `b"{bye}\n"` on fd 1. No log record contains the temp path. |
| Gate, `len(sys.argv) < 3` | No read of `argv[1]` or `argv[2]`, no `dup2`, no `Popen`, and the import does not exit. |
| Gate, Chromium path outside `<exe>/chromium` | `SystemExit(1)` before `dup2`. `dup2` and `Popen` are not called, and nothing is written. |
| Gate, signal timeout | The handler's `wait(5)` raising `subprocess.TimeoutExpired` is caught; `kill()` and a follow-up `wait()` still run. |
| Gate, `win32` | Even with the suffix in argv, no `dup2` and no `Popen`. |
| Gate, normal argv | Import of `entry.py` (existing `test_portable_entry.py` fixture) does not exit. `freeze_support` still runs for a non-wrapper import. |
| `bundled_browser` | Windows `chrome.exe`, Linux `chrome`, macOS `Chromium.app/Contents/MacOS/Chromium`, including an explicit `base`. |
| Frozen render | darwin and linux call `calc_fig` with that path and `mathjax=False`, and do not call `start_sync_server`. Missing file raises `BundledBrowserUnavailableError` without calling Kaleido. |
| Unfrozen and Light | Unchanged: `to_image`, and `PngExportUnavailableError` before Kaleido. |
| Notices | A macOS-shaped browser path reads notices from the `chromium/` ancestor. A Windows-shaped path still reads them from `chromium/` next to `chrome.exe`. |
| `ps` row | A command line whose executable is `.../chromium/Chromium.app/Contents/MacOS/Chromium --headless` yields an `exe` that `_inside` accepts and whose name contains `chrom`. The bootloader name `GUISkinDose` does not. |

`--png-check` is the frozen proof. It is not a new CI job. On a Full macOS or Linux build, with `BROWSER_PATH` pointed at a missing decoy:

```text
GUISkinDose --png-check <output-dir>
```

(or `GUISkinDose.app/Contents/MacOS/GUISkinDose` on macOS). The report must show at least one PNG, `launched_outside_onedir == 0`, and a `launched_from_onedir` entry for the bundled binary (`chromium/chrome` or `chromium/Chromium.app/Contents/MacOS/Chromium`). Relative paths only. The name filter in `_describe_launch` (`"chrom"` in the file name) counts `Chromium` and `Chromium Helper`. It does not count the intermediate bootloader, which is the wrapper process and is expected. Phase 0b's "bundled Chromium, not the app bootloader" check is this report, not an empty process list.

Record the run on the Phase 0b checkbox in the parent plan. Until that run exists, do not tick the checkbox.

## CI

This plan does not add a macOS or Linux workflow leg. Those builds download a browser, and macOS also signs. They already have open checkboxes:

- [PORTABLE_APP_PLAN.md](PORTABLE_APP_PLAN.md) Phase 1, "CI builds Windows, macOS, and Linux onedir zips" (Linux launches browser mode; the job records the system libraries the bundled Chromium needs).
- Phase 0b, "Export PNG offline from that Full app."

When either checkbox is implemented, its `--png-check` is the one specified above. No second proof.

## Commits

Chunk 1 before chunk 2. Chunk 2 without the gate makes a frozen macOS or Linux render `Popen` the bootloader, which then falls through into `run_gui` with the DevTools pipe on stdout. That is worse than today's fail-closed `None`. Chunk 1 alone is inert: nothing passes the wrapper argv until render is enabled. Chunk 3 can land with chunk 2 or after it. Chunk 4 is the doc closeout of the code chunks and can share chunk 2's commit or follow it. Do not squash 2 in front of 1.

Each function stays at Ruff C901 ≤ 10. `png_browser.py` is under `src/` and is scanned. `entry.py` and `pngcheck.py` live under `packaging/`, which `scripts/complexity_caps_helpers.py` does not scan (`SCAN_DIRS` is `src` and `scripts`); keep those functions under 10 anyway. The plan file stays under the 800-line doc cap. No paths in logs, reports, or new fixtures. No certificate or secret material.

### Chunk 1 — Entry gate

**Files:** `packaging/portable/entry.py`, `tests/unittests/test_portable_entry.py`.

**Steps:**

1. Add a stdlib-only gate at import time, after the existing stdlib imports and before `_route_missing_streams()`.
2. Match the wrapper suffix only off `win32`, and only when `len(sys.argv) >= 3`. Confine `argv[2]` to `<exe dir>/chromium/` and `SystemExit(1)` silently on failure before any `dup2`. Then `dup2`, `Popen`, signals (catch `subprocess.TimeoutExpired` from `wait(5)`, then `kill()` and `wait()`), `{bye}`.
3. Confirm in the PyInstaller 6.22.3 sources (portable group, not the default `.venv`) that the windowed subprocess hook does not replace an explicit stdin, stdout, or stderr. Note the file and the condition in the commit message. If it does replace them, stop. Do not ship the gate.
4. Add the drift test and the gate tests in the table above. The existing entry-module fixture must still import.

**Verify:**

```bash
uv run --extra dev --extra gui --locked python -m pytest tests/unittests/test_portable_entry.py -q
```

**Windows:** the new tests include a `win32` no-op. No spec change, no workflow change.

### Chunk 2 — Return the bundled path on macOS and Linux

**Depends on chunk 1.**

**Files:** `src/guiskindose/export/png_browser.py`, `tests/unittests/test_png_browser.py`.

**Steps:**

1. Split the relative name: `chrome.exe`, `chrome`, or `Chromium.app/Contents/MacOS/Chromium`. Keep `_host_platform()` so tests do not assign `sys.platform` (the asyncio note in `png_browser.py` still applies).
2. `bundled_browser_for_render()` returns that path when frozen and `None` otherwise. Delete the macOS/Linux fail-closed comment.
3. Replace `test_frozen_unix_fails_closed_but_path_resolves` with the frozen-render assertions in the table. Keep the missing-file, Light, unfrozen, sync-server, and Windows path tests.

**Verify:**

```bash
uv run --extra dev --extra gui --locked python -m pytest tests/unittests/test_png_browser.py tests/unittests/test_gui_figures.py tests/gui/test_export_error_semantics.py -q
uv run --extra dev --extra gui --locked python scripts/check_complexity.py
```

**Windows:** the Windows frozen test still expects `kopts["path"]` to be `chromium/chrome.exe` and `start_sync_server` unused.

### Chunk 3 — Notices and the process-list shape

**Files:** `packaging/portable/pngcheck.py`, `tests/unittests/test_portable_pngcheck.py`.

**Steps:**

1. Resolve notice files from the `chromium/` ancestor of `bundled_browser()`, not from `browser.parent`.
2. Add the macOS-ancestor test and the `ps` command-line test. Do not launch a browser.
3. Leave the Windows CIM sampler, the decoy comment, and the report fields as they are. Relative paths only.

**Verify:**

```bash
uv run --extra dev --extra gui --locked python -m pytest tests/unittests/test_portable_pngcheck.py -q
```

**Windows:** a fixture whose browser is `chromium/chrome.exe` still finds notices in `chromium/`.

### Chunk 4 — Docs

**Files:** `dev-docs/plans/PORTABLE_APP_PLAN.md` (pointer only; do not tick Phase 0b PNG), `dev-docs/MAINTENANCE_LOG.md` Unreleased, `dev-docs/references/PORTABLE_EXECUTABLE_PACKAGING.md` if it still says macOS and Linux Full PNG are fail-closed, `dev-docs/TO_DO.md` only to point the existing portable item at this plan (already linked when this plan was added).

**Steps:**

1. From the Phase 1 wrapper sentence and the Freeze bullet, link this plan. Leave the offline-PNG checkbox open until a frozen `--png-check` is recorded.
2. Maintenance-log entry: the bootloader now performs the Unix pipe-wrapper handoff, and frozen macOS and Linux resolve a bundled browser path. Add a brief [CHANGELOG.md](../../CHANGELOG.md) Unreleased note as well: the pre-push `check_changelog.py` hook requires an entry when `src/` or `tests/` change, even though no macOS or Linux portable zip ships yet. Keep the note unproven-safe (frozen `--png-check` still open). Full release wording stays with Phase 1 acceptance when those zips exist.
3. Archive this plan under `dev-docs/plans/archive/` only after the frozen `--png-check` on both macOS and Linux has been recorded, and move the `dev-docs/index.md` row in that same change. Chunks 1–3 landing without that proof do not archive the plan.

**Verify:**

```bash
uv run --extra dev --extra gui --locked python scripts/check_file_sizes.py
uv run --extra dev --extra gui --locked python scripts/check_doc_freshness.py
```

## Out of scope

- Pinning, fetching, or signing the macOS and Linux Chromium artifacts.
- A macOS or Linux CI job (follow-up location above).
- Turning the sandbox on, batching images into one Kaleido session, or pruning Chromium locales.
- Changing Windows Full PNG, the WebView2 runtime, or Briefcase.
- Editing choreographer or Kaleido.
