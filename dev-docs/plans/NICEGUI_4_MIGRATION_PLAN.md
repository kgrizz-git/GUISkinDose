# NiceGUI 4 migration plan

**Status:** in progress — Steps 1–5 complete (2026-11-22); Steps 6–8 remain. **Tracks:** Dependabot PR #233 (`nicegui` 3.18.0 → 4.0.0).

NiceGUI 4.0 removes the APIs deprecated during 3.x, changes a few defaults, and updates the bundled
JavaScript libraries. Most of its behaviour changes raise no error, so this plan records every change
in the 4.0 migration guide, what it means here, and what each step must verify. Reviewed by DeepSeek
V4.1 Flash and Muse Spark 1.3 (PR #238).

## Current findings

- **CI on PR #233:** `tests/gui` reports 11 failed, 477 passed, 1 skipped (`gui-smoke` and coverage
  jobs). The non-GUI suite passes. All 11 failures are in `tests/gui/test_run_state_roundtrip.py`.
- **Cause of the 11 failures: the test harness, not the app.** Through 3.18, `nicegui.testing.User` replaced
  `ui.notify` with its own recorder on every attribute access (`testing/user.py:65`). Our
  `install_notification_defaults()` (`gui/notifications.py`, called from `app.py`) captured that recorder,
  so a `ui.notify` reached outside any slot was recorded instead of raising. NiceGUI 3.19 (and 4.0) record
  notifications from the client outbox instead, so the captured function is the real `ui.notify`, and
  `_do_load` → `_notify_warnings` (`gui/tabs/_run_config.py`) raises
  `RuntimeError: The current slot cannot be determined`. The tests call `await _do_load(...)` after their
  `with _client(user):` block ends. In the app, `_do_load` runs from the upload handler `_on_load`, which
  has a slot.
- **Local-only failure:** `test_edition.py::test_light_rich_report_marks_images_unavailable_without_a_browser`
  failed locally under `uv sync --all-extras`, which pulls in IPython. That is the `subprocess.Popen`
  fixture bug PR #232 fixed on `main`; it does not reproduce in CI. Rebasing clears it locally.

## Impact of each 4.0 change on this repository

### Requirements and dependencies

| 4.0 change | Impact here | Step |
|---|---|---|
| Python ≥ 3.11 | None. `requires-python` is already `>=3.11`. | — |
| FastAPI ≥ 0.143.1 | The lock jumps fastapi 0.136.3 → 0.165.0, starlette 1.3.1 → 1.10.0, plus uvicorn and websockets. `gui/upload_body_limit_middleware.py` is pure ASGI and must still cap uploads; `tests/gui/test_upload_body_limit_integration.py` covers it. The upload route `/_nicegui/client/{id}/upload/{eid}` is unchanged in 4.0. | 1, 8 |
| `httpx` replaced by `httpx2` | No code imports `httpx`. The lock keeps `httpx` 0.28.1 through another dependency. `certifi` stays only because it is a direct `gui`/`gui-native` dependency, so the `pyproject.toml` comment "transitive via nicegui -> httpx" must be rewritten. New transitives: `httpx2`, `httpcore2`, `truststore`, `opentelemetry-api`. | 1, 8 |
| Pillow ≥ 13 (matplotlib extra) | Already satisfied (`pyproject.toml`). | — |
| Chrome/Edge ≥ 121, Safari ≥ 17.2 | `gui/webview2.py` gates `--native` on Windows at `MIN_WEBVIEW2_VERSION = (86, 0, 622, 0)`, pywebview's floor. A WebView2 between 86 and 120 would pass the check and open a broken window. On macOS, Safari 17.2 means WKWebView on macOS 14.2 or later. | 5 |

### Behaviour changes (guide items 1–13)

