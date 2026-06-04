# GUI Plan — MyPySkinDose

> See also: [CODEBASE_OVERVIEW.md](CODEBASE_OVERVIEW.md) | [UI_ANALYSIS.md](UI_ANALYSIS.md) | [FEATURE_INVENTORY.md](FEATURE_INVENTORY.md) | [AGENTS.md](../AGENTS.md)

_Last updated: 2026-04-22_

---

## 1. Goal

Build a standalone GUI that lets **non-Python users** (medical physicists, radiologists, radiation safety officers) upload a DICOM RDSR file, configure a patient phantom, run a skin dose calculation, and view/export results — all without touching the command line or editing JSON. All processing is local; no data leaves the machine.

The app must run on **Windows, macOS, and Linux** without platform-specific code paths.

---

## 2. Framework decision: NiceGUI

### 2.1 Why NiceGUI

NiceGUI is the right choice for this project. It runs a local server and renders in a browser (or optionally a native desktop window via `pywebview`), but unlike Streamlit it uses a **reactive, event-driven model** rather than a top-to-bottom script re-run. This makes it much better suited to a multi-step workflow where the user moves between steps non-linearly, changes settings, and re-runs calculations without losing state.

It is also **fully cross-platform** — the same code runs on Windows, macOS, and Linux with no platform-specific branches. The underlying stack (FastAPI + Starlette + a browser renderer) is pure Python and works identically on all three.

Key reasons:

- **`ui.plotly(fig)`** — renders Plotly figures natively, including interactive 3D `Mesh3d` and `Scatter3d` with hover, rotate, zoom, and sliders. Zero changes to existing plotting code.
- **`ui.upload`** — drag-and-drop file upload with callback, handles `.dcm` files directly.
- **`ui.tabs` / `ui.stepper`** — clean multi-step workflow layout.
- **`ui.linear_progress` / `ui.circular_progress`** — progress feedback during calculation.
- **`ui.download`** — file download button for JSON/HTML/PNG export.
- **`ui.slider`, `ui.select`, `ui.number`, `ui.checkbox`, `ui.table`** — all the form widgets needed for settings.
- **Reactive state** — `ui.state` and Python variables update the UI without re-running the whole page.
- **`ui.run(native=True)`** — optional: opens as a real desktop window (no browser tab needed) via `pywebview`. See caveat below.
- **Local-only** — runs on `localhost`, no internet required, no data uploaded anywhere.
- **Async support** — long-running calculations can run in a thread without freezing the UI.

### 2.2 Feature support matrix

| Feature needed | NiceGUI widget | Status |
|---|---|---|
| 3D phantom / dose map (Plotly Mesh3d) | `ui.plotly` | ✅ native |
| Procedure slider (Plotly slider) | `ui.plotly` | ✅ native |
| RDSR file upload | `ui.upload` | ✅ built-in |
| Local file path input | `ui.input` | ✅ built-in |
| Multi-step workflow | `ui.tabs` / `ui.stepper` | ✅ built-in |
| Progress bar during calculation | `ui.linear_progress` | ✅ built-in |
| Spinner | `ui.spinner` | ✅ built-in |
| Dropdowns (phantom model, mesh, orientation) | `ui.select` | ✅ built-in |
| Sliders (k_tab, offsets) | `ui.slider` | ✅ built-in |
| Number inputs (filtration, dimensions) | `ui.number` | ✅ built-in |
| Checkboxes (estimate k_tab, dark mode, etc.) | `ui.checkbox` | ✅ built-in |
| Correction factor table | `ui.table` | ✅ built-in |
| PSD metric display | `ui.label` / `ui.card` | ✅ built-in |
| JSON / HTML / PNG export | `ui.download` | ✅ built-in |
| Notifications / error messages | `ui.notify` | ✅ built-in |
| Dark / light mode | `ui.dark_mode` | ✅ built-in |
| Desktop window (no browser) | `ui.run(native=True)` | ⚠️ see note |

**Native window caveat:** `native=True` uses `pywebview` to open a desktop window instead of a browser tab. It works on all three platforms but has had intermittent blank-window issues on **Windows 11** with some pywebview versions. Default to browser mode (`native=False`); document `native=True` as an optional flag. On macOS and Linux it is generally reliable.

