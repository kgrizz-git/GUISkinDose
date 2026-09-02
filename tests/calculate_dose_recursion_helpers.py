"""Helpers for recursion-to-iteration refactor tests.

Builds synthetic normalized event tables for stress tests. ``new_geometry`` is
not a DataFrame column — it is derived at runtime by
:func:`guiskindose.geom_calc.check_new_geometry` from geometry columns, so
synthetic rows vary ``Tx`` / ``Ap1`` (and related fields) to simulate C-arm
repositioning between events.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pydicom

from guiskindose import get_path_to_example_rdsr_files, load_settings_example_json
from guiskindose.helpers.calculate_rotation_matrices import calculate_rotation_matrices
from guiskindose.rdsr_normalizer import rdsr_normalizer
from guiskindose.rdsr_parser import rdsr_parser
from guiskindose.settings import PyskindoseSettings

_SIEMENS_RDSR = get_path_to_example_rdsr_files() / "siemens_axiom_artis.dcm"


def generate_synthetic_normalized_events(
    n_events: int,
    *,
    seed: int = 42,
    geometry_change_fraction: float = 0.3,
) -> pd.DataFrame:
    """Return a normalized DataFrame with ``n_events`` irradiation events.

    Clones the first row of ``siemens_axiom_artis.dcm`` and perturbs geometry on
    roughly ``geometry_change_fraction`` of subsequent rows so
    ``check_new_geometry()`` yields a mix of True/False flags (not all-False,
    which would produce zero dose).
    """
    if n_events < 1:
        raise ValueError("n_events must be >= 1")

    base = load_settings_example_json()
    base["silence_pydicom_warnings"] = True
    settings = PyskindoseSettings(settings=base)
    parsed = rdsr_parser(pydicom.dcmread(str(_SIEMENS_RDSR)), silence_pydicom_warnings=True)
    template_row = rdsr_normalizer(parsed, settings=settings).iloc[0:1].copy()
    df = pd.concat([template_row.copy() for _ in range(n_events)], ignore_index=True)

    rng = np.random.default_rng(seed)
    for i in range(1, n_events):
        if rng.random() < geometry_change_fraction:
            df.at[i, "Tx"] = float(df.at[i - 1, "Tx"]) + float(rng.uniform(-2.0, 2.0))
            df.at[i, "Ap1"] = float(df.at[i - 1, "Ap1"]) + float(rng.uniform(-5.0, 5.0))

    return calculate_rotation_matrices(df)
