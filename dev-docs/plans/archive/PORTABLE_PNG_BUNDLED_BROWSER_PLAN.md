# Portable Full: render PNG through the bundled Chromium

_Status: shipped (2026-11-03). Every PNG render goes through `figure_to_png`, and the frozen Windows Full app renders with its bundled Chromium only. Still open: the manual Windows GUI offline PNG check, and recording the `--png-check` `render_seconds` after the next Windows Full CI run._
_Child of [PORTABLE_APP_PLAN.md](../PORTABLE_APP_PLAN.md), Phase 1 item "The bundled
browser path is passed to Kaleido explicitly inside the process that renders."_
_Implementation note: review found that `kaleido.calc_fig_sync` drops `kopts` when a global sync server is running, so `figure_to_png` runs the async `kaleido.calc_fig` on a fresh thread instead. The text below is the original plan._

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
def bundled_browser() -> Path: ...              # platform-general, moved from pngcheck.py
def bundled_browser_for_render() -> Path | None: ...
def figure_to_png(fig, *, width=None, height=None, scale=None) -> bytes: ...
class BundledBrowserUnavailableError(RuntimeError): ...
```

### Do not use Kaleido's global sync server

An earlier draft started `kaleido.start_sync_server(path=...)` once and let `fig.to_image()` use it. Review of
kaleido 1.5.0 (`kaleido/_sync_server.py`) found three problems with that, and all three are verified:

- `call_function` is not safe for concurrent callers. Every result goes into one shared `_return_queue`, so
  two GUI exports at once can receive each other's bytes or exceptions.
- `open()` sets `_initialized = True` right after `thread.start()`. The browser launches inside that thread.
  If the launch fails, the thread dies, `is_running()` stays true, and the next `call_function` blocks forever
  on `_task_queue.join()`. A damaged or quarantined `chrome.exe` would hang the export with no message.
- The server needs a shutdown hook. The GUI's only shutdown handler is registered when `not native`, and
  Windows Full is native.

Use Kaleido's one-shot path instead. With no server running, `kaleido.calc_fig_sync(...)` runs
`oneshot_async_run`, which starts a fresh `Kaleido` (and browser) in a new thread, returns the bytes, closes the
browser, and re-raises any exception in the caller. Each call is isolated, so there is no shared queue, no
stale state after a failure, and nothing to stop at exit. The cost is one browser start per image. See
"Performance" below.

### `bundled_browser()` and `bundled_browser_for_render()`

- `bundled_browser()` moves from `pngcheck.py` unchanged in behavior: `<exe dir>/chromium/chrome.exe` on
  Windows, `<exe dir>/chromium/chrome` elsewhere. Move `BROWSER_DIR` with it. It always returns a `Path`, so
  `pngcheck._check_bundle()` keeps working on every OS. Keep `pngcheck.app_dir()` where it is, because
  `test_portable_pngcheck.py` patches it; `bundled_browser()` may take an optional `base: Path` so pngcheck can
  pass `app_dir()`.
- `bundled_browser_for_render()` returns `None` when not frozen. When frozen on Windows, it returns
  `bundled_browser()`. When frozen on macOS or Linux it returns `None`: choreographer launches Chromium there
  through `[sys.executable, _unix_pipe_chromium_wrapper.py, ...]`, and `sys.executable` is the PyInstaller
  bootloader (PORTABLE_APP_PLAN.md, "Freeze"). Name that blocker in a comment. **Consequence:** a frozen
  macOS or Linux Full build fails PNG closed until the Phase 1 wrapper item lands. Say this in the parent plan.

### `figure_to_png(fig, *, width=None, height=None, scale=None)`

1. If `png_export_available()` is false (Light), raise `PngExportUnavailableError` before importing Kaleido.
2. If not frozen, return `fig.to_image(format="png", width=width, height=height, scale=scale)`. Pip users see
   no change.
3. If frozen Full:
   - If `bundled_browser_for_render()` is `None` or not a file, raise `BundledBrowserUnavailableError`.
     **Do not fall back** to a system or downloaded browser.
   - Fill width, height and scale the way plotly 6.8 does (`plotly/io/_kaleido.py`, `to_image`: argument,
     then `fig.layout`, then the layout template, then `plotly.io.defaults`). Factor that into a small helper
     and test it against `fig.to_image`'s defaults so the frozen and pip images keep the same size.
   - Call `kaleido.calc_fig_sync(fig.to_dict(), opts={"format": "png", "width": ..., "height": ...,
     "scale": ...}, kopts={"path": str(browser), "mathjax": False})`. Pass plotly's `defaults.plotlyjs` in
     `kopts` only if it is set, as plotly does. Confirm in the implementation that `calc_fig` passes
     `kopts` to `Kaleido(**kopts)` (kaleido 1.5.0 `__init__.py`, `calc_fig`), so `path` reaches choreographer.
   - Leave Kaleido's `timeout` at its default of 90 seconds. It bounds a browser that starts but never answers.
   - Catch every exception from Kaleido and re-raise it as `BundledBrowserUnavailableError` with a fixed
     message, `from None`. Kaleido's `ChromeNotFoundError` text embeds the absolute browser path
     (`kaleido/kaleido.py`, around line 195), and the export tab and logs must not show it.
4. A module `threading.Lock` around the Kaleido call is optional. Each one-shot call has its own browser, so it
   is correct without one. Add the lock only if the measurement below shows two concurrent Chromium starts
   cause trouble.

Fixed message: "The bundled browser for PNG export is missing or could not start in this GUISkinDose Full
copy. Re-extract the download and try again." Callers log through `safe_error_event`, which records the
exception type only.

choreographer logs `Found chromium path: ...` through logistro (`choreographer/browsers/chromium.py`). Confirm
those records do not reach the portable file log sink set up in `packaging/portable/entry.py`
(`_configure_file_log`). If they do, raise the `choreographer` and `kaleido` loggers to `WARNING` in the frozen
entry, and add a test.

### Performance

A rich export renders several views per exam (`export/payload.py`, `_render_images`), so it starts Chromium
several times. `--png-check` already records `render_seconds`. Record the new figure in PORTABLE_APP_PLAN.md
next to the Phase 0 number. If the export is more than about twice as slow as with the server, open a follow-up
to batch all views of one export into one `Kaleido` session. Do not batch in this change.

### Call sites

- `export/images.py`: replace `fig.to_image(...)` with `figure_to_png(fig, width=..., height=..., scale=...)`.
  Its `except Exception: return None` turns a missing bundled browser into the existing "image unavailable"
  notice.
- `gui/figures.py`: replace `fig.to_image(format="png")` with `figure_to_png(fig)`. It already logs and
  re-raises.
- `gui/tabs/export.py`: add `except BundledBrowserUnavailableError` **before** `except RuntimeError`, because
  it subclasses `RuntimeError`. Show the fixed message. The neighbouring PNG messages are string literals today;
  keep the new one a literal too, and do not add `ui_copy.json` plumbing in this change.
- `plotting/create_dose_map_plot.py`: replace `fig.to_image(format="png")` with `figure_to_png(fig)`, so every
  PNG follows one rule.

### `--png-check`

`_render_pngs` stops calling `kaleido.start_sync_server` and `stop_sync_server`. It renders through the normal
export payload, which now reaches `figure_to_png`, so the check proves the app's own path. Keep the
`generate_index` capture, the process-list assertions, and the http-script page check. The process list is
read while the payload renders today; with one-shot browsers, each browser has exited by the time
`collect_export_payload` returns. Move the process sampling into a wrapper around `figure_to_png` (patch
`guiskindose.export.images.figure_to_png` inside `_render_pngs` with a function that calls the real one on a
worker thread and samples `_list_processes()` while it runs), so at least one sample sees the live browser.
Restore the original in `finally`.

In `.github/workflows/portable-spike.yml`, reword the decoy comment that says the check passes the path
explicitly; the app now does.

## Tests

Unit tests in `tests/unittests/test_png_browser.py`. None of them launch a browser.

- Not frozen: `figure_to_png` calls `fig.to_image` and never calls `kaleido.calc_fig_sync` directly.
- Frozen Windows with `sys.executable` faked into `tmp_path` and a fake `chromium/chrome.exe`: `calc_fig_sync`
  gets `kopts["path"]` equal to that file and `mathjax=False`, and `kaleido.start_sync_server` is never called.
- Width, height and scale defaults match plotly's resolution order for an argument, a layout value, and neither.
- Frozen Full with the browser missing: raises `BundledBrowserUnavailableError`; Kaleido is not called.
- Kaleido raising an error whose text contains `str(tmp_path)`: the re-raised message does not contain it.
- Frozen on `darwin` and `linux`: raises `BundledBrowserUnavailableError` without calling Kaleido.
  `bundled_browser()` still returns a `Path` on both.
- Light: raises `PngExportUnavailableError` without importing or calling Kaleido, frozen or not.
- `images.render_dosemap_png` returns `None` on `BundledBrowserUnavailableError`; `figures.make_dosemap_png`
  re-raises it. Patch `figure_to_png` where each call site imports it.
- `tests/unittests/test_portable_pngcheck.py`: `_render_pngs` calls `figure_to_png` and never
  `start_sync_server`; the report records `render.error_type == "BundledBrowserUnavailableError"` and skips the
  page step when rendering fails; the moved `bundled_browser` still honors a patched `app_dir`.
- `tests/gui/test_export_error_semantics.py`: the export tab shows the bundled-browser message for
  `BundledBrowserUnavailableError`, not the "kaleido package" message.
- `test_edition.py` Light tests pass unchanged.

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
- Batching several images into one Kaleido session (see Performance).
- Turning Chromium's sandbox on (`enable_sandbox`). Record today's `--no-sandbox` default only.
- The WebView2 Fixed Version runtime (Phase 4).
