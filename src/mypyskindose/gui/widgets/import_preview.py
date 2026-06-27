"""Import preview card for tabular uploads (refactor plan Phase 3.2).

Visible only for non-DICOM tabular files. Shows schema badge, encoding/delimiter/
header metadata, optional multi-sheet picker, coordinate-correction toggles (single-
exam only), column mapping, and a five-row event sample.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from nicegui import run, ui

from mypyskindose.settings.normalization_settings import normalize_manufacturer_key

from ..concurrency import operation_guard
from ..helpers import apply_exam_transforms, load_tabular
from ..page_context import PageContext
from ..state import reset_results, state

_GE_MANUFACTURER_VARIANTS = frozenset({
    "ge", "ge medical systems", "ge healthcare", "general electric", "gems"
})


@dataclass
class ImportPreviewWidget:
    sheet_row: ui.row
    sheet_select: ui.select
    coord_card: ui.card
    coord_auto_label: ui.label
    refresh: Callable[[], None]
    set_transform_defaults: Callable[[], None]


def build(ctx: PageContext, upload_status: ui.label) -> ImportPreviewWidget:
    with ui.card().classes("modern-card w-full").bind_visibility_from(
        state, "input_source_type", backward=lambda v: v not in ("", "dicom")
    ):
        with ui.row().classes("items-center gap-3 q-mb-xs"):
            ui.label("Import preview").classes("text-subtitle2")
            import_schema_badge = ui.badge("—", color="blue").classes("text-xs uppercase")

        with ui.row().classes("w-full gap-6 q-mb-xs"):
            import_encoding_label = ui.label("Encoding: —").classes("text-caption text-grey-5")
            import_delimiter_label = ui.label("Delimiter: —").classes("text-caption text-grey-5")
            import_header_label = ui.label("Header row: —").classes("text-caption text-grey-5")
            import_sheet_label = ui.label("").classes("text-caption text-grey-5")

        sheet_row = ui.row().classes("w-full items-center gap-3 q-mb-xs")
        with sheet_row:
            ui.label("Sheet:").classes("text-caption text-grey-4")
            sheet_select = ui.select(options={}, label="").classes("grow")

            async def _on_sheet_change():
                if state.file_path is None:
                    return
                with operation_guard("switching sheets") as proceed:
                    if not proceed:
                        return
                    state.input_sheet_name = sheet_select.value or 0
                    ok, msg = await run.io_bound(load_tabular, state.file_path, state, True)
                    if ok:
                        upload_status.set_text(f"SUCCESS: {msg.upper()}")
                        reset_results()
                        ctx.refresh_event_table()
                        ctx.refresh_exams_table()
                        _refresh_import_preview()
                    else:
                        ui.notify(f"Sheet parse error: {msg[:200]}", type="negative", timeout=6000)

            sheet_select.on("update:model-value", _on_sheet_change)
        sheet_row.set_visibility(False)

        coord_card = ui.card().classes("modern-card w-full bg-blue-950/20 q-pa-sm q-mb-xs")
        coord_card.set_visibility(False)
        with coord_card:
            with ui.row().classes("items-center gap-3 q-mb-xs"):
                ui.label("COORDINATE CORRECTIONS").classes("text-caption text-grey-4 font-bold tracking-widest")
                coord_auto_label = ui.label("").classes("text-caption text-blue-400 italic")
            ui.label(
                "Applied after normalization. Use only for manual source/export corrections."
            ).classes("text-caption text-grey-6 q-mb-sm")

            with ui.row().classes("items-center gap-3 q-mb-xs"):
                ui.switch("Swap lateral ↔ longitudinal").bind_value(state, "swap_lat_lon").on(
                    "update:model-value", lambda: _on_swap_toggle()
                ).tooltip(
                    "Swaps Tx ↔ Tz in the normalized output.\n"
                    "GE RDSR-level correction is handled during normalization.\n"
                    "Use only when a site-specific export is known to need an extra swap."
                )
                ui.label("Tx ↔ Tz").classes("text-caption text-grey-5 font-mono")

            with ui.row().classes("items-center gap-3 q-mb-xs"):
                ui.switch("Flip primary angle (Ap1)").bind_value(state, "flip_ap1").on(
                    "update:model-value", lambda: _on_flip_ap1_toggle()
                ).tooltip(
                    "Negates Ap1 after normalization (e.g. RAO 30° → LAO 30°).\n"
                    "Use when the gantry primary rotation direction is opposite to convention."
                )
                ui.label("Ap1 × −1").classes("text-caption text-grey-5 font-mono")

            with ui.row().classes("items-center gap-3 q-mb-xs"):
                ui.switch("Flip secondary angle (Ap2)").bind_value(state, "flip_ap2").on(
                    "update:model-value", lambda: _on_flip_ap2_toggle()
                ).tooltip(
                    "Negates Ap2 after normalization (e.g. CRA 20° → CAU 20°).\n"
                    "Use when the gantry secondary rotation direction is opposite to convention."
                )
                ui.label("Ap2 × −1").classes("text-caption text-grey-5 font-mono")

            ui.separator().classes("q-my-xs")
            ui.label(
                "Vendor-specific normalization (rotation directions, iso-centre offsets) "
                "is applied automatically from manufacturer settings. "
                "Per-transform overrides are planned."
            ).classes("text-caption text-grey-6 italic")

        import_warnings_label = ui.label("").classes("text-caption text-orange-400 q-mb-xs")

        ui.label("Column mapping (source → normalized)").classes("text-caption text-grey-6 q-mb-xs")
        col_map_table = ui.table(
            columns=[
                {"name": "source", "label": "Source column", "field": "source", "align": "left"},
                {"name": "mapped", "label": "Normalized variable", "field": "mapped", "align": "left"},
            ],
            rows=[],
            row_key="source",
        ).classes("w-full mono-text")
        col_map_table.props("dense flat")

        ui.label("First 5 events (normalized)").classes("text-caption text-grey-6 q-mt-sm q-mb-xs")
        event_sample_table = ui.table(columns=[], rows=[], row_key="__idx").classes("w-full mono-text")
        event_sample_table.props("dense flat virtual-scroll")

    def _is_ge() -> bool:
        if normalize_manufacturer_key(state.manufacturer) in _GE_MANUFACTURER_VARIANTS:
            return True
        warnings_lower = " ".join(state.import_warnings).lower()
        return "ge manufacturer detected" in warnings_lower

    def _set_transform_defaults() -> None:
        if state.import_provenance is None:
            return
        if state.is_multi_exam:
            coord_auto_label.set_text("")
            return
        is_ge = _is_ge()
        state.swap_lat_lon = False
        state.flip_ap1 = False
        state.flip_ap2 = False
        if state.loaded_exam_meta:
            meta = state.loaded_exam_meta[0]
            meta["swap_lat_lon"] = False
            meta["flip_ap1"] = False
            meta["flip_ap2"] = False
            apply_exam_transforms(state, 0)
        coord_auto_label.set_text("· GE lat/lon handled in normalization" if is_ge else "")

    def _on_swap_toggle() -> None:
        if not state.loaded_exam_meta or state.input_source_type in ("", "dicom"):
            return
        prov = state.import_provenance
        if prov and prov.schema_name == "normalized":
            return
        state.loaded_exam_meta[0]["swap_lat_lon"] = state.swap_lat_lon
        apply_exam_transforms(state, 0)
        reset_results()
        ctx.refresh_event_table()
        ctx.refresh_exams_table()
        _refresh_import_preview()
        ctx.refresh_per_exam()
        ctx.refresh_geometry_tab()
        coord_auto_label.set_text("")

    def _on_flip_ap1_toggle() -> None:
        if not state.loaded_exam_meta or state.input_source_type in ("", "dicom"):
            return
        state.loaded_exam_meta[0]["flip_ap1"] = state.flip_ap1
        apply_exam_transforms(state, 0)
        reset_results()
        ctx.refresh_event_table()
        ctx.refresh_exams_table()
        _refresh_import_preview()
        ctx.refresh_per_exam()
        ctx.refresh_geometry_tab()

    def _on_flip_ap2_toggle() -> None:
        if not state.loaded_exam_meta or state.input_source_type in ("", "dicom"):
            return
        state.loaded_exam_meta[0]["flip_ap2"] = state.flip_ap2
        apply_exam_transforms(state, 0)
        reset_results()
        ctx.refresh_event_table()
        ctx.refresh_exams_table()
        _refresh_import_preview()
        ctx.refresh_per_exam()
        ctx.refresh_geometry_tab()

    def _refresh_import_preview():
        prov = state.import_provenance
        coord_card.set_visibility(
            prov is not None
            and getattr(prov, "schema_name", "") != "normalized"
            and not state.is_multi_exam
        )
        if prov is None:
            return
        import_schema_badge.set_text(prov.schema_name.upper().replace("_", " "))
        import_encoding_label.set_text(f"Encoding: {prov.detected_encoding or '—'}")
        delim = repr(prov.detected_delimiter) if prov.detected_delimiter else "N/A"
        import_delimiter_label.set_text(f"Delimiter: {delim}")
        import_header_label.set_text(f"Header row: {prov.header_row_index}")
        if state.available_sheets:
            sheet_name = state.input_sheet_name
            n = len(state.available_sheets)
            import_sheet_label.set_text(f"Sheet: {sheet_name!r} ({n} available)")
        else:
            import_sheet_label.set_text("")
        if state.import_warnings:
            import_warnings_label.set_text("Warning: " + "; ".join(state.import_warnings[:3]))
        else:
            import_warnings_label.set_text("")
        if prov.column_map:
            col_map_table.rows = [{"source": k, "mapped": v} for k, v in prov.column_map.items()]
            col_map_table.update()
        if state.rdsr_df is not None:
            df = state.rdsr_df.head(5).reset_index(drop=True)
            df.insert(0, "__idx", range(1, len(df) + 1))
            event_sample_table.columns = [
                {"name": c, "label": c, "field": c, "align": "left"} for c in df.columns
            ]
            event_sample_table.rows = df.fillna("—").astype(str).to_dict("records")
            event_sample_table.update()

    return ImportPreviewWidget(
        sheet_row=sheet_row,
        sheet_select=sheet_select,
        coord_card=coord_card,
        coord_auto_label=coord_auto_label,
        refresh=_refresh_import_preview,
        set_transform_defaults=_set_transform_defaults,
    )
