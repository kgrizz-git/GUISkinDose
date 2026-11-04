# Portable Full: render PNG through the bundled Chromium

_Status: planned (2026-11-03). Child of [PORTABLE_APP_PLAN.md](PORTABLE_APP_PLAN.md), Phase 1 item "The bundled
browser path is passed to Kaleido explicitly inside the process that renders."_

## Problem

The frozen Full app ships Chromium under `<onedir>/chromium/`. Only the headless `--png-check` uses it
(`packaging/portable/pngcheck.py`, which calls `kaleido.start_sync_server(path=...)`). The app's own PNG
exports call `fig.to_image()` with no path. Kaleido then lets choreographer 1.4.0 pick a browser in this order:
a Chrome for Testing it downloaded earlier, then `BROWSER_PATH`, then a system install
(`choreographer/browsers/chromium.py`, `find_browser`). So the GUI's offline PNG promise is not met. On a machine
with no Chrome, Full PNG fails. On a machine with Chrome, Full uses that Chrome instead of the bundled one.
Setting `BROWSER_PATH` cannot fix it, because a downloaded Chrome for Testing wins over it.

Three call sites render PNG:

| Call site | Used by |
|-----------|---------|
| `src/guiskindose/export/images.py` `render_dosemap_png` | Export payload images (HTML rich report, PDF, DOCX, PNG zip) |
| `src/guiskindose/gui/figures.py` `make_dosemap_png` | GUI PNG download |
| `src/guiskindose/plotting/create_dose_map_plot.py` (static dose maps) | CLI / notebook `plot_dose_map` |

## Design

Add one module, `src/guiskindose/export/png_browser.py`, and route all three call sites through it.

```python
def bundled_browser_path() -> Path | None: ...
def figure_to_png(fig, **to_image_kwargs) -> bytes: ...
def stop_png_browser() -> None: ...
class BundledBrowserUnavailableError(RuntimeError): ...
```

### `bundled_browser_path()`

- Returns `None` when the process is not frozen (`getattr(sys, "frozen", False)` is false). Pip installs keep
  today's behavior.
- When frozen on Windows, returns `Path(sys.executable).resolve().parent / "chromium" / "chrome.exe"`.
- When frozen on macOS or Linux, returns `None` for now. choreographer launches Chromium there through
  `[sys.executable, _unix_pipe_chromium_wrapper.py, ...]`, and `sys.executable` is the PyInstaller bootloader,
  so the right path alone does not work (PORTABLE_APP_PLAN.md, "Freeze"). The macOS and Linux Full builds are
  separate Phase 1 items. Leave a comment that names that blocker.
- `pngcheck.bundled_browser()` and `BROWSER_DIR` move here. `pngcheck.py` imports them, so the check and the app
  resolve the same file.

### `figure_to_png(fig, **kwargs)`

1. If `png_export_available()` is false (Light), raise `PngExportUnavailableError` before touching Kaleido.
   Callers already check this first. The guard here keeps the Light invariant if a new caller forgets.
2. If not frozen, return `fig.to_image(format="png", **kwargs)`. No change for pip users.
3. If frozen Full:
   - Resolve `bundled_browser_path()`. If it is `None` or not a file, raise `BundledBrowserUnavailableError`.
     **Do not fall back** to a system or downloaded browser. Full's claim is offline PNG from the shipped
     binary, and `--png-check` already fails when a browser outside the onedir launches.
   - Start Kaleido's global sync server once, lazily, under a module `threading.Lock`:
     `kaleido.start_sync_server(path=str(browser), mathjax=False, silence_warnings=True)`. These are the
     arguments `pngcheck.py` already proved offline. Skip the start when `kaleido._global_server.is_running()`
     would be true; keep that check behind a tiny helper so tests can fake it, or track a module flag set
     only after a successful start.
   - Return `fig.to_image(format="png", **kwargs)`. With the server running, plotly 6.8 routes through
     `kaleido.calc_fig_sync`, which calls the running server (`kaleido/__init__.py`).
4. Start lazily, not at app startup. A user who never exports PNG never spawns Chromium.

The error messages hold no paths. Use a fixed string such as
"The bundled browser for PNG export is missing from this GUISkinDose Full copy." Callers log through the
existing `safe_error_event` path, which records the exception type only.

### `stop_png_browser()`

Calls `kaleido.stop_sync_server(silence_warnings=True)` if this module started it. Kaleido registers an
`atexit` close itself. Also call `stop_png_browser()` from the GUI shutdown path in `gui/app.py` (the
`app.on_shutdown` hook, or next to the existing shutdown handler), so a windowed exit does not leave a
Chromium child behind. It must be safe to call when nothing was started.

