# Export Failure Messaging Plan

**Status:** **Complete** (2026-11-26) — implemented on `gui/export-failure-messaging`; archived.
**Branch:** `gui/export-failure-messaging`
**Scope owner:** GUI export paths and their shared, GUI-free failure classifier
**Backlog item:** `dev-docs/TO_DO.md` → GUI / UX → "Better export-failure messaging"

## 1. Problem

Exports fail with a generic toast even when the cause is specific and fixable. The most visible
case is PNG: `kaleido` 1.x no longer bundles Chromium, so a source or pip install without Chrome
fails; the Export tab currently says the export "may require the 'kaleido' package", which is
installed and is not the problem. The same class of gap exists for report backends and the data
table's XLSX writer.

Two existing mechanisms are close but incomplete:

- `MissingExportDependencyError` + `_show_missing_dependency_dialog()` already name a package, but
  the advice is stale: `reportlab`, `python-docx`, and `openpyxl` are **core** dependencies now and
  the `export` extra is a no-op alias (`pyproject.toml`). `pip install guiskindose[export]` is
  therefore the wrong primary instruction, and it is meaningless in the frozen portable app.
- `png_browser.py` classifies *frozen* browser errors well, but the source/pip path forwards raw
  Plotly/Kaleido exceptions. Plotly rewraps `ChromeNotFoundError` as a plain `RuntimeError` in both
  the 6.x line (from the 6.3.1 floor) and 7.x, so exception type alone cannot identify a missing
  browser there.

This plan adds one small classifier that maps an export failure to a user-facing guidance kind,
one reusable dialog that renders it, and targeted wiring in every GUI export path. Light-edition
gating and frozen-build repair messaging are preserved by construction.

## 2. Inventory — GUI export paths and current behavior

All paths resolve a native save path first (`gui/io_helpers._get_save_path`) and then write through
`gui/tabs/export._write_or_download` (`atomic_write_private` in native mode, `ui.download` in
browser mode). Write failures already use `safe_error_event` + `safe_user_error("<write_key>")`.

| # | Path | Entry point | Backend / external requirement | Current failure behavior |
|---|---|---|---|---|
| E1 | Results JSON | `ExportTabController.download_json` | stdlib `json` | `json.dumps` is outside any `try`; a serialization error escapes to NiceGUI |
| E2 | HTML dose map | `download_html` → `make_dosemap_html` | Plotly (core) | `except Exception` → negative toast plus "Could not generate the HTML dose map. Check the log for details." |
| E3 | PNG dose map | `download_png` → `make_dosemap_png` | `kaleido` + installed Chrome/Chromium (source/pip); bundled Chromium (frozen Full) | **Light:** `export.light_edition.no_png` warning (by design, keep). **Frozen Full:** `BundledBrowserUnavailableError` → re-extract message; `PngRenderError` → render message. **Source/pip:** any raw exception → generic toast that wrongly suggests installing `kaleido` |
| E4 | Rich report XLSX | `_render_rich_report` → `writers.render_bytes` | `openpyxl` (core) | `ModuleNotFoundError` → `MissingExportDependencyError` → stale package dialog |
| E5 | Rich report PDF | same | `reportlab` (core) | same stale dialog |
| E6 | Rich report DOCX | same | `python-docx` / import name `docx` (core) | same stale dialog |
| E7 | Rich report HTML | same | Plotly (core) | Non-backend exception → dismissible `safe_user_error("rich_report_export")` toast only |
| E8 | Rich report embedded images | `export/payload._render_images` → `export/images.render_dosemap_png` | `kaleido` + browser | Swallowed; report succeeds with "Image unavailable (kaleido/export error)" (Light gets its own wording) — no guidance, no dialog by design |
| E9 | Data table CSV/TXT | `gui/tabs/data._local_export` | pandas/stdlib | Content build is outside `try`; write errors handled |
| E10 | Data table XLSX | same, `_export_content` → `pandas.ExcelWriter` | `openpyxl` (core) | `_export_content` is outside `try` → missing `openpyxl` becomes an **uncaught** GUI exception |
| E11 | Example kerma-meter CSV | `gui/tabs/corrections._download_example_calibration_file` | none | Write failure → `safe_user_error("example_calibration_write")` |
| E12 | Run configuration JSON | `gui/tabs/_run_config._on_save` | stdlib + serialization | Serialize failure has its own message; write failure → `safe_user_error("run_config_write")` |

