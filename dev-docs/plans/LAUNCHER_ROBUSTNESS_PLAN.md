# Launcher Robustness Plan

_Date: 2026-09-13. Status: active (backlog: `TO_DO.md` "Launcher `set -e`
robustness" + install-default item is separate)._

## Goal

Finish the `run_gui.sh` / `run_gui.bat` hardening that PR94 deliberately
deferred: every interactive branch must reach the mode prompt or exit with a
clear message and an intentional exit code — no silent `set -e` deaths, no
parity gaps between the two launchers, and a version gate that cannot pass on
garbage input. No dose-calculation or package behavior change.

## Background

PR94 (GUI-first README + launcher consistency) fixed the 3.11 floor, added
post-selection interpreter re-validation, the `.bat` skip-install exit-0 flow,
and interpreter-qualified install hints. Reviewers (kilo, deepseek, codex,
cursor) found deeper pre-existing control-flow issues, verified identical on
`main` before PR94, and deferred here:

- `run_gui.sh` runs under `set -e` (line 22), but `setup_venv` (70–98) and
  `setup_dependencies` (110–150) signal decline/failure via `return 1`, and
  both are invoked as bare commands (lines 163, 185). Declining venv creation
  or picking skip-install kills the script with a bare nonzero exit before the
  mode prompt (kilo review).
- `.bat` handles skip-install with `exit /b 0` + rerun text; `.sh` has no
  equivalent — no rerun hint, nonzero exit (deepseek/cursor reviews).
- A broken `.venv/bin/python` skips the friendly version message under
  `set -e` (cursor review).
- `.bat` gained a `.venv`-first bypass (PR94 follow-up: skip the PATH-python
  gate when `.venv\Scripts\python.exe` exists); `.sh` still gates the system
  interpreter first, so a compatible `.venv` is rejected over an older system
  `python3` (same false-rejection shape CodeRabbit flagged for `.bat`).
- `.bat` version parsing is not reliably fail-closed: non-numeric `--version`
  output falls through the `LSS`/`EQU` comparisons (codex review). Threat
  model: a hostile binary at the `.venv` path already runs unconditionally at
  launch, so this guards accidents (corrupt venv), not attackers.

## Scope (in)

1. **`set -e` status handling (`run_gui.sh`)** — capture `setup_venv` /
   `setup_dependencies` outcomes explicitly (e.g. `if ! setup_venv; then …`)
   so decline/skip/failure paths print their existing UX messages and continue
   or exit intentionally. Preserve every current message; change only control
   flow and exit codes.
2. **Skip-install parity** — decide one deliberate contract for both launchers
   (recommend: print manual command + rerun instruction, exit 0, as `.bat`
   does) and implement it in `.sh` without breaking `set -e` elsewhere.
3. **Broken-`.venv` edge (`.sh`)** — missing or non-executable
   `.venv/bin/python` must produce the friendly 3.11 message (or a clear
   venv-repair hint), never a bare `set -e` death or a wrong-version pass.
4. **`.venv`-first gate parity (`.sh`)** — when `.venv/bin/python` exists and
   is executable, skip the system-`python3` gate and validate the venv
   interpreter (mirrors the `.bat` `:validate_selected` bypass). Mind
   `PYTHON_CMD` initialization for the venv-creation path and `set -e`
   interaction; keep the failure behavior identical otherwise.
5. **Version-parse numeric guard (`.bat`)** — reject non-numeric
   `PYTHON_VERSION`/`PYTHON_MAJOR`/`PYTHON_MINOR` with the existing error
   message (e.g. `findstr` numeric check before the `LSS`/`EQU` comparisons).
   Fail closed on unreadable output.

## Scope (out)

- Install-menu default (`[gui]`) vs run-menu default (native `[2]`) —
  separate `TO_DO.md` item, maintainer call (pulls pywebview into defaults).
- Any change to launch behavior on the success path (flags, modes, prompts).
- Dose calculation, packaging, GUI, or docs beyond what these fixes require.

## Validation

- `bash -n run_gui.sh`; `shellcheck` (pre-push hook) clean for touched lines.
- `python scripts/check_doc_freshness.py` if docs are touched.
- Manual smoke matrix, each branch on `.sh` and `.bat` where applicable:
  decline-venv, skip-install, install-fail, old-`.venv` (3.10), missing system
  python + good `.venv`, broken `.venv` binary, malformed `--version`.
- Windows manual smoke is required for `.bat` changes (per `AGENTS.md`
  conventions — note it in the PR/test plan; CI does not execute `.bat`).
- Privacy: launchers must not print file paths or identifiers (existing
  convention); Presidio staged scan clean.

## Acceptance

- Every matrix row ends at the mode prompt or exits with a clear message +
  intentional code; `.sh`/`.bat` agree on skip semantics.
- No `set -e` early-exit remains on any user-decline path.
- Non-numeric version output is rejected with the standard error in `.bat`.
- `TO_DO.md` launcher items checked off; this plan archived with index update.
