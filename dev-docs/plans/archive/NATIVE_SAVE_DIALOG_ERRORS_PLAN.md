# Native save-dialog error handling plan

**Status:** complete (2026-11-24) except the §7 manual `--native` smoke, which is pending. Drafted by DeepSeek V4.1 Flash; reviewed by Muse Spark 1.3 and Claude. Source: the *Native save dialogs swallow errors
as a cancel* item in [TO_DO.md](../../TO_DO.md) (GUI / UX), a follow-up from §5 of
[NATIVE_FILE_DIALOG_ERRORS_PLAN.md](NATIVE_FILE_DIALOG_ERRORS_PLAN.md).

## 1. Root cause

1. `_get_save_path()` in `src/guiskindose/gui/io_helpers.py` wraps `import webview` and
   `await main_window.create_file_dialog(...)` in `try/except Exception` that logs `native_save_dialog` at
   DEBUG and returns `None`.
2. `None` is the same value the genuine-cancel branch returns (`if not result: return None`). Callers cannot
   tell "user cancelled" from "the dialog broke".
3. Every caller gates on that value: `if save_path is None and _is_native_mode(): return`. So a real failure
   exits exactly like a cancel: no notification, no write, no visible trace.
4. Seven call sites: `tabs/export.py` (×4: JSON, HTML, PNG, rich report); `tabs/_run_config.py` (`_on_save`);
   `tabs/corrections.py` (example calibration file); `tabs/data.py` (`_local_export`).
5. `asyncio.CancelledError` is a `BaseException`, so none of this is involved in shutdown; it must keep
   propagating (NiceGUI 4 contract).

## 2. Design

1. **Rejected: propagate and add `try/except` at all seven callers.** It mirrors the merged phantom-pack fix,
   but duplicates the same handler seven times across four tabs, and each copy can drift.
2. **Rejected: a result type or error sentinel.** It is a new contract at seven sites for a distinction no
   caller acts on: all seven abort either way.
3. **Recommended: one shared reporting layer.** Keep `_get_save_path()` as the function callers await, but
   split it:
   - `_request_native_save_path(default_name, extension)` owns both the existing no-native-window guard
     (→ `None`) and the dialog block with its `try/except` removed. `if not result: return None` stays and
     covers `None`, `()`, `[]` and `""`; anything else returns the chosen path; every failure propagates,
     matching `open_phantom_pack_stream` after the merged fix.
   - `_get_save_path(...)` becomes a thin wrapper and owns the single handler:
     `try: return await _request_native_save_path(...)`; `except Exception as exc:` (exactly that, so
     `CancelledError` still propagates) → one `safe_error_event(logger, "native_save_dialog", exc)` at ERROR,
     one `ui.notify(copy_text("native.save_dialog.failure"), type="negative")`, then `return None`.
4. Why: one place to log, one place to notify, no duplicated `try/except`, and no new result contract. The
   name `_get_save_path` stays, so the seven call sites and the existing test monkeypatches keep working;
   only the `# user cancelled` comments need updating.
5. Keeping `None` is deliberate: every caller aborts either way, and the wrapper has already told the user.
   A browser-download fallback is not an option, because native pywebview windows ignore `ui.download()`.
6. The first guard (no native window → `None`) stays. If the window lookup itself fails, `_is_native_mode()`
   fails the same way, so the caller falls through to `ui.download()`. In browser mode that is a real download.
   In a native process it is a no-op, so that edge stays silent (pre-existing; see §8.4). Corrected in the final
   review: the draft called this "degraded, not silent", which is wrong for native mode.
7. Import `ui` lazily inside the handler (`from nicegui import ui`) so `io_helpers` stays importable without
   the GUI extra. `copy_text` needs no lazy import; it only reads JSON.
8. Notifying from the helper is safe: all seven callers await it inside NiceGUI button handlers, so a client
   slot is active. There is no double notification, because every caller returns on `None` before any
   write-failure notification.

**Done (§2):** implemented as written — `_request_native_save_path` owns the guard and dialog with no
`try/except`; `_get_save_path` owns the single ERROR + notify handler and returns `None`.

## 3. What the user sees

One new UI-copy key, `native.save_dialog.failure`, owned by `gui/io_helpers.py`:
"Could not open the save dialog, so nothing was saved. Try again." It fits all seven flows (exports, run
configuration, example calibration file, event table), and the `native.*` namespace already exists. The
sentence lives only in `dev-docs/ui_copy.json` (synced to the packaged mirror by `scripts/sync_ui_copy.py`);
`io_helpers.py` references the key through `copy_text(...)` and must not contain the literal, or
`check_ui_copy.py` fails.

| Caller | On failure |
|---|---|
| `export.download_json` | Notification from the helper; returns before building content; no write. |
| `export.download_html` | Same; no HTML render, no write. |
| `export.download_png` | Same; no PNG render, no write. |
| `export.export_rich_report` | Same; the rich-report dialog stays open, no "Generating report…", no write. |
| `_run_config._on_save` | Same; the status label keeps its previous text. |
| `corrections._download_example_calibration_file` | Same; no browser-download fallback. |
| `data._local_export` | Same; no write, no "Downloaded CSV/XLSX". |

Rejected: reusing each caller's write-failure copy. A dialog failure is not a write failure, and it would
need several new keys.

