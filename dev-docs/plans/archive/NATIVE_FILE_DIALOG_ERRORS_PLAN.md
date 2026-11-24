# Native file-dialog error handling plan

**Status:** complete (2026-11-23) except the §8 manual `--native` smoke, which is pending. Drafted by Muse Spark 1.3; reviewed by Claude. Source: the
*Native phantom-pack dialog errors look like cancellation* item in [TO_DO.md](../../TO_DO.md), added by PR #241.
The `--native` manual smoke (section 8) is still pending.

## 1. Root cause

1. `open_phantom_pack_stream()` in `src/guiskindose/gui/io_helpers.py` wraps the pywebview
   `create_file_dialog` call in `try/except Exception` and returns `None` on any error. That is the same value
   a genuine cancel produces (`if not result: return None`).
2. `native_install` in `src/guiskindose/gui/tabs/_phantom_catalog.py` already has an `except Exception` branch
   that logs through `safe_error_event` and calls `_notify_install_failure`. It never runs for a dialog
   failure, because the helper has already turned the error into `None`, so `native_install` returns
   silently.
3. `asyncio.CancelledError` is unaffected. It is a `BaseException`, so no `except Exception` catches it, and
   it already propagates from `run.io_bound` (covered by existing tests).

**Done:** confirmed as written; the fix removes only the second `try`.

## 2. Design

1. Let the dialog error propagate. Delete the `try/except` around the dialog block in
   `open_phantom_pack_stream()` and keep only the falsy-result-to-`None` mapping for a genuine cancel.
2. This is the smallest change. It matches the existing `run.io_bound(open, ...)` path in the same function,
   which already propagates `OSError` (`test_open_phantom_pack_stream_open_failure_propagates`), and it reuses
   the handler `native_install` already has.
3. Log at one layer only. `native_install` keeps `safe_error_event(logger, "phantom_pack_open_dialog", exc)`
   and `_notify_install_failure`. The helper stops logging its own `native_open_dialog` event, so one failure
   produces one log event.
4. The same `try` also covers `import webview`. A missing pywebview in native mode now notifies instead of
   failing silently, which is the intended behaviour.
5. Rejected alternatives: a result type or error sentinel adds a new contract for one call site, and
   re-raising after logging in the helper would log one failure twice.
6. The first `try` (no native main window → `None`) stays as it is: outside native mode there is no dialog
   to fail.

**Done:** implemented exactly as designed. `open_phantom_pack_stream()` now imports `webview` and awaits the dialog
outside any `try`; the `native_open_dialog` log call was deleted, and `native_install`'s existing
`safe_error_event(..., "phantom_pack_open_dialog", ...)` + `_notify_install_failure` handler is the single reporter.

## 3. What the user sees

1. On a dialog failure, the existing `copy_text("settings.phantom_catalog.install_failure")` sentence appears
   in the status label and as a negative notification, as for any other install failure.
2. No new UI copy, so `dev-docs/ui_copy.json` is unchanged.
3. A cancel stays silent.

**Done:** the existing `settings.phantom_catalog.install_failure` sentence is used unchanged; `ui_copy.json` untouched.

## 4. Privacy

`safe_error_event` records only the operation code, exception class, and code location, never a message,
path, or filename. No new log call sites are added.

**Done:** the helper no longer logs at all; the one remaining event is the caller's existing value-free one.

## 5. Scope

1. `_get_save_path` in `io_helpers.py` has the same swallow-as-cancel pattern. Its seven callers
   (`export.py` ×4, `_run_config.py`, `corrections.py`, `data.py`) treat `None` as a silent cancel.
2. Leave it unchanged here. Changing it alters the cancel-versus-failure contract across four tabs. Add a
   follow-up item to `TO_DO.md` instead.

**Done:** `_get_save_path` unchanged; the follow-up item is under **GUI / UX** in `TO_DO.md`.

## 6. Tests

1. Unit test in `tests/unittests/test_gui_io_helpers_phantom_pack.py`: `create_file_dialog` raises
   `RuntimeError`, and the error propagates. It returns `None` today, so it fails without the fix.
2. GUI tests in `tests/gui/test_phantom_pack_settings.py`, following the existing `install_upload` pattern
   (stub `catalog.run.io_bound`, capture `catalog.ui.notify`):
   - the dialog raises → a negative notification and the failure status text appear;
   - the dialog returns `None` → no notification and no status change.
3. Existing tests (cancel returns `None`, both cancellation-propagates tests, open failure propagates) keep
   passing unchanged.
4. Complexity stays within the C901 ≤ 10 gate; the change removes a branch.

**Done:** both new tests pass with the fix and fail without it (old `try/except` temporarily restored:
`test_open_phantom_pack_stream_dialog_failure_propagates` reported `DID NOT RAISE`,
`test_native_install_dialog_failure_notifies` saw no notification). The cancel GUI test and all existing tests pass
unchanged.

## 7. Docs

1. Add a `TO_DO.md` item for the `_get_save_path` follow-up.
2. Remove the *Native phantom-pack dialog errors* item from `TO_DO.md`. It arrives with PR #241, so do this
   when rebasing onto `main` after #241 merges.
3. `CHANGELOG.md` `[Unreleased]` → `Fixed`: a failed native phantom-pack file dialog now shows the install
   failure message instead of doing nothing.
4. `dev-docs/MAINTENANCE_LOG.md` entry.
5. Archive this plan to `dev-docs/plans/archive/` in the same PR and update `dev-docs/index.md`.

**Done:** all five items are complete. Item 2 was done when this branch was rebased onto `main` after PR #241
merged (2026-11-24), which brought in the TO_DO item.

## 8. Manual `--native` smoke

1. Run `python -m guiskindose --mode gui --native`, open Settings, click the phantom-pack install button,
   cancel the dialog, and confirm nothing is notified.
2. Install a pack through the same dialog to confirm the success path.
3. A real dialog failure is hard to force by hand, so the GUI test in step 6 is the evidence for that path.

**Pending:** not run. The three manual `--native` steps above remain outstanding; the automated evidence is the
`tests/gui/test_phantom_pack_settings.py` pair and `tests/unittests/test_gui_io_helpers_phantom_pack.py`.

## 9. Risks

1. pywebview may report a cancel as `None`, an empty tuple, or an empty list. `if not result` covers all three
   and stays.
2. `native_install`'s `except Exception` never catches `CancelledError`, so shutdown behaviour is unchanged.
3. Native dialogs differ by OS. Note in the PR which platforms were smoked.

**Done:** risks unchanged; no platform smoke was run (section 8 pending).
