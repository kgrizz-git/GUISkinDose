# macOS Native Window Maximization Plan

**STATUS: Active**

## Objective

Resolve the issue where the native mode GUI window does not open maximized on macOS. 

---

## Issue Summary

The current maximization logic stores a `"maximized": true` flag in `~/.mypyskindose/gui.json` and updates `app.native.window_args["maximized"] = True` before starting NiceGUI/pywebview. However, on macOS:
1. **Platform Clamping**: `pywebview`'s Cocoa implementation of `maximize()` simply resizes the window frame to the exact screen dimensions. Since standard titled windows cannot overlap the macOS menu bar or Dock, macOS immediately clamps and shifts the frame, which results in a misaligned and non-maximized appearance.
2. **State Tracking Mismatch**: `pywebview` only fires the `maximized` event on Cocoa when entering native macOS Full Screen mode (which hides the title bar and Dock). A standard "zoomed" window does not trigger this event, causing the saved window state to be out of sync.

---

## Proposed Options

### Option 1: Safe Multi-layered Sizing Fallback (Recommended)
Instead of relying on the buggy `maximized=True` parameter on macOS, we intercept maximization at startup on macOS and set the window to a "safe near-fullscreen" centered size.

* **Behavior**: If `sys.platform == "darwin"` and `prefs.maximized` is true:
  1. Set `app.native.window_args["maximized"] = False` to prevent `pywebview` from attempting native maximization.
  2. Query screen bounds using a multi-layered fallback strategy.
  3. Calculate a centered layout at **95% width** and **90% height** of the primary screen, shifted down by `y = 25` (or a safe offset) to leave the macOS menu bar fully visible.
* **Fallbacks for Screen Bounds Detection**:
  * **Layer 1**: `webview.screens()` (uses `pywebview`'s wrapper).
  * **Layer 2**: Direct `AppKit` Cocoa API (uses native `NSScreen` via `pyobjc` which is already installed as a dependency for `pywebview`).
  * **Layer 3**: `tkinter` fallback.
  * **Layer 4**: Hardcoded defaults (`1024x768` centered at origin) if all of the above fail.

### Option 2: Force Native Fullscreen
Instead of maximizing, map `maximized` to native macOS Full Screen mode (`fullscreen=True`).
* **Pros**: Fills the entire screen natively.
* **Cons**: Hides the OS title bar, window controls, and Dock, which drastically changes the user experience.

### Option 3: Access and Trigger Cocoa's `zoom_:` Method
Access the underlying Cocoa `NSWindow` instance using `pywebview`'s native handler and invoke `window.zoom_(None)` programmatically after the window is shown.
* **Pros**: Native zoom-maximize animation and standard title bar zoom behavior.
* **Cons**: Relies on accessing non-public `pywebview` native properties (`window.native` / `NSWindow` reference), which is brittle and prone to breaking on different `pywebview` versions.

---

## Detailed Implementation (Option 1)

### 1. Multi-Layered Screen Detection in `gui/app.py`
Modify `_detect_native_screens()` to prioritize the native `AppKit` library on macOS before falling back to `tkinter`:

```python
def _detect_native_screens() -> list[ScreenBounds]:
    screens: list[ScreenBounds] = []
    # Layer 1: webview screens
    try:
        import webview
        screens = [
            ScreenBounds(
                s.x, s.y, s.width, s.height,
                is_primary=bool(getattr(s, "is_primary", False))
            )
            for s in webview.screens()
        ]
    except Exception as exc:
        dprint("GUI", f"Screen detection failed ({exc}); trying AppKit/Tkinter fallbacks.")

    # Layer 2: AppKit Cocoa (macOS only)
    if not screens and sys.platform == "darwin":
        try:
            import AppKit
            screens = [
                ScreenBounds(
                    int(s.frame().origin.x),
                    int(s.frame().origin.y),
                    int(s.frame().size.width),
                    int(s.frame().size.height),
                    is_primary=(s == AppKit.NSScreen.mainScreen())
                )
                for s in AppKit.NSScreen.screens()
            ]
        except Exception as exc:
            dprint("GUI", f"AppKit screen detection failed ({exc}).")

    # Layer 3: Tkinter fallback
    if not screens:
        try:
            import tkinter as tk
            root = tk.Tk()
            root.withdraw()
            sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
            root.destroy()
            screens = [ScreenBounds(0, 0, sw, sh, is_primary=True)]
        except Exception as exc:
            dprint("GUI", f"Tkinter screen detection failed ({exc}).")
            
    return screens
```

### 2. macOS Maximization Interception in `run_gui()`
Before launching, adjust `prefs` if on macOS and maximized:

```python
    if native:
        screens = _detect_native_screens()
        prefs = _resolve_native_window_prefs(screens)
        
        # Intercept macOS maximization to calculate safe full bounds
        if sys.platform == "darwin" and prefs.maximized:
            prefs.maximized = False  # Prevent pywebview from applying buggy max logic
            primary = primary_screen(screens)
            if primary:
                prefs.width = int(primary.width * 0.95)
                prefs.height = int(primary.height * 0.90)
                prefs.x = primary.x + (primary.width - prefs.width) // 2
                prefs.y = primary.y + 25  # Offset down to clear macOS menu bar
        
        app.native.window_args.update(
            width=prefs.width,
            height=prefs.height,
            x=prefs.x,
            y=prefs.y,
        )
        if prefs.maximized:
            app.native.window_args["maximized"] = True
```
