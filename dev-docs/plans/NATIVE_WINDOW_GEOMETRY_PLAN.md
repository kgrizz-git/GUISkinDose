# Native Window Geometry Persistence Plan

**STATUS: REVIEWED — ready for implementation**

## Objective

When the GUI is launched with `--native`, restore the desktop window to the size, position, and maximized/normal state from the previous session. On first launch (no saved prefs), open **maximized** so the app fills the screen while keeping normal window chrome (title bar, close/minimize).

Browser mode (`--mode gui` without `--native`) is unchanged — this plan applies only to the pywebview window.

## Review summary (2026-06-25)

### Recommendation: remember last geometry — no full/windowed toggle

Persisting the last window state on close is **doable** with the current stack (NiceGUI ≥2 + pywebview) and is the better UX:

- Users already resize/maximize/minimize with OS controls; a “start full-screen” checkbox would **fight** remembered geometry (which wins on next launch?).
- A dedicated GUI toggle is unnecessary for v1. Defer any in-app control to an optional **“Reset window size on next launch”** action if users ask for it later.
- Do **not** use pywebview/NiceGUI `fullscreen=True` as the default. That is borderless kiosk mode (no title bar). Prefer **`maximized=True`** (via `app.native.window_args`) or `window.maximize()` on first run — fills the screen but keeps normal window controls.

### Issues in the original draft (corrected here)

| Issue | Resolution |
|---|---|
| Listed `main.py` as a change target | Not needed for v1. All logic belongs in `gui/app.py` plus a small prefs helper module. |
| “Full-screen” conflated with maximized | Use **maximized** for first-run default; only use `fullscreen=True` if a future kiosk mode is explicitly requested. |
| Checkbox in Settings tab | **Dropped for v1.** Visual Settings is for dose-map rendering, not shell/window prefs. |
| Config path TBD | `Path.home() / ".mypyskindose" / "gui.json"` (create parent dir on first write). |
| Size only | Persist **width, height, x, y**, and **maximized** flag. |
| No edge-case handling | Clamp dimensions; if saved position is off-screen after monitor change, fall back to centered or maximized. |
| No tests | Add unit tests for load/save/validate; manual smoke on macOS + Windows. |

### Existing code context

Current native startup in `gui/app.py`:

- Sets `window_size` to **75% of screen** via Tkinter when available; otherwise NiceGUI defaults to **800×600**.
- Does **not** persist anything between sessions.
- Sets `set_on_top(True)` on every client connect (unchanged by this plan; pre-existing focus behavior).

NiceGUI APIs available today:

- `ui.run(..., window_size=(w, h), fullscreen=False)` — `fullscreen` forces native mode.
- `app.native.window_args` — forwarded to `webview.create_window()` (`x`, `y`, `maximized`, `min_size`, etc.).
- `app.native.main_window.get_size()` / `get_position()` — async; available once native mode starts.
- `app.native.on('closed' | 'resized' | 'moved' | 'maximized' | 'restored', handler)` — native window events.
- `app.on_shutdown(handler)` — server teardown when the native window closes.

## Acceptance criteria

- [ ] First native launch (no `gui.json`): window opens **maximized** with normal OS chrome.
- [ ] Subsequent native launches restore saved **width, height, x, y** when the window was in normal (non-maximized) state.
- [ ] Subsequent native launches restore **maximized** when that was the state at last close.
- [ ] Preferences are written to `~/.mypyskindose/gui.json` on window close (and optionally debounced on `resized`/`moved` for crash resilience).
- [ ] Invalid or off-screen saved geometry falls back safely (maximized or 75% screen center) with a debug log, not a crash.
- [ ] Browser mode and headless CLI are unaffected.
- [ ] Unit tests cover prefs load/save/validation; README note added for native window behavior.

## Non-goals (v1)

- GUI checkbox or Settings-tab control for full-screen vs windowed.
- CLI flags such as `--fullscreen` or `--window-size` (can be added later if needed).
- Remembering browser tab/window size in non-native mode.
- Changing the `set_on_top` focus behavior.

## Implementation plan

### 1. Prefs module — `src/mypyskindose/gui/window_prefs.py`

Responsibilities:

- `config_path()` → `Path.home() / ".mypyskindose" / "gui.json"`.
- `load_native_window_prefs() -> NativeWindowPrefs | None` — parse JSON with schema version; return `None` if missing/invalid.
- `save_native_window_prefs(prefs)` — atomic write (write temp file + rename).
- `validate_prefs(prefs, screen_w, screen_h)` — minimum size (e.g. 640×480), clamp to screen, reset x/y if off-screen.