| # | 4.0 change | Impact here | Step |
|---|---|---|---|
| 1 | Old snake_case/camelCase prop names ignored | None. A grep for every renamed prop (`html_columns`, `camera_params`, `resource_path`, `use_mermaid`, …) finds nothing. `ui.markdown` is used (`app.py`, `components/help_button.py`) but with no props. `background-color` hits in `styles.py` are CSS. The 3.19 pass in step 1 is the real detector. | 1 |
| 2 | Cleared text inputs hold `''`, not `None` | Three `ui.input`s. `kerma_meter_file` and `kerma_meter_explicit_label` (`gui/tabs/corrections.py`) bind to `str \| None` state. Every consumer found is falsy-tolerant (`_kerma_meter_model.py` `if not …file`, `calculate.py` `(… or "").strip()`, `settings_builder.py` `or None`). The export title already uses `value or ""`. Remaining risk: saved run state round-tripping `''`. | 6 |
| 3 | `run.cpu_bound` uses "spawn" | None. No `cpu_bound` calls. | — |
| 4 | `run.io_bound`/`cpu_bound` raise `CancelledError` instead of returning `None` | 30 `run.io_bound` calls in `src/guiskindose/gui`. 13 go through `gui/concurrency.require_io_result`, which exists only to unwrap the `None`. Sentinel checks in `gui/tabs/_phantom_catalog.py`: `if result is not None` in `commit_install`, `if spool is None` in `install_upload`, and `if stream is None` after `open_phantom_pack_stream()` (`io_helpers.py`). Other call sites use `if fig:` style checks that become dead on shutdown. `dev-docs/HARNESS_ENGINEERING.md` § GUI tests says `io_bound` "short-circuits to `None`", which becomes false. | 4 |
| 5 | DOM IDs change from `c12` to `ng-12` | None. No hard-coded IDs in app or tests. `gui/dose_severity.py` targets tooltips through `row.html_id`, and its test follows `html_id`. | — |
| 6 | Spot lights default to `decay=2.0` | None. No `ui.scene`. | — |
| 7 | `table.pagination` shows controls | None. No table sets `pagination` after creation. | — |
| 8 | Custom scene objects and map layers need a `with` block | None. No `ui.scene` or `ui.leaflet`. | — |
| 9 | `Screen.should_not_contain` waits | None. No Selenium `Screen` tests; `should_not_see` in `tests/gui/test_gui_smoke.py` is the `User` API. | — |
| 10 | Observable collections have no `__dict__` | None. The repo's `vars()` and `__dict__.update` uses are on plain objects (`helpers/create_attributes_string.py`, `export/writers/pdf.py`). | — |
| 11 | Bindings no longer poll values written past `BindableProperty.__set__` | None. `state.__dict__.update(...)` in `gui/exam_loaders.py` and `tests/gui/conftest.py` writes to `AppState`, a plain dataclass. NiceGUI polls bindings to plain attributes, which this change does not touch. The smoke in step 7 confirms widgets follow exam loads. | 7 |
| 12 | `WEB_CONCURRENCY` > 1 raises | None. Not set by the app, launchers, or portable entry. | — |
| 13 | `ui.timer` callbacks must not swallow `CancelledError` | None found. No `except BaseException` or bare `except:` in `src/guiskindose/gui`; `except Exception` does not catch `CancelledError`. | — |

The 4.0 removed-API list (`ui.add_scss`/`ui.add_sass`, `coroutine=`, `sanitize=None`, `KWONLY_SLOTS`,
`Object3D`, awaitable lifecycle hooks, `ui.tab` outside `ui.tabs`, `Props.add_rename`) has no uses here;
`ui.tab`s are nested in `ui.tabs` in `app.py`. Step 8's basedpyright run confirms.

### Bundled libraries

