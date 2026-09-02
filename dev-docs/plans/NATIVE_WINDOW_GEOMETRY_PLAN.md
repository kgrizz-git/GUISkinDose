# Native Window Geometry Persistence Plan

**STATUS: Shipped**

## Objective

In `--native` mode, restore the window’s last size, position, and maximized state from `~/.guiskindose/gui.json` (read fallback: `~/.mypyskindose/gui.json`). First launch: start **maximized** with normal bounds set to **75% of the largest detected screen, centered** so Restore works immediately. Browser mode is unchanged.

`main.py` is unchanged — `--native` is already plumbed to `run_gui(native=True)`.

## Rules

- `width`, `height`, `x`, `y` in JSON = **normal (restored) geometry only**, never maximized frame size.
- Always pass normal bounds to `app.native.window_args`, even when `maximized=True`.
- Use `maximized=True`, not `fullscreen=True` (fullscreen hides window chrome).
- No GUI toggle for full/windowed in v1.
- Persist via in-memory tracking + debounced disk writes + synchronous flush on native `closed` (not `on_shutdown` alone).
- `window_prefs.py` must not import `webview` (CI unit tests run without `gui-native`).

## Acceptance criteria

- [ ] First launch: maximized; Restore → 75% centered normal size.
- [ ] Later launches restore saved normal geometry and maximized flag.
- [ ] Restore-from-maximize returns saved normal size, not OS default (smoke on Windows, macOS, Linux).
- [ ] Maximize-then-close does not overwrite normal bounds in `gui.json`.
- [ ] Corrupt/missing config, wrong `schema_version`, missing config dir, or failed `webview.screens()` never crash startup.
- [ ] Title-bar inaccessible position is re-clamped (or falls back to defaults), not left off-screen.
- [ ] Unit tests pass in CI without `gui-native`; test module does not import `webview`.

## Implementation

### 1. `src/guiskindose/gui/window_prefs.py`

| Symbol | Purpose |
|--------|---------|
| `ScreenBounds` | `x`, `y`, `width`, `height` as `int` (coerce floats at construction); no pywebview import |
| `NativeWindowPrefs` | `maximized`, `width`, `height`, `x`, `y` |
| `config_path()` | `Path.home() / ".guiskindose" / "gui.json"` |
| `load_native_window_prefs()` | Parse JSON; if `schema_version != 1`, missing/invalid keys, or any error → `None` |
| `save_native_window_prefs()` | `mkdir(parents=True)` → write temp → `tmp_path.replace(config_path)` |
| `primary_screen(screens)` | Prefer screen with `is_primary` when present; else largest `width × height` |
| `geometry_looks_maximized(w, h, screens, fill_ratio=0.90)` | Returns `False` when `screens` empty; else true if area ≥ `fill_ratio` of any screen |
| `title_bar_accessible_on_any_screen(...)` | Returns `False` when `screens` empty; else title-bar strip (32 px) fully on some screen with ≥50 px horizontal overlap |
| `clamp_title_bar_on_screen(x, y, w, h, screen, ...)` | Nudge origin so title bar is accessible on one screen |
| `validate_prefs(prefs, screens)` | Enforce min 640×480. If `screens` empty: clamp size only, keep `x`/`y`. If screens known and title bar inaccessible: **re-clamp** `x`/`y` on the first screen that can fit the title bar; if none, return `default_normal_bounds(screens)` with saved `maximized` flag |
| `default_normal_bounds(screens)` | 75% of `primary_screen(screens)` centered; if `screens` empty → 1024×768 at (0,0). Returns `maximized=False` (caller sets for first run) |

JSON schema v1:

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

### 2. Startup — `run_gui()` in `gui/app.py`

