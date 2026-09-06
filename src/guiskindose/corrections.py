"""Physics-based correction factors for inverse-square law, backscatter, medium, and table attenuation."""

import logging
from typing import cast

import numpy as np
import pandas as pd
import scipy.interpolate
from scipy.interpolate import CubicSpline, RegularGridInterpolator

from .db_connect import db_connect
from .grid_interp import (
    STATUS_CLAMPED,
    STATUS_EXACT,
    STATUS_INTERPOLATED,
    clamped_rgi_lookup,
    format_event_indices,
)

logger = logging.getLogger(__name__)


def calculate_k_isq(source: np.ndarray, cells: np.ndarray, dref: float) -> np.ndarray:
    """Calculate the IRP air kerma inverse-square law correction.

    This function corrects the X-ray fluence from the interventionl reference point
    (IRP), to the actual source to skin distance, so that the IRP air kerma is converted
    to air kerma at the patient skin surface.

    Parameters
    ----------
    source : np.array
        location of the X-ray source
    cells : np.array
        location of all the cells that are hit by the beam
    dref : float
        reference distance source to IRP, i.e. the distance at which the IRP air kerma
        is stated.

    Returns
    -------
    np.array
        Inverse-square law correction for all cells that are hit by the beam.

    """
    # Discriminate by dimensionality, not cell count. A 1-D ``cells`` is a single
    # (3,) coordinate -> scalar correction. A 2-D ``cells`` is (n_hits, 3); norm
    # over axis=1 gives one per-cell source-to-cell distance per hit cell, for any
    # n_hits. (A prior ``len(cells) > 3`` guard sent <=3 hits to axis=0, which
    # collapses the cell axis to shape (3,) — crashing for 1-2 hits and silently
    # mis-dosing exactly-3-hit events.)
    cells = np.asarray(cells)
    if cells.ndim == 1:
        return np.square(dref / np.linalg.norm(cells - source))
    return np.square(dref / np.linalg.norm(cells - source, axis=1))


def calculate_k_bs(data_norm: pd.DataFrame) -> list[CubicSpline]:
    """Calculate backscatter correction.

    This function calculates the backscatter correction factor for all events, at field
    sizes [5, 10, 20, 25, 35] cm^2. The function uses the non-linear interpolation
    method presented by
    Benmakhlouf et al. in the article "Influence of phantom thickness and material on
    the backscatter factors for diagnostic x-ray beam dosimetry",
    [doi:10.1088/0031-9155/58/2/247]

    Parameters
    ----------
    data_norm : pd.DataFrame
        RDSR data, normalized for compliance with PySkinDose.

    Returns
    -------
    List[CubicSpline]
        List of scipy cubic spline interpolation object for all events.

    """
    # Tabulated field side length in cm
    fsl_tab = [5, 10, 20, 25, 35]

    # polynomial coefficents
    c = np.array(
        [
            [+1.00870e0, +9.29969e-1, +8.65442e-1, +8.58665e-1, +8.57065e-1],
            [+2.35816e-3, +4.08549e-3, +5.36739e-3, +5.51579e-3, +5.55933e-3],
            [-9.48937e-6, -1.66271e-5, -2.21494e-5, -2.27532e-5, -2.28004e-5],
            [+1.03143e-1, +1.53605e-1, +1.72418e-1, +1.70826e-1, +1.66418e-1],
            [-1.04881e-3, -1.45187e-3, -1.46088e-3, -1.38540e-3, -1.28180e-3],
            [+3.59731e-6, +5.05312e-6, +5.17430e-6, +4.91192e-6, +4.53036e-6],
            [-7.31303e-3, -9.32427e-3, -8.30138e-3, -7.64330e-3, -6.81574e-3],
            [+7.93272e-5, +9.40568e-5, +7.13576e-5, +6.13126e-5, +4.94197e-5],
            [-2.74296e-7, -3.28449e-7, -2.54885e-7, -2.21399e-7, -1.79074e-7],
        ]
    )

    # Fetch kVp and HVL from data_norm
    kvp = data_norm.kVp
    hvl = data_norm.HVL

    # Calculate k_bs for field side length [5, 10, 20, 25, 35] cm
    # This is eq. (8) in doi:10.1088/0031-9155/58/2/247.
    bs_corr = [
        (c[0, :] + c[1, :] * kvp[event] + c[2, :] * np.square(kvp[event]))
        + (c[3, :] + c[4, :] * kvp[event] + c[5, :] * np.square(kvp[event])) * hvl[event]
        + (c[6, :] + c[7, :] * kvp[event] + c[8, :] * np.square(kvp[event])) * np.square(hvl[event])
        for event in range(len(kvp))
    ]

    # Create interpolation object for bs_corr
    bs_interp = [scipy.interpolate.CubicSpline(fsl_tab, bs_corr[event]) for event in range(len(kvp))]

    return bs_interp


