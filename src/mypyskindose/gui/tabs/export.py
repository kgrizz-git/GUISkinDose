"""Export tab — JSON / HTML / PNG downloads of the calculation result.

Refactor plan Phase 3.3b. The download handlers use only ``state`` plus the
shared figure/IO helpers; ``ctx`` is accepted for a uniform ``build(ctx)``
interface (notifications go through ``ui.notify``, not the drawer).
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from nicegui import run, ui

from mypyskindose.export import MissingExportDependencyError

from ..components import HelpButton
from ..export_source import build_export_source_from_gui
from ..figures import make_dosemap_html, make_dosemap_png
from ..io_helpers import _get_save_path, _inject_html_tabular_meta, _is_native_mode, _tabular_input_meta
from ..page_context import PageContext
from ..state import state
from ..ui_copy import copy_text


def _rich_report_bytes_titled(fmt: str, title: str | None) -> bytes:
    """Build the export payload from GUI state and render it (heavy: kaleido).

    Runs on a worker thread via ``run.io_bound``.
    """
    from mypyskindose.export import collect_export_payload
    from mypyskindose.export.writers import render_bytes

    source = build_export_source_from_gui(state)
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

                os.startfile(str(target))  # type: ignore[attr-defined]  # noqa: S606 — Windows-only
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


def build(ctx: PageContext) -> None:
    with ui.tab_panel("export"):
        with ui.column().classes("max-w-4xl mx-auto w-full gap-6"):
            with ui.row().classes("w-full items-center justify-between"):
                ui.label("Export Results").classes("text-2xl font-bold tracking-tight")
                HelpButton(
                    title="Export help",
                    content_path="export_workflow.md",
                    help_id="export",
                )

            ui.label(
                "Run a calculation first (tab 4) to enable exports."
            ).classes("text-caption text-grey-6 q-mb-md").bind_visibility_from(state, "calculation_done", backward=lambda v: not v)

            with ui.grid(columns=2).classes("w-full gap-6"):
                with ui.card().classes("modern-card"):
                    ui.label("JSON — full results dict").classes("text-subtitle2 q-mb-sm")
                    ui.label("Full results dictionary containing all data.").classes("text-xs text-grey-5 q-mb-md")
                    ui.button("Download JSON", icon="download", on_click=lambda: download_json()).classes("full-width modern-btn icon-outlined")

                with ui.card().classes("modern-card modern-card-teal"):
                    ui.label("Interactive HTML dose map").classes("text-subtitle2 q-mb-sm")
                    ui.label("Standalone HTML file with interactive 3D map.").classes("text-xs text-grey-5 q-mb-md")
                    ui.button("Download HTML", icon="html", on_click=lambda: download_html()).classes("full-width modern-btn icon-outlined")

                with ui.card().classes("modern-card"):
                    ui.label("PNG dose map").classes("text-subtitle2 q-mb-sm")
                    ui.label("Static capture of the current dose map view.").classes("text-xs text-grey-5 q-mb-md")
                    ui.button("Download PNG", icon="image", on_click=lambda: download_png()).classes("full-width modern-btn icon-outlined")

                with ui.card().classes("modern-card modern-card-teal"):
                    ui.label("Rich report — audit document").classes("text-subtitle2 q-mb-sm")
                    ui.label(
                        "Self-contained XLSX / PDF / HTML with results, settings, "
                        "provenance, corrections, warnings, and dose-map images."
                    ).classes("text-xs text-grey-5 q-mb-md")
                    ui.button(
                        "Rich report…", icon="description", on_click=lambda: rich_report_dialog.open()
                    ).classes("full-width modern-btn icon-outlined").bind_enabled_from(state, "calculation_done")

            # ── Rich report modal ────────────────────────────────────────────
            with ui.dialog() as rich_report_dialog, ui.card().classes("min-w-96 gap-3"):
                ui.label("Rich report export").classes("text-lg font-bold")
                fmt_select = ui.select(
                    {
                        "xlsx": "Excel workbook (.xlsx)",
                        "pdf": "PDF document (.pdf)",
                        "html": "Web page (.html)",
                        "docx": "Word document (.docx)",
                    },
                    value="pdf", label="Format",
                ).classes("w-full")
                title_input = ui.input(label="Report title (optional)").classes("w-full")
                with ui.row().classes("w-full justify-end gap-2"):
                    ui.button("Cancel", on_click=rich_report_dialog.close).props("flat")
                    ui.button("Export", icon="download", on_click=lambda: export_rich_report()).classes("modern-btn")

            async def export_rich_report():
                if not state.calculation_done:
                    ui.notify("Run a calculation first", color="warning")
                    return
                fmt = fmt_select.value
                title = (title_input.value or "").strip() or None
                stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
                default_name = f"mypyskindose_report_{stamp}.{fmt}"
                save_path = await _get_save_path(default_name, fmt)
                if save_path is None and _is_native_mode():
                    return  # user cancelled native dialog
                rich_report_dialog.close()
                ui.notify("Generating report…")
                # Stash the optional title on the source builder via state-free arg:
                # collect happens inside the worker; pass title through a closure.
                try:
                    content = await run.io_bound(_rich_report_bytes_titled, fmt, title)
                except MissingExportDependencyError as exc:
                    _show_missing_dependency_dialog(exc)
                    return
                except Exception as exc:  # kaleido or writer failure
                    ui.notify(f"Report failed: {exc}", type="negative", timeout=0, close_button="Dismiss")
                    return
                if save_path:
                    saved = Path(save_path)
                    with open(saved, "wb") as f:
                        f.write(content)
                    _show_saved_dialog(saved)
                else:
                    ui.download(content, default_name)
                    ui.notify("Report downloaded via your browser's download location.", color="positive")

            def _show_missing_dependency_dialog(exc: MissingExportDependencyError) -> None:
                """Persistent, actionable dialog for a missing optional export package."""
                install_name = "python-docx" if exc.package == "docx" else exc.package
                with ui.dialog() as dep_dialog, ui.card().classes("gap-3").style("max-width: 32rem"):
                    with ui.row().classes("items-center gap-2"):
                        ui.icon("extension_off", color="warning").classes("text-2xl")
                        ui.label(f"{exc.format.upper()} export needs an extra package").classes(
                            "text-lg font-medium"
                        )
                    ui.label(
                        f"The '{install_name}' package is required to generate {exc.format.upper()} "
                        "reports but isn't installed in this environment."
                    ).classes("text-sm")
                    ui.label("Install it, then try the export again:").classes("text-sm")
                    cmd = "pip install mypyskindose[export]"

                    def _copy_cmd() -> None:
                        ui.clipboard.write(cmd)
                        ui.notify("Copied", color="positive")

                    with ui.row().classes("w-full items-center gap-2 no-wrap"):
                        ui.label(cmd).classes("font-mono text-xs bg-grey-2 rounded p-2 grow")
                        ui.button(icon="content_copy", on_click=_copy_cmd).props(
                            "flat dense"
                        ).tooltip(copy_text("export.copy_command.tooltip"))
                    ui.label(
                        f"Or install just this one: pip install {install_name}"
                    ).classes("text-xs text-grey-6")
                    with ui.row().classes("w-full justify-end"):
                        ui.button("Close", on_click=dep_dialog.close).props("flat")
                dep_dialog.open()

            def _show_saved_dialog(saved: Path) -> None:
                """Native-mode success dialog with Open file / Open folder actions."""
                with ui.dialog() as done_dialog, ui.card().classes("gap-3"):
                    ui.label(f"Saved to {saved.name}").classes("font-medium")
                    ui.label(str(saved.parent)).classes("text-xs text-grey-6")
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

            def _build_export_payload() -> dict:
                """Return state.output enriched with tabular provenance when applicable."""
                payload = dict(state.output or {})
                if state.import_provenance is not None:
                    payload["tabular_input"] = _tabular_input_meta(
                        state.file_name,
                        state.import_provenance,
                        state.swap_lat_lon,
                        state.import_warnings,
                    )
                return payload

            async def download_json():
                if not state.calculation_done or state.output is None:
                    ui.notify("No data to export", color="warning")
                    return
                default_name = f"psd_results_{state.file_name or 'data'}.json"
                save_path = await _get_save_path(default_name, "json")
                if save_path is None and _is_native_mode():
                    return  # user cancelled the native dialog
                payload = _build_export_payload()
                if save_path:
                    with open(save_path, "w") as f:
                        json.dump(payload, f, indent=4)
                    ui.notify(f"Saved to {Path(save_path).name}", color="positive")
                else:
                    content = json.dumps(payload, indent=4)
                    ui.download(content.encode(), default_name)

            async def download_html():
                if not state.calculation_done:
                    ui.notify("No data to export", color="warning")
                    return
                default_name = f"dose_map_{state.file_name or 'data'}.html"
                save_path = await _get_save_path(default_name, "html")
                if save_path is None and _is_native_mode():
                    return  # user cancelled the native dialog
                content = await run.io_bound(make_dosemap_html)
                if not content:
                    ui.notify("Failed to generate HTML", type="negative")
                    return
                if state.import_provenance is not None:
                    meta = _tabular_input_meta(
                        state.file_name,
                        state.import_provenance,
                        state.swap_lat_lon,
                        state.import_warnings,
                    )
                    content = _inject_html_tabular_meta(content, meta)
                if save_path:
                    with open(save_path, "wb") as f:
                        f.write(content)
                    ui.notify(f"Saved to {Path(save_path).name}", color="positive")
                else:
                    ui.download(content, default_name)

            async def download_png():
                if not state.calculation_done:
                    ui.notify("No data to export", color="warning")
                    return
                default_name = f"dose_map_{state.file_name or 'data'}.png"
                save_path = await _get_save_path(default_name, "png")
                if save_path is None and _is_native_mode():
                    return  # user cancelled the native dialog
                content = await run.io_bound(make_dosemap_png)
                if not content:
                    ui.notify("Failed to generate PNG (requires kaleido)", type="negative")
                    return
                if save_path:
                    with open(save_path, "wb") as f:
                        f.write(content)
                    ui.notify(f"Saved to {Path(save_path).name}", color="positive")
                else:
                    ui.download(content, default_name)
