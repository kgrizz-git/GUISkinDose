# Portable executable packaging (research note)

_Status: research only — not an active implementation plan._  
_Created: 2026-07-30._  
_Related backlog: Deferred item in [TO_DO.md](../TO_DO.md)._

## Summary

MyPySkinDose today ships as a **Python package**: `pip install`, then
`python -m mypyskindose --mode gui` (optional `--native` / `gui-native` via pywebview).
There is **no** frozen-app or installer pipeline in this repository.

A **portable desktop executable** is feasible in principle via NiceGUI’s
[`nicegui-pack`](https://nicegui.io/documentation/section_configuration_deployment)
(PyInstaller wrapper), but it is a non-trivial productization project for this
codebase — not a one-afternoon packaging tweak.

## What “portable” would mean here

| Goal | Realistic shape |
|------|-----------------|
| Double-click GUI for non-Python users | Per-OS build (Windows `.exe`, macOS `.app`, Linux binary) |
| USB / zip without Python install | Prefer **onedir** (or zip of onedir) over onefile for faster start and easier debugging |
| One binary for all OSes | **No** — rebuild on each target OS/arch |
| JVM / “wrapped for Java” | **No** — see below |

## Recommended approach (if prioritized)

1. **Tooling:** `nicegui-pack` / PyInstaller; call `ui.run(reload=False, …)`; use `native=True` only with
   `--windowed` when a console-less window is desired (see NiceGUI packaging tips).
2. **Entry:** freeze the existing GUI entry (`python -m mypyskindose --mode gui` path / `run_gui`), not a
   separate toy script.
3. **Must bundle as data:**
   - `src/mypyskindose/phantom_data/` STLs (full + reduced previews)
   - `corrections.db` (or CSV seed path used on first run)
   - GUI help under package `gui/help/`
   - `settings_example.json` / normalization settings JSON as used at runtime
4. **Extras:** decide whether `[export]` / kaleido / reportlab are in the default freeze or optional
   “full” builds (size vs features).
5. **CI:** build on Windows + macOS + Linux runners; upload artifacts privately or as GitHub Release
   assets only after privacy/release gates. Do not commit binaries to the tree.
6. **Smoke:** launch, load example RDSR, calculate, export HTML/PNG on each OS.

Expect **large** artifacts (hundreds of MB+ with scientific stack + phantoms), slower cold start,
Windows AV false positives, and ongoing rebuild cost when dependencies change.

## Out of scope / not recommended

- **Java / JVM wrap** of the dose engine or GUI — Jython cannot run this stack; a JVM rewrite would
  be a different product. If a Java host (PACS, hospital app) must drive MyPySkinDose, prefer:
  - subprocess to CLI or a frozen GUI/CLI, or
  - a local HTTP API with a Java client.
- Embedding via GraalPy / Jep / Py4J for the full NiceGUI + scipy + Plotly stack — high friction,
  weak ROI versus subprocess/API.
- Committing built executables or bundling PHI-bearing fixtures into release zips.

## Preconditions before implementation

- Product decision: who needs double-click installs, and which OS first?
- Size/privacy policy for shipped phantoms and example data in the bundle.
- Maintainer bandwidth for per-OS smoke on each release.
- Spike PR: minimal freeze of GUI on one OS with package-data inclusion proven; document failure
  modes (missing static/NiceGUI data, missing `corrections.db`, path resolution under `_MEIPASS`).

## Pointers

- NiceGUI: [Package for Installation](https://nicegui.io/documentation/section_configuration_deployment)
- Current GUI launch: `run_gui.sh` / `run_gui.bat`, `python -m mypyskindose --mode gui [--native]`
- GUI goals (non-Python users, still Python install today): [plans/GUI_PLAN.md](../plans/GUI_PLAN.md)
