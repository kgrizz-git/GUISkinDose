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

from ..export_source import build_export_source_from_gui
from ..figures import make_dosemap_html, make_dosemap_png
from ..io_helpers import _get_save_path, _inject_html_tabular_meta, _is_native_mode, _tabular_input_meta
from ..page_context import PageContext
from ..state import state


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


def build(ctx: PageContext) -> None:
    with ui.tab_panel("export"):
        with ui.column().classes("max-w-4xl mx-auto w-full gap-6"):
            ui.label("Export Results").classes("text-2xl font-bold tracking-tight")

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
                    {"xlsx": "Excel workbook (.xlsx)", "pdf": "PDF document (.pdf)", "html": "Web page (.html)"},
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
                save_path = _get_save_path(default_name, fmt)
                if save_path is None and _is_native_mode():
                    return  # user cancelled native dialog
                rich_report_dialog.close()
                ui.notify("Generating report…")
                # Stash the optional title on the source builder via state-free arg:
                # collect happens inside the worker; pass title through a closure.
                try:
                    content = await run.io_bound(_rich_report_bytes_titled, fmt, title)
                except Exception as exc:  # kaleido or writer failure
                    ui.notify(f"Report failed: {exc}", type="negative")
                    return
                if save_path:
                    with open(save_path, "wb") as f:
                        f.write(content)
                    ui.notify(f"Saved to {Path(save_path).name}", color="positive")
                else:
                    ui.download(content, default_name)
                    ui.notify("Report downloaded via your browser's download location.", color="positive")

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

            def download_json():
                if not state.calculation_done or state.output is None:
                    ui.notify("No data to export", color="warning")
                    return
                default_name = f"psd_results_{state.file_name or 'data'}.json"
                save_path = _get_save_path(default_name, "json")
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
                save_path = _get_save_path(default_name, "html")
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
                save_path = _get_save_path(default_name, "png")
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