### 2.4 Cross-platform notes

All core dependencies (NiceGUI, Plotly, pydicom, numpy-stl, scipy) are pure-Python or have wheels for Windows/macOS/Linux. Specific things to keep in mind:

| Concern | Detail |
|---------|--------|
| File paths | Always use `pathlib.Path` — never string concatenation with `/` or `\` |
| File dialogs | Use `ui.upload` (browser-based) rather than OS file dialogs — works identically everywhere |
| PDF export (Phase 3) | Use `reportlab` — it has wheels for all platforms. Avoid `weasyprint` (requires GTK on Windows, fragile) |
| `pywebview` (native mode) | Requires `pywebview` package; on Linux also needs `python3-gi` or `python3-webview` system package. Document this clearly. |
| Line endings | Not relevant — NiceGUI serves HTML, no text file issues |
| Shell commands | The `--gui` CLI entry point uses Python only, no shell commands |

### 2.3 Dependencies

Add to `pyproject.toml` as optional `[gui]` extra:

```toml
[project.optional-dependencies]
gui = ["nicegui>=2.0.0"]
```

Add to `requirements.txt` for development:

```
nicegui>=2.0.0
```

Install:

```bash
pip install "mypyskindose[gui]"
# or for development:
pip install nicegui
```

---

## 3. Proposed app structure

```
src/mypyskindose/gui/
  __init__.py
  app.py              # Entry point — ui.run() lives here
  pages/
    upload.py         # Step 1: Upload RDSR + metadata preview
    geometry.py       # Step 2: Geometry preview (plot_setup / plot_procedure)
    settings.py       # Step 3: Phantom + calculation settings form
    calculate.py      # Step 4: Run dose calculation with progress
    results.py        # Step 5: Dose map + PSD + correction factors
    export.py         # Step 6: Export (JSON, HTML, PNG)
  components/
    settings_panel.py # Reusable settings form (phantom, offsets, k_tab, etc.)
    plotly_card.py    # Wrapper: renders a Plotly figure in a ui.card
    results_table.py  # Correction factor breakdown table
  state.py            # Shared app state (dataclass or dict)
```

### Entry point

```bash
python -m mypyskindose --gui
# or directly:
python src/mypyskindose/gui/app.py
```

Wire `--gui` in `main.py`:

```python
elif args.mode == "gui":
    from mypyskindose.gui.app import run_gui
    run_gui()
