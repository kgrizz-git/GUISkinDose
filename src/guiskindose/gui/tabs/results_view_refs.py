"""UI element references for the Results tab."""

from __future__ import annotations

from dataclasses import dataclass

from nicegui import ui

from ..dose_severity import PsdReadout


@dataclass
class ResultsViewRefs:
    """UI element references for the Results tab."""

    # Banded PSD readouts: the label, its band icon, and its band tooltip move
    # together, so they are held as one unit rather than as loose references.
    psd_readout: PsdReadout | None = None
    kerma_metric: ui.label = None  # type: ignore[assignment]
    events_metric: ui.label = None  # type: ignore[assignment]
    dap_metric: ui.label = None  # type: ignore[assignment]
    fluoro_metric: ui.label = None  # type: ignore[assignment]
    rotational_badge: ui.label = None  # type: ignore[assignment]
    tube_label: ui.label = None  # type: ignore[assignment]
    equipment_profile_label: ui.label = None  # type: ignore[assignment]
    dosemap_plot: ui.plotly = None  # type: ignore[assignment]
    dosemap_spinner: ui.spinner = None  # type: ignore[assignment]
    corr_table: ui.table = None  # type: ignore[assignment]
    agg_psd_readout: PsdReadout | None = None
    agg_events_metric: ui.label = None  # type: ignore[assignment]
    agg_totals_metric: ui.label = None  # type: ignore[assignment]
    agg_rotational_badge: ui.label = None  # type: ignore[assignment]
    agg_tube_label: ui.label = None  # type: ignore[assignment]
    agg_equipment_profile_label: ui.label = None  # type: ignore[assignment]
    run_warnings_label: ui.label = None  # type: ignore[assignment]
    agg_dosemap_plot: ui.plotly = None  # type: ignore[assignment]
    agg_dosemap_spinner: ui.spinner = None  # type: ignore[assignment]
    multi_exam_accordion_container: ui.column = None  # type: ignore[assignment]
    subset_checkboxes_container: ui.column = None  # type: ignore[assignment]