Out of scope but noted: native save-dialog failures (already reported by `_get_save_path`), unsafe
destination rejections (`safe_output.UnsafeOutputPathError`, separately coded), and CLI export
failures (see §9 follow-up).

## 3. Design

### 3.1 Failure taxonomy

Six kinds (five actionable plus the existing unknown fallback):

| Kind | Meaning | User action |
|---|---|---|
| `missing_package` | A known export backend module is absent (`openpyxl`, `reportlab`, `docx`, `kaleido`) | Install that package |
| `missing_browser` | Source/pip PNG render has no resolvable Chrome/Chromium | `plotly_get_chrome -y`, or set `BROWSER_PATH` |
| `incomplete_install` | An import failed but no known backend is missing (damaged/incomplete app) | Reinstall GUISkinDose (pip) |
| `portable_repair` | Any of the above in a frozen build, or a missing bundled browser | Re-extract the download; never mention pip |
| `unknown` | Anything else | Existing generic, value-safe failure toast |
| *edition gate* | Light edition PNG, by design | Existing `export.light_edition.no_png` message; no dialog |

### 3.2 GUI-free classifier

New module `src/guiskindose/export/failure_guidance.py`:

```python
class ExportFailureKind(StrEnum):
    MISSING_PACKAGE = "missing_package"
    MISSING_BROWSER = "missing_browser"
    INCOMPLETE_INSTALL = "incomplete_install"
    PORTABLE_REPAIR = "portable_repair"
    UNKNOWN = "unknown"

@dataclass(frozen=True)
class ExportFailure:
    kind: ExportFailureKind
    format: str | None = None
    import_name: str | None = None
    pip_name: str | None = None
    command: str | None = None

def classify_export_failure(
    exc, *, format=None, frozen: bool | None = None
) -> ExportFailure: ...
```

`frozen=None` auto-detects with `is_frozen_app()`; callers may pass an explicit value in tests.
A frozen build is **never** given a pip command, regardless of the kind.

Rules, evaluated in order:

1. `MissingExportDependencyError` → `missing_package` using its own `format` / `package`
   (`frozen=True` → `portable_repair`).
2. `ImportError` (including `ModuleNotFoundError`):
   - If a **known backend for `format`** is absent (`importlib.util.find_spec` returns `None`) →
     `missing_package` for that backend. Probing beats message sniffing and keeps exception text
     out of the decision.
   - Otherwise → `incomplete_install` (pip) or `portable_repair` (frozen).
3. `PngBrowserUnavailableError` → `missing_browser` with `plotly_get_chrome -y`;
   `frozen=True` → `portable_repair`.
4. `BundledBrowserUnavailableError` → `portable_repair`.
5. Anything else → `unknown`.

The browser probe must be read-only: `find_browser(skip_local=False)` only checks paths and the
environment. It must never run `plotly_get_chrome` or otherwise touch the network, and a test pins
that (patch the download helpers to fail if called).

Backend table (single source of truth):

```python
FORMAT_BACKENDS = {
    "png":  ("kaleido",),
    "xlsx": ("openpyxl",),
    "pdf":  ("reportlab",),
    "docx": ("docx",),
    "html": (),
}
PIP_INSTALL_NAMES = {"docx": "python-docx"}
PLOTLY_GET_CHROME_COMMAND = "plotly_get_chrome -y"
```

The module also owns `pip_name()`, `install_hint_for(package)`, and
`package_install_command(package)` so the writer layer keeps one message source:

- `install_hint_for()` replaces `writers.__init__._install_hint()` and drops the stale
  `guiskindose[export]` claim. It names the exact package command and, for an incomplete install,
  says to reinstall the app.