```

---

## 4. Screen-by-screen design

### Step 1 — Upload RDSR

**Purpose:** Get the RDSR file into the app and show the user what's in it.

**Widgets:**
- `ui.upload` — drag-and-drop `.dcm` file
- `ui.input` — or type a local file path directly
- `ui.select` — "Use example file" dropdown (lists bundled `.dcm` files)
- `ui.button("Load")` — triggers parsing

**On load:**
- Parse with `rdsr_parser` + `rdsr_normalizer`
- `ui.notify("Loaded N events")` on success, `ui.notify(..., type='negative')` on error
- Show summary: number of events, device model, total air kerma
- Show per-event table (`ui.table`): event index, kVp, beam angles, field size

**State saved:** parsed DataFrame, file path

---

### Step 2 — Geometry Preview _(optional)_

**Purpose:** Visually verify phantom placement and beam geometry before calculating.

**Widgets:**
- Phantom model `ui.select`: `plane`, `cylinder`, `human`
- Human mesh `ui.select` (conditional): `hudfrid`, `adult_male`, etc.
- Patient orientation `ui.radio`: `head_first_supine`, `feet_first_supine`
- Patient offset `ui.number` × 3: d_lon, d_ver, d_lat
- `ui.button("Preview setup")` → runs `mode="plot_setup"`, shows `ui.plotly(fig)`
- Event index `ui.slider` + `ui.button("Preview event")` → runs `mode="plot_event"`
- `ui.button("Preview full procedure")` → runs `mode="plot_procedure"` (all events + slider)

These are fast (no dose calculation), so they run synchronously on button click.

---

### Step 3 — Settings

**Purpose:** Configure all calculation parameters with sensible defaults and tooltips.

Organised into `ui.expansion` (collapsible) sections:

**Phantom:**
- Model, human mesh, orientation, offsets (same as Step 2, kept in sync)

**Physics:**
- `ui.checkbox("Use estimated k_tab")` — if checked, show `ui.slider(0.0, 1.0)` for k_tab value
- `ui.number("Inherent filtration (mmAl)")` — default 3.1
- `ui.checkbox("Remove invalid RDSR rows (kVp=0)")`

**Output:**
- `ui.checkbox("Plot dose map after calculation")`
- `ui.checkbox("Dark mode")`
- `ui.select("Dose map colorscale")` — jet, viridis, plasma, etc.

**Validation:** `ui.notify` warnings for out-of-range values (e.g. k_tab > 1.0).

---

### Step 4 — Calculate

**Purpose:** Run the dose calculation with visible progress feedback.

**Widgets:**
- Read-only settings summary (`ui.card`)
- `ui.button("Run Calculation")` — triggers async calculation
- `ui.linear_progress` — updates as events are processed
- `ui.label` — "Processing event N of M..."
- On completion: `ui.notify("Done! PSD = X.X mGy", type='positive')`

**Implementation:** Run `main()` in a background thread via `asyncio.run_in_executor` or `run.io_bound()` so the UI stays responsive.

**Error handling:** Catch exceptions, show `ui.notify(str(e), type='negative')` with a copy-to-clipboard button for the traceback.

---

### Step 5 — Results

**Purpose:** Display the dose map and correction factor breakdown.

**Widgets:**
- `ui.card` metric tiles: PSD (mGy), air kerma (mGy), number of events
- `ui.plotly(dose_map_fig)` — interactive 3D dose map, full rotate/zoom/hover
- `ui.select("Colorscale")` — updates the figure reactively
- `ui.button` camera presets: AP, LAT, PA (update Plotly camera via `fig.update_layout`)
- `ui.table` — per-event correction factors (k_isq, k_bs, k_med, k_tab), sortable

---

### Step 6 — Export

**Purpose:** Save results in useful formats.

**Widgets:**
- `ui.button("Download JSON")` → `ui.download(json_bytes, "results.json")`
- `ui.button("Download dose map HTML")` → `ui.download(html_bytes, "dosemap.html")`
- `ui.button("Download dose map PNG")` → saves via kaleido, then `ui.download`
- _(Phase 3)_ `ui.button("Download PDF report")` → generated report

---

## 5. Layout

NiceGUI uses a left-drawer + main-area pattern naturally:

```
┌─────────────────────────────────────────────────────┐
│  MyPySkinDose                          [dark mode 🌙] │
├──────────────┬──────────────────────────────────────┤
│              │                                       │
│  📁 File     │   Main content area                   │
│  📊 47 events│   (changes per tab)                   │
│  👤 hudfrid  │                                       │
│  🔧 k_tab:0.8│                                       │
│              │                                       │
│  [1] Upload  │                                       │
│  [2] Geometry│                                       │
│  [3] Settings│                                       │
│  [4] Calculate│                                      │
│  [5] Results │                                       │
│  [6] Export  │                                       │
│              │                                       │
│  [▶ Run]     │                                       │
└──────────────┴──────────────────────────────────────┘
```

Implemented with `ui.left_drawer` + `ui.tabs` (or `ui.stepper`).

---

## 6. State management

NiceGUI is reactive — state lives in plain Python objects. A simple dataclass in `state.py`:

```python
from dataclasses import dataclass, field
import pandas as pd
from mypyskindose.settings import PyskindoseSettings

@dataclass
class AppState:
    rdsr_df: pd.DataFrame | None = None
    file_path: str | None = None
    settings: PyskindoseSettings | None = None
    output: dict | None = None
    calculation_done: bool = False

state = AppState()  # single shared instance
```

Helper functions:
- `build_settings_from_ui()` → constructs `PyskindoseSettings` from current widget values
- `reset_results()` → clears `output` and `calculation_done` when settings change

---

## 7. Async calculation

NiceGUI has built-in support for running blocking code without freezing the UI:

```python
from nicegui import run

