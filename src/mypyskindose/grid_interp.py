"""Shared 2-D (kVp × Cu) grid lookup with edge clamping.

Both the HVL lookup (``geom_calc.fetch_and_append_hvl``) and the table-attenuation
lookup (``corrections.calculate_k_tab``) interpolate a correction over a complete
``(kVp × Cu)`` grid slice. kVp is tabulated at a dense 1 kV step, so it is rounded
to its nearest integer node (lossless dosimetrically); the sparse Cu axis is
linearly interpolated. Queries outside the grid are **clamped** to the nearest
edge — we never extrapolate past the tabulated range.

See ``dev-docs/plans/archive/hvl-interpolation-and-below-floor-kvp.md``.
"""

from __future__ import annotations

import numpy as np
from scipy.interpolate import RegularGridInterpolator

# Per-event lookup classification.
STATUS_EXACT = "exact"
STATUS_INTERPOLATED = "interpolated"
STATUS_CLAMPED = "clamped"


def format_event_indices(indices: list[int], limit: int = 20) -> str:
    """Format a list of affected event indices for a warning, capping the spam at
    ``limit`` entries (``"... (+N more)"``) so long procedures do not flood logs."""
    extra = f" (+{len(indices) - limit} more)" if len(indices) > limit else ""
    return f"{indices[:limit]}{extra}"


def clamped_rgi_lookup(
    rgi: RegularGridInterpolator,
    kv_axis: np.ndarray,
    cu_axis: np.ndarray,
    kvp: float,
    cu: float,
) -> tuple[float, str]:
    """Look up ``(kVp, Cu)`` from a prebuilt 2-D ``RegularGridInterpolator``.

    kVp is rounded to its nearest integer node; Cu is interpolated. Out-of-range
    queries on either axis are clamped to the grid edge (never extrapolated).

    Returns ``(value, status)`` where ``status`` is one of ``"exact"`` (query on a
    grid node), ``"interpolated"`` (off-node Cu, in range), or ``"clamped"`` (query
    fell outside the grid and was pinned to the nearest edge).
    """
    kv_q = float(round(kvp))
    kv_c = float(np.clip(kv_q, kv_axis[0], kv_axis[-1]))
    cu_c = float(np.clip(cu, cu_axis[0], cu_axis[-1]))
    was_clamped = kv_c != kv_q or cu_c != cu

    value = float(rgi((kv_c, cu_c)))

    if was_clamped:
        status = STATUS_CLAMPED
    elif bool(np.any(np.isclose(cu_axis, cu_c))):
        status = STATUS_EXACT
    else:
        status = STATUS_INTERPOLATED
    return value, status
