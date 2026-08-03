"""Neutralize attacker-controlled strings before spreadsheet export.

RDSR and tabular inputs can carry arbitrary text that becomes dynamic DataFrame
columns. Prefixing formula-trigger characters with a single quote prevents Excel,
LibreOffice, and similar tools from evaluating CSV/XLSX cell contents as formulas
(CWE-1236). The same rules apply to column names and index labels, which exporters
write as header cells.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

_DANGEROUS_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def neutralize_spreadsheet_value(value: Any) -> Any:
    """Return *value* safe to write into a CSV/XLSX/TXT spreadsheet cell."""
    if not isinstance(value, str) or not value:
        return value
    if value[0] in _DANGEROUS_PREFIXES:
        return "'" + value
    return value


def _neutralize_label(label: Any) -> Any:
    """Neutralize a column or index label (including MultiIndex tuple parts)."""
    if isinstance(label, tuple):
        return tuple(neutralize_spreadsheet_value(part) for part in label)
    return neutralize_spreadsheet_value(label)


def neutralize_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy of *df* with values, column names, and index labels neutralized.

    Cell values in string/object columns are neutralized, and so are column names
    and index labels (including the index name). Callers that export with
    ``index=True`` must use this helper so formula-shaped headers cannot become
    live Excel formulas (``data_type='f'``).
    """
    out = df.copy()
    out.columns = [_neutralize_label(col) for col in out.columns]

    if out.index.nlevels == 1:
        names = _neutralize_label(out.index.name)
        if pd.api.types.is_string_dtype(out.index.dtype) or out.index.dtype == object:
            out.index = pd.Index(
                [neutralize_spreadsheet_value(value) for value in out.index],
                name=names,
            )
        else:
            out.index = out.index.set_names(names)
    else:
        out.index = out.index.set_names([_neutralize_label(name) for name in out.index.names])
        neutralized_tuples = [
            tuple(neutralize_spreadsheet_value(part) for part in levels) for levels in out.index
        ]
        out.index = pd.MultiIndex.from_tuples(neutralized_tuples, names=out.index.names)

    for col in out.columns:
        if pd.api.types.is_string_dtype(out[col]) or pd.api.types.is_object_dtype(out[col]):
            out[col] = out[col].map(neutralize_spreadsheet_value)
    return out