async def on_calculate_click():
    progress.visible = True
    result = await run.io_bound(main, file_path=state.file_path, settings=state.settings)
    state.output = result
    progress.visible = False
    ui.notify(f"Done! PSD = {result['psd']:.1f} mGy", type='positive')
```

For per-event progress updates, wrap `tqdm` with a callback that calls `progress.set_value(event / total)`.

---

## 8. Wiring into the CLI

In `main.py`:

```python
elif args.mode == "gui":
    from mypyskindose.gui.app import run_gui
    run_gui()
```

In `gui/app.py`:

```python
from nicegui import ui

def run_gui(native: bool = False):
    # ... build all pages ...
    ui.run(title="MyPySkinDose", native=native, reload=False)
```

Users can do:

```bash
python -m mypyskindose --gui
# or for desktop window mode (optional, requires pywebview):
python -m mypyskindose --gui --native
```

---

## 9. Implementation phases

### Phase 1 — Minimal working app (implemented, continuing refinement)

Goal: upload RDSR → configure phantom → run calculation → see PSD + dose map.

Files to create:
- `src/mypyskindose/gui/__init__.py`
- `src/mypyskindose/gui/app.py` — single-file NiceGUI app
- `src/mypyskindose/gui/state.py` — shared state dataclass

Functionality:
- File upload + example file selector
- Phantom model + mesh selector
- k_tab slider
- Run button with progress bar
- PSD metric display
- Dose map `ui.plotly` figure

### Phase 2 — Full multi-step app (~3–4 more days)

- Left drawer navigation
- Geometry preview (plot_setup, plot_event, plot_procedure)
- Full settings form with validation
- Correction factor table
- JSON + HTML + PNG export

### Phase 2b — Tabular input workflow

- Extend upload acceptance from DICOM RDSR/JSON to `.csv`, `.tsv`, `.xlsx`, and `.xlsm`.
- Add source-schema selection and Excel sheet selection.
- Reuse the shared input adapter registry planned in `dev-docs/TABULAR_RDSR_INPUT_PLAN.md`.
- Show import provenance, unit conversions, missing columns, and warnings before calculation.

### Phase 3 — Report generation (~2–3 more days)

- PDF report via `reportlab` (pure Python, wheels for Windows/macOS/Linux — do **not** use `weasyprint`)
- Report template: dose map image, metadata, correction table, PSD value
- Add `report` optional dependency: `pip install "mypyskindose[report]"`

### Phase 4 — Polish (~1–2 days)

- Tooltips on every setting explaining the physics (k_tab, HVL, etc.)
- Human-readable error messages (not raw Python tracebacks)
- Custom CSS for a clean clinical look
- `--native` flag for desktop window mode (with pywebview)

---

## 10. Open questions

1. **Calculation time:** How long does a typical RDSR take? If >30 seconds, the async approach in §7 is essential. Worth benchmarking with the bundled example files before building the UI.

2. **Native window mode:** `ui.run(native=True)` requires `pywebview`. Works on macOS and Linux reliably; has had blank-window issues on Windows 11 with some pywebview versions. Default to browser mode; offer `--native` as an opt-in flag with a note in the docs about the Windows caveat.

3. **Linux pywebview dependency:** On Linux, `pywebview` needs a system-level WebKit package (`python3-gi` + `gir1.2-webkit2-4.0` on Debian/Ubuntu, or equivalent). This is only needed for `--native` mode — browser mode has no system dependencies beyond Python.

4. **Single-file vs package:** For Phase 1, a single `app.py` is easiest. Refactor into pages/components in Phase 2.

---

## 11. Immediate next steps

1. Add `nicegui>=2.0.0` to `requirements.txt` and as `[gui]` optional dep in `pyproject.toml`
2. Install: `pip install nicegui`
3. Create `src/mypyskindose/gui/__init__.py` (empty)
4. Create `src/mypyskindose/gui/state.py`
5. Create `src/mypyskindose/gui/app.py` — Phase 1 single-page app
6. Test with bundled example RDSR files
7. Wire `--gui` in `main.py`
