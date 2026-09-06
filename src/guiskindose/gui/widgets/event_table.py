"""Event summary table widget for the Upload tab (refactor plan Phase 3.2)."""

from __future__ import annotations

from dataclasses import dataclass

from nicegui import ui

from ..state import state


@dataclass
class EventTableWidget:
    """Eventtablewidget."""
    table: ui.table

    def refresh(self) -> None:
        """Refresh."""
        if state.rdsr_df is None:
            self.table.rows = []
            self.table.update()
            return
        df = state.rdsr_df
        rows = []
        for idx, (_, row) in enumerate(df.iterrows()):
            rows.append({
                "idx": idx + 1,
                "kVp": round(float(row.get("kVp", 0)), 1),
                "Ap1": round(float(row.get("Ap1", 0)), 1),
                "Ap2": round(float(row.get("Ap2", 0)), 1),
                "K_IRP": round(float(row.get("K_IRP", 0)), 3),
            })
        self.table.rows = rows
        self.table.update()


def build() -> EventTableWidget:
    """Build."""
    ui.label("Irradiation events").classes("text-subtitle2 q-mt-md q-mb-xs")
    table = ui.table(
        columns=[
            {"name": "idx", "label": "#", "field": "idx", "align": "right"},
            {"name": "kVp", "label": "kVp", "field": "kVp", "align": "right"},
            {"name": "Ap1", "label": "Ap1 (°)", "field": "Ap1", "align": "right"},
            {"name": "Ap2", "label": "Ap2 (°)", "field": "Ap2", "align": "right"},
            {"name": "K_IRP", "label": "K_IRP (mGy)", "field": "K_IRP", "align": "right"},
        ],
        rows=[],
        row_key="idx",
    ).classes("w-full modern-card mono-text")
    return EventTableWidget(table=table)