def calculate_k_med(data_norm: pd.DataFrame, field_area: list[float], event: int, corrections_db: str) -> float:
    """Calculate medium correction.

    This function calculates and appends the medium correction factor for all skin cells
    that are hit by the X-ray beam in an event. The correction factors are from the
    article "Backscatter factors and mass energy-absorption coefficient ratios for
    surface dose determination in diagnostic radiology".

    Parameters
    ----------
    data_norm : pd.DataFrame
        RDSR data, normalized for compliance with PySkinDose.
    field_area : List[float]
        X-ray field area in (cm^2) for each phantom skin cell that are hit by the X-ray
        beam.
    event : int
        Irradiation event index.
    corrections_db : str
        A string defining the path to the corrections SQLite db


    Returns
    -------
    float
        Medium correction k_med for all cells that are hit by the beam.

    """
    # Tabulated field side length in cm
    fsl_tab = [5, 10, 20, 25, 35]

    # Fetch kVp and HVL from data_norm
    kvp = data_norm.kVp[event]
    hvl = data_norm.HVL[event]

    # Calculate mean side length for all cells that are hit by the beam.
    # This field size dependance of k_med is negligible (<= 1%), therefore,
    # independep field size resolution is omitted for computational speed.
    fsl_mean = np.mean(np.sqrt(field_area))

    # Select the closest available tabulated field size length.
    fsl = fsl_tab[int(np.argmin(np.abs(np.asarray(fsl_tab) - fsl_mean)))]

    # Connect to database
    conn = db_connect(db_name=corrections_db)[0]

    # Fetch k_med = f(kVp, HVL) from database. This is table 2 in
    # [doi:10.1088/0031-9155/58/2/247]
    df = pd.read_sql_query(
        """SELECT kvp_kv, hvl_mmal, field_side_length_cm,
                           mu_en_quotient FROM correction_medium_and_backscatter""",
        conn,
    )

    conn.commit()
    conn.close()

    # Fetch kVp entries from table
    kvp_data = df.loc[(df["field_side_length_cm"] == fsl), "kvp_kv"]
    # Select closest tabulated kVp (strongest dependence for k_med)
    kvp_series = cast(pd.Series, kvp_data)
    kvp_round = min(kvp_series.tolist(), key=lambda x: abs(x - kvp))

    # Fetch HVL entries from table
    hvl_data = df.loc[(df["field_side_length_cm"] == fsl) & (df["kvp_kv"] == kvp_round), "hvl_mmal"]

    # Select closest tabulated HVL (second strongest dependence for k_med)
    hvl_round = min(cast(pd.Series, hvl_data).tolist(), key=lambda x: abs(x - hvl))

    # Fetch corresponding k_med
    k_med = float(
        cast(pd.Series, df.loc[
            (df["hvl_mmal"] == hvl_round) & (df["kvp_kv"] == kvp_round) & (df["field_side_length_cm"] == fsl),
            "mu_en_quotient",
        ]).iloc[0]
    )

    return k_med


def _match_device_rows(tab: pd.DataFrame, model: str, plane: str) -> pd.DataFrame:
    """Filter the attenuation table to the rows for ``model`` (or its de-spaced
    form) on ``plane``. Pure row filter; no caching."""
    return tab[
        tab["device_model"].isin([model, model.replace(" ", "")]) & (tab["acquisition_plane"] == plane)
    ]


