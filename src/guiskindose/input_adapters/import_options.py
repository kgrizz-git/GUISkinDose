"""Post-normalization tabular import coordinate overrides (GUI/CLI parity).

Purpose: apply expert coordinate-correction flags to an internal event DataFrame
after adapter normalization — Tx↔Tz swap, Ap1 negation, Ap2 negation.

Inputs: a pandas DataFrame in GUISkinDose internal column convention, the
adapter ``schema_name`` string, and a :class:`TabularImportOptions` instance
(or ``None`` for identity).

Outputs: a new DataFrame copy with selected transforms applied; the input frame
is never mutated.

Requirements: pandas only; no dependency on the optional GUI extra.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class TabularImportOptions:
    """Expert post-normalization coordinate overrides for tabular imports."""

    swap_lat_lon: bool = False
    flip_ap1: bool = False
    flip_ap2: bool = False

    def any_set(self) -> bool:
        """True if any override flag is enabled."""
        return self.swap_lat_lon or self.flip_ap1 or self.flip_ap2


def _swap_tx_tz(df: pd.DataFrame) -> None:
    """In-place swap Tx/Tz when both columns are present (copy-safe assignment)."""
    if "Tx" in df.columns and "Tz" in df.columns:
        df["Tx"], df["Tz"] = df["Tz"].copy(), df["Tx"].copy()


def apply_tabular_import_coordinate_options(
    df: pd.DataFrame,
    schema_name: str,
    options: TabularImportOptions | None,
) -> pd.DataFrame:
    """Return a copy of ``df`` with tabular import coordinate options applied.

    Tx↔Tz swap runs only when ``options.swap_lat_lon`` is true, ``schema_name``
    is not ``normalized``, and both ``Tx`` and ``Tz`` exist. ``Ap1`` / ``Ap2``
    are negated when the corresponding flip flag is true and the column exists.

    ``None`` or all-false options yield numeric identity on a fresh copy; the
    input frame is unchanged.
    """
    out = df.copy()
    if options is None or not options.any_set():
        return out

    if options.swap_lat_lon and schema_name != "normalized":
        _swap_tx_tz(out)
    if options.flip_ap1 and "Ap1" in out.columns:
        out["Ap1"] = -out["Ap1"]
    if options.flip_ap2 and "Ap2" in out.columns:
        out["Ap2"] = -out["Ap2"]
    return out
