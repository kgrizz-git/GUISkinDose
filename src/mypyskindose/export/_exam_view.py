"""Uniform view over the two calculation-result shapes.

Single-exam results arrive as a **dict** (``PySkinDoseOutput.to_dict()``) with a
*sparse* ``dose_map`` (``[(vertex_index, dose), ...]``). Multi-exam results arrive
as ``PySkinDoseOutput`` **objects** with a dense ``np.ndarray`` ``dose_map`` and
canonical lowercase attributes. ``ExamView`` normalizes both into one interface so the metrics
and image code never branch on dict-vs-object. See §7 of the Rich Export plan.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass
class ExamView:
    """Canonical, shape-agnostic view of one exam's calculation output."""

    psd: float
    air_kerma: float
    patient: dict[str, Any]  # inner patient dict: patient_skin_cells + triangle_vertex_indices + human_phantom
    dense_dose_map: np.ndarray
    # Correction factors, keyed by physics name regardless of source dict keys.
    hits: list[list[int]]  # per-event hit cell indices
    k_bs: list[Any]  # per-event per-hit lists
    k_isq: list[Any]  # per-event per-hit lists or per-event scalar
    k_med: list[float]  # per-event scalar
    k_tab: list[float]  # per-event scalar
    kerma: list[float]  # per-event air kerma used for dose-weighted stats
    k_meter: list[float] | None = None  # per-event kerma-meter CF when present
    air_kerma_corrected: float | None = None
    kerma_reported: list[float] | None = None

    def peak_vertex(self) -> tuple[int | None, float]:
        """Return ``(vertex_index, dose)`` of the peak dose cell.

        Returns ``(None, 0.0)`` for an all-zero map (nothing hit the phantom).
        """
        if self.dense_dose_map.size == 0:
            return None, 0.0
        idx = int(np.argmax(self.dense_dose_map))
        dose = float(self.dense_dose_map[idx])
        if dose <= 0.0:
            return None, 0.0
        return idx, dose

    def skin_cell_xyz(self, index: int) -> tuple[float, float, float] | None:
        """Return skin-cell XYZ (cm) for *index*, or None if out of range."""
        cells = self.patient.get("patient_skin_cells")
        if not cells or index >= len(cells["x"]):
            return None
        return float(cells["x"][index]), float(cells["y"][index]), float(cells["z"][index])


def _dense_from_sparse(sparse: list[Any], num_cells: int) -> np.ndarray:
    """Expand sparse (index, dose) pairs into a dense length-*num_cells* array."""
    dense = np.zeros(num_cells)
    for idx, dose in sparse:
        dense[int(idx)] = dose
    return dense


def _to_list(value: Any) -> list[Any]:
    """Coerce None/ndarray/scalar values to a plain Python list."""
    if value is None:
        return []
    if isinstance(value, np.ndarray):
        return value.tolist()
    return list(value)


def view_from_dict(output: dict[str, Any]) -> ExamView:
    """Build an ``ExamView`` from a single-exam ``PySkinDoseOutput.to_dict()``."""
    patient = output["patient"]["patient"]
    num_cells = len(patient["patient_skin_cells"]["x"])
    dense = _dense_from_sparse(output.get("dose_map", []), num_cells)
    corr = output.get("corrections", {})
    kerma_reported = [float(v) for v in corr.get("kerma", [])]
    kerma_corrected = corr.get("kerma_corrected")
    weight_kerma = (
        [float(v) for v in kerma_corrected] if kerma_corrected is not None else kerma_reported
    )
    k_meter = corr.get("kerma_meter")
    return ExamView(
        psd=float(output.get("psd", 0.0)),
        air_kerma=float(output.get("air_kerma", 0.0)),
        patient=patient,
        dense_dose_map=dense,
        hits=[list(map(int, h)) for h in corr.get("correction_value_index", [])],
        k_bs=[_to_list(ev) for ev in corr.get("backscatter", [])],
        k_isq=[ev if isinstance(ev, (int, float)) else _to_list(ev) for ev in corr.get("inverse_square_law", [])],
        k_med=[float(v) for v in corr.get("medium", [])],
        k_tab=[float(v) for v in corr.get("table", [])],
        kerma=weight_kerma,
        k_meter=[float(v) for v in k_meter] if k_meter is not None else None,
        air_kerma_corrected=(
            float(output["air_kerma_corrected"])
            if "air_kerma_corrected" in output
            else None
        ),
        kerma_reported=kerma_reported,
    )


def view_from_output(obj: Any) -> ExamView:
    """Build an ``ExamView`` from a ``PySkinDoseOutput`` object (multi-exam path)."""
    patient = obj.patient_export()["patient"].to_dict()
    kerma_reported = [float(v) for v in _to_list(obj.events.kerma)]
    kerma_corrected = [float(v) for v in (obj.kerma_corrected or kerma_reported)]
    k_meter = obj.kerma_meter_correction
    return ExamView(
        psd=float(obj.psd),
        air_kerma=float(obj.air_kerma),
        patient=patient,
        dense_dose_map=np.asarray(obj.dose_map, dtype=float),
        hits=[list(map(int, h)) for h in obj.sparse_hit_indices()],
        k_bs=[_to_list(ev) for ev in obj.backscatter_correction],
        k_isq=[ev if isinstance(ev, (int, float)) else _to_list(ev) for ev in obj.inverse_square_law_correction],
        k_med=[float(v) for v in obj.medium_correction],
        k_tab=[float(v) for v in obj.table_correction],
        kerma=kerma_corrected,
        k_meter=[float(v) for v in k_meter] if k_meter is not None else None,
        air_kerma_corrected=float(obj.air_kerma_corrected),
        kerma_reported=kerma_reported,
    )