- `MissingExportDependencyError.install_hint` continues to carry a ready-to-print sentence for the
  CLI. GUI rendering uses structured fields + catalog copy, not that sentence.

Frozen detection: one helper `is_frozen_app()` in `src/guiskindose/edition.py` (beside
`png_export_available()`, using `getattr(sys, "frozen", False)`). `png_browser._is_frozen()` and
`safe_output.validate_output_path()` both delegate to it; no new module, no platform branches.

### 3.3 Typed source-install PNG errors

In `export/png_browser.py`:

- Add `PngBrowserUnavailableError(RuntimeError)` with message
  `"PNG export needs an installed Chrome or Chromium browser."`
- In `figure_to_png()`, only on the **non-frozen** path, wrap `fig.to_image(...)` in
  `try/except`:
  1. `safe_error_event(logger, "png_render", exc)` (value-free, as today).
  2. `importlib.util.find_spec("kaleido") is None` → raise
     `MissingExportDependencyError("png", "kaleido", install_hint_for("kaleido"))`.
  3. `system_browser_available()` returns `False` → raise `PngBrowserUnavailableError()`.
     Probe: `choreographer.browsers.chromium.Chromium.find_browser(skip_local=False)` (honors
     `BROWSER_PATH`, checks the choreographer-managed download and typical installs). It performs
     filesystem/environment lookups only — never a download or network call. Return `None` if the
     probe itself errors, so an uncertain probe never produces a wrong message. A test patches the
     download helpers to fail if invoked.
  4. Otherwise raise `PngRenderError()`.
- Frozen path and messages stay unchanged (`BundledBrowserUnavailableError`, `PngRenderError`).
- Why post-failure probing: the success path and its tests stay untouched, and Plotly's
  `ChromeNotFoundError` → `RuntimeError` conversion no longer hides the cause. A browser that is
  discoverable but fails to launch is reported as a render failure, which is honest.

### 3.4 One reusable GUI dialog

New module `src/guiskindose/gui/components/export_failure_dialog.py`:

```python
@dataclass(frozen=True)
class FailureDialogContent:
    title: str
    body: str
    detail: tuple[str, ...]          # "Format: PDF", "Package: reportlab"
    command: str | None
    command_label: str | None
    retry: str | None

def failure_dialog_content(failure: ExportFailure) -> FailureDialogContent: ...
def show_export_failure_dialog(failure: ExportFailure) -> None: ...
```

- Pure `failure_dialog_content()` (catalog lookups plus code-owned package/format values) is
  unit-testable; `show_export_failure_dialog()` renders a persistent modal with an icon, title,
  body, detail lines, a monospace command with the existing copy-to-clipboard control
  (`export.copy_command.tooltip`), and a Close button.
- `portable_repair` content has **no command** and no pip wording.
- `unknown` never opens the dialog; callers keep the existing toast.
- Replaces `_show_missing_dependency_dialog()` in `gui/tabs/export.py`.

### 3.5 Handler wiring

| Path | Change |
|---|---|
| E1 `download_json` | Wrap payload serialization in `try/except`; `safe_error_event("json_export")` + existing generic notify (no dependency guidance) |
| E2 `download_html` | **Unchanged.** HTML needs only core Plotly; the existing generic toast is sufficient and no dialog wiring is added |
| E3 `download_png` | Keep Light gate first. Add `except MissingExportDependencyError` and `except PngBrowserUnavailableError` → dialog; keep `BundledBrowserUnavailableError` and `PngRenderError` branches. Remove the misleading "may require the 'kaleido' package" text from the final fallback |
| E4–E7 `_render_rich_report` | Replace the `MissingExportDependencyError`-only handler with `except (MissingExportDependencyError, ImportError)` → `classify_export_failure(..., format=fmt)` → dialog. Other exceptions keep the dismissible `safe_user_error("rich_report_export")` toast |
| E9/E10 data tab | Probe the known backend with `probe_export_readiness(fmt)`, build content in `try/except ImportError` (and generic `except Exception`), then call `_get_save_path` — so a missing backend or content failure never prompts for or precedes a save path. Classify with `format=fmt`; XLSX failure becomes handled instead of uncaught |
| E8, E11, E12 | Unchanged; recorded as non-goals/follow-ups (§9) |