Suggested JSON schema (version 1):

```json
{
  "schema_version": 1,
  "native_window": {
    "maximized": false,
    "width": 1440,
    "height": 900,
    "x": 100,
    "y": 50
  }
}
```

Use `platformdirs` only if the project already depends on it; otherwise `Path.home()` is sufficient and matches existing docs convention.

### 2. Startup — `run_gui()` in `gui/app.py`

Before `ui.run()` when `native=True`:

1. `prefs = load_native_window_prefs()`.
2. If prefs exist and valid:
   - If `maximized`: set `app.native.window_args['maximized'] = True` (do not pass conflicting `window_size`).
   - Else: pass `window_size=(width, height)` and set `app.native.window_args['x']` / `['y']`.
3. If no prefs (first run): set `app.native.window_args['maximized'] = True`.
4. Keep existing Tkinter screen-size probe as fallback for validation defaults only (not as the primary window size when prefs exist).

Call `ui.run(..., fullscreen=False)` — never default to true fullscreen.

### 3. Shutdown / persistence hooks — `run_gui()` in `gui/app.py`

Register when `native=True`:

```python
async def _capture_native_window_geometry() -> None:
    if app.native.main_window is None:
        return
    w, h = await app.native.main_window.get_size()
    x, y = await app.native.main_window.get_position()
    save_native_window_prefs(...)

app.on_shutdown(_capture_native_window_geometry)
```

Also track maximized state:

- Maintain a module-level or closure flag updated by `app.native.on('maximized', ...)` and `app.native.on('restored', ...)`.
- Include that flag in the saved prefs.

Optional: debounced save on `resized`/`moved` (e.g. 1 s timer) so an abnormal exit still has recent geometry.

### 4. Tests — `tests/unittests/test_window_prefs.py`

- Round-trip save/load.
- Invalid JSON / wrong schema version → `None`.
- Off-screen x/y clamped or rejected.
- Minimum size enforcement.

No headless native-window integration test required (pywebview subprocess is heavy for CI); document manual smoke steps below.

### 5. Documentation

- `README.md` — one sentence: native mode remembers window size/position between sessions; first launch opens maximized.
- `CHANGELOG.md` — minor UX improvement under Unreleased.
- `dev-docs/FEATURE_INVENTORY.md` — note geometry persistence under GUI/native.
- `dev-docs/TO_DO.md` — update backlog item wording to match this plan.

## Manual test plan

1. **First launch:** delete `~/.mypyskindose/gui.json`, run `python -m mypyskindose --mode gui --native` → window maximized.
2. **Restore normal:** restore/downsize, move window, quit → relaunch → same size and position.
3. **Restore maximized:** maximize, quit → relaunch → maximized.
4. **Monitor change:** save prefs with one monitor, disconnect/move → relaunch → safe fallback, no crash.
5. **Browser mode:** `python -m mypyskindose --mode gui` → no `gui.json` writes; behavior unchanged.

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Windows 11 blank-window issues with some pywebview versions (see `GUI_PLAN.md`) | Manual smoke on Windows; do not change webview backend settings in v1. |
| `get_size()`/`get_position()` unavailable at shutdown | Guard on `main_window is None`; best-effort save in `closed` handler as backup. |
| Multi-monitor / DPI scaling | Validate against primary screen metrics from Tkinter; fall back to maximized if coords invalid. |
| Race on fast quit | Prefer `on_shutdown`; optional debounced mid-session saves. |

## Progress log

- 2026-06-25 — Plan created as `NATIVE_WINDOW_FULLSCREEN_PLAN.md` (full-screen default + Settings toggle).
- 2026-06-25 — **Reviewed:** pivot to geometry persistence; drop Settings toggle for v1; clarify maximized vs fullscreen; flesh out schema, hooks, tests, and edge cases.
- 2026-06-25 — Renamed to `NATIVE_WINDOW_GEOMETRY_PLAN.md` to match scope.

## Decision log

- **GUI setting location:** **None for v1.** Remember-last-geometry makes a full/windowed toggle redundant. If a control is added later, use a new **Settings → Application** expansion (visible only in native mode), not Visual Settings — not a header control.
- **First-run default:** **Maximized** (not pywebview fullscreen).
- **Config file:** `~/.mypyskindose/gui.json`, schema version 1.
- **`main.py` changes:** **Not required** for v1.