```python
screens: list[ScreenBounds] = []
try:
    import webview
    screens = [ScreenBounds(s.x, s.y, s.width, s.height) for s in webview.screens()]
except Exception as exc:
    dprint("GUI", f"Screen detection failed ({exc}); trying Tkinter fallback.")
if not screens:
    # existing Tkinter probe → single ScreenBounds for validation / defaults

raw_prefs = load_native_window_prefs()
if raw_prefs is not None:
    prefs = validate_prefs(raw_prefs, screens)
else:
    prefs = default_normal_bounds(screens)
    prefs.maximized = True

app.native.window_args.update(width=prefs.width, height=prefs.height, x=prefs.x, y=prefs.y)
if prefs.maximized:
    app.native.window_args['maximized'] = True

ui.run(..., window_size=(prefs.width, prefs.height), fullscreen=False)
```

### 3. Runtime tracking — `run_gui()` in `gui/app.py`

Register **five** handlers before `ui.run()` when `native=True` (one event name per `app.native.on` call):

```python
app.native.on('resized', _apply_native_event)
app.native.on('moved', _apply_native_event)
app.native.on('maximized', _apply_native_event)
app.native.on('restored', _apply_native_event)
app.native.on('closed', _on_native_closed)
```

Two debounce layers:

1. **Geometry commit** (~300 ms) — update in-memory normal bounds from `resized`/`moved`.
2. **Disk save** (~1 s) — write `gui.json`.

```python
def _apply_native_event(e: NativeEventArguments) -> None:
    if e.type == 'maximized':
        _current_geometry.maximized = True
        if _commit_task is not None:
            _commit_task.cancel()
    elif e.type == 'restored':
        _current_geometry.maximized = False
    elif e.type in ('resized', 'moved'):
        _schedule_geometry_commit(e)
    _schedule_debounced_save()

async def _commit_after_settle(e):
    await asyncio.sleep(0.3)
    if _current_geometry.maximized:
        return
    if e.type == 'resized':
        w, h = e.args['width'], e.args['height']
        if geometry_looks_maximized(w, h, _screens):
            return
        _current_geometry.width, _current_geometry.height = w, h
    elif e.type == 'moved':
        _current_geometry.x, _current_geometry.y = e.args['x'], e.args['y']
```

```python
def _on_native_closed(_e: NativeEventArguments) -> None:
    # Optional: apply pending commit synchronously if _pending_event is set
    if _commit_task is not None:
        _commit_task.cancel()
        _commit_task = None
    if _save_task is not None:
        _save_task.cancel()
        _save_task = None
    save_native_window_prefs(_current_geometry)
```

### 4. Tests — `tests/unittests/test_window_prefs.py`

- File header: `pytest.importorskip("nicegui")` (repo convention); **do not import `webview`** — use `ScreenBounds` literals only.
- Load: valid; corrupt; missing; `schema_version != 1` → `None`, no raise.
- Save: creates parent dir; uses `replace`.
- `geometry_looks_maximized` / `title_bar_accessible_on_any_screen`: empty `screens` → `False`.
- `validate_prefs`: re-clamp when title bar off-screen; empty `screens` preserves `x`/`y`.
- `default_normal_bounds`: multi-screen uses largest; `screens=[]` → 1024×768.

### 5. Docs

- `README.md` — one sentence on native geometry persistence.
- `CHANGELOG.md` — Unreleased entry (Keep a Changelog format; must pass `scripts/check_changelog.py`).
- `FEATURE_INVENTORY.md` — note under GUI/native.
- `dev-docs/index.md` — row for this plan under execution plans.

## Manual smoke tests

1. Delete `gui.json` → launch native → maximized → Restore → 75% centered.
2. Resize/move → quit → relaunch → same normal geometry.
3. Maximize → quit → relaunch maximized → Restore → prior normal size.
4. **All OSes:** normal size → maximize (title-bar button) → quit → relaunch → Restore → prior normal size.
5. External monitor: place window → quit → relaunch on same monitor.
6. Unplug monitor → relaunch → safe fallback, no crash.
7. Corrupt / wrong-schema `gui.json` → launch → defaults, no crash.
8. Browser mode → no `gui.json` writes.

## Out of scope (v1)

- Settings/CLI controls for window mode.
- Browser-tab geometry persistence.
- Platform-native maximized-state queries from the main process.
- pywebview `closing` event (not bridged by NiceGUI).
- In-app help under `docs/source/gui_help/` (shell behavior only).
