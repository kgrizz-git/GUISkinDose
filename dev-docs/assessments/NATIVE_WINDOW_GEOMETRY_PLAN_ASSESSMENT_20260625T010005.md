# `NATIVE_WINDOW_GEOMETRY_PLAN.md` — Round 2 Gap Review

**Date:** 2026-06-25 01:00 UTC  
**Scope:** Second-pass review of the updated geometry persistence plan (post Round 1 assessment). Focus on restored-size UX, event-state logic, startup safety, debounce lifecycle, CI, and cross-platform file I/O.  
**Method:** Read plan + Round 1 assessment; verify against NiceGUI/pywebview APIs and CI config (`.github/workflows/ci.yml` installs `.[dev,gui]` only for unit tests — **not** `gui-native`).

---

## 1. Executive summary

| # | Finding | Verdict | Plan action |
|---|---------|---------|-------------|
| 2.1 | Restored size lost when starting maximized | **Valid UX bug** | Always pass normal `width`/`height`/`x`/`y` to `window_args` even when `maximized=True` |
| 2.2 | Title bar off-screen passes intersection test | **Valid edge case** | Title-bar overlap check in `geometry_visible_on_any_screen` |
| 2.3 | Uncaught `webview.screens()` at startup | **Valid risk** | try/except + empty-screen fallback |
| 2.4 | Maximized events overwrite normal bounds | **Valid state bug** | `width`/`height`/`x`/`y` = normal geometry only; ignore `resized`/`moved` while maximized |
| 2.5 | Debounced save races on close | **Valid reliability risk** | Cancel pending asyncio task; synchronous flush on `closed` |
| 2.6 | CI breakage from `webview` import in tests | **Valid** | Pure validation helpers + synthetic screen rects in tests; no `webview` import in unit tests |
| 2.7 | Windows atomic write via `os.rename` | **Valid** | Use `Path.replace()` / `os.replace` |

**Bottom line:** Round 1 API corrections stand. Round 2 catches real state-management and packaging gaps that would cause subtle UX bugs (restore-from-maximize) or CI failures if implemented literally from the current plan text.

---

## 2. Finding details

### 2.1 Restored size when starting maximized

When `maximized=True` at startup, pywebview still needs the **normal** (restored) bounds registered via `width`, `height`, `x`, `y` in `create_window` / `app.native.window_args`. If only `maximized=True` is set, the OS restore button falls back to default dimensions.

**Fix:** On startup, **always** set:

```python
app.native.window_args['width'] = prefs.width
app.native.window_args['height'] = prefs.height
app.native.window_args['x'] = prefs.x
app.native.window_args['y'] = prefs.y
if prefs.maximized:
    app.native.window_args['maximized'] = True
```

Also pass `window_size=(width, height)` to `ui.run()` for consistency with NiceGUI defaults.

### 2.2 Title bar accessibility

Rectangle intersection alone allows windows whose title bar is above/below visible screen area (common on macOS menu bar overlap or stacked monitors). User cannot drag or close the window.

**Fix:** Require minimum horizontal overlap (~50 px) and vertical overlap of the **title-bar strip** (top ~32 logical px) against at least one screen. Use platform-agnostic constants; no need for exact OS chrome metrics in v1.

### 2.3 Startup screen detection safety

`webview.screens()` can raise if pywebview is missing (should not happen in `--native` with correct extras) or if no display server is available (headless CI, SSH without DISPLAY).

**Fix:**

```python
screens: list[ScreenBounds] = []
if native:
    try:
        import webview
        screens = [screen_bounds_from_webview(s) for s in webview.screens()]
    except Exception as exc:
        dprint("GUI", f"Screen detection failed ({exc}); using fallback validation.")
```

Map `webview.Screen` → a local `ScreenBounds` dataclass in `window_prefs.py` so validation logic stays importable without pywebview.

### 2.4 Normal vs maximized geometry in event tracker

JSON field semantics must be:

| Field | Meaning |
|-------|---------|
| `maximized` | Window state at last save |
| `width`, `height`, `x`, `y` | **Normal (restored) geometry only** |

While `_current_geometry.maximized is True`, **do not** apply `resized` or `moved` events to `width`/`height`/`x`/`y`. Process `maximized` / `restored` before dimension updates. On `restored`, the next `resized`/`moved` events repopulate normal bounds.

Round 1 note §3 (“persist maximized pixel rect for debugging”) was **incorrect** and contradicted restore UX — removed from plan.

### 2.5 Debounced save lifecycle

Pending debounce timers/tasks must be cancelled on `closed`. Final `save_native_window_prefs()` must be **synchronous** in the close handler so the write completes before process exit.

Use a cancelable `asyncio.Task` (NiceGUI runs on asyncio), not `ui.timer` alone, so cancellation is explicit.

### 2.6 CI-safe tests

CI unit-test job: `pip install -e ".[dev,gui]"` + `pytest --ignore=tests/gui` — **pywebview not installed**.

**Fix:** `window_prefs.py` validation functions accept `list[ScreenBounds]` (project dataclass). Unit tests construct synthetic screens — **no `pytest.importorskip("webview")` required** if tests never import webview. Optional integration test under `tests/gui/` may use `importorskip` if added later.

### 2.7 Atomic write on Windows

`os.rename` to an existing path fails on Windows. Use:

```python
tmp_path.replace(config_path)  # pathlib.Path.replace → os.replace
```

---

## 3. Suggested plan edits (checklist)

- [x] Documented in plan (Round 2 incorporation):
  - [ ] Always set normal bounds at startup, including when maximized
  - [ ] Title-bar overlap validation
  - [ ] try/except around `webview.screens()`; `ScreenBounds` dataclass
  - [ ] Filter `resized`/`moved` when maximized
  - [ ] Cancel debounce task + sync flush on `closed`
  - [ ] CI-safe pure unit tests (no webview import)
  - [ ] `Path.replace()` for atomic config write

---

## 4. Manual test additions

7. **Restore-from-maximize:** Save normal size 1200×800, maximize, quit → relaunch maximized → click Restore → window returns to 1200×800 at saved position (not OS default).