### Call sites

- `export/images.py`: replace `fig.to_image(...)` with `figure_to_png(fig, width=..., height=..., scale=...)`.
  It keeps its `except Exception: return None`, so a missing bundled browser becomes the existing
  "image unavailable" notice.
- `gui/figures.py`: replace `fig.to_image(format="png")` with `figure_to_png(fig)`. It already logs and
  re-raises. In `gui/tabs/export.py`, the PNG failure notify currently blames a missing `kaleido` package.
  Add a branch for `BundledBrowserUnavailableError` that says the bundled browser is missing and suggests
  re-extracting the zip. Put the text in `dev-docs/ui_copy.json` and run `scripts/sync_ui_copy.py`.
- `plotting/create_dose_map_plot.py`: replace `fig.to_image(format="png")` with `figure_to_png(fig)`. The
  frozen app does not reach this path today; routing it keeps one rule for every PNG.

### Thread safety

GUI exports run off the event loop. Two exports can start at once. The start lock covers the first-start
race. The implementer must confirm that `GlobalKaleidoServer.call_function` is safe to call from several
threads (it queues tasks to one server thread) and note the finding in a code comment. If it is not, wrap the
`to_image` call in the same lock.

### `--png-check`

Change `_render_pngs` to stop calling `kaleido.start_sync_server` itself. It should render through the normal
export payload, which now goes through `figure_to_png`, and call `stop_png_browser()` in `finally`. The check
then proves the app's own path instead of a parallel one. Keep its process-list assertions, the
`BROWSER_PATH` decoy in `portable-spike.yml`, and the http-script page check.

`run_png_check` sets nothing extra: `sys.frozen` is already true in the onedir, and the edition is Full.

## Tests

Unit tests in `tests/unittests/test_png_browser.py`. None of them launch a browser.

- Not frozen: `figure_to_png` calls `fig.to_image` and never calls `kaleido.start_sync_server`.
- Frozen Windows with a fake `sys.executable` in `tmp_path` and a fake `chromium/chrome.exe`: the first call
  starts the server with that exact path and `mathjax=False`. A second call does not start it again.
- Frozen Full with the browser missing: raises `BundledBrowserUnavailableError`, and neither `to_image` nor
  `start_sync_server` is called. The message does not contain `str(tmp_path)`.
- Frozen on `darwin` and `linux`: raises `BundledBrowserUnavailableError` without calling Kaleido.
- Light: raises `PngExportUnavailableError` without calling Kaleido, frozen or not.
- `stop_png_browser()` is a no-op when nothing started, and stops once after a start.
- Two threads calling `figure_to_png` at once start the server exactly once.
- Each call site: `images.render_dosemap_png` returns `None` on `BundledBrowserUnavailableError`;
  `figures.make_dosemap_png` re-raises it. Patch `figure_to_png` where the call site imports it.
- Update `tests/unittests/test_portable_pngcheck.py` for the moved `bundled_browser` helper and the removed
  direct `start_sync_server` call.
- Keep the Light tests in `test_edition.py` passing unchanged. They already refuse `start_sync_server`.

The export-tab notify branch is GUI code; its test goes under `tests/gui/`.

## Acceptance

- The Windows Full job in `portable-spike.yml` passes `--png-check` with the decoy system Chrome on `BROWSER_PATH`,
  and the report shows only onedir browser processes. This now exercises `figure_to_png`.
- Manual, Windows Full: launch the GUI with the network off, calculate the example RDSR, and download the PNG.
  Record which `chrome.exe` launched. This closes the open interactive half of Phase 0's offline check if it
  passes on a machine with no system Chrome.
- Pip install on macOS: GUI PNG download still works with the system browser.

## Docs

- `PORTABLE_APP_PLAN.md`: tick the Phase 1 sub-item and point at this plan. Keep the macOS and Linux
  wrapper blocker visible.
- `dev-docs/MAINTENANCE_LOG.md` Unreleased entry. `CHANGELOG.md` only if a user-visible message changed
  (the new export-tab notice does, so add one line).
- `dev-docs/CODEBASE_OVERVIEW.md` and `FEATURE_INVENTORY.md` if they list the export modules.
- Archive this plan under `plans/archive/` when it ships, and update `dev-docs/index.md` in the same PR.

## Out of scope

- The macOS and Linux Full builds and the choreographer wrapper replacement.
- Turning Chromium's sandbox on (`enable_sandbox`). Record today's `--no-sandbox` default only.
- The WebView2 Fixed Version runtime (Phase 4).