def _interpolate_off_grid(
    rows: pd.DataFrame,
    model: str,
    plane: str,
    kvp: float,
    cu: float,
    al: float,
    pivot_cache: dict[tuple[str, str, float], pd.DataFrame],
) -> tuple[float, str]:
    """Snap Al to the nearest measured grid value, build-or-reuse the
    ``(kVp × Cu)`` pivot for this ``(model, plane, Al)`` slice, and run a
    clamped ``RegularGridInterpolator`` lookup.

    ``pivot_cache`` is initialised by ``calculate_k_tab`` and threaded through
    each event so the pivot table is only built once per ``(model, plane,
    Al-snapped)`` key. The key is derived from the *input* ``model``/``plane``
    (not ``rows``) so callers using a spaced alias and the de-spaced DB form
    share a single cache slot, matching the pre-refactor behaviour.

    Returns ``(value, status)`` where ``status`` is ``STATUS_CLAMPED`` if Al was
    snapped off the query or the rgi lookup clamped, else the underlying
    ``STATUS_EXACT`` / ``STATUS_INTERPOLATED``.
    """
    al_grid = np.sort(np.unique(rows["filtration_added_mmal"].to_numpy(dtype=float)))
    al_snap = float(al_grid[int(np.abs(al_grid - round(al)).argmin())])

    cache_key = (model, str(plane), al_snap)
    piv = pivot_cache.get(cache_key)
    if piv is None:
        selected_rows = rows[rows["filtration_added_mmal"] == al_snap]
        piv = selected_rows.pivot_table(index="kvp_kv", columns="filtration_added_mmcu", values="k_patient_support")
        pivot_cache[cache_key] = piv
    value, status = _lookup_pivot(piv, kvp, cu)
    al_clamped = al_snap != round(al)
    return value, STATUS_CLAMPED if (al_clamped or status == STATUS_CLAMPED) else status


def _lookup_pivot(pivot: pd.DataFrame, kvp: float, cu: float) -> tuple[float, str]:
    """Look up a correction value from a pivot table with 2D/degenerate handling."""
    cu_axis = pivot.columns.to_numpy(dtype=float)
    kv_axis = pivot.index.to_numpy(dtype=float)
    if len(cu_axis) < 2:
        return _lookup_single_cu(pivot, kv_axis, cu_axis, kvp, cu)
    if len(kv_axis) < 2:
        return _lookup_single_kvp(pivot, kv_axis, cu_axis, kvp, cu)
    interpolator = RegularGridInterpolator((kv_axis, cu_axis), pivot.to_numpy(dtype=float))
    return clamped_rgi_lookup(interpolator, kv_axis, cu_axis, kvp, cu)


def _lookup_single_kvp(
    pivot: pd.DataFrame, kv_axis: np.ndarray, cu_axis: np.ndarray, kvp: float, cu: float
) -> tuple[float, str]:
    """Interpolate the copper axis when the table has one kVp row."""
    kvp_node = kv_axis[0]
    cu_node = float(np.clip(cu, cu_axis[0], cu_axis[-1]))
    value = float(np.interp(cu_node, cu_axis, pivot.to_numpy(dtype=float)[0, :]))
    if kvp_node != round(kvp) or cu_node != cu:
        return value, STATUS_CLAMPED
    if bool(np.any(np.isclose(cu_axis, cu_node))):
        return value, STATUS_EXACT
    return value, STATUS_INTERPOLATED


def _lookup_single_cu(
    pivot: pd.DataFrame, kv_axis: np.ndarray, cu_axis: np.ndarray, kvp: float, cu: float
) -> tuple[float, str]:
    """Interpolate the kVp axis when the table has one copper column."""
    kvp_node = float(np.clip(round(kvp), kv_axis[0], kv_axis[-1]))
    value = float(np.interp(kvp_node, kv_axis, pivot.to_numpy(dtype=float)[:, 0]))
    cu_node = cu_axis[0] if len(cu_axis) > 0 else 0.0
    status = STATUS_CLAMPED if (kvp_node != round(kvp) or cu != cu_node) else STATUS_EXACT
    return value, status



