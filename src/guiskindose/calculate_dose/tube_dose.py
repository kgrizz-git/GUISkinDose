"""Per-tube dose accounting beside the combined dose map.

Each event belongs to one tube (``single`` / ``A`` / ``B`` / ``unknown``). The
combined dose map stays the sum over every event, and the headline peak skin dose
stays the peak of that combined map. When more than one tube is present, one
partial map per present tube is accumulated as well, so the partial maps sum
cellwise to the combined map. With a single tube the partial map would equal the
combined one, so none is allocated and the combined map is used for its peak.

Per-tube peaks are maxima of different maps. They do not, in general, sum to the
headline peak skin dose.

Privacy: outputs carry tube identities only, never equipment labels.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from guiskindose import constants as c
from guiskindose.kerma_correction import resolve_correction_keys

# Stable display order.
TUBE_ORDER = ("single", "A", "B", c.TUBE_IDENTITY_UNKNOWN)


def tube_identities(normalized_data: pd.DataFrame) -> list[str]:
    """Return the tube (``single`` / ``A`` / ``B`` / ``unknown``) of every event.

    Uses the same identity rules as kerma-meter correction (CID 10003 canonical
    plane first, then the plane meaning text), independent of equipment labels.
    """
    return [tube for _, tube in resolve_correction_keys(normalized_data, explicit_label=None)]


def init_tube_outputs(output: dict[str, Any], tubes: list[str], n_cells: int) -> None:
    """Record per-event tubes and allocate partial maps for the tubes present.

    Parameters
    ----------
    output : dict[str, Any]
        Dose-loop output dict, modified in place.
    tubes : list[str]
        Tube of each event.
    n_cells : int
        Number of patient skin cells.
    """
    present = [t for t in TUBE_ORDER if t in set(tubes)]
    output[c.OUTPUT_KEY_TUBE_IDENTITY] = list(tubes)
    output[c.OUTPUT_KEY_TUBE_DOSE_MAPS] = {t: np.zeros(n_cells) for t in present} if len(present) > 1 else {}


def add_event_dose(output: dict[str, Any], event: int, dose_vector: np.ndarray) -> None:
    """Add one event's dose vector to the combined map and, if kept, its tube's map."""
    output[c.OUTPUT_KEY_DOSE_MAP] += dose_vector
    maps = output.get(c.OUTPUT_KEY_TUBE_DOSE_MAPS)
    tubes = output.get(c.OUTPUT_KEY_TUBE_IDENTITY)
    if maps and tubes is not None and event < len(tubes):
        partial = maps.get(tubes[event])
        if partial is not None:
            partial += dose_vector


def summarize_tubes(output: dict[str, Any]) -> list[dict[str, Any]]:
    """Per-tube reported kerma, corrected kerma, applied CF and partial-map peak.

    ``applied_cf`` is corrected over reported kerma, i.e. the kerma-weighted mean
    CF; for zero reported kerma it is the plain mean of the event CFs. ``cf_min`` /
    ``cf_max`` give the range of event CFs (equal when one factor was used) and
    ``cf_source`` is ``manual`` / ``file`` / ``default``, ``mixed`` when the tube's
    events used more than one source, or ``off`` when correction is disabled. A
    tube whose events all miss the phantom reports a peak of exactly 0.0.
    """
    tubes = output.get(c.OUTPUT_KEY_TUBE_IDENTITY) or []
    maps = output.get(c.OUTPUT_KEY_TUBE_DOSE_MAPS) or {}
    kerma = output[c.OUTPUT_KEY_KERMA]
    corrected = output[c.OUTPUT_KEY_KERMA_CORRECTED]
    meter = output[c.OUTPUT_KEY_CORRECTION_KERMA_METER]
    combined = output[c.OUTPUT_KEY_DOSE_MAP]
    sources = output.get(c.OUTPUT_KEY_KERMA_CF_SOURCES) or ["off"] * len(tubes)
    summary: list[dict[str, Any]] = []
    for tube in (t for t in TUBE_ORDER if t in set(tubes)):
        idx = [i for i, t in enumerate(tubes) if t == tube]
        reported = float(sum(kerma[i] for i in idx))
        corr = float(sum(corrected[i] for i in idx))
        cf = corr / reported if reported > 0 else float(np.mean([meter[i] for i in idx]))
        dose = maps.get(tube, combined)
        event_cfs = [float(meter[i]) for i in idx]
        tube_sources = {sources[i] for i in idx}
        summary.append(
            {
                "tube": tube,
                "events": len(idx),
                "kerma_reported": reported,
                "kerma_corrected": corr,
                "applied_cf": cf,
                "cf_min": min(event_cfs),
                "cf_max": max(event_cfs),
                "cf_source": tube_sources.pop() if len(tube_sources) == 1 else "mixed",
                "peak_dose": float(dose.max()) if dose.size else 0.0,
            }
        )
    return summary