All handlers keep `safe_error_event` as the only log path. The dialog shows only code-owned
format/package names and fixed commands — never exception text, file names, or paths.

## 4. UI copy keys (canonical: `dev-docs/ui_copy.json`)

New keys, owner `gui/components/export_failure_dialog.py`:

| Key | Text |
|---|---|
| `export.failure.format_line` | `Format: {format}` |
| `export.failure.package_line` | `Package: {package}` |
| `export.failure.missing_package.title` | `Export needs an extra package` |
| `export.failure.missing_package.body` | `This export format needs a Python package that is not installed in this copy of GUISkinDose.` |
| `export.failure.missing_browser.title` | `PNG export needs a web browser` |
| `export.failure.missing_browser.body` | `Kaleido 1.x renders images with an installed Chrome or Chromium browser and no longer includes one. Install Chrome for Testing with the command below, or point the BROWSER_PATH environment variable at an existing Chrome or Chromium.` |
| `export.failure.incomplete_install.title` | `GUISkinDose is missing a required component` |
| `export.failure.incomplete_install.body` | `A dependency is missing or damaged. Reinstall GUISkinDose with pip, then try the export again.` |
| `export.failure.portable_repair.title` | `This GUISkinDose copy is incomplete` |
| `export.failure.portable_repair.body` | `A component this export needs is missing from the app files. Re-extract the GUISkinDose download and try again.` |
| `export.failure.install_package_label` | `Install the missing package:` |
| `export.failure.install_browser_label` | `Install a browser for image export:` |
| `export.failure.retry` | `Then try the export again.` |

Reused: `export.copy_command.tooltip`, `export.light_edition.no_png`.
Placeholders use the existing `copy_text(...).format(...)` pattern (precedent:
`settings.human_mesh.unavailable`, `native.webview2.runtime_missing`).

`src/guiskindose/gui/ui_copy.json` is regenerated with `python scripts/sync_ui_copy.py`; never
hand-edited.

## 5. Files

### New

- `src/guiskindose/export/failure_guidance.py`
- `src/guiskindose/gui/components/export_failure_dialog.py`
- `tests/unittests/test_export_failure_guidance.py`
- `tests/gui/test_export_failure_messaging.py`
- `dev-docs/plans/archive/EXPORT_FAILURE_MESSAGING_PLAN.md` (this file)

### Modified

- `src/guiskindose/edition.py` — `is_frozen_app()` helper
- `src/guiskindose/safe_output.py` — frozen check delegates to `is_frozen_app()`
- `src/guiskindose/export/png_browser.py` — typed source errors, shared frozen probe
- `src/guiskindose/export/writers/__init__.py` — `_install_hint` delegates to shared guidance
- `src/guiskindose/gui/tabs/export.py` — unified dialog + PNG/rich-report catch branches
- `src/guiskindose/gui/tabs/data.py` — handled XLSX failure; content before save dialog
- `src/guiskindose/__main__.py` — value-safe `MissingExportDependencyError` handling in `_call_or_exit`
- `dev-docs/ui_copy.json` + generated `src/guiskindose/gui/ui_copy.json`
- `docs/source/gui_help/export_workflow.md` + generated `src/guiskindose/gui/help/export_workflow.md`
- `docs/source/user/running_the_gui.md` — PNG section: `plotly_get_chrome -y`, `BROWSER_PATH`, and
  where the in-app guidance appears
