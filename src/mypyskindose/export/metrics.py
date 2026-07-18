"""Dosimetric and correction-factor metrics for the export payload (§7–§8).

All functions consume :class:`ExamView` (shape-agnostic) plus the per-exam
normalized DataFrame; none read GUI state.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from mypyskindose.constants import (
    KEY_NORMALIZATION_ACQUISITION_TYPE,
    KEY_NORMALIZATION_AIR_KERMA,
)

from ._exam_view import ExamView
from .models import (
    AcquisitionBreakdown,
    CorrectionStat,
    DosimetricMetrics,
    PrimaryContributingExam,
)

_DAP_COL = "DoseAreaProduct_Gym2"  # Gy·m²; ×1e4 → Gy·cm²
_GYM2_TO_GYCM2 = 10_000.0
_FLUORO_TIME_COL = "fluoro_time_s"  # per-event fluoro time in seconds

CORRECTION_KEYS = ("k_bs", "k_isq", "k_med", "k_tab")


# ── dosimetric ────────────────────────────────────────────────────────────────


def total_dap_gycm2(df: pd.DataFrame | None) -> float | None:
    """Total DAP in Gy·cm² from the normalized DataFrame, or ``None``."""
    if df is None or _DAP_COL not in df.columns:
        return None
    series = pd.to_numeric(df[_DAP_COL], errors="coerce").dropna()
    if series.empty:
        return None
    return float(series.sum()) * _GYM2_TO_GYCM2


def total_fluoro_time_s(df: pd.DataFrame | None) -> float | None:
    """Total fluoro time in seconds from the normalized DataFrame, or ``None``.

    Per-event values are NaN on non-fluoro (acquisition) events; those are
    skipped so the sum is the procedure fluoro time only.
    """
    if df is None or _FLUORO_TIME_COL not in df.columns:
        return None
    series = pd.to_numeric(df[_FLUORO_TIME_COL], errors="coerce").dropna()
    if series.empty:
        return None
    return float(series.sum())


def _normalize_acquisition(raw: Any) -> str:
    label = str(raw).lower()
    if "fluoro" in label:
        return "fluoroscopy"
    if "acq" in label:
        return "acquisition"
    return "other"


def acquisition_breakdown(df: pd.DataFrame | None) -> list[AcquisitionBreakdown]:
    if df is None or KEY_NORMALIZATION_ACQUISITION_TYPE not in df.columns:
        return []
    kerma_col = KEY_NORMALIZATION_AIR_KERMA if KEY_NORMALIZATION_AIR_KERMA in df.columns else None
    has_dap = _DAP_COL in df.columns
    groups: dict[str, dict[str, Any]] = {}
    for _, row in df.iterrows():
        raw = row[KEY_NORMALIZATION_ACQUISITION_TYPE]
        mode = _normalize_acquisition(raw)
        g = groups.setdefault(mode, {"raw": set(), "count": 0, "kerma": 0.0, "dap": 0.0, "dap_seen": False})
        g["raw"].add(str(raw))
        g["count"] += 1
        if kerma_col is not None:
            g["kerma"] += float(pd.to_numeric(row[kerma_col], errors="coerce") or 0.0)
        if has_dap:
            val = pd.to_numeric(row[_DAP_COL], errors="coerce")
            if not pd.isna(val):
                g["dap"] += float(val) * _GYM2_TO_GYCM2
                g["dap_seen"] = True
    order = {"fluoroscopy": 0, "acquisition": 1, "other": 2}
    return [
        AcquisitionBreakdown(
            mode=mode,
            raw_labels=sorted(g["raw"]),
            event_count=g["count"],
            air_kerma=round(g["kerma"], 6),
            dap_gycm2=(round(g["dap"], 6) if g["dap_seen"] else None),
        )
        for mode, g in sorted(groups.items(), key=lambda kv: order.get(kv[0], 3))
    ]


def dosimetric_metrics(
    view: ExamView,
    df: pd.DataFrame | None,
    *,
    events_discarded: int = 0,
) -> DosimetricMetrics:
    peak_idx, _ = view.peak_vertex()
    peak_xyz = view.skin_cell_xyz(peak_idx) if peak_idx is not None else None
    events_processed = 0 if df is None else len(df)
    return DosimetricMetrics(
        psd=view.psd,
        air_kerma=view.air_kerma,
        dap_gycm2=total_dap_gycm2(df),
        fluoro_time_s=total_fluoro_time_s(df),
        events_processed=events_processed,
        events_discarded=events_discarded,
        peak_vertex_index=peak_idx,
        peak_xyz=peak_xyz,
        acquisition_breakdown=acquisition_breakdown(df),
    )


# ── corrections ───────────────────────────────────────────────────────────────


def _per_event_values(view: ExamView, key: str) -> list[float | None]:
    """Representative per-event value for a factor, restricted to events with hits.

    Non-hit events (``len(hits[i]) == 0``) yield ``None``. For ``k_bs`` / ``k_isq``
    the value is the arithmetic mean across hit cells; for ``k_med`` / ``k_tab`` it
    is the per-event scalar.
    """
    n = len(view.hits)
    out: list[float | None] = []
    for i in range(n):
        if len(view.hits[i]) == 0:
            out.append(None)
            continue
        if key == "k_med":
            out.append(float(view.k_med[i]) if i < len(view.k_med) else None)
        elif key == "k_tab":
            out.append(float(view.k_tab[i]) if i < len(view.k_tab) else None)
        elif key == "k_bs":
            cells = view.k_bs[i] if i < len(view.k_bs) else []
            out.append(float(np.mean(cells)) if len(cells) else None)
        elif key == "k_isq":
            v = view.k_isq[i] if i < len(view.k_isq) else []
            if isinstance(v, (int, float)):
                out.append(float(v))
            else:
                out.append(float(np.mean(v)) if len(v) else None)
        else:  # pragma: no cover - guarded by CORRECTION_KEYS
            out.append(None)
    return out


def _dose_weighted_mean(values: list[float | None], kerma: list[float], hits: list[list[int]]) -> float | None:
    num = 0.0
    den = 0.0
    for i, val in enumerate(values):
        if val is None or len(hits[i]) == 0:
            continue
        k = kerma[i] if i < len(kerma) else 0.0
        num += k * val
        den += k
    if not den:
        return None
    return num / den


def correction_stats(view: ExamView) -> list[CorrectionStat]:
    stats: list[CorrectionStat] = []
    for key in CORRECTION_KEYS:
        values = _per_event_values(view, key)
        present = [v for v in values if v is not None]
        stats.append(
            CorrectionStat(
                key=key,
                minimum=(min(present) if present else None),
                maximum=(max(present) if present else None),
                mean=(float(np.mean(present)) if present else None),
                dose_weighted_mean=_dose_weighted_mean(values, view.kerma, view.hits),
            )
        )
    return stats


def cumulative_correction_stats(views: list[ExamView]) -> list[CorrectionStat]:
    """Kerma-weighted cumulative corrections (§8): min/max/mean pool per-event
    values across exams; dose-weighted mean is kerma-weighted across per-exam
    weighted means."""
    stats: list[CorrectionStat] = []
    for key in CORRECTION_KEYS:
        pooled: list[float] = []
        wnum = 0.0
        wden = 0.0
        for view in views:
            values = _per_event_values(view, key)
            pooled.extend(v for v in values if v is not None)
            exam_dwm = _dose_weighted_mean(values, view.kerma, view.hits)
            if exam_dwm is not None and view.air_kerma > 0:
                wnum += view.air_kerma * exam_dwm
                wden += view.air_kerma
        stats.append(
            CorrectionStat(
                key=key,
                minimum=(min(pooled) if pooled else None),
                maximum=(max(pooled) if pooled else None),
                mean=(float(np.mean(pooled)) if pooled else None),
                dose_weighted_mean=(wnum / wden if wden > 0 else None),
            )
        )
    return stats


# ── cumulative dosimetric ─────────────────────────────────────────────────────


def cumulative_air_kerma(views: list[ExamView]) -> float:
    """Explicit sum of per-exam air kerma (not stored on ``MultiExamResult``)."""
    return float(sum(v.air_kerma for v in views))


def primary_contributing_exam(
    views: list[ExamView],
    exam_ids: list[str],
    aggregate_dose_map: np.ndarray,
) -> PrimaryContributingExam | None:
    """Identify the exam delivering the largest dose fraction to the cumulative
    PSD peak vertex (§7 PSD peak frame)."""
    if aggregate_dose_map.size == 0:
        return None
    peak_idx = int(np.argmax(aggregate_dose_map))
    total = float(aggregate_dose_map[peak_idx])
    if total <= 0.0:
        return None
    contribs = []
    for view in views:
        dm = view.dense_dose_map
        contribs.append(float(dm[peak_idx]) if peak_idx < dm.size else 0.0)
    best = int(np.argmax(contribs))
    baseline_xyz = views[0].skin_cell_xyz(peak_idx) if views else None
    primary_xyz = views[best].skin_cell_xyz(peak_idx)
    return PrimaryContributingExam(
        exam_id=exam_ids[best],
        dose_fraction=contribs[best] / total,
        peak_xyz_baseline=baseline_xyz,
        peak_xyz_primary_frame=primary_xyz,
    )
