# First-Run Onboarding Popup Plan

## Objective

On first launch of the GUI, show a modal dialog explaining basic usage: supported file types, how to load data, how to run calculations, and how to view/export results. The user can dismiss it permanently via a "Don't show again" checkbox. If unchecked, the popup reappears on every launch until the user checks it.

The preference is persisted in `~/.mypyskindose/gui.json` (the same config file used for native window geometry). Browser mode shows the popup identically.

**Status:** Completed 2026-06-25.

## Acceptance criteria

- [x] On every page render where `gui.json` lacks or has `onboardingDismissed: false`, the modal opens after the main page renders (the flag is read from disk on each render, so the modal reappears on relaunch until dismissed).
- [x] Modal explains: file types accepted (RDSR `.dcm`, CSV, TSV, XLSX), how to upload (drag-and-drop or path input), how to run calculation (Settings → Calculate), and where to find results/export.
- [x] "Don't show again" checkbox persists to `gui.json` (`onboardingDismissed: true`).
- [x] When dismissed, never show again on any future launch.
- [x] If unchecked, shows on every subsequent launch.
- [x] Works in both browser and native modes.
- [x] Does not block use of the app after dismissal — user can close the modal without checking the box and continue navigating normally.
- [x] Modal is dismissible ONLY via a "Got it" button (persistent modal; no backdrop/Escape dismissal).
- [x] Plan is registered in `dev-docs/index.md` under **Archived plans (`plans/archive/`)**.
- [x] Feature entry added to `CHANGELOG.md` under `[Unreleased] → Added`.

## Design

### Modal content

The modal uses NiceGUI's `ui.dialog` + `ui.card` pattern.

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

The `onboardingDismissed` flag is a top-level boolean. When loading, if the key is absent or `false`, show the modal. When saving, set it to `true`. Writes must preserve the existing `schema_version` and `native_window` keys.

`load_gui_config()` treats missing, corrupt, and non-object JSON as `{}`. Corrupt/non-object files are backed up best-effort before the app rewrites `gui.json`; backup failures must not prevent startup.

## Implementation

### 1. `src/mypyskindose/gui/window_prefs.py` — generic config helpers + refactor

Add `load_gui_config()` and `save_gui_config()` that read/write the full JSON dict. Refactor `save_native_window_prefs()` to use them so it **merges** with existing keys.

```python
# ── generic config helpers (new) ──────────────────────────────────────────

from typing import Any


def _backup_bad_gui_config(path: Path) -> None:
    """Best-effort backup; never let a broken backup block GUI startup."""
    if not path.exists():
        return
    target = path.with_suffix(".json.corrupt")
    try:
        path.replace(target)
    except Exception as exc:
        logger.debug("Could not back up bad gui config from %s to %s: %s", path, target, exc)


def load_gui_config() -> dict[str, Any]:
    """Load the raw gui.json dict; return {} if missing or corrupt (backs up corrupt file)."""
    path = config_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except Exception as exc:
        logger.debug("Could not load gui config from %s: %s", path, exc)
        _backup_bad_gui_config(path)
        return {}
    if not isinstance(data, dict):
        logger.debug("Ignoring non-object gui config from %s", path)
        _backup_bad_gui_config(path)
        return {}
    return data


def save_gui_config(data: dict[str, Any]) -> None:
    """Atomically write gui.json using tempfile + replace (cross-platform safe)."""
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    directory = path.parent
    tmp_path: Path | None = None
    try:
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
    except Exception:
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)
        raise


# ── refactored save_native_window_prefs ───────────────────────────────────

def save_native_window_prefs(prefs: NativeWindowPrefs) -> None:
    """Save window preferences while preserving other configuration keys."""
    data = load_gui_config()

    # Assumes SCHEMA_VERSION is already defined/imported in this module
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

New module. Interacts with the config file **only** via `load_gui_config()` / `save_gui_config()`; it does not import `config_path` directly, so tests can monkeypatch `window_prefs.config_path` once.

```python
from mypyskindose.debug import dprint

from .window_prefs import load_gui_config, save_gui_config

ONBOARDING_KEY = "onboardingDismissed"


def is_onboarding_dismissed() -> bool:
    """Return True if the user has dismissed the onboarding popup."""
    data = load_gui_config()
    return bool(data.get(ONBOARDING_KEY, False))


def dismiss_onboarding() -> None:
    """Persist the user's choice to stop showing onboarding."""
    try:
        data = load_gui_config()
        data[ONBOARDING_KEY] = True
        save_gui_config(data)
    except Exception as exc:
        dprint("GUI", f"Failed to persist onboarding dismissal: {exc}")


