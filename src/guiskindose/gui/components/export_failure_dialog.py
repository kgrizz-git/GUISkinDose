"""Persistent, actionable dialog for a classified export failure."""

from __future__ import annotations

from dataclasses import dataclass

from nicegui import ui

from guiskindose.export.failure_guidance import ExportFailure, ExportFailureKind

from ..ui_copy import copy_text


@dataclass(frozen=True)
class FailureDialogContent:
    """Rendered content for one failure kind (pure, testable without a client)."""

    title: str
    body: str
    detail: tuple[str, ...] = ()
    command: str | None = None
    command_label: str | None = None
    retry: str | None = None


def _format_line(fmt: str | None) -> tuple[str, ...]:
    if not fmt:
        return ()
    return (copy_text("export.failure.format_line").format(format=fmt.upper()),)


def _missing_package_content(failure: ExportFailure) -> FailureDialogContent:
    package = failure.pip_name or failure.import_name or ""
    detail = _format_line(failure.format)
    if package:
        detail += (copy_text("export.failure.package_line").format(package=package),)
    return FailureDialogContent(
        title=copy_text("export.failure.missing_package.title"),
        body=copy_text("export.failure.missing_package.body"),
        detail=detail,
        command=failure.command,
        command_label=copy_text("export.failure.install_package_label"),
        retry=copy_text("export.failure.retry"),
    )


def _missing_browser_content(failure: ExportFailure) -> FailureDialogContent:
    return FailureDialogContent(
        title=copy_text("export.failure.missing_browser.title"),
        body=copy_text("export.failure.missing_browser.body"),
        detail=_format_line(failure.format),
        command=failure.command,
        command_label=copy_text("export.failure.install_browser_label"),
        retry=copy_text("export.failure.retry"),
    )


def _incomplete_install_content(failure: ExportFailure) -> FailureDialogContent:
    return FailureDialogContent(
        title=copy_text("export.failure.incomplete_install.title"),
        body=copy_text("export.failure.incomplete_install.body"),
        detail=_format_line(failure.format),
        retry=copy_text("export.failure.retry"),
    )


def _portable_repair_content(failure: ExportFailure) -> FailureDialogContent:
    # No command and no pip wording: a frozen build can only be re-extracted.
    return FailureDialogContent(
        title=copy_text("export.failure.portable_repair.title"),
        body=copy_text("export.failure.portable_repair.body"),
        detail=_format_line(failure.format),
    )


def failure_dialog_content(failure: ExportFailure) -> FailureDialogContent:
    """Map a classified failure to catalog-backed dialog copy.

    Raises ``ValueError`` for ``unknown``: callers keep the existing generic toast
    for those instead of opening this dialog.
    """
    if failure.kind is ExportFailureKind.MISSING_PACKAGE:
        return _missing_package_content(failure)
    if failure.kind is ExportFailureKind.MISSING_BROWSER:
        return _missing_browser_content(failure)
    if failure.kind is ExportFailureKind.INCOMPLETE_INSTALL:
        return _incomplete_install_content(failure)
    if failure.kind is ExportFailureKind.PORTABLE_REPAIR:
        return _portable_repair_content(failure)
    raise ValueError("unknown export failures do not use the guidance dialog")


def show_export_failure_dialog(failure: ExportFailure) -> None:
    """Open a dismissible dialog describing the failure and its fix."""
    content = failure_dialog_content(failure)
    with ui.dialog() as dialog, ui.card().classes("gap-3").style("max-width: 32rem"):
        with ui.row().classes("items-center gap-2"):
            ui.icon("extension_off", color="warning").classes("text-2xl")
            ui.label(content.title).classes("text-lg font-medium")
        ui.label(content.body).classes("text-sm")
        for line in content.detail:
            ui.label(line).classes("text-xs text-grey-6")
        if content.command:
            if content.command_label:
                ui.label(content.command_label).classes("text-sm")
            _build_command_row(content.command)
        if content.retry:
            ui.label(content.retry).classes("text-sm")
        with ui.row().classes("w-full justify-end"):
            ui.button("Close", on_click=dialog.close).props("flat")
    dialog.open()


def copy_command(command: str) -> None:
    """Copy *command* and confirm, used by the dialog's copy button."""
    ui.clipboard.write(command)
    ui.notify("Copied", color="positive")


def _build_command_row(command: str) -> None:
    with ui.row().classes("w-full items-center gap-2 no-wrap"):
        ui.label(command).classes("font-mono text-xs bg-grey-2 rounded p-2 grow")
        ui.button(icon="content_copy", on_click=lambda: copy_command(command)).props("flat dense").tooltip(
            copy_text("export.copy_command.tooltip")
        )
