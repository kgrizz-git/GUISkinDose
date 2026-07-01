"""Data tab — raw/normalized event table with local CSV/XLSX/TXT export.

Refactor plan Phase 3.3c. Timer-driven (`_refresh_raw_table`) plus the
`view_toggle`; `_local_export` writes via the native save dialog. Reads only
`state` (+ `_get_save_path`), so `ctx` is accepted only for a uniform interface.
"""

from __future__ import annotations

import io
from pathlib import Path

import pandas as pd
from nicegui import ui

from ..helpers import EXAM_COLUMN, EXAM_INDEX_COLUMN
from ..io_helpers import _get_save_path, _is_native_mode
from ..page_context import PageContext
from ..state import state

COLUMN_LABEL_ALIASES = {
    "Tx": "Tx (X, DICOM LON, PT L-R)",
    "Ty": "Ty (Y, DICOM VER, PT A-P)",
    "Tz": "Tz (Z, DICOM LAT, PT S-I)",
}


def display_column_label(column: str) -> str:
    return COLUMN_LABEL_ALIASES.get(column, column)


def build(ctx: PageContext) -> None:
    with ui.tab_panel("data"):
        with ui.column().classes("w-full gap-4"):
            with ui.column().classes("w-full gap-2 px-4"):
                ui.label("Irradiation Event Stream").classes("text-2xl font-bold tracking-tight")
                ui.label().bind_text_from(
                    state, "import_provenance",
                    backward=lambda v: (
                        f"Source: {state.file_name}  ·  Schema: {v.schema_name}"
                        if v is not None else f"Source: {state.file_name}"
                    ),
                ).classes("text-caption text-grey-5").bind_visibility_from(state, "file_name", backward=bool)

                with ui.row().classes("w-full items-center gap-3 q-mb-sm"):
                    ui.label("View:").classes("text-sm opacity-60 self-center")
                    view_toggle = ui.toggle(
                        {"norm": "NORMALIZED", "raw": "RAW (UN-NORMALIZED)"},
                        value="norm"
                    ).bind_value_to(state, "view_raw", forward=lambda v: v == "raw").classes("modern-toggle")

                with ui.row().classes("w-full items-center gap-3"):
                    ui.button("EXPORT CSV", icon="description", on_click=lambda: _local_export("csv")).classes("modern-btn h-10 icon-outlined")
                    ui.button("EXPORT XLSX", icon="table_view", on_click=lambda: _local_export("xlsx")).classes("modern-btn h-10 icon-outlined")
                    ui.button("EXPORT TXT", icon="text_snippet", on_click=lambda: _local_export("txt")).classes("modern-btn h-10 icon-outlined")

            def _local_export(fmt: str):
                df = state.rdsr_raw_df if state.view_raw else state.rdsr_df
                if df is None:
                    ui.notify("No data to export", type="warning")
                    return

                prefix = "raw_" if state.view_raw else "normalized_"
                default_name = f"{prefix}events_{state.file_name or 'data'}.{fmt}"
                save_path = _get_save_path(default_name, fmt)
                if save_path is None and _is_native_mode():
                    return  # user cancelled the native dialog

                # Prepare normalization metadata
                meta_df = pd.DataFrame([{
                    "Manufacturer": state.manufacturer,
                    "Model": state.model,
                    "Normalization Method": state.normalization_method,
                    "Table Offset X [cm]": state.table_offset_x,
                    "Table Offset Y [cm]": state.table_offset_y,
                    "Table Offset Z [cm]": state.table_offset_z,
                    "Export Type": "Raw" if state.view_raw else "Normalized",
                }])

                if save_path:
                    try:
                        p = Path(save_path)
                        if fmt == "csv":
                            df.to_csv(p, index=True)
                        elif fmt == "txt":
                            with open(p, "w") as f:
                                f.write("=== NORMALIZATION METADATA ===\n")
                                f.write(meta_df.to_string() + "\n\n")
                                f.write("=== EVENT DATA ===\n")
                                f.write(df.to_string())
                        elif fmt == "xlsx":
                            with pd.ExcelWriter(p) as writer:
                                df.to_excel(writer, sheet_name="Event Data", index=True)
                                meta_df.to_excel(writer, sheet_name="Normalization Info", index=False)
                        ui.notify(f"Saved to {p.name}", color="positive")
                        return
                    except Exception as e:
                        ui.notify(f"Save failed: {e}", type="negative")

                # Fallback to browser download
                if fmt == "csv":
                    content = df.to_csv(index=True)
                    ui.download(content.encode(), default_name)
                elif fmt == "txt":
                    content = "=== METADATA ===\n" + meta_df.to_string() + "\n\n" + df.to_string()
                    ui.download(content.encode(), default_name)
                elif fmt == "xlsx":
                    output = io.BytesIO()
                    with pd.ExcelWriter(output) as writer:
                        df.to_excel(writer, sheet_name="Event Data", index=True)
                        meta_df.to_excel(writer, sheet_name="Normalization Info", index=False)
                    ui.download(output.getvalue(), default_name)
                ui.notify(f"Downloaded {fmt.upper()}", color="positive")

            with ui.card().classes("modern-card w-full p-0 overflow-hidden sticky-header"):
                raw_data_table = ui.table(
                    columns=[],
                    rows=[],
                    row_key="index",
                ).classes("w-full h-[600px]")
                # Allow horizontal scroll and sticky header
                raw_data_table.props('flat bordered dense virtual-scroll')

            def _refresh_raw_table():
                df_to_show = state.rdsr_raw_df if state.view_raw else state.rdsr_df
                if df_to_show is None:
                    raw_data_table.columns = []
                    raw_data_table.rows = []
                    return

                df = df_to_show.reset_index()
                # create columns from df; pin the exam tag (multi-exam only) first
                ordered = [c for c in df.columns if c != EXAM_INDEX_COLUMN]
                if EXAM_COLUMN in ordered:
                    ordered.insert(0, ordered.pop(ordered.index(EXAM_COLUMN)))
                cols = [
                    {
                        "name": c,
                        "label": display_column_label(c),
                        "field": c,
                        "sortable": True,
                        "align": "left",
                    }
                    for c in ordered
                ]
                raw_data_table.columns = cols
                raw_data_table.rows = df.to_dict("records")
                raw_data_table.update()

            ui.timer(2.0, _refresh_raw_table)
            view_toggle.on("update:model-value", _refresh_raw_table)
