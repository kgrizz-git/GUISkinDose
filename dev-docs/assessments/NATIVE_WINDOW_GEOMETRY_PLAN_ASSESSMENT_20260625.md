# `NATIVE_WINDOW_GEOMETRY_PLAN.md` — Gap & API Review

**Date:** 2026-06-25  
**Scope:** Verify proposed NiceGUI/pywebview APIs, persistence timing, and multi-monitor validation against the installed stack (`nicegui>=2.0.0`, `pywebview` in `.[gui-native]`).  
**Method:** Read the plan, inspect NiceGUI `native/` sources and pywebview API in the project venv. Do not implement — assessment only.

---

## 1. Executive summary

| Finding | Verdict | Action for plan |
|---------|---------|-----------------|
| §1 `get_size()` / `get_position()` | **Plan is correct** (NiceGUI proxy, not raw pywebview) | Keep async proxy calls; document that these are NiceGUI APIs |
| §2 `app.native.on(...)` | **Plan is correct** | Clarify registration is per event type, not a Python `\|` expression |
| §3 Save only in `app.on_shutdown` | **Valid risk** | Primary: in-memory geometry + debounced disk writes; flush on `closed` |
| §4 Tkinter-only off-screen check | **Valid gap** | Use `webview.screens()` for multi-monitor bounds at startup validation |

**Bottom line:** Two of four reported “bugs” misread the NiceGUI abstraction layer. The persistence timing and multi-monitor validation concerns are real and should be folded into the plan before implementation.

---

## 2. Finding details

### 2.1 `get_size()` / `get_position()` — not a bug in NiceGUI context

The original review stated that pywebview exposes only synchronous `window.width`, `window.height`, `window.x`, `window.y` and that `await app.native.main_window.get_size()` would raise `AttributeError`.

**Verification:** In native mode, `app.native.main_window` is NiceGUI’s `WindowProxy` (see `nicegui/native/native.py`), not the raw pywebview `Window`. The proxy implements:

- `async def get_size() -> tuple[int, int]`
- `async def get_position() -> tuple[int, int]`

These marshal calls into the pywebview subprocess via queues (`method_queue` / `response_queue`). The executor in `native_mode.py` maps them to `window.width`, `window.height`, `window.x`, `window.y` in the child process.

**Recommendation:** Keep the async proxy calls in the plan. Add a one-line note that geometry reads go through NiceGUI’s proxy, not direct pywebview properties from the main thread.

### 2.2 `app.native.on(...)` — exists and is the supported API

The original review stated that `app.native` has no `on()` method and that handlers must attach to `main_window.events.*` directly.

**Verification:** `NativeConfig.on()` in `nicegui/native/native_config.py` registers handlers on `event_manager`, which receives bridged events from the pywebview subprocess (`shown`, `loaded`, `minimized`, `maximized`, `restored`, `resized`, `moved`, `closed`, `drop`).

**Caveat:** The plan’s illustrative syntax `app.native.on('closed' | 'resized' | ...)` is documentation shorthand. Implementation must register separate handlers (or one handler that inspects `NativeEventArguments.type`):

```python
def _on_native_event(e: NativeEventArguments) -> None:
    ...

app.native.on('resized', _on_native_event)
app.native.on('moved', _on_native_event)
app.native.on('maximized', _on_native_event)
app.native.on('restored', _on_native_event)
app.native.on('closed', _flush_geometry_to_disk)
```

Raw `main_window.events.*` is not available on the proxy in the main process.

**Note:** pywebview’s synchronous `closing` event (veto-capable, pre-destroy) is **not** bridged by NiceGUI yet (`native_mode.py` comment). Do not plan on it for v1.

### 2.3 Shutdown timing — valid; do not rely on `on_shutdown` alone

**Risk:** By the time `app.on_shutdown` runs, the native window subprocess may already be torn down. A final `get_size()` / `get_position()` call can fail or return stale values.

**Recommended persistence model:**

1. Maintain an in-memory `NativeWindowPrefs` (or dict) updated on `resized`, `moved`, `maximized`, and `restored` events.
2. Debounce writes to `gui.json` (e.g. 1 s after last change) for crash resilience.
3. On `app.native.on('closed', ...)`, flush the in-memory snapshot to disk synchronously (no async geometry read required if state is current).
4. Optionally attempt async `get_size()` / `get_position()` on `closed` only as a last-chance refresh if in-memory state might be stale — guard with try/except; never block shutdown.

Treat `app.on_shutdown` as a best-effort backup only, not the primary save path.

### 2.4 Multi-monitor validation — valid; replace Tkinter primary-screen check

**Risk:** `tkinter.Tk().winfo_screenwidth()` reflects the primary display. A window saved at `x=2500` on a secondary monitor will be misclassified as off-screen when validated against primary dimensions only.

**Verification:** `webview.screens()` initializes the GUI backend if needed and returns a `list[Screen]` with `x`, `y`, `width`, `height` (and `scale`) per display. Callable before `webview.start()`.

**Recommendation:**

- Add `geometry_visible_on_any_screen(x, y, width, height, screens) -> bool` in `window_prefs.py`.
- At startup (native mode, pywebview importable): validate saved prefs against `webview.screens()`.
- Fall back to Tkinter primary metrics only when pywebview is unavailable (should not happen in `--native` mode if deps are correct).
- If no screen contains the saved origin (monitor unplugged): fall back to maximized or centered on primary — log at DEBUG.

---

## 3. Additional notes (not in original review)

| Topic | Note |
|-------|------|
| Maximized vs normal geometry | When `maximized=True`, persisted `width`/`height`/`x`/`y` may reflect maximized frame, not restored size. Persist the `maximized` flag and prefer restoring via `window_args['maximized']=True`; only use stored width/height/x/y when `maximized=False`. |
| Event payloads | `resized` passes `width`/`height` in `NativeEventArguments.args`; `moved` passes `x`/`y`. Prefer event args over polling where possible. |
| Tests | Unit-test `validate_prefs` with synthetic multi-screen rectangles; no CI requirement for live pywebview subprocess. |
| `set_on_top` on connect | Pre-existing behavior in `app.py`; out of scope for geometry plan. |

---

## 4. Suggested plan edits (checklist)

- [ ] Replace “save on `on_shutdown`” with in-memory tracker + debounced save + `closed` flush.
- [ ] Document `app.native.on` as the event API; show per-event registration example.
- [ ] Replace Tkinter-only validation with `webview.screens()` when available.
- [ ] Add note that NiceGUI `get_size`/`get_position` are proxy methods (assessment §2.1).
- [ ] Link this assessment from the plan progress log.