def _log_k_tab_warnings(
    n: int,
    no_device: list[int],
    interpolated: list[int],
    clamped: list[int],
) -> None:
    """Emit the three per-class k_tab WARNING summaries (no_device / interpolated /
    clamped). Message strings are pinned by ``test_corrections.py`` and the golden
    status classification — do not paraphrase."""
    if no_device:
        logger.warning(
            "k_tab: %d of %d event(s) had no table-attenuation data for their "
            "device model / acquisition plane and fall back to k_tab=1.0 (no table "
            "correction). Affected event index(es): %s.",
            len(no_device), n, format_event_indices(no_device),
        )
    if interpolated:
        logger.warning(
            "k_tab: %d of %d event(s) had a beam quality between tabulated grid "
            "points and were linearly interpolated. Affected event index(es): %s.",
            len(interpolated), n, format_event_indices(interpolated),
        )
    if clamped:
        logger.warning(
            "k_tab: %d of %d event(s) fell outside the tabulated grid and were "
            "clamped to the nearest edge. Affected event index(es): %s.",
            len(clamped), n, format_event_indices(clamped),
        )


def calculate_k_tab(
    data_norm: pd.DataFrame, corrections_db: str, estimate_k_tab: bool = False, k_tab_val: float = 0.8
) -> list[float]:
    """Fetch table correction factor from database.

    This function fetches measured table correction factor as a function of
    HVL and kVp. Further, if no measurement are conducted on a specific unit,
    the function can also return user specified estimated table correction.

    Parameters
    ----------
    data_norm : pd.DataFrame
        RDSR data, normalized for compliance with PySkinDose.
    estimate_k_tab: bool
        Set to True to use estimated table correction, default is False.
    k_tab_val: float
        Value of estimated table corrections, must be in range (0, 1).
    corrections_db : str
        A string defining the path to the corrections SQLite db

    Returns
    -------
    List[float]
        List of table correction factor for all events in procedure.

    """
    if estimate_k_tab:
        return [k_tab_val] * len(data_norm)

    # Load the whole attenuation table once, then resolve each event in pandas.
    # The historical implementation did an exact-match SQL lookup ending in
    # ``c.fetchone()[0]`` — ``None[0]`` raised TypeError and aborted the entire
    # calculation on any off-grid (kVp, Cu, Al) tuple or unknown device/plane
    # (e.g. a non-Siemens/Philips export). We keep exact match as the primary path
    # (so in-table events are unchanged) but fail soft and interpolate otherwise.
    # See dev-docs/plans/archive/hvl-interpolation-and-below-floor-kvp.md.
    conn = db_connect(db_name=corrections_db)[0]
    tab = pd.read_sql_query("SELECT * FROM correction_table_and_pad_attenuation", conn)
    conn.commit()
    conn.close()

    k_tab = [1.0] * len(data_norm)
    no_device_events: list[int] = []
    interpolated_events: list[int] = []
    clamped_events: list[int] = []

    # Cache the (kVp × Cu) pivot per (device, plane, Al) slice — built only when an
    # off-grid event actually needs interpolation (exact matches skip it).
    pivot_cache: dict[tuple[str, str, float], pd.DataFrame] = {}

    for event in range(len(data_norm)):
        model = str(data_norm.model[event])
        plane = data_norm.acquisition_plane[event]
        kvp = float(data_norm.kVp[event])
        cu = float(data_norm.filter_thickness_Cu[event])
        al = float(data_norm.filter_thickness_Al[event])

        # Match the device the same way the old SQL did: model or its de-spaced form.
        rows = _match_device_rows(tab, model, plane)
        if len(rows) == 0:
            # Unknown device/plane — no measured correction. Fail soft to k_tab=1.0
            # (no table attenuation) rather than crashing.
            no_device_events.append(event)
            continue

        # Exact match first (bit-for-bit parity with the historical lookup).
        exact = rows[
            (rows["kvp_kv"] == round(kvp))
            & (rows["filtration_added_mmcu"] == cu)
            & (rows["filtration_added_mmal"] == round(al))
        ]
        if len(exact):
            k_tab[event] = float(cast(pd.Series, exact["k_patient_support"]).iloc[0])
            continue

        # Off-grid within this device/plane: snap Al, then interpolate over (kVp,
        # Cu) with edge clamping.
        value, status = _interpolate_off_grid(rows, model, plane, kvp, cu, al, pivot_cache)
        k_tab[event] = value

        if status == STATUS_CLAMPED:
            clamped_events.append(event)
        elif status == STATUS_INTERPOLATED:
            interpolated_events.append(event)

    _log_k_tab_warnings(len(data_norm), no_device_events, interpolated_events, clamped_events)

    return k_tab
