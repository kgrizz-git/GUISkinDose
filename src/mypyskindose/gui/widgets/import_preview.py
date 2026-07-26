"""Import preview card for tabular uploads (refactor plan Phase 3.2).

Visible only for non-DICOM tabular files. Shows schema badge, encoding/delimiter/
header metadata, optional multi-sheet picker, coordinate-correction toggles (single-
exam only), column mapping, and a five-row event sample.

The card is built by ``build``, which stays a thin layout shell: it constructs the
widgets through small module-level builders and hands their references to an
``ImportPreviewController`` that owns the refresh/transform behaviour. Parsing and
transforms stay in ``helpers``; ``build`` returns an ``ImportPreviewWidget`` so the
upload tab keeps its existing interface.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from nicegui import run, ui

from mypyskindose.settings.normalization_settings import normalize_manufacturer_key

from ..concurrency import operation_guard, require_io_result
from ..helpers import apply_exam_transforms, load_tabular
from ..page_context import PageContext
from ..state import reset_results, state

_GE_MANUFACTURER_VARIANTS = frozenset({
    "ge", "ge medical systems", "ge healthcare", "general electric", "gems"
})
_COMPACT_ROW_CLASSES = "items-center gap-3 q-mb-xs"
_MUTED_CAPTION_CLASSES = "text-caption text-grey-5"
_MODEL_VALUE_EVENT = "update:model-value"
_COORDINATE_LABEL_CLASSES = "text-caption text-grey-5 font-mono"
_MONO_FULL_WIDTH_CLASSES = "w-full mono-text"


@dataclass
class ImportPreviewWidget:
    sheet_row: ui.row
    sheet_select: ui.select
    coord_card: ui.card
    coord_auto_label: ui.label
    refresh: Callable[[], None]
    set_transform_defaults: Callable[[], None]


class ImportPreviewController:
    """Own import-preview widget references and refresh/transform behaviour.

    Widget attributes are populated by ``build`` before ``refresh`` is ever called;
    parsing/transform logic continues to live in ``helpers`` and ``state``.
    """

    sheet_row: ui.row
    sheet_select: ui.select
    coord_card: ui.card
    coord_auto_label: ui.label
    schema_badge: ui.badge
    encoding_label: ui.label
    delimiter_label: ui.label
    header_label: ui.label
    sheet_label: ui.label
    warnings_label: ui.label
    col_map_table: ui.table
    unit_conv_row: ui.column
    unit_conv_table: ui.table
    event_sample_table: ui.table

    def __init__(self, ctx: PageContext, upload_status: ui.label) -> None:
        self.ctx = ctx
        self.upload_status = upload_status

    # --- transform helpers -------------------------------------------------
    def _is_ge(self) -> bool:
        if normalize_manufacturer_key(state.manufacturer) in _GE_MANUFACTURER_VARIANTS:
            return True
        warnings_lower = " ".join(state.import_warnings).lower()
        return "ge manufacturer detected" in warnings_lower

    def set_transform_defaults(self) -> None:
        if state.import_provenance is None:
            return
        if state.is_multi_exam:
            self.coord_auto_label.set_text("")
            return
        is_ge = self._is_ge()
        state.swap_lat_lon = False
        state.flip_ap1 = False
        state.flip_ap2 = False
        if state.loaded_exam_meta:
            meta = state.loaded_exam_meta[0]
            meta["swap_lat_lon"] = False
            meta["flip_ap1"] = False
            meta["flip_ap2"] = False
            apply_exam_transforms(state, 0)
        self.coord_auto_label.set_text("· GE lat/lon handled in normalization" if is_ge else "")

    def _single_exam_transform_active(self) -> bool:
        return bool(state.loaded_exam_meta) and state.input_source_type not in ("", "dicom")

    def _commit_single_exam_transform(self) -> None:
        apply_exam_transforms(state, 0)
        reset_results()
        self.ctx.refresh_event_table()
        self.ctx.refresh_exams_table()
        self.refresh()
        self.ctx.refresh_per_exam()
        self.ctx.refresh_geometry_tab()

    def on_swap_toggle(self) -> None:
        if not self._single_exam_transform_active():
            return
        prov = state.import_provenance
        if prov and prov.schema_name == "normalized":
            return
        state.loaded_exam_meta[0]["swap_lat_lon"] = state.swap_lat_lon
        self._commit_single_exam_transform()
        self.coord_auto_label.set_text("")

    def on_flip_toggle(self, key: str) -> None:
        if not self._single_exam_transform_active():
            return
        state.loaded_exam_meta[0][key] = getattr(state, key)
        self._commit_single_exam_transform()

    async def on_sheet_change(self) -> None:
        if state.file_path is None:
            return
        with operation_guard("switching sheets") as proceed:
            if not proceed:
                return
            state.input_sheet_name = self.sheet_select.value or 0
            ok, msg = require_io_result(await run.io_bound(load_tabular, state.file_path, state, True))
            if ok:
                self.upload_status.set_text(f"SUCCESS: {msg.upper()}")
                reset_results()
                self.ctx.refresh_event_table()
                self.ctx.refresh_exams_table()
                self.refresh()
            else:
                ui.notify(
                    "Sheet parse failed. Review the selected sheet and schema.",
                    type="negative",
                    timeout=6000,
                )

    # --- refresh -----------------------------------------------------------
    def refresh(self) -> None:
        prov = state.import_provenance
        self.coord_card.set_visibility(
            prov is not None
            and getattr(prov, "schema_name", "") != "normalized"
            and not state.is_multi_exam
        )
        if prov is None:
            return
        self._refresh_metadata(prov)
        self._refresh_warnings()
        self._refresh_column_map(prov)
        self._refresh_unit_conversions(prov)
        self._refresh_event_sample()

    def _refresh_metadata(self, prov) -> None:
        self.schema_badge.set_text(prov.schema_name.upper().replace("_", " "))
        self.encoding_label.set_text(f"Encoding: {prov.detected_encoding or '—'}")
        delim = repr(prov.detected_delimiter) if prov.detected_delimiter else "N/A"
        self.delimiter_label.set_text(f"Delimiter: {delim}")
        self.header_label.set_text(f"Header row: {prov.header_row_index}")
        if state.available_sheets:
            n = len(state.available_sheets)
            self.sheet_label.set_text(f"Sheet: {state.input_sheet_name!r} ({n} available)")
        else:
            self.sheet_label.set_text("")

    def _refresh_warnings(self) -> None:
        if state.import_warnings:
            self.warnings_label.set_text("Warning: " + "; ".join(state.import_warnings[:3]))
        else:
            self.warnings_label.set_text("")

    def _refresh_column_map(self, prov) -> None:
        if prov.column_map:
            self.col_map_table.rows = [{"source": k, "mapped": v} for k, v in prov.column_map.items()]
            self.col_map_table.update()

    def _refresh_unit_conversions(self, prov) -> None:
        conversions = getattr(prov, "unit_conversions", None) or {}
        self.unit_conv_row.set_visibility(bool(conversions))
        self.unit_conv_table.rows = [
            {"field": field, "conversion": desc} for field, desc in conversions.items()
        ]
        self.unit_conv_table.update()

    def _refresh_event_sample(self) -> None:
        if state.rdsr_df is None:
            return
        df = state.rdsr_df.head(5).reset_index(drop=True)
        df.insert(0, "__idx", range(1, len(df) + 1))
        self.event_sample_table.columns = [
            {"name": c, "label": c, "field": c, "align": "left"} for c in df.columns
        ]
        self.event_sample_table.rows = df.fillna("—").astype(str).to_dict("records")
        self.event_sample_table.update()


def _build_metadata_row(controller: ImportPreviewController) -> None:
    with ui.row().classes(_COMPACT_ROW_CLASSES):
        ui.label("Import preview").classes("text-subtitle2")
        controller.schema_badge = ui.badge("—", color="blue").classes("text-xs uppercase")

    with ui.row().classes("w-full gap-6 q-mb-xs"):
        controller.encoding_label = ui.label("Encoding: —").classes(_MUTED_CAPTION_CLASSES)
        controller.delimiter_label = ui.label("Delimiter: —").classes(_MUTED_CAPTION_CLASSES)
        controller.header_label = ui.label("Header row: —").classes(_MUTED_CAPTION_CLASSES)
        controller.sheet_label = ui.label("").classes(_MUTED_CAPTION_CLASSES)


def _build_sheet_picker(controller: ImportPreviewController) -> None:
    sheet_row = ui.row().classes("w-full items-center gap-3 q-mb-xs")
    with sheet_row:
        ui.label("Sheet:").classes("text-caption text-grey-4")
        sheet_select = ui.select(options={}, label="").classes("grow")
        sheet_select.on(_MODEL_VALUE_EVENT, controller.on_sheet_change)
    sheet_row.set_visibility(False)
    controller.sheet_row = sheet_row
    controller.sheet_select = sheet_select


def _build_coord_toggle(label: str, state_key: str, badge: str, tooltip: str, handler: Callable[[], None]) -> None:
    with ui.row().classes(_COMPACT_ROW_CLASSES):
        ui.switch(label).bind_value(state, state_key).on(_MODEL_VALUE_EVENT, handler).tooltip(tooltip)
        ui.label(badge).classes(_COORDINATE_LABEL_CLASSES)


def _build_coord_card(controller: ImportPreviewController) -> None:
    coord_card = ui.card().classes("modern-card w-full bg-blue-950/20 q-pa-sm q-mb-xs")
    coord_card.set_visibility(False)
    with coord_card:
        with ui.row().classes(_COMPACT_ROW_CLASSES):
            ui.label("COORDINATE CORRECTIONS").classes("text-caption text-grey-4 font-bold tracking-widest")
            controller.coord_auto_label = ui.label("").classes("text-caption text-blue-400 italic")
        ui.label(
            "Applied after normalization. Use only for manual source/export corrections."
        ).classes("text-caption text-grey-6 q-mb-sm")

        _build_coord_toggle(
            "Swap lateral ↔ longitudinal",
            "swap_lat_lon",
            "Tx ↔ Tz",
            "Swaps Tx ↔ Tz in the normalized output.\n"
            "GE RDSR-level correction is handled during normalization.\n"
            "Use only when a site-specific export is known to need an extra swap.",
            controller.on_swap_toggle,
        )
        _build_coord_toggle(
            "Flip primary angle (Ap1)",
            "flip_ap1",
            "Ap1 × −1",
            "Negates Ap1 after normalization (e.g. RAO 30° → LAO 30°).\n"
            "Use when the gantry primary rotation direction is opposite to convention.",
            lambda: controller.on_flip_toggle("flip_ap1"),
        )
        _build_coord_toggle(
            "Flip secondary angle (Ap2)",
            "flip_ap2",
            "Ap2 × −1",
            "Negates Ap2 after normalization (e.g. CRA 20° → CAU 20°).\n"
            "Use when the gantry secondary rotation direction is opposite to convention.",
            lambda: controller.on_flip_toggle("flip_ap2"),
        )

        ui.separator().classes("q-my-xs")
        ui.label(
            "Vendor-specific normalization (rotation directions, iso-centre offsets) "
            "is applied automatically from manufacturer settings. "
            "Per-transform overrides are planned."
        ).classes("text-caption text-grey-6 italic")
    controller.coord_card = coord_card


def _build_mapping_and_sample(controller: ImportPreviewController) -> None:
    controller.warnings_label = ui.label("").classes("text-caption text-orange-400 q-mb-xs")

    ui.label("Column mapping (source → normalized)").classes("text-caption text-grey-6 q-mb-xs")
    col_map_table = ui.table(
        columns=[
            {"name": "source", "label": "Source column", "field": "source", "align": "left"},
            {"name": "mapped", "label": "Normalized variable", "field": "mapped", "align": "left"},
        ],
        rows=[],
        row_key="source",
    ).classes(_MONO_FULL_WIDTH_CLASSES)
    col_map_table.props("dense flat")
    controller.col_map_table = col_map_table

    # Unit conversions applied (read from the source headers). Hidden when none.
    unit_conv_row = ui.column().classes("w-full q-mt-sm")
    with unit_conv_row:
        ui.label("Units applied (source unit → internal)").classes("text-caption text-grey-6 q-mb-xs")
        unit_conv_table = ui.table(
            columns=[
                {"name": "field", "label": "Field", "field": "field", "align": "left"},
                {"name": "conversion", "label": "Conversion", "field": "conversion", "align": "left"},
            ],
            rows=[],
            row_key="field",
        ).classes(_MONO_FULL_WIDTH_CLASSES)
        unit_conv_table.props("dense flat")
    controller.unit_conv_row = unit_conv_row
    controller.unit_conv_table = unit_conv_table

    ui.label("First 5 events (normalized)").classes("text-caption text-grey-6 q-mt-sm q-mb-xs")
    event_sample_table = ui.table(columns=[], rows=[], row_key="__idx").classes(_MONO_FULL_WIDTH_CLASSES)
    event_sample_table.props("dense flat virtual-scroll")
    controller.event_sample_table = event_sample_table


def build(ctx: PageContext, upload_status: ui.label) -> ImportPreviewWidget:
    controller = ImportPreviewController(ctx, upload_status)
    with ui.card().classes("modern-card w-full").bind_visibility_from(
        state, "input_source_type", backward=lambda v: v not in ("", "dicom")
    ):
        _build_metadata_row(controller)
        _build_sheet_picker(controller)
        _build_coord_card(controller)
        _build_mapping_and_sample(controller)

    return ImportPreviewWidget(
        sheet_row=controller.sheet_row,
        sheet_select=controller.sheet_select,
        coord_card=controller.coord_card,
        coord_auto_label=controller.coord_auto_label,
        refresh=controller.refresh,
        set_transform_defaults=controller.set_transform_defaults,
    )
