# First-Run Onboarding Popup Plan

> **IN REVIEW**
>
> Review findings: [FIRST_RUN_ONBOARDING_PLAN_REVIEW_20260625T070012Z.md](file:///Users/kevingrizzard/MyCode/MyPySkinDose/tmp/FIRST_RUN_ONBOARDING_PLAN_REVIEW_20260625T070012Z.md)

**STATUS: Planned**

## Objective

On first launch of the GUI, show a modal dialog explaining basic usage: supported file types, how to load data, how to run calculations, and how to view/export results. The user can dismiss it permanently via a "Don't show again" checkbox. If unchecked, the popup reappears on every launch until the user checks it.

The preference is persisted in `~/.mypyskindose/gui.json` (the same config file used for native window geometry). Browser mode shows the popup identically.

## Acceptance criteria

- [ ] On first launch (no prior preference): show onboarding modal after the main page renders.
- [ ] Modal explains: file types accepted (RDSR `.dcm`, CSV, TSV, XLSX), how to upload (drag-and-drop or path input), how to run calculation (Settings → Calculate), and where to find results/export.
- [ ] "Don't show again" checkbox persists to `gui.json` (`onboardingDismissed: true`).
- [ ] When dismissed, never show again on any future launch.
- [ ] If unchecked, shows on every subsequent launch.
- [ ] Works in both browser and native modes.
- [ ] Does not block page navigation — user can close the modal without checking the box and still use the app.
- [ ] Modal is dismissible via a "Got it" button, clicking outside the modal, or pressing Escape — the "Don't show again" preference is captured regardless of how the dialog is dismissed.

## Design

### Modal content

The modal uses NiceGUI's `ui.dialog` + `ui.card` pattern. Quasar's `q-dialog` (which `ui.dialog` wraps) already provides a backdrop and click-outside dismissal, so no custom overlay is needed:

```
┌─────────────────────────────────────────────────┐
│  Welcome to MyPySkinDose                         │
│                                                  │
│  MyPySkinDose estimates peak skin dose from      │
│  fluoroscopic X-ray procedures. Here's how to    │
│  get started:                                    │
│                                                  │
│  1. Upload   — Drag-and-drop a DICOM RDSR (.dcm) │
│     file, or import CSV/TSV/XLSX data.           │
│  2. Settings — Choose phantom model and adjust   │
│     physics parameters (optional defaults work). │
│  3. Geometry — Preview beam geometry before      │
│     calculating.                                 │
│  4. Calculate — Run the dose calculation.        │
│  5. Results — View the 3D dose map and PSD.      │
│  6. Export   — Download results as JSON, HTML,   │
│     or PNG.                                      │
│                                                  │
│  All processing runs locally. No data leaves     │
│  your machine.                                   │
│                                                  │
│  [ ] Don't show this again                       │
│                                                  │
│  [ Got it ]                                      │
└─────────────────────────────────────────────────┘
```

### Storage location

Reuse `gui.json` under `~/.mypyskindose/`:

```json
{
  "schema_version": 1,
  "native_window": { ... },
  "onboardingDismissed": true
}
```

The `onboardingDismissed` flag is a top-level boolean. When loading, if the key is absent or `false`, show the modal. When saving, set it to `true`.

### Concurrency, Races, and I/O Considerations

- **Synchronous Disk I/O**: `is_onboarding_dismissed()` calls `load_gui_config()`, which performs synchronous disk reads on the event loop. Given the small size of `gui.json` (under 1 KB) and local-only serving, this introduces negligible latency (< 1 ms), matching the existing pattern for window preference loading.
- **Merge/Save Race in Native Mode**: On first native launch, the native geometry tracker registers and writes to `gui.json` on resize/move. Since `load_gui_config()` and `save_gui_config()` read/write the full JSON dictionary atomically using `Path.replace()`, the two concurrent writers will merge keys (last-writer-wins but without key loss, as both load the current file before updating). The race is minor, best-effort, and acceptable for this state.
- **Multi-Tab Browser Mode**: NiceGUI's `@ui.page("/")` creates a new page tree and modal dialog instance per client connection. If a user opens multiple tabs, each tab independently reads `gui.json`. The user can dismiss the modal in any tab, and the state will persist correctly, but already-open tabs will not close the modal automatically until reloaded.

## Implementation

### 1. `src/mypyskindose/gui/window_prefs.py` — generic config helpers + refactor

Add `load_gui_config()` and `save_gui_config()` that read/write the full JSON dict. Refactor `save_native_window_prefs()` to use them so it **merges** with existing keys (preserving `onboardingDismissed` and any future fields) instead of overwriting the entire file.

```python
# ── generic config helpers (new) ──────────────────────────────────────────

def load_gui_config() -> dict | None:
    """Load the raw gui.json dict; return None on any error."""
    path = config_path()
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except Exception as exc:
        logger.debug("Could not load gui config from %s: %s", path, exc)
        return None


def save_gui_config(data: dict) -> None:
    """Atomically write gui.json using tempfile + replace (cross-platform safe)."""
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    directory = path.parent
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=directory,
        delete=False,
        suffix=".tmp",
    ) as tmp:
        json.dump(data, tmp, indent=2)
        tmp_path = Path(tmp.name)
    tmp_path.replace(path)


# ── refactored save_native_window_prefs ───────────────────────────────────

def save_native_window_prefs(prefs: NativeWindowPrefs) -> None:
    """Save window preferences while preserving other configuration keys."""
    data = load_gui_config() or {}
    data["schema_version"] = SCHEMA_VERSION
    data["native_window"] = {
        "maximized": prefs.maximized,
        "width": prefs.width,
        "height": prefs.height,
        "x": prefs.x,
        "y": prefs.y,
    }
    save_gui_config(data)
```

**Note:** `load_native_window_prefs()` already calls `config_path()` internally, so no change needed there.

### 2. `src/mypyskindose/gui/onboarding.py`

New module. Interacts with the config file **only** via `load_gui_config()` / `save_gui_config()` — never imports `config_path` directly, so unit-test mocking of `window_prefs.config_path` remains effective.

```python
from mypyskindose.debug import dprint

from .window_prefs import load_gui_config, save_gui_config

ONBOARDING_KEY = "onboardingDismissed"


def is_onboarding_dismissed() -> bool:
    """Return True if the user has dismissed the onboarding popup."""
    data = load_gui_config()
    if not data:
        return False
    return bool(data.get(ONBOARDING_KEY, False))


def dismiss_onboarding() -> None:
    """Persist the user's choice to stop showing onboarding."""
    try:
        data = load_gui_config() or {}
        data[ONBOARDING_KEY] = True
        save_gui_config(data)
    except Exception as exc:
        dprint("GUI", f"Failed to persist onboarding dismissal: {exc}")


def reset_onboarding() -> None:
    """Re-enable the onboarding popup (for power users who dismissed by accident)."""
    try:
        data = load_gui_config() or {}
        data[ONBOARDING_KEY] = False
        save_gui_config(data)
    except Exception as exc:
        dprint("GUI", f"Failed to reset onboarding: {exc}")
```

### 3. `gui/app.py` — show modal at startup

After the page layout is built, check the dismissal flag and show the modal if needed. Quasar's `q-dialog` (wrapped by `ui.dialog`) provides its own backdrop; click-outside and Escape-to-dismiss are handled automatically.

A `value-change` listener on the dialog captures the "Don't show again" preference regardless of how the dialog is closed (button, backdrop click, or Escape key):

```python
# Add this import at the top of app.py with the other local imports:
from .onboarding import is_onboarding_dismissed, dismiss_onboarding

# ...

@ui.page("/")
def index():
    # ... existing layout code ...

    # ── onboarding modal ─────────────────────────────────────────────────
    if not is_onboarding_dismissed():
        with ui.dialog() as dialog, ui.card().classes("modern-card w-full max-w-md p-6"):
            ui.label("Welcome to MyPySkinDose").classes("text-h5 q-mb-sm")
            ui.markdown("""
            MyPySkinDose estimates peak skin dose from fluoroscopic X-ray procedures.

            **1. Upload** — Drag-and-drop a DICOM RDSR (`.dcm`) file, or import
            CSV/TSV/XLSX data.

            **2. Settings** — Choose a phantom model and adjust physics parameters
            (defaults usually work).

            **3. Geometry** — Preview beam geometry before calculating.

            **4. Calculate** — Run the dose calculation.

            **5. Results** — View the 3D dose map and peak skin dose (PSD).

            **6. Export** — Download results as JSON, HTML, or PNG.

            All processing runs locally. No data leaves your machine.
            """)
            dont_show = ui.checkbox("Don't show this again").classes("q-mt-md")

            opened = False

            def on_ok():
                dialog.close()

            def on_value_change(e):
                nonlocal opened
                if e.value:
                    opened = True
                elif opened and not e.value:
                    if dont_show.value:
                        dismiss_onboarding()

            dialog.on("value-change", on_value_change)

            with ui.row().classes("justify-end q-mt-md"):
                ui.button("Got it", on_click=on_ok).classes("modern-btn-primary text-white")

        dialog.open()
```

### 4. State integration (optional future enhancement)

If the user dismisses the popup, the `state.onboardingDismissed` flag could be set so other parts of the app (e.g. a "Show onboarding" button in Help) can check it. This is out of scope for v1.

A "Reset onboarding" button or hidden gesture (e.g. triple-click the app title) can be added later for power users who accidentally dismissed it. The `reset_onboarding()` function in `onboarding.py` is ready for this.

### 5. Documentation & Indexing

- Register `FIRST_RUN_ONBOARDING_PLAN.md` under **Execution plans (`plans/`)** in [dev-docs/index.md](file:///Users/kevingrizzard/MyCode/MyPySkinDose/dev-docs/index.md).
- Add the first-run onboarding popup feature entry to [CHANGELOG.md](file:///Users/kevingrizzard/MyCode/MyPySkinDose/CHANGELOG.md) under the unreleased changes.

## Help menu (separate item)

The central Help menu/item is tracked as a separate TO DO item. It is **not** part of this plan.

## Testing

- Unit: `tests/unittests/test_onboarding.py`
  - `is_onboarding_dismissed()` → `False` when file missing / no key / key is `false`.
  - `is_onboarding_dismissed()` → `True` when key is `true`.
  - `dismiss_onboarding()` writes `gui.json` with `onboardingDismissed: true`.
  - `reset_onboarding()` writes `gui.json` with `onboardingDismissed: false`.
  - Corrupt `gui.json` → `is_onboarding_dismissed()` returns `False` (safe default: show onboarding).
- Unit: `tests/unittests/test_window_prefs.py` (additions)
  - `load_gui_config()` returns `None` for missing/corrupt file.
  - `save_gui_config()` writes valid JSON that `load_gui_config()` can read back.
  - `save_gui_config()` preserves existing keys (e.g. `schema_version`, `native_window`) when updating.
  - `save_native_window_prefs()` preserves `onboardingDismissed` when called after `dismiss_onboarding()`.
  - `save_gui_config()` uses atomic write (no partial file left on crash).
- Manual:
  1. Delete `gui.json` → launch → modal appears. Click "Got it" without checking → modal appears again. Verify that the key `onboardingDismissed` is either absent or set to `false` in `gui.json`.
  2. Same flow, check "Don't show again" → modal never appears again. Verify that `onboardingDismissed: true` is saved in `gui.json`.
  3. Check "Don't show again" and dismiss via backdrop click → preference is saved (modal never appears again).
  4. Check "Don't show again" and dismiss via Escape key → preference is saved.
  5. Launch in native mode → modal appears.
  6. Launch in browser mode → modal appears.
  7. Corrupt `gui.json` → app launches, modal appears (safe default).
  8. After dismissing, manually set `onboardingDismissed: false` in `gui.json` → modal reappears on next launch.
  9. Launch native → dismiss onboarding → resize window → quit → relaunch → onboarding does not appear (no data loss from `save_native_window_prefs`).
  10. Run validation scripts: verify that `python scripts/check_doc_freshness.py` executes successfully and reports zero issues/broken links.

## Out of scope

- Multi-language/localization support.
- Per-tab contextual help (tracked separately).
- Help menu / dedicated Help tab (tracked as a separate TO DO item).
- Interactive walkthrough / tooltips on first use.
- Onboarding content changes based on user role or prior experience.
