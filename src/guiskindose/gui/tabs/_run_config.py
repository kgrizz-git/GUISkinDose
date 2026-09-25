"""Run-configuration export/import card (settings export, Phase 3 chunk E).

"Save run configuration" serializes the full GUI run state via
`build_settings()` + `serialize_run_state()` (Settings-tab checkbox gates
source identifiers). "Load run configuration" parses an uploaded JSON
document through `apply_run_state()`, re-parses tabular inputs when the
schema/sheet changed (single-file sessions), then resets results and
refreshes every tab. Warnings surface as notifications; `RunStateError`
fails loudly without mutating anything user-visible beyond the notify.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from nicegui import run, ui

from guiskindose.gui.run_state import (
    RunStateError,
    apply_run_state,
    restore_app_state_snapshot,
    serialize_run_state,
    snapshot_app_state,
)
from guiskindose.gui.settings_builder import build_settings
from guiskindose.privacy import safe_error_event, safe_user_error

from ..components import HelpButton
from ..concurrency import operation_guard, require_io_result
from ..helpers import load_tabular
from ..io_helpers import _get_save_path, _is_native_mode
from ..page_context import PageContext
from ..state import reset_results, state
from .export import _write_or_download

logger = logging.getLogger(__name__)

_CONFIG_DEFAULT_NAME = "guiskindose_run_config.json"
_CONFIG_UPLOAD_MAX_BYTES = 8 * 1024 * 1024
_MAX_SHOWN_WARNINGS = 5


def build_run_config_card(ctx: PageContext) -> None:
    """Render the Settings-tab run-configuration card and wire its handlers."""
    with ui.card().classes("modern-card w-full"):
        with ui.row().classes("w-full items-center justify-between"):
            ui.label("Run configuration").classes("text-subtitle2 q-mb-sm")
            HelpButton(
                title="Run configuration help",
                content_path="run_configuration.md",
                help_id="run_configuration",
            )
        ui.label(
            "Save the full run state (settings, corrections, per-exam offsets) as JSON, "
            "or load one back to reproduce a run."
        ).classes("text-xs text-grey-5 q-mb-md")
        include_ids = ui.checkbox("Include source identifiers (filenames, paths, labels)").classes("text-xs q-mb-sm")
        status_label = ui.label("").classes("text-xs text-grey-5")
        with ui.row().classes("w-full gap-2"):
            ui.button("Save run configuration", icon="save", on_click=lambda: _on_save(include_ids, status_label))
            uploader = (
                ui.upload(
                    label="LOAD RUN CONFIGURATION",
                    max_file_size=_CONFIG_UPLOAD_MAX_BYTES,
                )
                .props('accept=".json" flat bordered color=deep-purple auto-upload')
                .classes("uploader-no-list")
            )
            uploader.on_upload(lambda e: _on_load(e, ctx, status_label, uploader))


async def _on_save(include_ids: ui.checkbox, status_label: ui.label) -> None:
    """Serialize the live run state and persist it (native dialog or download)."""
    try:
        settings_obj = build_settings(state)
        document = serialize_run_state(
            settings_obj,
            state,
            normalization_profiles=settings_obj.normalization_settings.to_profile_list(),
            include_identifiers=bool(include_ids.value),
            passthrough=dict(state.run_state_passthrough),
        )
        content = json.dumps(document, indent=2).encode("utf-8")
    except Exception as exc:
        safe_error_event(logger, "run_config_serialize", exc)
        ui.notify("Could not serialize the run configuration. Check the log for details.", type="negative")
        return
    save_path = await _get_save_path(_CONFIG_DEFAULT_NAME, "json")
    if save_path is None and _is_native_mode():
        return  # user cancelled the native dialog
    _write_or_download(save_path, content, _CONFIG_DEFAULT_NAME, "Run configuration saved.", "run_config_write")
    status_label.set_text(f"Saved run configuration ({len(content)} bytes).")


async def _on_load(e: Any, ctx: PageContext, status_label: ui.label, uploader: ui.upload) -> None:
    """Parse an uploaded run-configuration document and apply it to GUI state."""
    try:
        await _do_load(e, ctx, status_label)
    finally:
        # Always clear the widget so the same file can be re-uploaded after a fix.
        uploader.reset()


_IMPORT_ERROR_MESSAGES = {
    "exam_count_mismatch": (
        "Cannot apply run configuration: the document covers a different number of exams "
        "than currently loaded. Load the same inputs in the same order and count, then re-import."
    ),
    "unsupported_schema": "Cannot apply run configuration: this file is not a run-configuration document.",
    "unsupported_schema_version": ("Cannot apply run configuration: the document needs a newer application version."),
    "invalid_settings": (
        "Cannot apply run configuration: the imported settings failed validation. Check the log for details."
    ),
}


async def _do_load(e: Any, ctx: PageContext, status_label: ui.label) -> None:
    """Implement `_on_load` (split out so the `finally` reset always runs)."""
    try:
        raw = await e.file.read()
    except Exception as exc:
        safe_error_event(logger, "run_config_read", exc)
        ui.notify("Could not read the uploaded file.", type="negative")
        return
    try:
        document = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        safe_error_event(logger, "run_config_parse", exc)
        ui.notify("The uploaded file is not valid JSON.", type="negative")
        return
    if state.busy:
        ui.notify(
            "Busy — please wait for the current operation to finish before importing a configuration.",
            type="warning",
        )
        return
    # Snapshot first: if the re-parse fails later, the pass-1 Tier-3 values
    # sitting over old parsed data would silently mix on the next calculation.
    # Rolling back makes a failed import atomic (all-or-nothing).
    snapshot = snapshot_app_state(state)
    try:
        result = apply_run_state(document, state)
    except RunStateError as exc:
        restore_app_state_snapshot(state, snapshot)
        safe_error_event(logger, "run_config_apply", exc)
        ui.notify(
            _IMPORT_ERROR_MESSAGES.get(exc.code, safe_user_error("run_config_apply")), type="negative", timeout=8000
        )
        ctx.refresh_event_table()
        ctx.refresh_exams_table()
        ctx.refresh_import_preview()
        ctx.refresh_per_exam()
        ctx.refresh_geometry_tab()
        return
    _notify_warnings(result.warnings)
    if result.mode != "calculate_dose":
        ui.notify(
            f"Document mode is {result.mode!r}, which the GUI cannot run — "
            "settings imported; calculation will use 'calculate_dose'.",
            type="warning",
            timeout=8000,
        )
    resequence_ok = await _resequence_reparse_if_needed(document, result.schema_or_sheet_changed)
    if not resequence_ok:
        # Roll back the pass-1 values: they sit over old parsed data and
        # would silently mix into the next calculation. Refresh repaints the
        # restored state (whose pre-import results stay valid, so no reset);
        # the failure itself was already notified.
        restore_app_state_snapshot(state, snapshot)
        ctx.refresh_event_table()
        ctx.refresh_exams_table()
        ctx.refresh_import_preview()
        ctx.refresh_per_exam()
        ctx.refresh_geometry_tab()
        return
    reset_results()
    ctx.refresh_event_table()
    ctx.refresh_exams_table()
    ctx.refresh_import_preview()
    ctx.refresh_per_exam()
    ctx.refresh_geometry_tab()
    status_label.set_text(f"Loaded run configuration ({result.applied_exams} exam(s)).")
    ui.notify(f"Run configuration loaded ({result.applied_exams} exam(s)).", color="positive")


def _notify_warnings(warnings: list[str]) -> None:
    """Surface import warnings, capped so multi-exam storms stay readable.

    Only the count is logged: warning text may carry source identifiers when
    the document was exported with them, so it must never reach the log.
    """
    if warnings:
        logger.warning("run-state import produced %d warning(s)", len(warnings))
    for warning in warnings[:_MAX_SHOWN_WARNINGS]:
        ui.notify(warning, type="warning", timeout=8000)
    if len(warnings) > _MAX_SHOWN_WARNINGS:
        ui.notify(f"+{len(warnings) - _MAX_SHOWN_WARNINGS} more import warnings.", type="warning")


async def _resequence_reparse_if_needed(document: dict, schema_or_sheet_changed: bool) -> bool:
    """Re-parse tabular inputs after a schema/sheet change, then re-apply exams.

    `apply_run_state` already wrote the new schema/sheet plus the per-exam
    offsets — but the re-parse rebuilds `loaded_exam_meta`, wiping those
    offsets. Re-running the (Tier-3-idempotent) applier afterwards restores
    them onto the fresh metas. Multi-exam sessions have no single re-parse
    entry point, so they get loud guidance instead of silent staleness.

    Returns False when loading or re-applying fails (caller must suppress its
    success status), True when the re-parse succeeded or was unnecessary.
    """
    if not schema_or_sheet_changed:
        return True
    if state.is_multi_exam or state.input_source_type not in ("csv", "tsv", "xlsx") or state.file_path is None:
        ui.notify(
            "Schema/sheet changed with multiple (or non-tabular) inputs — "
            "reload the files, then re-import the configuration to restore per-exam offsets.",
            type="warning",
            timeout=0,
            close_button="Dismiss",
        )
        return True
    with operation_guard("re-parsing after configuration import") as proceed:
        if not proceed:
            return True
        ok, msg = require_io_result(await run.io_bound(load_tabular, state.file_path, state, True))
    if not ok:
        ui.notify(f"Re-parse after import failed: {msg}. Per-exam offsets may be stale.", type="negative")
        return False
    try:
        # Restore offsets onto the rebuilt metas (Tier-3 re-apply is idempotent).
        # Guarded: the re-parsed file may yield a different exam count than the
        # document (e.g. file changed since export) — offsets are already lost
        # to the rebuild, so fail with a notification, not a traceback.
        apply_run_state(document, state)
    except RunStateError as exc:
        safe_error_event(logger, "run_config_reapply", exc)
        ui.notify("Re-parse changed the exam set. Per-exam offsets could not be restored.", type="negative")
        return False
    return True