- `dev-docs/feature_doc_matrix.json` — `rich_exports` code/tests/help entries
- `dev-docs/FEATURE_INVENTORY.md` — §7.7 failure-guidance sentence
- `dev-docs/plans/RICH_EXPORT_PLAN.md` — pointer to this plan in its GUI UX section
- `dev-docs/index.md` — plan row (moved to archived after completion)
- `dev-docs/TO_DO.md` — remove the finished item (same PR, after CHANGELOG impact is logged)
- `CHANGELOG.md` — `[Unreleased] → Fixed`
- `tests/unittests/test_export_missing_dependency.py` — install-hint assertions
- `tests/unittests/test_png_browser.py` — source-path classification + no-download probe tests
- `tests/unittests/test_export_cli.py` — CLI hint reaches the user
- `tests/unittests/test_edition.py` — `is_frozen_app()` reads the runtime flag
- `tests/gui/test_export_error_semantics.py` — PNG/source and dialog-dispatch assertions
- `tests/gui/test_data_tab_coverage.py` — XLSX import failure handled

## 6. Tests

### Classification (pure, `tests/unittests/test_export_failure_guidance.py`)

- `MissingExportDependencyError` → `missing_package` with expected pip name; frozen →
  `portable_repair`.
- `ImportError` with a backend absent (patched `importlib.util.find_spec`) → `missing_package`
  per format; backend present → `incomplete_install`; frozen → `portable_repair`.
- `PngBrowserUnavailableError` → `missing_browser` with `plotly_get_chrome -y`; frozen →
  `portable_repair`.
- Omitting `frozen` in a simulated frozen runtime (`sys.frozen` patched, `is_frozen_app` not
  patched) → `portable_repair` with no command.
- `BundledBrowserUnavailableError` → `portable_repair`.
- Arbitrary `RuntimeError` → `unknown`.
- `install_hint_for` contains the exact pip name, contains no `guiskindose[export]`, and (for the
  docx case) uses `python-docx`.

### PNG boundary (`tests/unittests/test_png_browser.py`)

- Source `to_image` raises + `find_spec("kaleido") is None` → `MissingExportDependencyError`.
- Source `to_image` raises + browser probe `False` → `PngBrowserUnavailableError`.
- Probe `True` or probe error (`None`) → `PngRenderError`.
- The probe does not download or touch the network: patch the choreographer download helpers to
  raise if called and assert the classification still completes.
- Raised messages carry no exception text/path (mirror `test_render_failure_is_logged_by_class_only`).
- Existing frozen/Light tests stay green unchanged.

### Dialog content (`tests/gui/test_export_failure_messaging.py`)

- `failure_dialog_content()` per kind: title/body/detail/command/label/retry; portable has no
  command and no pip text; missing package uses the pip name (`python-docx` for `docx`).
- One `User`-harness render test: `show_export_failure_dialog()` displays the catalog title, the
  command, and copies it via `ui.clipboard.write` (patched).

### Handler dispatch (extend `tests/gui/test_export_error_semantics.py`)

- `download_png` with `PngBrowserUnavailableError` → dialog (patched) and no "kaleido" toast.
- `download_png` with `MissingExportDependencyError("png", "kaleido", ...)` → dialog.
- Frozen `BundledBrowserUnavailableError` → existing re-extract message, dialog not opened.
- Light → `export.light_edition.no_png`; dialog not opened.
- `_render_rich_report` with `ImportError` → dialog; unknown `RuntimeError` → toast only.
- `download_html` behavior is unchanged (no new assertion beyond the existing generic toast test).

### CLI (`tests/unittests/test_export_cli.py`)

- A `MissingExportDependencyError` reaches `_call_or_exit` and prints its code-owned install hint
  (format + package + command) to stderr, then exits 1 — not the generic `cli_run` message.
- No path, file name, or exception text appears in that output.

### Data tab (`tests/gui/test_data_tab_coverage.py`)

- `_export_content` patched to raise `ModuleNotFoundError` with `fmt="xlsx"` and openpyxl absent →
  dialog; no uncaught exception; no save dialog requested.
- CSV path unchanged.

## 7. Implementation phases (each independently green)

