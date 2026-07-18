"""Data tab — raw/normalized event table with local CSV/XLSX/TXT export.

Refactor plan Phase 3.3c. Timer-driven (`_refresh_raw_table`) plus the
`view_toggle`; `_local_export` writes via the native save dialog. Reads only
`state` (+ `_get_save_path`), so `ctx` is accepted only for a uniform interface.
"""

from __future__ import annotations

import io
import logging
import pandas as pd
from nicegui import ui

from mypyskindose.spreadsheet_safety import neutralize_dataframe
from mypyskindose.privacy import safe_error_event, safe_user_error
from mypyskindose.safe_output import atomic_write_private

from ..components import HelpButton
from ..helpers import EXAM_COLUMN, EXAM_INDEX_COLUMN
from ..io_helpers import _get_save_path, _is_native_mode
from ..page_context import PageContext
from ..state import state

logger = logging.getLogger(__name__)

_EXPORT_BUTTON_CLASSES = "modern-btn h-10 icon-outlined"

COLUMN_LABEL_ALIASES = {
    "Tx": "Tx (X, DICOM LON, PT L-R)",
    "Ty": "Ty (Y, DICOM VER, PT A-P)",
    "Tz": "Tz (Z, DICOM LAT, PT S-I)",
}


def display_column_label(column: str) -> str:
    return COLUMN_LABEL_ALIASES.get(column, column)


def _selected_dataframe() -> pd.DataFrame | None:
    return state.rdsr_raw_df if state.view_raw else state.rdsr_df


def _export_metadata() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Manufacturer": state.manufacturer,
                "Model": state.model,
                "Normalization Method": state.normalization_method,
                "Table Offset X [cm]": state.table_offset_x,
                "Table Offset Y [cm]": state.table_offset_y,
                "Table Offset Z [cm]": state.table_offset_z,
                "Export Type": "Raw" if state.view_raw else "Normalized",
            }
        ]
    )


def _export_content(dataframe: pd.DataFrame, fmt: str) -> bytes:
    safe_dataframe = neutralize_dataframe(dataframe)
    safe_metadata = neutralize_dataframe(_export_metadata())
    if fmt == "csv":
        return safe_dataframe.to_csv(index=True).encode("utf-8")
    if fmt == "txt":
        return ("=== METADATA ===\n" + safe_metadata.to_string() + "\n\n" + safe_dataframe.to_string()).encode("utf-8")

    output = io.BytesIO()
    with pd.ExcelWriter(output) as writer:
        safe_dataframe.to_excel(writer, sheet_name="Event Data", index=True)
        safe_metadata.to_excel(writer, sheet_name="Normalization Info", index=False)
    return output.getvalue()


async def _local_export(fmt: str) -> None:
    dataframe = _selected_dataframe()
    if dataframe is None:
        ui.notify("No data to export", type="warning")
        return

    prefix = "raw_" if state.view_raw else "normalized_"
    default_name = f"mypyskindose_{prefix}events.{fmt}"
    save_path = await _get_save_path(default_name, fmt)
    if save_path is None and _is_native_mode():
        return

    content = _export_content(dataframe, fmt)
    if save_path:
        try:
            atomic_write_private(save_path, content, force=True)
        except Exception as exc:
            safe_error_event(logger, "event_table_export", exc)
            ui.notify(safe_user_error("event_table_export"), type="negative")
            return
        ui.notify("Event-table export saved.", color="positive")
        return

    ui.download(content, default_name)
    ui.notify(f"Downloaded {fmt.upper()}", color="positive")


def _refresh_raw_table(raw_data_table: ui.table) -> None:
    dataframe = _selected_dataframe()
    if dataframe is None:
        raw_data_table.columns = []
        raw_data_table.rows = []
        raw_data_table.update()
        return

    dataframe = dataframe.reset_index()
    ordered = [column for column in dataframe.columns if column != EXAM_INDEX_COLUMN]
    if EXAM_COLUMN in ordered:
        ordered.insert(0, ordered.pop(ordered.index(EXAM_COLUMN)))
    raw_data_table.columns = [
        {
            "name": column,
            "label": display_column_label(column),
            "field": column,
            "sortable": True,
            "align": "left",
        }
        for column in ordered
    ]
    raw_data_table.rows = dataframe.to_dict("records")
    raw_data_table.update()


def _build_data_header() -> ui.toggle:
    with ui.column().classes("w-full gap-2 px-4"):
        with ui.row().classes("w-full items-center justify-between"):
            ui.label("Irradiation Event Stream").classes("text-2xl font-bold tracking-tight")
            HelpButton(title="Data table help", content_path="data_table_workflow.md", help_id="data")
        ui.label().bind_text_from(
            state,
            "import_provenance",
            backward=lambda value: (
                f"Source: loaded data  ·  Schema: {value.schema_name}"
                if value is not None
                else "Source: loaded data"
            ),
        ).classes("text-caption text-grey-5").bind_visibility_from(state, "file_name", backward=bool)
        with ui.row().classes("w-full items-center gap-3 q-mb-sm"):
            ui.label("View:").classes("text-sm opacity-60 self-center")
            view_toggle = ui.toggle({"norm": "NORMALIZED", "raw": "RAW (UN-NORMALIZED)"}, value="norm")
            view_toggle.bind_value_to(state, "view_raw", forward=lambda value: value == "raw").classes("modern-toggle")
        with ui.row().classes("w-full items-center gap-3"):
            ui.button("EXPORT CSV", icon="description", on_click=lambda: _local_export("csv")).classes(
                _EXPORT_BUTTON_CLASSES
            )
            ui.button("EXPORT XLSX", icon="table_view", on_click=lambda: _local_export("xlsx")).classes(
                _EXPORT_BUTTON_CLASSES
            )
            ui.button("EXPORT TXT", icon="text_snippet", on_click=lambda: _local_export("txt")).classes(
                _EXPORT_BUTTON_CLASSES
            )
    return view_toggle


def build(_ctx: PageContext) -> None:
    with ui.tab_panel("data"):
        with ui.column().classes("w-full gap-4"):
            view_toggle = _build_data_header()
            with ui.card().classes("modern-card w-full p-0 overflow-hidden sticky-header"):
                raw_data_table = ui.table(columns=[], rows=[], row_key="index").classes("w-full h-[600px]")
                raw_data_table.props("flat bordered dense virtual-scroll")

            def refresh_table() -> None:
                _refresh_raw_table(raw_data_table)

            ui.timer(2.0, refresh_table)
            view_toggle.on("update:model-value", refresh_table)
