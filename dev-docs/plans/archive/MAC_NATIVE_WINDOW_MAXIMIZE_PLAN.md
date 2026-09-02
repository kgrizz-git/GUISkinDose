# macOS Native Window Maximization Plan

**STATUS: Completed (2026-07-03)**

> Archived after implementation. The shipped behavior lives in
> [src/guiskindose/gui/app.py](../../../src/guiskindose/gui/app.py)
> with regression coverage in
> [tests/unittests/test_gui_app_native_window.py](../../../tests/unittests/test_gui_app_native_window.py),
> [tests/unittests/test_window_prefs.py](../../../tests/unittests/test_window_prefs.py),
> and [tests/gui/test_gui_security.py](../../../tests/gui/test_gui_security.py).

## Objective

Resolve the macOS native-window startup bug where `--native` launches with a saved `"maximized": true`
state but the resulting Cocoa window appears misaligned, partially clamped, or visually "not really
maximized".

---

## Problem Summary

The current native-window flow in [src/guiskindose/gui/app.py](../../../src/guiskindose/gui/app.py)
does this on startup:

1. Load `NativeWindowPrefs` from `~/.mypyskindose/gui.json`.
2. Pass `width` / `height` / `x` / `y` into `app.native.window_args`.
3. If `prefs.maximized` is true, also pass `app.native.window_args["maximized"] = True`.

That works well enough on Windows/Linux, but macOS behaves differently:

1. `pywebview`/Cocoa maximization clamps a titled window against the visible desktop area, so a
   full-screen-sized frame request can be shifted or resized by the OS.
2. Standard macOS "zoomed" windows do not reliably map onto pywebview's `maximized` event model.
3. The saved `maximized` flag can therefore be replayed on every launch even though macOS never
   produced a stable native maximized state for this window.

Result: startup geometry and persisted state drift apart.

---

## Corrections To The Previous Draft

The earlier draft in this file had several issues. This plan supersedes them:

1. **Do not assume `AppKit` is guaranteed.**
   `pywebview` is the only declared dependency in the `gui-native` extra. `import AppKit` must be
   treated as best-effort unless this project explicitly adds a macOS-only `pyobjc` dependency later.

2. **Do not use arbitrary `95% x 90%` sizing as the primary strategy.**
   On macOS, the right target is the screen's `visibleFrame`, which already excludes the menu bar
   and Dock.

3. **Do not rely on a hardcoded `y = 25` menu-bar offset.**
   `visibleFrame` handles this correctly and adapts to Dock position and auto-hide behavior.

4. **Do not keep replaying `"maximized": true` forever on macOS after interception.**
   If startup converts macOS maximize into safe visible-frame bounds, the saved prefs must be
   normalized so later launches honor the user's last manual geometry.

5. **Do not treat Cocoa `zoom_:` as impossible.**
   It is a plausible future experiment, but not the initial fix because it adds post-launch timing
   and native-handle coupling that the current startup-path bug does not require.

---

## Recommended Fix

### Chosen approach

Implement a **macOS-only startup interception**:

1. Detect when `sys.platform == "darwin"` and loaded `prefs.maximized` is `True`.
2. Resolve a **safe visible desktop rect** for the primary screen.
3. Replace the startup geometry with that rect.
4. Clear the runtime `maximized` flag so `app.native.window_args["maximized"]` is **not** passed.
5. Persist the normalized geometry with `maximized=False` so later launches use stable normal bounds.

This intentionally changes macOS semantics from "replay pywebview maximize" to:

> "Open as a safe near-fullscreen titled window that matches the macOS visible desktop."

That is the least brittle fix that preserves title bar, Dock, restore behavior, and local state.

### Why this is the preferred fix

1. Uses the macOS-native notion of available desktop area (`visibleFrame`) when available.
2. Avoids pywebview's problematic Cocoa maximize path at startup.
3. Keeps the window in standard titled-window mode instead of macOS fullscreen mode.
4. Preserves cross-platform behavior by limiting special handling to Darwin.
5. Fixes the persistence loop where every launch retries a broken maximize.

---

## Screen-Bounds Strategy

### On macOS

Use this detection order inside `_detect_native_screens()` or a closely related helper:

1. **AppKit first**: best-effort import and query `NSScreen`.
   - Prefer `visibleFrame()` for the startup maximize interception path.
   - Use `frame()` only if needed for generic screen metadata or validation.