1. **Classifier foundation** — `edition.is_frozen_app()`, `safe_output` delegation,
   `export/failure_guidance.py`, writers hint delegation, unit tests,
   `test_export_missing_dependency.py` updates.
2. **PNG boundary** — typed source errors + read-only probe, `png_browser` tests.
3. **GUI + CLI wiring** — dialog component, export/data handlers, `_call_or_exit`,
   `ui_copy.json` + `sync_ui_copy.py`, GUI/CLI tests.
4. **Docs + lifecycle** — help source + `sync_gui_help.py`, running-the-GUI guide, feature matrix,
   FEATURE_INVENTORY, RICH_EXPORT_PLAN pointer, `dev-docs/index.md`, CHANGELOG impact first, then
   remove the TO_DO item; archive the plan once verified.

## 8. Acceptance criteria

1. A missing report backend (XLSX/PDF/DOCX) opens a persistent dialog that names the import and pip
   package (for example `python-docx`), offers the exact `pip install ...` command, and never claims
   `guiskindose[export]` is required.
2. In a source or pip install, a PNG export without Chrome shows the browser dialog with
   `plotly_get_chrome -y`; it no longer suggests that `kaleido` may be missing when it is installed.
3. A frozen (portable) build shows only the re-extract message — no pip command appears in any
   portable repair dialog.
4. The Light edition still hides the PNG card and shows `export.light_edition.no_png`; no dialog is
   opened for the edition gate.
5. A data-table XLSX export with `openpyxl` unavailable is handled with the same guidance instead
   of an uncaught GUI exception.
6. Unknown failures keep today's value-safe toast; logs remain value-free
   (`guiskindose.privacy.safe_error_event` only); no exception text, file name, or path is shown or
   logged.
7. The CLI prints the same code-owned install hint instead of the generic `cli_run` message.
8. The failure-path browser probe performs no download and no network access.
9. Gates pass: `scripts/check_ui_copy.py`, `scripts/sync_ui_copy.py --check`,
   `scripts/sync_gui_help.py --check`, `scripts/check_help_registry.py`,
   `scripts/check_feature_doc_matrix.py`, `scripts/check_file_sizes.py`,
   `scripts/check_complexity.py`, Ruff, `basedpyright`, and the full unit/GUI pytest suites.
10. TO_DO item removed, CHANGELOG entry added, help/guide updated, and this plan archived with
    `dev-docs/index.md` updated once implementation lands.

## 9. Non-goals and recorded follow-ups

- **Embedded report images (E8)** — still degrade to "Image unavailable (kaleido/export error)".
  Using the classifier wording there changes payload/report text and is deferred.
- **Write-destination failures (E11/E12 and every `atomic_write_private` call)** — remain generic
  coded messages; surfacing `UnsafeOutputPathError` guidance is a separate UX item.
- **JSON serialization failure (E1)** — handled generically; no dependency guidance is possible
  without a concrete cause.

## 10. Implementation evidence (2026-11-26)

- Classification and typed PNG errors: new/updated tests in `test_export_failure_guidance.py`,
  `test_png_browser.py`, `test_export_missing_dependency.py`, `test_export_cli.py`, and
  `test_edition.py`.
- GUI wiring: 591 GUI tests pass, including the new dialog-content and dispatch tests and the
  existing Light/frozen behavior tests.
- Full unit suite: 3997 passed, 4 skipped.
- Gates: UI-copy sync/check, help-registry, feature matrix, file sizes, complexity, Ruff, and
  basedpyright all pass.

## 11. Verification commands

```bash
python scripts/sync_ui_copy.py
python scripts/sync_gui_help.py
python scripts/check_ui_copy.py
python scripts/check_help_registry.py
python scripts/check_feature_doc_matrix.py
python scripts/check_file_sizes.py
uv run --extra dev --extra gui --locked pytest -q --ignore=tests/gui -n auto
uv run --extra dev --extra gui --locked pytest -q tests/gui -n auto
uv run --extra dev --extra gui --locked ruff check src tests
uv run --extra dev --extra gui --locked basedpyright
```
