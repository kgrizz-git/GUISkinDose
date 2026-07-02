"""Shared presentation helpers for report writers (labels, colors, formatting)."""

from __future__ import annotations

from typing import Any

from .models import CorrectionStat, DosimetricMetrics, ExportPayload

# Executive-alert palette (shared by XLSX/PDF/HTML).
COLOR_WARNING = "FFF3CD"  # amber — warnings
COLOR_ERROR = "F8D7DA"    # amber-red — data loss / skips / beam misses

# Human-readable correction factor names.
CORRECTION_LABELS = {
    "k_bs": "Backscatter (k_bs)",
    "k_isq": "Inverse-square law (k_isq)",
    "k_med": "Medium (k_med)",
    "k_tab": "Table (k_tab)",
}

# Patient-offset field → clear anatomical direction. The offset fields carry the
# axis in their name: d_lon = longitudinal (superior-inferior), d_ver = vertical
# (anterior-posterior), d_lat = lateral (left-right).
OFFSET_LABELS = {
    "d_lon": "Longitudinal (Superior-Inferior)",
    "d_ver": "Vertical (Anterior-Posterior)",
    "d_lat": "Lateral (Left-Right)",
}


def fmt_float(value: Any, digits: int = 2) -> str:
    if value is None:
        return "N/A"
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return str(value)


def fmt_dose(value: Any) -> str:
    return fmt_float(value, 1)


def fmt_correction(value: Any) -> str:
    return fmt_float(value, 4)


def fmt_xyz(xyz: tuple[float, float, float] | None) -> str:
    if xyz is None:
        return "N/A"
    return f"({xyz[0]:.2f}, {xyz[1]:.2f}, {xyz[2]:.2f}) cm"


def correction_row(stat: CorrectionStat) -> list[str]:
    """One correction factor as [label, min, max, mean, dose-weighted mean]."""
    return [
        CORRECTION_LABELS.get(stat.key, stat.key),
        fmt_correction(stat.minimum),
        fmt_correction(stat.maximum),
        fmt_correction(stat.mean),
        fmt_correction(stat.dose_weighted_mean),
    ]


CORRECTION_HEADER = ["Correction factor", "Min", "Max", "Mean", "Dose-weighted mean"]


def dosimetric_rows(metrics: DosimetricMetrics) -> list[list[str]]:
    """Metric | Value rows for a dosimetric summary block."""
    rows = [
        ["Peak skin dose (PSD)", f"{fmt_dose(metrics.psd)} mGy"],
        ["Reference air kerma (Ka,r)", f"{fmt_dose(metrics.air_kerma)} mGy"],
        ["Total DAP", (f"{fmt_float(metrics.dap_gycm2, 2)} Gy·cm²" if metrics.dap_gycm2 is not None else "N/A")],
        ["Total fluoro time", (f"{metrics.fluoro_time_s:.0f} s" if metrics.fluoro_time_s is not None else "N/A")],
        ["Events processed", str(metrics.events_processed)],
        ["Events discarded", str(metrics.events_discarded)],
        ["PSD peak vertex index", ("N/A" if metrics.peak_vertex_index is None else str(metrics.peak_vertex_index))],
        ["PSD peak location", fmt_xyz(metrics.peak_xyz)],
    ]
    return rows


def collect_alert_lines(payload: ExportPayload) -> list[tuple[str, str]]:
    """Return (text, severity) pairs for the executive alert block.

    Severity is ``"error"`` for data loss (discarded events) and ``"warning"``
    otherwise.
    """
    lines: list[tuple[str, str]] = []
    w = payload.warnings
    for reason, count in w.discarded_events.items():
        lines.append((f"{count} event(s) discarded: {reason}", "error"))
    for msg in w.run_warnings:
        sev = "error" if "missed" in msg.lower() or "failed" in msg.lower() else "warning"
        lines.append((msg, sev))
    for msg in w.calc_warnings:
        lines.append((msg, "warning"))
    for msg in w.import_warnings:
        lines.append((msg, "warning"))
    if not lines:
        lines.append(("No warnings, discarded events, or QA alerts.", "ok"))
    return lines
