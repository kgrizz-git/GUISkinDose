"""Post-normalization tabular import coordinate overrides (GUI/CLI parity).

Purpose: apply expert coordinate-correction flags to an internal event DataFrame
after adapter normalization — Tx↔Tz swap, Ap1 negation, Ap2 negation.

Inputs: a pandas DataFrame in GUISkinDose internal column convention, the
adapter ``schema_name`` string, and a :class:`TabularImportOptions` instance
(or ``None`` for identity).

Outputs: a new DataFrame copy with selected transforms applied; the input frame
is never mutated.

Requirements: pandas and ``UserFacingInputError`` for suffix rejection; no
optional GUI extra.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from guiskindose.privacy import UserFacingInputError

_TABULAR_SUFFIXES = frozenset({".csv", ".tsv", ".xlsx", ".xlsm"})

IMPORT_OPTIONS_NON_TABULAR_MESSAGE = (
    "Coordinate import flags (--swap-lat-lon, --flip-ap1, --flip-ap2) apply only to "
    "tabular inputs (.csv, .tsv, .xlsx, .xlsm)."
)


@dataclass(frozen=True)
class TabularImportOptions:
    """Expert post-normalization coordinate overrides for tabular imports."""

    swap_lat_lon: bool = False
    flip_ap1: bool = False
    flip_ap2: bool = False

    def any_set(self) -> bool:
        """True if any override flag is enabled."""
        return self.swap_lat_lon or self.flip_ap1 or self.flip_ap2


def reject_import_options_for_non_tabular(
    paths: Sequence[str | Path],
    options: TabularImportOptions | None,
) -> None:
    """Raise when coordinate import flags are set for a non-tabular path suffix.

    Uses suffix only (case-insensitive); does not open or stat files.
    """
    if options is None or not options.any_set():
        return
    for path in paths:
        if Path(path).suffix.lower() not in _TABULAR_SUFFIXES:
            raise UserFacingInputError(IMPORT_OPTIONS_NON_TABULAR_MESSAGE)


def coordinate_override_preview_line(options: TabularImportOptions | None) -> str | None:
    """Return a value-safe preview line naming enabled flags, or ``None`` if none."""
    if options is None or not options.any_set():
        return None
    names: list[str] = []
    if options.swap_lat_lon:
        names.append("swap_lat_lon")
    if options.flip_ap1:
        names.append("flip_ap1")
    if options.flip_ap2:
        names.append("flip_ap2")
    return f"Coordinate overrides applied: {', '.join(names)}"


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
