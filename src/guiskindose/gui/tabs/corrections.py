"""Corrections tab — dose-physics corrections and kerma-meter correction factors.

Split from the Settings tab. Two-way ``state`` binds with ``reset_results`` on
change, exactly as before the split. The per-exam corrections block (patient
offsets, coordinate fixes, table origin) stays in Settings because it places the
phantom rather than correcting dose physics.
"""

from __future__ import annotations

import math

from nicegui import ui

from ..components import HelpButton
from ..page_context import PageContext
from ..state import reset_results, state
from ..ui_copy import copy_text
from ._kerma_meter_dialog import open_review_dialog
from .settings import (
    _MODEL_VALUE_EVENT,
    _SETTINGS_EXPANSION_CLASSES,
    _SETTINGS_HEADER_ROW_CLASSES,
    _SETTINGS_SECTION_CLASSES,
    BEAM_MISS_WARN_OPTIONS,
    BELOW_FLOOR_KVP_OPTIONS,
    COMPACT_FULL_WIDTH_COLUMN_CLASSES,
)


def build(ctx: PageContext) -> None:
    """Construct the Corrections tab panel."""
    del ctx  # corrections need no cross-tab callbacks
    with ui.tab_panel("corrections"), ui.column().classes("max-w-4xl mx-auto w-full gap-6"):
        ui.label("Corrections").classes("text-2xl font-bold tracking-tight")
        _build_physics_section()
        _build_kerma_meter_section()


def _build_physics_section() -> None:
    """Dose physics expansion: transmission factor, filtration, below-floor kVp policy, beam-miss warnings."""
    with (
        ui.expansion("Dose physics", icon="science", value=True).classes(_SETTINGS_EXPANSION_CLASSES),
        ui.column().classes(_SETTINGS_SECTION_CLASSES),
    ):
        with ui.row().classes("items-center gap-1"):
            ui.checkbox("Use estimated patient-support transmission factor", value=state.estimate_k_tab).bind_value(
                state, "estimate_k_tab"
            ).on(_MODEL_VALUE_EVENT, reset_results)
            HelpButton(
                title="Patient-support transmission factor",
                content=copy_text("settings.k_tab.info"),
                icon="info",
            )

        with ui.column().classes(COMPACT_FULL_WIDTH_COLUMN_CLASSES):
            ui.label("TRANSMISSION FACTOR (patient-support)").classes("technical-label")
            with ui.row().classes("items-center w-full gap-4"):
                ui.slider(min=0.01, max=1.0, step=0.01, value=state.k_tab_val).bind_value(state, "k_tab_val").on(
                    _MODEL_VALUE_EVENT, reset_results
                ).classes("grow")
                ui.label().bind_text_from(
                    state,
                    "k_tab_val",
                    backward=lambda v: (
                        f"{float(v):.2f}" if isinstance(v, (int, float)) and math.isfinite(float(v)) else "—"
                    ),
                ).classes("mono-text font-bold")

        ui.number(label="Inherent filtration (mmAl)", value=state.inherent_filtration, min=0.0, step=0.1).bind_value(
            state, "inherent_filtration"
        ).on(_MODEL_VALUE_EVENT, reset_results).classes("w-full")

        ui.checkbox("Remove invalid data (kVp = 0)", value=state.remove_invalid_rows).bind_value(
            state, "remove_invalid_rows"
        ).on(_MODEL_VALUE_EVENT, reset_results)

        with ui.column().classes("w-full gap-2"):
            with ui.row().classes(_SETTINGS_HEADER_ROW_CLASSES):
                ui.label("Below-floor kVp handling (< 25 kV)").classes("text-subtitle2")
                HelpButton(
                    title="Below-floor kVp handling",
                    content_path="below_floor_kvp.md",
                    help_id="settings_below_floor_kvp",
                )
            ui.select(
                BELOW_FLOOR_KVP_OPTIONS,
                label="Policy for events below the HVL table floor",
                value=state.below_floor_kvp_policy,
            ).bind_value(state, "below_floor_kvp_policy").on(_MODEL_VALUE_EVENT, reset_results).classes("w-full")

            manual_kvp = (
                ui.number(label="Manual kVp", value=state.below_floor_kvp_manual, min=25.0, max=175.0, step=1.0)
                .bind_value(state, "below_floor_kvp_manual")
                .on(_MODEL_VALUE_EVENT, reset_results)
                .classes("w-full")
            )

            def _update_manual_kvp_visibility():
                """Show the manual kVp field only when policy is manual."""
                manual_kvp.visible = state.below_floor_kvp_policy == "manual"

            ui.timer(0.5, _update_manual_kvp_visibility)

        ui.select(
            BEAM_MISS_WARN_OPTIONS,
            label="Beam-miss warning verbosity",
            value=state.beam_miss_warn,
        ).bind_value(state, "beam_miss_warn").on(_MODEL_VALUE_EVENT, reset_results).classes("w-full")