| Library | Impact here | Step |
|---|---|---|
| Quasar 2.18 → 2.35: dialogs close on mousedown on the backdrop | Ten `ui.dialog`s. The welcome dialog is `persistent`. The pre-calculation prompts (`gui/tabs/calculate.py`, three dialogs) are not, so a stray press on the backdrop now dismisses them sooner. | 7 |
| plotly.js 3.1.1 → 4.2.0 in-browser | All in-app plots. Plotly 7.1 (Python) embeds plotly.js 4.1.1 in HTML exports, so the split shrinks to 4.1.1 export vs 4.2.0 app. No removed features are used (`mapbox`, `hsv()`, 0–1 `rgb()` fractions, `fitbounds`, `splom`); the repo's colours are integer `rgb(...)`. **Privacy:** 4.2 adds a "Share chart" button that uploads chart data to `cloud.plotly.com`. It is hidden by default and must stay hidden. | 6, 7 |
| AG Grid, three.js, xterm.js, nipplejs | None. `ui.aggrid`, `ui.scene`, `ui.xterm`, `ui.joystick` are unused. | — |

## Steps

1. **Step through 3.19 first, as the guide asks.** On a branch, pin `nicegui>=3.19,<4`, run the app and the
   full test suite with warnings shown, and fix every NiceGUI deprecation warning. This is the only reliable
   detector for changes that are silent in 4.0, such as ignored prop names.
   **Done (2026-11-22):** `gui`/`gui-native` now require `nicegui>=3.19,<4`; the lock moved only `nicegui`
   3.18.0 → 3.19.0. No NiceGUI deprecation warnings were raised (pytest with warnings shown, NiceGUI log
   warnings, GUI startup/render, and a static sweep of deprecated props and removed APIs). The 11
   `test_run_state_roundtrip.py` failures that reproduce under 3.19 were fixed here (Step 3), by running
   `_do_load` inside the client slot. ruff, basedpyright, the complexity gate, and the full suite pass.
2. **Rebase PR #233 on that work.** Run `uv lock` (both touch `uv.lock`) and check the fastapi, starlette,
   uvicorn, `httpx2` and `truststore` versions. Set the `gui` and `gui-native` extras to
   `nicegui>=4.0.0,<5`, so the next major is a deliberate migration. Rewrite the `certifi` comment in
   `pyproject.toml` to say it is a direct dependency.
   **Done (2026-11-22):** applied on `gui/nicegui-4` instead of rebasing PR #233 — both extras say
   `nicegui>=4.0.0,<5`, `uv lock --upgrade-package nicegui` moved nicegui 3.19.0 → 4.0.0, fastapi
   0.136.3 → 0.165.0 and starlette 1.3.1 → 1.10.0, and added `httpx2`, `httpcore2`, `truststore` and
   `opentelemetry-api`; PR #233 was not touched.
3. **Fix the 11 tests.** In `tests/gui/test_run_state_roundtrip.py`, move each `await _do_load(...)` inside
   the existing `with _client(user):` block. Do not weaken assertions.
   **Already landed in Step 1 (2026-11-22)** — the failures reproduce under 3.19, not only 4.0; the rebase in
   Step 2 should keep this change.