2. **`webview.screens()` second**:
   - Keep it as a fallback because it is already in use and may work even when `AppKit` import is
     unavailable in a given environment.
3. **Tkinter third**:
   - Final portable fallback for width/height discovery.
4. **Implicit hard fallback**:
   - If all detection fails, let existing `default_normal_bounds(screens)` behavior drive a safe
     `1024x768 @ (0,0)` default.

### On Windows/Linux

Keep the current order:

1. `webview.screens()`
2. Tkinter
3. Existing default bounds fallback

No platform behavior changes are intended outside macOS.

---

## Implementation Details

### 1. Add a macOS visible-bounds helper

File: [src/guiskindose/gui/app.py](../../../src/guiskindose/gui/app.py)

Add a small helper dedicated to the startup interception path, for example:

- `_detect_macos_visible_primary_bounds() -> ScreenBounds | None`

Requirements:

1. Guard with `sys.platform == "darwin"`.
2. `try: import AppKit` and return `None` on failure.
3. Use `NSScreen.mainScreen()` when available; otherwise fall back to the largest screen.
4. Read `visibleFrame()` and convert origin/size to `ScreenBounds`.
5. Mark that screen as primary.

This helper is intentionally best-effort and must not introduce a required macOS dependency for
test environments or non-native installs.

### 2. Adjust `_detect_native_screens()`

File: [src/guiskindose/gui/app.py](../../../src/guiskindose/gui/app.py)

Refine `_detect_native_screens()` so the platform-specific order is explicit:

1. On macOS, first try AppKit-backed screen enumeration.
2. If that fails or returns nothing, try `webview.screens()`.
3. If that fails, try Tkinter.
4. Return an empty list only if all strategies fail.

Important: the helper used for the safe maximize path should prefer **visible** bounds, while the
general screen list can continue using full screen bounds if needed for validation helpers in
`window_prefs.py`.

Implementation guardrail:

1. Do **not** silently switch the general `screens` list from `frame()` semantics to
   `visibleFrame()` semantics as part of this fix.
2. Treat `visibleFrame()` as a startup-normalization input for the macOS maximize interception path.
3. Keep the broader `ScreenBounds` / `validate_prefs()` / `geometry_looks_maximized()` behavior on
   full-frame bounds unless tests show a concrete bug that requires widening the change.
4. If testing shows full-frame metadata is insufficient, capture that as a follow-up adjustment in
   the implementation notes or PR summary rather than broadening scope implicitly.

### 3. Add a macOS maximize-normalization helper

File: [src/guiskindose/gui/app.py](../../../src/guiskindose/gui/app.py)

Create a focused helper for startup-only behavior, for example:

- `_normalize_macos_maximized_startup(prefs: NativeWindowPrefs, screens: list[ScreenBounds]) -> NativeWindowPrefs`

Behavior:

1. If not on macOS, return `prefs` unchanged.
2. If `prefs.maximized` is false, return unchanged.
3. Try `visibleFrame` primary bounds first.
4. If unavailable, derive a safe centered fallback from `primary_screen(screens)`.
   - Use a conservative but documented fallback such as centered `90%` of the detected primary
     screen for width and height.
   - This fallback only applies when native visible bounds are unavailable.
5. Return a **new** `NativeWindowPrefs` (or mutate deliberately, but keep the logic obvious) with:
   - `maximized=False`
   - `width` / `height` / `x` / `y` set to the safe visible-bounds rect

The fallback percentage path is secondary, not the primary design.

### 4. Normalize persisted state at startup

File: [src/guiskindose/gui/app.py](../../../src/guiskindose/gui/app.py)

Update `run_gui(native=True)` so the sequence becomes:

1. `screens = _detect_native_screens()`
2. `prefs = _resolve_native_window_prefs(screens)`
3. `prefs = _normalize_macos_maximized_startup(prefs, screens)`
4. Apply `width` / `height` / `x` / `y` to `app.native.window_args`
5. Only set `window_args["maximized"] = True` when `prefs.maximized` is still true
   - This will remain true on Windows/Linux.
   - It will be false on macOS after normalization.
6. If normalization changed a macOS startup from `maximized=True` to `False`, immediately persist
   the normalized prefs once before entering the event loop.

That immediate save is required so a later manual resize is not overwritten by the stale
`"maximized": true` value on next launch.

### 5. Keep geometry tracking behavior unchanged unless needed