def _build_kerma_meter_section() -> None:
    """Kerma-meter correction expansion: factors file, review dialog, example download."""
    with (
        ui.expansion("Kerma-meter correction", icon="speed", value=True).classes(_SETTINGS_EXPANSION_CLASSES),
        ui.column().classes(_SETTINGS_SECTION_CLASSES),
        ui.column().classes("w-full gap-2"),
    ):
        with ui.row().classes(_SETTINGS_HEADER_ROW_CLASSES):
            ui.label("Kerma-meter correction").classes("text-subtitle2")
            HelpButton(
                title="Kerma-meter correction",
                content_path="kerma_meter_correction.md",
                help_id="settings_kerma_meter_correction",
            )
        ui.checkbox(
            "Enable kerma-meter correction factors",
            value=state.kerma_meter_enable,
        ).bind_value(state, "kerma_meter_enable").on(_MODEL_VALUE_EVENT, reset_results)
        ui.checkbox(
            copy_text("settings.kerma_meter.ask_missing"),
            value=state.kerma_meter_ask_for_missing,
        ).bind_value(state, "kerma_meter_ask_for_missing").tooltip(
            copy_text("settings.kerma_meter.ask_missing.tooltip")
        )
        ui.button(copy_text("settings.kerma_meter.review_button"), on_click=open_review_dialog).props(
            "flat dense no-caps"
        )
        ui.button(copy_text("settings.kerma_meter.example_button"), on_click=_download_example_calibration_file).props(
            "flat dense no-caps"
        )
        ui.input(
            label="Correction table path (CSV/TSV/XLSX/JSON)",
            value=state.kerma_meter_file or "",
        ).bind_value(state, "kerma_meter_file").on(_MODEL_VALUE_EVENT, reset_results).classes("w-full")
        ui.number(
            label="Default factor (unresolved / table miss)",
            value=state.kerma_meter_default_factor,
            min=0.01,
            step=0.01,
        ).bind_value(state, "kerma_meter_default_factor").on(_MODEL_VALUE_EVENT, reset_results).classes("w-full")
        ui.input(
            label="Explicit equipment label (optional override)",
            value=state.kerma_meter_explicit_label or "",
        ).bind_value(state, "kerma_meter_explicit_label").on(_MODEL_VALUE_EVENT, reset_results).classes("w-full")
        ui.label(
            "CF = (real measured dose) / (unit reported dose). "
            "Radimetrics Equipment = room; DoseTrack Equipment Name is often the model."
        ).classes("text-xs text-grey-6")


async def _download_example_calibration_file() -> None:
    """Offer the bundled example kerma-meter calibration CSV.

    Native (pywebview) windows ignore browser downloads, so a native "Save As"
    dialog is used there; a browser session streams a normal download.
    """
    from guiskindose import get_path_to_example_kerma_meter_file

    from ..io_helpers import _get_save_path
    from .export import _write_or_download

    path = get_path_to_example_kerma_meter_file()
    save_path = await _get_save_path(path.name, "csv")
    _write_or_download(
        save_path, path.read_bytes(), path.name, "Example calibration file saved.", "example_calibration_write"
    )