4. **Replace the `None` sentinel.** Remove `require_io_result` and its 13 call sites
   (`widgets/import_preview.py`, `tabs/calculate.py`, `tabs/_run_config.py`, `tabs/upload_builders.py`,
   `tabs/export.py`). In `_phantom_catalog.py`, delete the three `None` checks and let `CancelledError`
   propagate; the existing `finally` blocks still close the stream and spool, and a shutdown notification
   is pointless. Review the other 17 `run.io_bound` call sites for checks that assumed `None` meant
   cancellation. Update the `gui/figures.py` docstrings and `HARNESS_ENGINEERING.md` § GUI tests.
   **Done (2026-11-22):** `require_io_result` and all 13 call sites removed; the export handlers no longer
   special-case a cancellation string. The two `io_bound` shutdown sentinels (`result is not None`,
   `spool is None`) are gone. The `stream is None` check in `native_install` stays: that `None` is a
   cancelled native dialog, not an `io_bound` result, and `CancelledError` now propagates from the open.
   Reviewed 24 `io_bound` sites (the plan's 30 is stale); the remaining `if fig:`-style checks are genuine
   builder failures. Tests assert `CancelledError` propagates with the pack stream and spool closed.
5. **Raise the native browser floors.** Set `MIN_WEBVIEW2_VERSION` in `gui/webview2.py` to a 121.x floor,
   update its comment (it is no longer pywebview's threshold), and add a "120 is too old" case to
   `tests/gui/test_webview2_check.py`. State the macOS 14.2 minimum for `--native` in
   `docs/source/user/running_the_gui.md` and the portable-app notes.
   **Done (2026-11-22):** `MIN_WEBVIEW2_VERSION = (121, 0, 0, 0)` with a NiceGUI 4 comment and a
   120-too-old/121-passes test; `running_the_gui.md` and `PORTABLE_APP_PLAN.md` state WebView2/Edge 121,
   macOS 14.2 (Safari 17.2 WebKit), and Chrome/Edge 121+ or Safari 17.2+ in browser mode.
6. **Normalise cleared inputs and lock down plotly sharing.** For the two kerma-meter inputs, map `''` to
   `None` in the binding (`forward=lambda v: v or None, backward=lambda v: v or ''`), and add a GUI test that
   clears each field and round-trips saved run state. Add a test or grep gate that no `ui.plotly` config or
   exported figure sets `showSendToCloud`.
7. **Manual smoke.** In browser mode and `--native` on macOS, and on Windows if possible:
   - welcome dialog, upload, and an exam load whose values appear in bound widgets;
   - Settings preview, Geometry views, a calculation, and the Results dose map (placeholder and real);
   - each non-persistent dialog, including the three pre-calculation prompts: confirm a press on the
     backdrop does not lose an answer the user meant to give, and mark any that must be `persistent`;
   - HTML and PNG export; confirm no "Share chart" button in the app or the exported HTML.
   Record the results in the PR.
   **Browser mode done (2026-11-22, PR #240):** a Playwright smoke on Chromium and WebKit passed every
   check: the persistent welcome dialog survives a backdrop press; the Results placeholder and caption show
   before upload; upload (24 events), the Data Table, the Settings preview and Geometry render; the
   calculation gives 14.08 mGy; the real dose map replaces the placeholder; HTML (plotly.js 4.1.1) and PNG
   export work; there is no "Share chart" button in the app (plotly.js 4.2.0) and the export does not enable
   `showSendToCloud`. The only console error, plotly's "Resize must be passed a displayed plot div element"
   from hidden tabs, occurs equally on `main` under 3.19. The pre-calculation prompts were checked in code
   rather than driven: a backdrop dismissal resolves the dialog as cancel, so no answer is applied by
   accident. **Remaining:** `--native` on macOS (and Windows if available), which Playwright cannot drive.
8. **Gates and docs.** Full `pytest`, basedpyright, the complexity gate, Semgrep, a local SonarQube scan,
   `check_doc_freshness.py`, and `check_help_registry.py` if help copy changed. Update `CHANGELOG.md`
   (Changed: NiceGUI 4; native browser minimums), `dev-docs/MAINTENANCE_LOG.md`,
   `dev-docs/THIRD_PARTY_NOTICES.md` (`check_licenses.py --write-notices`), `dev-docs/plans/GUI_PLAN.md`
   §0, and `dev-docs/index.md`. When packaging resumes, re-check the portable freeze's collect list for the
   new transitives. Archive this plan when the migration merges.

## Follow-ups found during the migration

- `open_phantom_pack_stream()` (`gui/io_helpers.py`) catches every exception from the native file dialog and
  returns `None`, so a real dialog error looks like a user cancel and `native_install` exits silently.
  Pre-existing; found in the Step 4 review. Distinguish the two and notify on a real error.

## Out of scope

Adopting new 4.0 features (`pagination_controls`, `httpx2` in our own code, Python 3.15 support).
Revisit after the migration lands.