Files:

- [src/guiskindose/gui/app.py](../../../src/guiskindose/gui/app.py)
- [src/guiskindose/gui/window_prefs.py](../../../src/guiskindose/gui/window_prefs.py)

The existing `_register_native_geometry_tracking()` logic already:

1. Treats `width` / `height` / `x` / `y` as normal geometry.
2. Ignores `resized` geometry updates that look like maximized fill.
3. Persists `maximized` and normal bounds separately.

That logic should remain the baseline. Only adjust it if the macOS startup change reveals a real
bug in tests. Do not broaden this plan into a second geometry-system rewrite.

---

## Alternatives Considered

### Option A: Map macOS maximize to native fullscreen

Rejected for now.

Reason: fullscreen changes UX substantially by hiding normal titled-window chrome and Dock behavior.
This does not match the current cross-platform meaning of "open big and usable immediately."

### Option B: Call Cocoa `zoom_:` after window creation

Deferred, not rejected forever.

Reason: this may become a better long-term "true macOS zoom" experience, but it adds:

1. Post-launch timing concerns
2. Reliance on the native window handle API
3. More event-model uncertainty than the current bug requires

If the visible-frame startup fix proves unsatisfactory in manual testing, revisit this as a follow-up
spike rather than mixing both strategies into the same patch.

### Option C: Add explicit `pyobjc-framework-Cocoa` dependency

Deferred.

Reason: the fix should work even when `AppKit` import is unavailable. Dependency expansion is only
worth considering if real-world packaging shows AppKit access is too unreliable.

---

## Tests

### Unit tests

Add or extend tests near:

- [tests/unittests/test_window_prefs.py](../../../tests/unittests/test_window_prefs.py)
- new or existing GUI app unit tests if needed

Minimum coverage:

1. **macOS normalize path clears maximize**
   - Input: `prefs.maximized=True`
   - Expected: normalized prefs have `maximized=False`

2. **visible-frame path wins when available**
   - Mock AppKit helper to return a primary visible rect
   - Expected: returned bounds match that rect exactly

3. **fallback path works when AppKit unavailable**
   - Mock helper to return `None`
   - Expected: safe centered fallback uses detected primary screen and remains within bounds

4. **non-macOS unchanged**
   - Expected: startup prefs pass through without normalization

5. **normalized startup is persisted**
   - Mock `save_native_window_prefs`
   - Expected: macOS intercepted launch saves `maximized=False`

### Manual smoke checks

Run on macOS native mode:

1. Delete `~/.mypyskindose/gui.json` and launch `python -m mypyskindose --mode gui --native`
   - Expect a large titled window that fits the visible desktop without menu-bar overlap.

2. Quit immediately and inspect saved prefs
   - Expect `native_window.maximized` to be `false` on macOS after interception.

3. Manually resize and move the window, quit, relaunch
   - Expect the manual geometry to restore instead of reapplying stale maximize.

4. Repeat with external monitor attached and with the built-in display as primary
   - Expect the initial window to land on the primary visible desktop area.

5. If feasible, test with Dock on bottom and side, plus auto-hide enabled
   - Expect no hardcoded offset artifacts.

---

## Documentation Follow-up

If the implementation lands, update:

1. [AGENTS.md](../../../AGENTS.md)
   - Note that macOS native "maximized" startup is intentionally normalized to a visible-desktop
     titled window rather than pywebview's direct maximize flag.

2. [dev-docs/index.md](../../index.md)
   - Refresh the plan description if the implementation meaning changes materially.

3. Any native-window help or release notes touched by the change

---

## Acceptance Criteria

- [ ] macOS native launch no longer uses `window_args["maximized"] = True` after intercepted startup.
- [ ] The startup window fits the macOS visible desktop area without menu-bar/Dock overlap.
- [ ] Saved macOS prefs are normalized to `maximized=False` after interception.
- [ ] Manual resize/move after first intercepted launch persists across relaunches.
- [ ] Windows/Linux startup behavior remains unchanged.
- [ ] Tests cover the normalization path and persistence update.

---

## Out Of Scope

This plan does **not** include:

1. A broader redesign of native window geometry persistence
2. Browser-mode window behavior changes
3. A guaranteed new macOS-only runtime dependency
4. Post-launch Cocoa `zoom_:` orchestration
5. Changes to first-run onboarding or general GUI layout
