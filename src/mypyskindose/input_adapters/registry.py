"""Route tabular input files to the correct schema adapter."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd

from mypyskindose.input_adapters import generic_rdsr as generic_rdsr_adapter
from mypyskindose.input_adapters import normalized as normalized_adapter
from mypyskindose.input_adapters.column_mapper import (
    GENERIC_RDSR_COLUMN_NAMES,
    NORMALIZED_COLUMN_NAMES,
    detect_header_row,
)
from mypyskindose.input_adapters.models import InputAdapterResult
from mypyskindose.input_adapters.tabular_loader import _RawLoad, load

if TYPE_CHECKING:
    from mypyskindose.settings import PyskindoseSettings

_TABULAR_SUFFIXES = frozenset({".csv", ".tsv", ".xlsx", ".xlsm"})
_SUPPORTED_SCHEMAS = ("normalized", "generic_rdsr_like", "auto")
_AUTO_MIN_MARGIN = 0.20  # required score gap between best and runner-up

# Ordered list of (schema_name, known_names) used for auto-detection scoring.
_SCHEMA_KNOWN_NAMES: list[tuple[str, frozenset[str]]] = [
    ("normalized", NORMALIZED_COLUMN_NAMES),
    ("generic_rdsr_like", GENERIC_RDSR_COLUMN_NAMES),
]


def _score_schema(raw_df: pd.DataFrame, known_names: frozenset[str]) -> float:
    """Return the header-row match score for *known_names* against *raw_df*."""
    try:
        idx = detect_header_row(raw_df, known_names, min_score=0.05)
    except ValueError:
        return 0.0
    row = raw_df.iloc[idx]
    cells = [str(c).strip().lower() for c in row if pd.notna(c) and str(c).strip()]
    if not cells:
        return 0.0
    return sum(1 for c in cells if c in known_names) / len(cells)


def _detect_schema(loaded: _RawLoad) -> str:
    """Score each schema and return the best match name.

    Raises ValueError if no schema clears a minimum threshold or if the two
    top schemas are within _AUTO_MIN_MARGIN of each other.
    """
    scores = {name: _score_schema(loaded.raw_df, known) for name, known in _SCHEMA_KNOWN_NAMES}

    if max(scores.values()) == 0.0:
        raise ValueError(
            "Schema auto-detection: no schema could be matched. "
            f"Scores: {scores}. Pass --input-schema explicitly."
        )

    sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    best_name, best_score = sorted_scores[0]

    if len(sorted_scores) > 1:
        _, runner_up_score = sorted_scores[1]
        if best_score - runner_up_score < _AUTO_MIN_MARGIN:
            raise ValueError(
                f"Schema auto-detection is ambiguous (scores: {scores}). "
                "Pass --input-schema explicitly."
            )

    return best_name


def read_and_normalize_input(
    file_path: str | Path,
    *,
    input_schema: str | None = None,
    sheet_name: str | int = 0,
    settings: PyskindoseSettings | None = None,
) -> InputAdapterResult:
    """Load a tabular file and return a normalized InputAdapterResult.

    Parameters
    ----------
    file_path:
        Path to a .csv, .tsv, .xlsx, or .xlsm file.
    input_schema:
        Which schema adapter to use. ``None`` defaults to ``"normalized"``.
        Use ``"auto"`` to score each known schema and pick the best match
        (requires a clear margin; raises ValueError if ambiguous).
    sheet_name:
        Sheet name or 0-based index for Excel files (ignored for CSV/TSV).
    settings:
        Required when *input_schema* is ``"generic_rdsr_like"`` or when
        ``"auto"`` resolves to that schema.

    Raises
    ------
    ValueError
        On unsupported suffix, unknown schema, ambiguous auto-detection, or
        data validation failures from the selected adapter.
    """
    path = Path(file_path)
    suffix = path.suffix.lower()

    if suffix not in _TABULAR_SUFFIXES:
        raise ValueError(
            f"Unsupported suffix {suffix!r}. "
            "The tabular adapter handles .csv, .tsv, .xlsx, .xlsm. "
            "For DICOM RDSR or JSON use read_and_normalise_rdsr_data()."
        )

    loaded = load(path, sheet_name=sheet_name)

    schema = input_schema or "normalized"

    if schema == "auto":
        schema = _detect_schema(loaded)

    if schema == "normalized":
        result = normalized_adapter.adapt(loaded, original_filename=path.name)
    elif schema == "generic_rdsr_like":
        if settings is None:
            raise ValueError(
                "settings is required for generic_rdsr_like schema "
                "(needed by rdsr_normalizer for manufacturer/model lookup)."
            )
        result = generic_rdsr_adapter.adapt(loaded, original_filename=path.name, settings=settings)
    else:
        raise ValueError(
            f"Unknown schema {schema!r}. Supported: {_SUPPORTED_SCHEMAS!r}."
        )

    # Propagate sheet_name into provenance for Excel files
    if suffix in (".xlsx", ".xlsm"):
        result.provenance.sheet_name = sheet_name

    return result