**Done (§3):** one new key, `native.save_dialog.failure`, owned by `gui/io_helpers.py` with the sentence as
written; `io_helpers.py` holds no literal.

## 4. Privacy

1. `safe_error_event` records only the operation code, exception class, and code location; never a filename,
   path, or message. The code `native_save_dialog` is reused; only its level changes from DEBUG to ERROR.
2. One event per failure at one layer: the primitive logs nothing, the wrapper logs once, and the callers add
   nothing.
3. The notification carries catalog text only, never exception text.

**Done (§4):** as written — value-free code/class/location log, one event at one layer, catalog-only notify.

## 5. Tests

1. `tests/unittests/test_gui_io_helpers_save_path.py` (new; nicegui stubbed via `sys.modules` as in
   `test_gui_io_helpers_phantom_pack.py`): the primitive propagates a raising dialog; maps `None`, `()`, `[]`
   and `""` to `None`; returns `str`, `tuple` and `list` results; browser mode returns `None` without
   importing `webview`; a missing `webview` raises.
2. `tests/gui/test_save_dialog_errors.py` (new): the wrapper turns a raising primitive into exactly one
   `native_save_dialog` ERROR record and one notification with the catalog sentence, and returns `None`; a
   falsy result gives no record and no notification; a path passes through; a `CancelledError` propagates.
   The helper imports `ui` lazily, so patch `nicegui.ui.notify` (the object the lazy import binds), as
   `test_phantom_pack_settings.py` patches `catalog.ui.notify`. Capture logs at INFO: at DEBUG,
   `safe_error_event` adds a second, value-free traceback record for the same event.
3. Same file, a failure/cancel pair per caller (14 tests): monkeypatch `io_helpers._request_native_save_path`
   to raise or to return `None`, with `_is_native_mode` → `True`. On failure: one notification and the
   write/download/label seam not called. On cancel: no notification.
4. Prove the fix: restoring the old code removes the primitive, so the per-caller tests in §5.3 cannot run
   against it verbatim. The fail-without-fix evidence is §5.1's propagation test (old code returns `None`)
   and §5.2's wrapper test (old code gives no notification and only a DEBUG record).
5. Existing tests that monkeypatch `_get_save_path` keep working because the name stays.
6. Direct-call tests do not go through the `user` fixture, so they need no allowlist entry. Only if a
   `user`-fixture flow test lets the record reach teardown, add
   `ExpectedGuiError("guiskindose.gui.io_helpers", "native_save_dialog")` to `tests/gui/expected_gui_errors.py`.
7. Run `scripts/sync_ui_copy.py` and `scripts/check_ui_copy.py`. Keep complexity within C901 ≤ 10.

**Done (§5):** `tests/unittests/test_gui_io_helpers_save_path.py` and
`tests/gui/test_save_dialog_errors.py` as written (wrapper + 14 per-caller tests; logs captured at INFO).
Fail-without-fix: with the old code restored, 30 of the 31 new tests fail (no `_request_native_save_path`
primitive), and a direct old-code probe returns `None` with no notification and only a DEBUG
`native_save_dialog` record. No `user`-fixture flow tests, so no allowlist entry was needed.

## 6. Docs

1. Remove the *Native save dialogs swallow errors as a cancel* item from `TO_DO.md`.
2. `CHANGELOG.md` `[Unreleased]` → `Fixed`: a failed native save dialog now reports that nothing was saved
   instead of silently doing nothing; cancelling still does nothing.
3. `dev-docs/MAINTENANCE_LOG.md` entry: the split, the DEBUG → ERROR change, the new UI-copy key, the tests.
4. Archive this plan to `dev-docs/plans/archive/` in the same PR and add its `dev-docs/index.md` row.

**Done (§6):** TO_DO item removed; CHANGELOG `[Unreleased]` Fixed entry added under the first `### Fixed`
heading; MAINTENANCE_LOG entry added; this plan archived with fixed relative links and an index row.

## 7. Manual `--native` smoke

1. Run `python -m guiskindose --mode gui --native`, load an example RDSR, calculate, export JSON, and cancel:
   nothing is notified or written.
2. Repeat without cancelling: the file saves.
3. Repeat once each for HTML, PNG, a rich report, run-configuration save, the example calibration file, and
   the Data tab CSV/XLSX export.
4. A real dialog failure is hard to force by hand; the automated tests in §5.3 are the evidence. Note the
   platform smoked.

**Pending (§7):** not run. The four manual `--native` steps above remain outstanding.

## 8. Risks

1. Users now see an error where they saw silence. That is the intent. On a platform where pywebview raises on
   every save, exports now stop with a message instead of doing nothing.
2. `native_save_dialog` moves from DEBUG to ERROR, so it can surface in fixture log assertions (§5.6).
3. All flows share one log code and one sentence, so per-flow detail is lost in the log line.
4. If `_is_native_mode()` ever returned `False` in native mode, a reported failure would fall through to
   `ui.download()`, a no-op in pywebview. Pre-existing and out of scope.
5. A missing `webview` in native mode now notifies instead of failing silently, as in the merged
   phantom-pack fix.
6. Light edition: `download_png` is gated by `png_export_available()` before the dialog, and Light offers no
   PNG card, so that path is unreachable there. Nothing extra to test.

**Done (§8):** risks unchanged; no platform smoke was run (§7 pending).
