# NiceGUI 4 migration plan

**Status:** planned (2026-11-22). **Tracks:** Dependabot PR #233 (`nicegui` 3.18.0 → 4.0.0).

NiceGUI 4.0 removes the APIs deprecated during 3.x, changes a few defaults, and updates the bundled
JavaScript libraries. Most of its behaviour changes raise no error, so this plan lists what was
checked in this repository and what each step must verify.

## Current findings

PR #233 was run locally against its own lock (Python 3.13, `uv sync --all-extras`):

- `tests/gui`: 11 failed, 478 passed. Every failure is in `tests/gui/test_run_state_roundtrip.py`
  and has one cause (step 2).
- `tests/unittests`: 1 failure, `test_edition.py::test_light_rich_report_marks_images_unavailable_without_a_browser`.
  It is the `subprocess.Popen` fixture bug that PR #232 fixed on `main`; the Dependabot branch predates
  that fix. Rebasing clears it.

The failing tests call `_run_config._do_load(...)` outside any client slot. NiceGUI 3 fell back to a
default slot when `ui.notify` ran there. NiceGUI 4 raises `RuntimeError: The current slot cannot be
determined because the slot stack for this task is empty`. In the running app, `_do_load` runs inside
an upload handler, which has a slot, so this is a test-harness change rather than an app bug. Step 3
audits the app for the same pattern anyway.

## Impact of each 4.0 change on this repository

| 4.0 change | Impact here | Step |
|---|---|---|
| Minimum Python 3.11, FastAPI 0.143.1 | None. `requires-python` is already `>=3.11`; the lock resolves FastAPI. | 1 |
| `httpx` no longer installed (replaced by `httpx2`) | No code imports `httpx`. The `certifi` floor comment in `pyproject.toml` names `nicegui -> httpx`; check `certifi` stays in the lock and update the comment. | 1 |
| UI created outside a slot raises | 11 GUI tests. Audit app code for UI calls in background tasks. | 2, 3 |
| `run.io_bound` / `run.cpu_bound` raise `CancelledError` instead of returning `None` | `gui/concurrency.require_io_result` (21 call sites) exists only to unwrap that `None`. `gui/tabs/_phantom_catalog.py:146` checks `spool is None`. `gui/figures.py` docstrings describe the sentinel. | 4 |
| `ui.timer` callbacks must not swallow `CancelledError` | No `except BaseException` or bare `except:` in `src/guiskindose/gui`. Re-check timers that wrap awaits in broad `except Exception` (safe: `CancelledError` is a `BaseException`). | 4 |
| Cleared `ui.input` holds `''`, not `None` | Three inputs. `kerma_meter_file` and `kerma_meter_explicit_label` (`gui/tabs/corrections.py:154,164`) bind to state that elsewhere may treat `None` as unset. The export title already uses `value or ""`. | 5 |
| Element IDs change from `c12` to `ng-12` | No hard-coded IDs found. `gui/dose_severity.py:130` builds a tooltip target from `row.html_id`, which stays correct. | 6 |
| Old snake_case/camelCase prop names ignored | No affected props found (`ui.scene`, `ui.leaflet`, `ui.aggrid`, `ui.markdown` extras unused). | 6 |
| `table.pagination` now shows controls | No table sets `pagination` after creation. | 6 |
| Quasar 2.35: dialogs close on mousedown on the backdrop | Ten `ui.dialog` uses, including the welcome dialog and pre-calculation prompts. Check none relied on click-only dismissal. | 7 |
| plotly.js 3.1.1 → 4.2.0 in-browser | All in-app plots (Geometry, Settings preview, Results dose maps). Plotly 7 (Python) already targets plotly.js 4, so this removes the current 3/4 version split. | 7 |
| Chrome/Edge 121, Safari 17.2 minimum | Affects `--native` (WebView2 on Windows, WKWebView on macOS) and the portable app. Note in release notes. | 7 |
| Removed APIs (`ui.add_scss`, `coroutine=`, `Object3D`, awaitable lifecycle hooks, `ui.tab` outside `ui.tabs`) | None found by grep. Step 8 runs basedpyright to confirm. | — |

## Steps

1. **Rebase PR #233 on `main`.** Regenerate the lock if Dependabot has not. Raise the floors in the `gui`
   and `gui-native` extras to `nicegui>=4.0.0`. Confirm `certifi` still resolves and correct the
   `httpx` comment.
2. **Fix the 11 tests.** Wrap each `_do_load(...)` call in `with _client(user):`, the pattern the same
   file already uses to create its status label. Do not weaken assertions.
3. **Audit app code for UI outside a slot.** Search for `ui.notify`, `ui.*(` element creation, and
   `.update()` reached from `background_tasks.create`, `asyncio.create_task`, `run.io_bound` callbacks,
   and `app.on_*` hooks. Each must run under an element's `with` block or a handler's slot. Add a GUI test
   for any path found.
4. **Replace the `None` sentinel.** Remove `require_io_result` and its call sites, or reduce it to a
   pass-through and remove it in a follow-up. Replace `if spool is None` in `_phantom_catalog.py` with an
   `except asyncio.CancelledError` that notifies and re-raises. Update `gui/figures.py` docstrings. Grep
   for any other `is None` check on an `io_bound` result.
5. **Normalise cleared inputs.** For the two kerma-meter inputs, map `''` to `None` in the binding
   (`forward=lambda v: v or None, backward=lambda v: v or ''`), so saved run state and calculations keep
   treating an empty field as unset. Add a GUI test that clears each field.
6. **Grep checks.** Confirm no hard-coded `c<digits>` IDs, old prop names, or post-creation
   `table.pagination` assignments crept in since this plan.
7. **Manual smoke.** In browser mode and `--native` on macOS, and on Windows if possible: welcome dialog,
   upload, Settings preview, Geometry views, a calculation, the Results dose map (placeholder and real),
   pre-calculation prompts, and HTML/PNG export. Record results in the PR.
8. **Gates.** Full `pytest`, basedpyright, the complexity gate, Semgrep, and a local SonarQube scan. Then
   update `CHANGELOG.md` (Changed: NiceGUI 4; browser minimums), `dev-docs/MAINTENANCE_LOG.md`,
   `dev-docs/THIRD_PARTY_NOTICES.md` (`check_licenses.py --write-notices`), and
   `dev-docs/plans/GUI_PLAN.md` §0. Archive this plan when the PR merges.

## Out of scope

Adopting new 4.0 features (`pagination_controls`, `httpx2` in our own code, Python 3.15 support).
Revisit after the migration lands.
