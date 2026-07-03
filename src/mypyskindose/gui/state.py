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

    # Tabular import
    input_schema: str = "auto"
    input_source_type: str = ""  # "dicom" | "csv" | "tsv" | "xlsx" | ""
    input_sheet_name: str | int = 0  # selected sheet (name or 0-based index)
    available_sheets: list[str] = field(default_factory=list)  # all sheet names (xlsx only)
    import_provenance: Any | None = None
    import_warnings: list[str] = field(default_factory=list)
    import_has_errors: bool = False
    swap_lat_lon: bool = False    # post-norm: swap Tx ↔ Tz
    flip_ap1: bool = False        # post-norm: negate Ap1 (primary angle)
    flip_ap2: bool = False        # post-norm: negate Ap2 (secondary angle)

    # ── Multi-exam support ─────────────────────────────────────────────────
    multi_exam_result: Any | None = None
    loaded_exams: list[Any] = field(default_factory=list)  # list[InputAdapterResult]
    loaded_exam_meta: list[dict] = field(default_factory=list)  # per-exam metadata parallel to loaded_exams
    is_multi_exam: bool = False
    active_exam_index: int | None = None

    # ── Settings (raw values mirrored from UI widgets) ─────────────────────
    phantom_model: str = "human"
    human_mesh: str = "hudfrid"
    patient_orientation: str = "head_first_supine"
    d_lon: float = 0.0
    d_ver: float = 0.0
    d_lat: float = 0.0
    phantom_scale_lat: float = 1.0
    phantom_scale_ap: float = 1.0
    phantom_scale_lon: float = 1.0
    # Bumped when any per-exam or global patient offset changes so Calculate summary
    # labels bound to d_lon/d_ver/d_lat alone refresh in multi-exam mode.
    per_exam_offsets_version: int = 0

    estimate_k_tab: bool = True
    k_tab_val: float = 0.8
    inherent_filtration: float = 3.1
    remove_invalid_rows: bool = False

    # Below-floor kVp handling (events with kVp < 25 kV HVL table floor): policy is
    # "snap" (default) / "skip" / "manual" / "exam_average"; manual value used only
    # by "manual". below_floor_prompt_suppressed silences the pre-calc prompt once
    # the user picks "don't ask again".
    below_floor_kvp_policy: str = "exam_average"
    below_floor_kvp_manual: float = 70.0
    below_floor_prompt_suppressed: bool = False
    beam_miss_warn: str = "summary"

    plot_dosemap: bool = True
    dark_mode: bool = True
    colorscale: str = "jet"

    # ── Calculation results ────────────────────────────────────────────────
    output: dict[str, Any] | None = None
    calculation_done: bool = False
    # Incremented on each successful dose run so Results UI can rebuild when
    # multi_exam_result is replaced (offsets changed, then recalculated).
    calc_run_id: int = 0
    psd: float | None = None
    air_kerma: float | None = None
    # Warnings emitted during the last calculation (e.g. HVL lookups snapped to the
    # nearest grid point for out-of-range events). Surfaced in the GUI after a run.
    calc_warnings: list[str] = field(default_factory=list)

    # ── Geometry preview figures (Plotly Figure objects) ───────────────────
    setup_fig: Any | None = None
    event_fig: Any | None = None
    procedure_fig: Any | None = None
    dosemap_fig: Any | None = None

    # ── Concurrency guard ──────────────────────────────────────────────────
    # True while a load/sheet-change/calculation is in flight. Prevents a second
    # operation from interleaving its state mutations with one already running
    # (e.g. double-click upload, or Calculate while a coordinate swap is applied).
    busy: bool = False

    # ── Navigation ─────────────────────────────────────────────────────────
    active_tab: str = "input"

    # ── Misc ───────────────────────────────────────────────────────────────
    errors: list[str] = field(default_factory=list)


# Single shared instance
state = AppState()


def reset_results() -> None:
    """Clear calculation results when settings or file change."""
    state.output = None
    state.multi_exam_result = None
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
