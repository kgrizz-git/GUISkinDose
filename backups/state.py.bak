"""Shared application state for the MyPySkinDose GUI.

A single AppState instance is created at import time and shared across all
pages. NiceGUI's reactive model means UI elements bind directly to these
values; call reset_results() whenever settings change so stale output is
never displayed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd


@dataclass
class AppState:
    # ── RDSR data ──────────────────────────────────────────────────────────
    rdsr_df: pd.DataFrame | None = None
    rdsr_raw_df: pd.DataFrame | None = None
    view_raw: bool = False
    file_path: Path | None = None
    file_name: str = ""
    manufacturer: str = ""
    model: str = ""
    normalization_method: str = "Unknown"
    normalization_warnings: list[str] = field(default_factory=list)
    table_offset_x: float = 0.0
    table_offset_y: float = 0.0
    table_offset_z: float = 0.0

    # ── Settings (raw values mirrored from UI widgets) ─────────────────────
    phantom_model: str = "human"
    human_mesh: str = "hudfrid"
    patient_orientation: str = "head_first_supine"
    d_lon: float = 0.0
    d_ver: float = 0.0
    d_lat: float = 0.0

    estimate_k_tab: bool = True
    k_tab_val: float = 0.8
    inherent_filtration: float = 3.1
    remove_invalid_rows: bool = False

    plot_dosemap: bool = True
    dark_mode: bool = True
    colorscale: str = "jet"

    # ── Calculation results ────────────────────────────────────────────────
    output: dict[str, Any] | None = None
    calculation_done: bool = False
    psd: float | None = None
    air_kerma: float | None = None

    # ── Geometry preview figures (Plotly Figure objects) ───────────────────
    setup_fig: Any | None = None
    event_fig: Any | None = None
    procedure_fig: Any | None = None
    dosemap_fig: Any | None = None

    # ── Misc ───────────────────────────────────────────────────────────────
    errors: list[str] = field(default_factory=list)


# Single shared instance
state = AppState()


def reset_results() -> None:
    """Clear calculation results when settings or file change."""
    state.output = None
    state.calculation_done = False
    state.psd = None
    state.air_kerma = None
    state.dosemap_fig = None


def is_ready_to_calculate() -> bool:
    return state.rdsr_df is not None


def event_count() -> int:
    if state.rdsr_df is None:
        return 0
    return len(state.rdsr_df)
