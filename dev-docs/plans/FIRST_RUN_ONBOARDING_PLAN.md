# First-Run Onboarding Popup Plan

## Objective

On first launch of the GUI, show a modal dialog explaining basic usage: supported file types, how to load data, how to run calculations, and how to view/export results. The user can dismiss it permanently via a "Don't show again" checkbox. If unchecked, the popup reappears on every launch until the user checks it.

The preference is persisted in `~/.mypyskindose/gui.json` (the same config file used for native window geometry). Browser mode shows the popup identically.

## Acceptance criteria

- [ ] On every page render where `gui.json` lacks or has `onboardingDismissed: false`, the modal opens after the main page renders (the flag is read from disk on each render, so the modal reappears on relaunch until dismissed).
- [ ] Modal explains: file types accepted (RDSR `.dcm`, CSV, TSV, XLSX), how to upload (drag-and-drop or path input), how to run calculation (Settings → Calculate), and where to find results/export.
- [ ] "Don't show again" checkbox persists to `gui.json` (`onboardingDismissed: true`).
- [ ] When dismissed, never show again on any future launch.
- [ ] If unchecked, shows on every subsequent launch.
- [ ] Works in both browser and native modes.
- [ ] Does not block page navigation — user can close the modal without checking the box and still use the app.
- [ ] Modal is dismissible via a "Got it" button, clicking outside the modal, or pressing Escape.
- [ ] The "Don't show again" preference is persisted when the user checks the box and clicks "Got it." If the user checks the box and dismisses via backdrop click or Escape (without clicking "Got it"), the preference is **not** persisted — the user must click "Got it" for the choice to take effect.
- [ ] Plan is registered in `dev-docs/index.md` under **Execution plans (`plans/`)**.
- [ ] Feature entry added to `CHANGELOG.md` under `[Unreleased] → Added`.

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

**Corrupt-json safe default:** If `gui.json` is unparseable (truncated, invalid JSON), `load_gui_config()` returns `None`, which `is_onboarding_dismissed()` treats as "not dismissed" — the modal shows. This is the safe default: a corrupt config file never blocks the user from seeing onboarding.

### Concurrency, Races, and I/O Considerations

- **Synchronous Disk I/O**: `is_onboarding_dismissed()` calls `load_gui_config()`, which reads `gui.json` synchronously on the event loop. At under 1 KB on local disk, this is sub-millisecond and matches the existing `load_native_window_prefs()` pattern.
- **Merge/Save Race in Native Mode**: After the refactor, both `save_native_window_prefs()` and `dismiss_onboarding()` funnel through `save_gui_config()` (the single I/O path), so concurrent writers load-then-save the full dict and merge keys (last-writer-wins per key, no key loss). The race is best-effort and acceptable.
- **Multi-Tab Browser Mode**: `@ui.page("/")` creates a new page tree per client connection. Each tab reads `gui.json` independently; dismissing in any tab persists correctly, but already-open tabs do not auto-close their modal. Native mode is a single webview window, so multi-tab concerns do not apply there.

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
    """Atomically write gui.json using tempfile + replace (cross-platform safe).

    On Windows, Path.replace cannot move across volumes but the NamedTemporaryFile is
    created in the same directory, so it always stays on the same volume. On POSIX the
    replace is a rename (atomic by filesystem guarantee)."""
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

The "Don't show again" preference is persisted in `on_ok()` — the button's `on_click` handler. This avoids the fragility of listening for `update:model-value` transitions on the dialog (which can fire spuriously from open/close animation events). The listener on the dialog is therefore **not used** for persistence; backdrop and Escape simply close the dialog without persisting the preference.

#### Module-level import

Add this import at the top of `app.py` with the other local imports:

```python
from .onboarding import is_onboarding_dismissed, dismiss_onboarding
```

#### Page handler addition

Inside `index()`, after the existing layout code, add:

```python
    # ── onboarding modal ─────────────────────────────────────────────────
    if not is_onboarding_dismissed():
        with ui.dialog() as dialog, ui.card().classes("modern-card w-full max-w-md max-h-[80vh] p-6"):
            ui.label("Welcome to MyPySkinDose").classes("text-h5 q-mb-sm")
            with ui.scroll_area().classes("w-full"):
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

            def on_ok():
                if dont_show.value:
                    dismiss_onboarding()
                dialog.close()

            with ui.row().classes("justify-end q-mt-md"):
                ui.button("Got it", on_click=on_ok).classes("modern-btn-primary text-white")

        dialog.open()
```

### 4. State integration (optional future enhancement)

If a future "Show onboarding" button (e.g. in Help) needs to check the flag in-process, an `onboardingDismissed: bool = False` field would need to be added to `AppState` in `state.py`. This is out of scope for v1 — the flag currently lives only in `gui.json`. A "Reset onboarding" button or hidden gesture (e.g. triple-click the app title) can also be added later for power users who accidentally dismissed it; the `reset_onboarding()` helper in `onboarding.py` is ready for this.

