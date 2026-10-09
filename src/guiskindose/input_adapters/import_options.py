"""Post-normalization tabular import coordinate overrides (GUI/CLI parity).

Apply expert Tx↔Tz swap and Ap1/Ap2 negation to an internal event DataFrame
after adapter normalization. ``None`` or all-false options are a numeric identity
on a copy; the input frame is never mutated. Also owns tabular suffix checks and
value-safe CLI rejection messages. No optional GUI extra.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from guiskindose.privacy import UserFacingInputError

TABULAR_SUFFIXES = frozenset({".csv", ".tsv", ".xlsx", ".xlsm"})

IMPORT_OPTIONS_NON_TABULAR_MESSAGE = (
    "Coordinate import flags (--swap-lat-lon, --flip-ap1, --flip-ap2) apply only to "
    "tabular inputs (.csv, .tsv, .xlsx, .xlsm)."
)
PREVIEW_NON_TABULAR_MESSAGE = "Input preview applies only to tabular inputs (.csv, .tsv, .xlsx, .xlsm)."
PREVIEW_AGGREGATE_MESSAGE = "--input-preview-only cannot be combined with --aggregate."
GUI_IMPORT_OPTIONS_MESSAGE = (
    "Coordinate import flags (--swap-lat-lon, --flip-ap1, --flip-ap2) apply only to "
    "headless tabular runs, not --mode gui."
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


def reject_non_tabular_paths(paths: Sequence[str | Path], message: str) -> None:
    """Raise ``UserFacingInputError`` when any path suffix is not tabular.

    Uses suffix only (case-insensitive); does not open or stat files.
    """
    for path in paths:
        if Path(path).suffix.lower() not in TABULAR_SUFFIXES:
            raise UserFacingInputError(message)


def reject_import_options_for_non_tabular(
    paths: Sequence[str | Path],
    options: TabularImportOptions | None,
) -> None:
    """Raise when coordinate import flags are set for a non-tabular path suffix."""
    if options is None or not options.any_set():
        return
    reject_non_tabular_paths(paths, IMPORT_OPTIONS_NON_TABULAR_MESSAGE)


def coordinate_override_preview_line(
    options: TabularImportOptions | None,
    schema_name: str | None = None,
) -> str | None:
    """Return a value-safe preview line naming applied and skipped flags.

    ``swap_lat_lon`` is listed as skipped when ``schema_name`` is ``normalized``.
    ``None`` or all-false options yield ``None``.
    """
    if options is None or not options.any_set():
        return None
    applied: list[str] = []
    skipped: list[str] = []
    if options.swap_lat_lon:
        if schema_name == "normalized":
            skipped.append("swap_lat_lon")
        else:
            applied.append("swap_lat_lon")
    if options.flip_ap1:
        applied.append("flip_ap1")
    if options.flip_ap2:
        applied.append("flip_ap2")
    parts: list[str] = []
    if applied:
        parts.append(f"Coordinate overrides applied: {', '.join(applied)}")
    if skipped:
        parts.append(f"Coordinate overrides skipped for normalized schema: {', '.join(skipped)}")
    return "; ".join(parts) if parts else None


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
