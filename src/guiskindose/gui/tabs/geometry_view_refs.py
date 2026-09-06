"""UI element references for the Geometry tab."""

from __future__ import annotations

from dataclasses import dataclass, field

from nicegui import ui


@dataclass
class GeometryViewRefs:
    """UI element references owned by the Geometry tab."""

    spinner: ui.spinner = None  # type: ignore[assignment]
    vendor_notice: ui.label = None  # type: ignore[assignment]
    preview_caption: ui.label = None  # type: ignore[assignment]
    exam_select: ui.select = None  # type: ignore[assignment]
    geom_exam_select: ui.select = None  # type: ignore[assignment]
    geom_event_select: ui.select = None  # type: ignore[assignment]
    geom_event_context: ui.label = None  # type: ignore[assignment]
    prev_btn: ui.button = None  # type: ignore[assignment]
    next_btn: ui.button = None  # type: ignore[assignment]
    composite_checkbox: ui.checkbox = None  # type: ignore[assignment]
    plot: ui.plotly = None  # type: ignore[assignment]
    paused_badge: ui.badge = None  # type: ignore[assignment]
    stale_caption: ui.label = None  # type: ignore[assignment]
    patient_sliders: dict[str, ui.slider] = field(default_factory=dict)
    patient_val_labels: dict[str, ui.label] = field(default_factory=dict)
    table_sliders: dict[str, ui.slider] = field(default_factory=dict)
    table_val_labels: dict[str, ui.label] = field(default_factory=dict)