### 5. Documentation & Indexing

- Register `FIRST_RUN_ONBOARDING_PLAN.md` under **Execution plans (`plans/`)** in [dev-docs/index.md](file:///Users/kevingrizzard/MyCode/MyPySkinDose/dev-docs/index.md) — **promoted to acceptance criterion**.
- Add the first-run onboarding popup feature entry to [CHANGELOG.md](file:///Users/kevingrizzard/MyCode/MyPySkinDose/CHANGELOG.md) under `[Unreleased] → Added` — **promoted to acceptance criterion**.

## Testing

### `tests/unittests/test_window_prefs.py` (additions)

Follow the existing monkeypatch pattern (e.g. `test_load_missing_file_returns_none` at `test_window_prefs.py:28`):

- `load_gui_config()` returns `None` for missing file.
- `load_gui_config()` returns `None` for corrupt JSON file.
- `load_gui_config()` → `save_gui_config()` round-trip: writes valid JSON that loads back with the same keys and values.
- `save_gui_config()` uses atomic write (no partial file left on crash).
- `save_native_window_prefs()` preserves the `onboardingDismissed` key when it exists in the config (regression test: without this, future code changes could silently wipe the onboarding flag).

Fixture pattern — monkeypatch `mypyskindose.gui.window_prefs.config_path`:

```python
def test_save_native_window_prefs_preserves_onboarding_flag(tmp_path, monkeypatch):
    target = tmp_path / "gui.json"
    target.write_text(json.dumps({"onboardingDismissed": True}), encoding="utf-8")
    monkeypatch.setattr("mypyskindose.gui.window_prefs.config_path", lambda: target)
    save_native_window_prefs(NativeWindowPrefs(False, 800, 600, 0, 0))
    loaded = json.loads(target.read_text(encoding="utf-8"))
    assert loaded.get("onboardingDismissed") is True
    assert "native_window" in loaded
    assert "schema_version" in loaded
```

### `tests/unittests/test_onboarding.py` (new file, uses same monkeypatch pattern)

Mock `mypyskindose.gui.window_prefs.config_path` to point to a `tmp_path` config, then test:

- `is_onboarding_dismissed()` → `False` when file missing / no key / key is `false`.
- `is_onboarding_dismissed()` → `True` when key is `true`.
- `dismiss_onboarding()` writes `gui.json` with `onboardingDismissed: true`, preserving any pre-existing keys.
- `reset_onboarding()` writes `gui.json` with `onboardingDismissed: false`, preserving any pre-existing keys.
- Corrupt `gui.json` → `is_onboarding_dismissed()` returns `False` (safe default: show onboarding).
- Regression: `save_native_window_prefs()` after `dismiss_onboarding()` preserves `onboardingDismissed: true` (this test exercises the cross-module contract — `onboarding.py` writes the flag, `window_prefs.py` must not overwrite it).

**Import safety:** Neither `onboarding.py` nor `test_onboarding.py` imports `nicegui`, so no `pytest.importorskip("nicegui")` guard is needed.

### Manual tests

  1. Delete `gui.json` → launch → modal appears. Click "Got it" without checking → modal appears again. Verify that the key `onboardingDismissed` is either absent or set to `false` in `gui.json`.
  2. Same flow, check "Don't show again" → modal never appears again. Verify that `onboardingDismissed: true` is saved in `gui.json`.
  3. Check "Don't show again" → click "Got it" → preference is saved (modal never appears again).
  4. Check "Don't show again" and dismiss via backdrop click or Escape → preference is **not** saved (only "Got it" persists). This is by design.
  5. Launch in native mode → modal appears.
  6. Launch in browser mode → modal appears.
  7. Corrupt `gui.json` → app launches, modal appears (safe default).
  8. After dismissing, manually set `onboardingDismissed: false` in `gui.json` → modal reappears on next launch.
  9. Launch native → dismiss onboarding → resize window → **wait ≥ 1.5 s** (native geometry save is debounced 1.0 s; see `app.py:246-258`) → quit → relaunch → onboarding does not appear (no data loss from `save_native_window_prefs`).
  10. Run validation scripts: verify that `python scripts/check_doc_freshness.py` executes successfully and reports zero issues/broken links.

## Out of scope

- Multi-language/localization support.
- Per-tab contextual help (tracked separately).
- Help menu / dedicated Help tab — tracked as a separate TO DO item in
  [dev-docs/TO_DO.md](../TO_DO.md); a "Show onboarding" gesture can land alongside it.
- Interactive walkthrough / tooltips on first use.
- Onboarding content changes based on user role or prior experience.
