"""Export tab — JSON / HTML / PNG downloads of the calculation result.

Refactor plan Phase 3.3b. The download handlers use only ``state`` plus the
shared figure/IO helpers; ``ctx`` is accepted for a uniform ``build(ctx)``
interface (notifications go through ``ui.notify``, not the drawer).

``build`` stays a thin layout shell that constructs the cards and rich-report
dialog and wires them to an ``ExportTabController`` (Phase 4.4). The controller
owns UI references only; export payloads still come from
``build_export_source_from_gui`` and the shared safe-output helpers.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from nicegui import run, ui

from guiskindose.export import MissingExportDependencyError
from guiskindose.privacy import safe_error_event, safe_user_error
from guiskindose.safe_output import atomic_write_private

from ..components import HelpButton
from ..concurrency import require_io_result
from ..export_source import build_export_source_from_gui
from ..figures import make_dosemap_html, make_dosemap_png
from ..io_helpers import _get_save_path, _inject_html_tabular_meta, _is_native_mode, _tabular_input_meta
from ..page_context import PageContext
from ..state import state
from ..ui_copy import copy_text

logger = logging.getLogger(__name__)

_EXPORT_CARD_TITLE_CLASSES = "text-subtitle2 q-mb-sm"
_EXPORT_CARD_DESCRIPTION_CLASSES = "text-xs text-grey-5 q-mb-md"
_EXPORT_CARD_BUTTON_CLASSES = "full-width modern-btn icon-outlined"
_NO_DATA_TO_EXPORT_MESSAGE = "No data to export"


def _rich_report_bytes_titled(
    fmt: str, title: str | None, include_source_identifiers: bool = False
) -> bytes:
    """Build the export payload from GUI state and render it (heavy: kaleido).

    Runs on a worker thread via ``run.io_bound``.
    """
    from guiskindose.export import collect_export_payload
    from guiskindose.export.writers import render_bytes

    source = build_export_source_from_gui(
        state, include_source_identifiers=include_source_identifiers
    )
    if title:
        source.report_title = title
    payload = collect_export_payload(source)
    return render_bytes(payload, fmt)


def _open_path(path: Path, *, reveal: bool = False) -> bool:
    """Open a file (or reveal it in the file manager) with the OS default handler.

    Native mode only. Returns ``True`` on success. Platform-native by necessity;
    each branch is best-effort and falls back to opening the parent directory.
    """
    import subprocess
    import sys

    target = Path(path)
    try:
        if sys.platform.startswith("win"):
            if reveal:
                subprocess.run(["explorer", "/select,", str(target)], check=False)
            else:
                import os

                os.startfile(str(target))  # type: ignore[attr-defined]
            return True
        if sys.platform == "darwin":
            args = ["open", "-R", str(target)] if reveal else ["open", str(target)]
            subprocess.run(args, check=False)
            return True
        # Linux / other: xdg-open has no reveal; open the containing directory.
        subprocess.run(["xdg-open", str(target.parent if reveal else target)], check=False)
        return True
    except Exception:
        return False


def _write_or_download(save_path, content, default_name: str, saved_msg: str, write_key: str) -> None:
    """Persist ``content`` to ``save_path`` (native) or stream a browser download.

    Shared tail of every download handler: safe error reporting on write failure,
    a positive notification on native save, and a browser download otherwise.
    """
    if save_path:
        try:
            atomic_write_private(save_path, content, force=True)
        except Exception as exc:
            safe_error_event(logger, write_key, exc)
            ui.notify(safe_user_error(write_key), type="negative")
            return
        ui.notify(saved_msg, color="positive")
    else:
        ui.download(content, default_name)


def _notify_export_failure(safe_error_key: str, exc: Exception, message: str) -> None:
    """Log an export failure safely and show actionable, dismissible negative notifications.

    Shared by every non-cancel exception path in ``download_html``/``download_png`` (both the
    non-cancel ``RuntimeError`` branch and the generic ``Exception`` branch) so a builder failure
    such as ``RuntimeError("Dose map figure could not be built")`` can never escape the handler
    silently mislabeled as a cancellation.
    """
    safe_error_event(logger, safe_error_key, exc)
    ui.notify(safe_user_error(safe_error_key), type="negative", timeout=0, close_button="Dismiss")
    ui.notify(message, type="negative")


def _show_missing_dependency_dialog(exc: MissingExportDependencyError) -> None:
    """Persistent, actionable dialog for a missing optional export package."""
    install_name = "python-docx" if exc.package == "docx" else exc.package
    with ui.dialog() as dep_dialog, ui.card().classes("gap-3").style("max-width: 32rem"):
        with ui.row().classes("items-center gap-2"):
            ui.icon("extension_off", color="warning").classes("text-2xl")
            ui.label(f"{exc.format.upper()} export needs an extra package").classes("text-lg font-medium")
        ui.label(
            f"The '{install_name}' package is required to generate {exc.format.upper()} "
            "reports but isn't installed in this environment."
        ).classes("text-sm")
        ui.label("Install it, then try the export again:").classes("text-sm")
        cmd = "pip install guiskindose[export]"

        def _copy_cmd() -> None:
            ui.clipboard.write(cmd)
            ui.notify("Copied", color="positive")

        with ui.row().classes("w-full items-center gap-2 no-wrap"):
            ui.label(cmd).classes("font-mono text-xs bg-grey-2 rounded p-2 grow")
            ui.button(icon="content_copy", on_click=_copy_cmd).props("flat dense").tooltip(
                copy_text("export.copy_command.tooltip")
            )
        ui.label(f"Or install just this one: pip install {install_name}").classes("text-xs text-grey-6")
        with ui.row().classes("w-full justify-end"):
            ui.button("Close", on_click=dep_dialog.close).props("flat")
    dep_dialog.open()


def _show_saved_dialog(saved: Path) -> None:
    """Native-mode success dialog with Open file / Open folder actions."""
    with ui.dialog() as done_dialog, ui.card().classes("gap-3"):
        ui.label(f"Saved to {saved.name}").classes("font-medium")
        with ui.row().classes("w-full justify-end gap-2"):
            def _open_file():
                if not _open_path(saved):
                    ui.notify("Could not open the file", type="negative")

            def _open_folder():
                if not _open_path(saved, reveal=True):
                    ui.notify("Could not open the folder", type="negative")

            ui.button("Open folder", icon="folder_open", on_click=_open_folder).props("flat")
            ui.button("Open file", icon="open_in_new", on_click=_open_file).classes("modern-btn")
            ui.button("Close", on_click=done_dialog.close).props("flat")
    done_dialog.open()


class ExportTabController:
    """Own Export-tab widget references while payloads stay in the shared helpers."""

    include_identifiers: ui.checkbox
    rich_report_dialog: ui.dialog
    fmt_select: ui.select
    title_input: ui.input

    def _include_ids(self) -> bool:
        return bool(self.include_identifiers.value)

    def _build_export_payload(self) -> dict:
        """Return state.output enriched with tabular provenance when applicable."""
        if state.multi_exam_result is not None:
            payload = state.multi_exam_result.to_dict(include_source_identifiers=self._include_ids())
        else:
            payload = dict(state.output or {})
        if state.import_provenance is not None:
            payload["tabular_input"] = _tabular_input_meta(
                state.file_name,
                state.import_provenance,
                state.swap_lat_lon,
                state.import_warnings,
                include_source_identifiers=self._include_ids(),
            )
        return payload

    async def download_json(self) -> None:
        """Download json."""
        if not state.calculation_done or (state.output is None and state.multi_exam_result is None):
            ui.notify(_NO_DATA_TO_EXPORT_MESSAGE, color="warning")
            return
        default_name = "guiskindose_results.json"
        save_path = await _get_save_path(default_name, "json")
        if save_path is None and _is_native_mode():
            return  # user cancelled the native dialog
        content = json.dumps(self._build_export_payload(), indent=4).encode("utf-8")
        _write_or_download(save_path, content, default_name, "JSON export saved.", "json_export_write")

    async def download_html(self) -> None:
        """Download html."""
        if not state.calculation_done:
            ui.notify(_NO_DATA_TO_EXPORT_MESSAGE, color="warning")
            return
        default_name = "guiskindose_dose_map.html"
        save_path = await _get_save_path(default_name, "html")
        if save_path is None and _is_native_mode():
            return  # user cancelled the native dialog
        explicit_dose_map = None
        explicit_patient = None
        if state.multi_exam_result is not None and state.multi_exam_result.exams:
            explicit_dose_map = state.multi_exam_result.aggregate_dose_map
            explicit_patient = state.multi_exam_result.exams[0].output.to_dict()["patient"]
        try:
            content = require_io_result(
                await run.io_bound(make_dosemap_html, explicit_dose_map, explicit_patient)
            )
        except RuntimeError as exc:
            if "Background task was cancelled" in str(exc):
                ui.notify("Export cancelled — the application is shutting down.", type="warning")
                return
            _notify_export_failure(
                "html_export", exc, "Could not generate the HTML dose map. Check the log for details."
            )
            return
        except Exception as exc:
            _notify_export_failure(
                "html_export", exc, "Could not generate the HTML dose map. Check the log for details."
            )
            return
        if state.import_provenance is not None:
            meta = _tabular_input_meta(
                state.file_name,
                state.import_provenance,
                state.swap_lat_lon,
                state.import_warnings,
                include_source_identifiers=self._include_ids(),
            )
            content = _inject_html_tabular_meta(content, meta)
        logger.info("dosemap html export rendered (bytes=%d)", len(content))
        _write_or_download(save_path, content, default_name, "HTML export saved.", "html_export_write")

    async def download_png(self) -> None:
        """Download png."""
        if not state.calculation_done:
            ui.notify(_NO_DATA_TO_EXPORT_MESSAGE, color="warning")
            return
        default_name = "guiskindose_dose_map.png"
        save_path = await _get_save_path(default_name, "png")
        if save_path is None and _is_native_mode():
            return  # user cancelled the native dialog
        explicit_dose_map = None
        explicit_patient = None
        if state.multi_exam_result is not None and state.multi_exam_result.exams:
            explicit_dose_map = state.multi_exam_result.aggregate_dose_map
            explicit_patient = state.multi_exam_result.exams[0].output.to_dict()["patient"]
        try:
            content = require_io_result(
                await run.io_bound(make_dosemap_png, explicit_dose_map, explicit_patient)
            )
        except RuntimeError as exc:
            if "Background task was cancelled" in str(exc):
                ui.notify("Export cancelled — the application is shutting down.", type="warning")
                return
            _notify_export_failure(
                "png_export",
                exc,
                "Could not generate the PNG dose map (this may require the 'kaleido' "
                "package). Check the log for details.",
            )
            return
        except Exception as exc:
            _notify_export_failure(
                "png_export",
                exc,
                "Could not generate the PNG dose map (this may require the 'kaleido' "
                "package). Check the log for details.",
            )
            return
        logger.info("dosemap png export rendered (bytes=%d)", len(content))
        _write_or_download(save_path, content, default_name, "PNG export saved.", "png_export_write")

    async def _render_rich_report(self, fmt: str, title: str | None) -> bytes | None:
        try:
            return require_io_result(
                await run.io_bound(_rich_report_bytes_titled, fmt, title, self._include_ids())
            )
        except MissingExportDependencyError as exc:
            _show_missing_dependency_dialog(exc)
        except Exception as exc:  # kaleido or writer failure
            safe_error_event(logger, "rich_report_export", exc)
            ui.notify(
                safe_user_error("rich_report_export"),
                type="negative",
                timeout=0,
                close_button="Dismiss",
            )
        return None

    async def export_rich_report(self) -> None:
        """Export rich report."""
        if not state.calculation_done:
            ui.notify("Run a calculation first", color="warning")
            return
        fmt = self.fmt_select.value
        title = (self.title_input.value or "").strip() or None
        stamp = datetime.now(UTC).strftime("%Y-%m-%d_%H%M%S")
        default_name = f"guiskindose_report_{stamp}.{fmt}"
        save_path = await _get_save_path(default_name, fmt)
        if save_path is None and _is_native_mode():
            return  # user cancelled native dialog
        self.rich_report_dialog.close()
        ui.notify("Generating report…")
        content = await self._render_rich_report(fmt, title)
        if content is None:
            return
        if save_path:
            saved = Path(save_path)
            try:
                atomic_write_private(saved, content, force=True)
            except Exception as exc:
                safe_error_event(logger, "rich_report_write", exc)
                ui.notify(safe_user_error("rich_report_write"), type="negative")
                return
            _show_saved_dialog(saved)
        else:
            ui.download(content, default_name)
            ui.notify("Report downloaded via your browser's download location.", color="positive")


def _build_export_header(controller: ExportTabController) -> None:
    with ui.row().classes("w-full items-center justify-between"):
        ui.label("Export Results").classes("text-2xl font-bold tracking-tight")
        HelpButton(title="Export help", content_path="export_workflow.md", help_id="export")

    ui.label("Run a calculation first (tab 4) to enable exports.").classes(
        "text-caption text-grey-6 q-mb-md"
    ).bind_visibility_from(state, "calculation_done", backward=lambda v: not v)

    controller.include_identifiers = ui.checkbox(
        copy_text("export.include_identifiers.label"), value=False
    ).props("color=warning")
    ui.label(copy_text("export.include_identifiers.explanation")).classes("text-xs text-orange-5")


def _build_export_card(title: str, description: str, button_label: str, icon: str, on_click, *, teal: bool = False):
    card_classes = "modern-card modern-card-teal" if teal else "modern-card"
    with ui.card().classes(card_classes):
        ui.label(title).classes(_EXPORT_CARD_TITLE_CLASSES)
        ui.label(description).classes(_EXPORT_CARD_DESCRIPTION_CLASSES)
        return ui.button(button_label, icon=icon, on_click=on_click).classes(_EXPORT_CARD_BUTTON_CLASSES)


def _build_export_cards(controller: ExportTabController) -> None:
    with ui.grid(columns=2).classes("w-full gap-6"):
        _build_export_card(
            "JSON — full results dict",
            "Full results dictionary containing all data.",
            "Download JSON", "download", controller.download_json,
        )
        _build_export_card(
            "Interactive HTML dose map",
            "Standalone HTML file with interactive 3D map.",
            "Download HTML", "html", controller.download_html, teal=True,
        )
        _build_export_card(
            "PNG dose map",
            "Static capture of the current dose map view.",
            "Download PNG", "image", controller.download_png,
        )
        _build_export_card(
            "Rich report — audit document",
            "Self-contained XLSX / PDF / HTML with results, settings, "
            "provenance, corrections, warnings, and dose-map images.",
            "Rich report…", "description", controller.rich_report_dialog.open, teal=True,
        ).bind_enabled_from(state, "calculation_done")


def _build_rich_report_dialog(controller: ExportTabController) -> None:
    with ui.dialog() as rich_report_dialog, ui.card().classes("min-w-96 gap-3"):
        ui.label("Rich report export").classes("text-lg font-bold")
        controller.fmt_select = ui.select(
            {
                "xlsx": "Excel workbook (.xlsx)",
                "pdf": "PDF document (.pdf)",
                "html": "Web page (.html)",
                "docx": "Word document (.docx)",
            },
            value="pdf", label="Format",
        ).classes("w-full")
        controller.title_input = ui.input(label="Report title (optional)").classes("w-full")
        with ui.row().classes("w-full justify-end gap-2"):
            ui.button("Cancel", on_click=rich_report_dialog.close).props("flat")
            ui.button("Export", icon="download", on_click=controller.export_rich_report).classes("modern-btn")
    controller.rich_report_dialog = rich_report_dialog


def build(_ctx: PageContext) -> None:
    """Build."""
    controller = ExportTabController()
    with ui.tab_panel("export"), ui.column().classes("max-w-4xl mx-auto w-full gap-6"):
        _build_export_header(controller)
        _build_rich_report_dialog(controller)
        _build_export_cards(controller)
