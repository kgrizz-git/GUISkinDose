"""Neutralize attacker-controlled strings before spreadsheet export.

RDSR and tabular inputs can carry arbitrary text that becomes dynamic DataFrame
columns. Prefixing formula-trigger characters with a single quote prevents Excel,
LibreOffice, and similar tools from evaluating CSV/XLSX cell contents as formulas
(CWE-1236).
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


def neutralize_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy of *df* with string-column cell values neutralized for export."""
    out = df.copy()
    for col in out.columns:
        if pd.api.types.is_string_dtype(out[col]) or pd.api.types.is_object_dtype(out[col]):
            out[col] = out[col].map(neutralize_spreadsheet_value)
    return out
