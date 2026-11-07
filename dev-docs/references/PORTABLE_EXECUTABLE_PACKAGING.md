# Portable executable packaging (research note)

_Status: research note. Execution plan: [plans/PORTABLE_APP_PLAN.md](../plans/PORTABLE_APP_PLAN.md) (in progress; payload cleanup plan: [plans/archive/PORTABLE_PHASE1_PAYLOAD_CLEANUP_PLAN.md](../plans/archive/PORTABLE_PHASE1_PAYLOAD_CLEANUP_PLAN.md))._
_Created: 2026-07-30. Updated: 2026-11-05._
_Parent hub: [RELEASES_AND_DISTRIBUTION.md](../RELEASES_AND_DISTRIBUTION.md)._
_Related backlog: Active Work item in [TO_DO.md](../TO_DO.md) (in progress, tracked in [plans/PORTABLE_APP_PLAN.md](../plans/PORTABLE_APP_PLAN.md))._

## Summary

GUISkinDose ships as a **Python package**: `pip install`, then
`python -m guiskindose --mode gui` (optional `--native` / `gui-native` via pywebview).
A **portable desktop application** is in progress under
[plans/PORTABLE_APP_PLAN.md](../plans/PORTABLE_APP_PLAN.md).

A Windows PyInstaller onedir exists. The spec is `packaging/portable/guiskindose.spec`.
The workflow is `.github/workflows/portable-spike.yml`. There is still no installer.
macOS and Linux release zips remain open in the parent plan. PyPI / GitHub
Release process lives in the parent hub and [PUBLISHING.md](../../PUBLISHING.md).

## What “portable” means here

| Goal | Realistic shape |
|------|-----------------|
| Double-click GUI for non-Python users | Per-OS build (Windows `.exe`, macOS `.app`, Linux binary) |
| USB / zip without Python install | Prefer **onedir** (or zip of onedir) over onefile for faster start and easier debugging |
| One binary for all OSes | **No** — rebuild on each target OS/arch |
| JVM / “wrapped for Java” | **No** — see below |

## Frozen packaging implementation

1. **Tooling:** PyInstaller onedir builds via `packaging/portable/guiskindose.spec`.
2. **Entry:** The frozen program is `packaging/portable/entry.py`. It is outside the wheel,
   so `guiskindose.__main__:cli` stays the console script (`entry.py` lines 1–5).
   Windows and macOS call `run_gui(native=True)`. Linux v1 calls `run_gui(native=False)`
   (`entry.py` lines 154–156 for `_native_window`, and line 191 for the `run_gui` call).
3. **Bundled package data:**
   - Phantom files come from `edition.py`: Light is the 28-file starter set; Full is
     every clinical STL except `_reduced_1000t` (92 files).
   - `table_data/*.csv` (spec line 141) and `table_data/*.json` (spec line 142). `resolve_corrections_source`
     (`src/guiskindose/correction_data.py` lines 192–215) only classifies the setting: the default
     (empty or the exact string `corrections.db`) returns `("packaged", None)`. It does not open
     a database file. Later readers use the packaged CSV tables. The spec does not list `corrections.db`.
   - GUI help under package `gui/help/`.
   - `settings_example.json` / normalization settings JSON as used at runtime.
4. **Editions:** Light does not bundle Chromium and disables PNG export. Its native window uses the
   WebView2 runtime already installed on the PC. Full bundles Chromium and the clinical STL set in
   item 3. Neither frozen edition bundles the Fixed Version WebView2 runtime yet.
5. **CI:** `.github/workflows/portable-spike.yml` builds Windows, macOS arm64, and Linux x86_64 Light
   and Full onedir zips ([PORTABLE_MAC_LINUX_CI_BUILDS_PLAN.md](../plans/PORTABLE_MAC_LINUX_CI_BUILDS_PLAN.md)).
   Artifacts expire after seven days and are not committed. macOS release Developer ID signing and
   notarization stay in the parent plan.
6. **Smoke & checks:** Windows Full smokes offline PNG with `GUISkinDose.exe --png-check`. Light proves
   PNG never starts: `to_image` call count stays 0 on every OS. macOS and Linux Full jobs define the
   same frozen `--png-check` assertions as Windows, with a decoy `BROWSER_PATH` and (on macOS Full)
   ad-hoc re-sign after the browser copy. Those steps have not run green on a completed Actions run yet.
   Linux Full prepends `chromium/` to `LD_LIBRARY_PATH` in the wrapper child; the job summary lists sonames
   `ldd` resolves outside the bundle. That proof is wrapper and path containment, not a claim that the
   tarball is self-contained on an air-gapped machine.

Expect **large** artifacts (hundreds of MB with scientific stack + phantoms), slower cold start,
Windows AV false positives, and ongoing rebuild cost when dependencies change.

## Out of scope / not recommended

- **Java / JVM wrap** of the dose engine or GUI — Jython cannot run this stack; a JVM rewrite would
  be a different product. If a Java host (PACS, hospital app) must drive GUISkinDose, prefer:
  - subprocess to CLI or a frozen GUI/CLI, or
  - a local HTTP API with a Java client.
- Embedding via GraalPy / Jep / Py4J for the full NiceGUI + scipy + Plotly stack — high friction,
  weak ROI versus subprocess/API.
- Committing built executables or bundling PHI-bearing fixtures into release zips.

## Current open items before general release

- The Windows spike and package-data proof are done (`--self-check` opens data through `importlib.resources`).
  A default corrections path resolves to packaged data, and a file named `corrections.db` in the working directory is ignored.
- Per-OS release smoke is still open. That includes a zip downloaded through a browser, so Mark of the Web and macOS quarantine are present.
- Green macOS and Linux Full `--png-check` runs from CI, macOS Developer ID signing/notarization, and
  confirmation whether Linux PNG on a clean VM needs packages only root can install.

## Pointers

- Execution plan: [plans/PORTABLE_APP_PLAN.md](../plans/PORTABLE_APP_PLAN.md)
- Unix Chromium pipe wrapper: [plans/PORTABLE_BROWSER_WRAPPER_PLAN.md](../plans/PORTABLE_BROWSER_WRAPPER_PLAN.md)
- Payload cleanup plan: [plans/archive/PORTABLE_PHASE1_PAYLOAD_CLEANUP_PLAN.md](../plans/archive/PORTABLE_PHASE1_PAYLOAD_CLEANUP_PLAN.md)
- NiceGUI: [Package for Installation](https://nicegui.io/documentation/section_configuration_deployment)
- Current GUI launch: `run_gui.sh` / `run_gui.bat`, `python -m guiskindose --mode gui [--native]`
- GUI goals: [plans/GUI_PLAN.md](../plans/GUI_PLAN.md)