def reset_onboarding() -> None:
    """Re-enable the onboarding popup (for power users who dismissed by accident)."""
    try:
        data = load_gui_config()
        data[ONBOARDING_KEY] = False
        save_gui_config(data)
    except Exception as exc:
        dprint("GUI", f"Failed to reset onboarding: {exc}")
```

### 3. `gui/app.py` — show modal at startup

After the page layout is built, check the dismissal flag and show the modal if needed. Use `.props("persistent")` to force the user to click the "Got it" button, ensuring the checkbox state is accurately captured.

Open the dialog through a one-shot timer so it appears after the page tree is created rather than during initial element construction.

#### Module-level import

Add this import at the top of `app.py` with the other local imports:

```python
from textwrap import dedent

from .onboarding import is_onboarding_dismissed, dismiss_onboarding
```

#### Page handler addition

Inside `index()`, after the existing layout code, add:

```python
    # ── onboarding modal ─────────────────────────────────────────────────
    if not is_onboarding_dismissed():
        with ui.dialog().props("persistent") as dialog, ui.card().classes("modern-card w-full max-w-md max-h-[80vh] p-6"):
            with ui.row().classes("w-full justify-between items-center q-mb-sm"):
                ui.label("Welcome to MyPySkinDose").classes("text-h5")

            with ui.scroll_area().classes("w-full"):
                ui.markdown(dedent("""
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
                """).strip())
            dont_show = ui.checkbox("Don't show this again").classes("q-mt-md")

            def on_ok():
                if dont_show.value:
                    dismiss_onboarding()
                dialog.close()

            with ui.row().classes("justify-end q-mt-md w-full"):
                ui.button("Got it", on_click=on_ok).classes("modern-btn-primary text-white")

        ui.timer(0.1, dialog.open, once=True)
```

### 4. Documentation & Indexing

- Register `FIRST_RUN_ONBOARDING_PLAN.md` under **Archived plans (`plans/archive/`)** in [dev-docs/index.md](../../index.md).
- Add the first-run onboarding popup feature entry to [CHANGELOG.md](../../../CHANGELOG.md) under `[Unreleased] → Added`.

## Testing

### `tests/unittests/test_window_prefs.py` (additions)

Follow the existing monkeypatch pattern:

- `load_gui_config()` returns `{}` for missing file.
- `load_gui_config()` returns `{}` for corrupt JSON file and backs up the corrupt file.
- `load_gui_config()` returns `{}` for non-object JSON such as `[]`, backs it up, and does not crash callers that expect a dict.
- Corrupt/non-object backup is best-effort: an existing or unwritable `.json.corrupt` target logs and still returns `{}`.
- `load_gui_config()` → `save_gui_config()` round-trip: writes valid JSON that loads back with the same keys and values.
- `save_gui_config()` uses atomic write: a write/replace failure leaves the previous `gui.json` intact and cleans up the temp file when possible.
- `save_native_window_prefs()` preserves the `onboardingDismissed` key when it exists in the config.

### `tests/unittests/test_onboarding.py` (new file)

Mock `mypyskindose.gui.window_prefs.config_path` to point to a `tmp_path` config, then test:

- `is_onboarding_dismissed()` → `False` when file missing / no key / key is `false`.
- `is_onboarding_dismissed()` → `True` when key is `true`.
- `dismiss_onboarding()` writes `gui.json` with `onboardingDismissed: true`, preserving any pre-existing keys.
- `reset_onboarding()` writes `gui.json` with `onboardingDismissed: false`, preserving any pre-existing keys.
- Corrupt `gui.json` → `is_onboarding_dismissed()` returns `False` safely.
- Regression: `save_native_window_prefs()` after `dismiss_onboarding()` preserves `onboardingDismissed: true`.

### Manual tests

  1. Delete `gui.json` → launch → modal appears. Click "Got it" without checking → modal appears again.
  2. Same flow, check "Don't show again" → click "Got it" → modal never appears again. Verify that `onboardingDismissed: true` is saved in `gui.json`.
  3. Verify modal cannot be dismissed by clicking the backdrop or pressing Escape (persistent prop works).
  4. Launch in native mode → modal appears.
  5. Launch in browser mode → modal appears.
  6. Corrupt `gui.json` → app launches, modal appears (safe default, file backed up to `.json.corrupt`).
  7. Run validation scripts: verify that `python scripts/check_doc_freshness.py` executes successfully.
