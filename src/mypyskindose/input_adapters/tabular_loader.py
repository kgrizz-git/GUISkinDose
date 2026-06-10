"""Low-level file readers for CSV, TSV, and XLSX.

All functions return the raw DataFrame with header=None (every row included,
all values as str/object). Callers are responsible for header detection,
column mapping, and type coercion.

Each function also returns encoding/delimiter metadata needed for provenance.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

_ENCODINGS = ("utf-8-sig", "utf-8", "cp1252", "latin-1")


@dataclass
class _RawLoad:
    raw_df: pd.DataFrame
    encoding: str
    delimiter: str | None  # None for xlsx


def _sniff_delimiter(path: Path, encoding: str) -> str:
    with path.open(encoding=encoding, newline="", errors="replace") as f:
        sample = f.read(8192)
    sniffer = csv.Sniffer()
    try:
        dialect = sniffer.sniff(sample, delimiters=",;\t|")
        return dialect.delimiter
    except csv.Error:
        return ","


def _try_read_csv(path: Path, delimiter: str, encoding: str) -> pd.DataFrame:
    return pd.read_csv(
        path,
        sep=delimiter,
        header=None,
        dtype=str,
        encoding=encoding,
        keep_default_na=False,
        skip_blank_lines=False,
    )


def read_csv(path: Path | str) -> _RawLoad:
    """Read a CSV file with encoding fallback and delimiter sniffing."""
    path = Path(path)
    last_exc: Exception = RuntimeError("No encodings tried")

    for enc in _ENCODINGS:
        try:
            delimiter = _sniff_delimiter(path, enc)
            raw_df = _try_read_csv(path, delimiter, enc)
            return _RawLoad(raw_df=raw_df, encoding=enc, delimiter=delimiter)
        except UnicodeDecodeError as exc:
            last_exc = exc
        except Exception as exc:
            last_exc = exc
            break

    raise ValueError(f"Could not read {path.name!r} with any supported encoding") from last_exc


def read_tsv(path: Path | str) -> _RawLoad:
    """Read a TSV file with encoding fallback (tab delimiter assumed)."""
    path = Path(path)
    last_exc: Exception = RuntimeError("No encodings tried")

    for enc in _ENCODINGS:
        try:
            raw_df = _try_read_csv(path, "\t", enc)
            return _RawLoad(raw_df=raw_df, encoding=enc, delimiter="\t")
        except UnicodeDecodeError as exc:
            last_exc = exc
        except Exception as exc:
            last_exc = exc
            break

    raise ValueError(f"Could not read {path.name!r} with any supported encoding") from last_exc


def read_excel(path: Path | str, sheet_name: str | int = 0) -> _RawLoad:
    """Read an XLSX/XLSM file with header=None so all rows are returned."""
    path = Path(path)
    raw_df = pd.read_excel(
        path,
        sheet_name=sheet_name,
        header=None,
        dtype=object,
        keep_default_na=False,
    )
    # Coerce every cell to str (openpyxl returns mixed types)
    raw_df = raw_df.map(lambda x: "" if pd.isna(x) else str(x))  # type: ignore[operator]
    return _RawLoad(raw_df=raw_df, encoding="utf-8", delimiter=None)


def load(
    path: Path | str,
    sheet_name: str | int = 0,
) -> _RawLoad:
    """Dispatch to the correct reader based on file suffix."""
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return read_csv(path)
    if suffix == ".tsv":
        return read_tsv(path)
    if suffix in (".xlsx", ".xlsm"):
        return read_excel(path, sheet_name=sheet_name)
    raise ValueError(
        f"Unsupported file suffix {suffix!r}. "
        "Tabular adapter handles .csv, .tsv, .xlsx, .xlsm."
    )
