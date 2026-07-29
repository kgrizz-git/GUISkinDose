"""Route tabular input files to the correct schema adapter."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Literal, overload

import pandas as pd

from mypyskindose.input_adapters import dosetrack as dosetrack_adapter
from mypyskindose.input_adapters import generic_rdsr as generic_rdsr_adapter
from mypyskindose.input_adapters import normalized as normalized_adapter
from mypyskindose.input_adapters import radimetrics as radimetrics_adapter
from mypyskindose.input_adapters import stubs
from mypyskindose.input_adapters.column_mapper import _normalize_str, detect_header_row
from mypyskindose.input_adapters.dosetrack import DOSETRACK_COLUMN_NAMES
from mypyskindose.input_adapters.generic_rdsr import GENERIC_RDSR_COLUMN_NAMES
from mypyskindose.input_adapters.models import InputAdapterResult
from mypyskindose.input_adapters.normalized import NORMALIZED_HEADER_NAMES
from mypyskindose.input_adapters.radimetrics import RADIMETRICS_COLUMN_NAMES
from mypyskindose.input_adapters.tabular_loader import _RawLoad, load

if TYPE_CHECKING:
    from mypyskindose.settings import PyskindoseSettings

class SchemaDetectionError(ValueError):
    """Auto-detection could not pick a schema (no match, or an ambiguous tie).

    Subclasses ValueError so existing ``except ValueError`` / ``pytest.raises``
    callers keep working, while callers that want to distinguish "couldn't guess
    the format" from a genuine parse error (e.g. the GUI, to show a friendly
    "choose a schema" hint instead of a traceback) can catch this specifically.
    """


_TABULAR_SUFFIXES = frozenset({".csv", ".tsv", ".xlsx", ".xlsm"})
# Schemas marked (stub) are wired for explicit selection but raise NotImplementedError
# until a real export fixture is available to build the column map.
_SUPPORTED_SCHEMAS = (
    "normalized",
    "generic_rdsr_like",
    "radimetrics",
    "dosetrack",
    "qaelum",      # stub — needs real export fixture
    "dosemonitor", # stub — needs real export fixture
    "dosewatch",   # stub — needs real export fixture
    "auto",
)
_AUTO_MIN_MARGIN = 0.20  # required score gap between best and runner-up

# Ordered list of (schema_name, known_names) used for auto-detection scoring.
_SCHEMA_KNOWN_NAMES: list[tuple[str, frozenset[str]]] = [
    ("normalized", NORMALIZED_HEADER_NAMES),
    ("generic_rdsr_like", GENERIC_RDSR_COLUMN_NAMES),
    ("radimetrics", RADIMETRICS_COLUMN_NAMES),
    ("dosetrack", DOSETRACK_COLUMN_NAMES),
]


def _score_schema(raw_df: pd.DataFrame, known_names: frozenset[str]) -> float:
    """Return how well *known_names* match the best header row in *raw_df*.

    Score is *recall*: the fraction of the schema's known column names that are
    present in the header row (matched / len(known_names)) — not the fraction of
    header cells that are known. Recall is robust to wide exports: a real
    Radimetrics CSV has ~87 columns of which 13 are recognised, a poor precision
    (13/87 ≈ 0.15) but a perfect recall (13/13 = 1.0). Precision scaled with file
    width and made wide exports look ambiguous against any schema that matched a
    single stray column; recall gives the correct schema ~1.0 and the rest ~0.
    """
    try:
        idx = detect_header_row(raw_df, known_names, min_score=1)
    except ValueError:
        return 0.0
    if not known_names:
        return 0.0
    # Normalize both sides with _normalize_str (the same collapse of "_"/"-"/
    # whitespace used by detect_header_row and map_columns) so underscored older
    # exports compare equal to their spaced counterparts.
    row = raw_df.iloc[idx]
    cells = {_normalize_str(str(c)) for c in row if pd.notna(c) and str(c).strip()}
    known_norm = {_normalize_str(k) for k in known_names}
    return sum(1 for k in known_norm if k in cells) / len(known_norm)


def _detect_schema(loaded: _RawLoad) -> str:
    """Score each schema and return the best match name.

    Raises ValueError if no schema clears a minimum threshold or if the two
    top schemas are within _AUTO_MIN_MARGIN of each other.
    """
    scores = {name: _score_schema(loaded.raw_df, known) for name, known in _SCHEMA_KNOWN_NAMES}

    if not max(scores.values()):
        raise SchemaDetectionError(
            "Schema auto-detection: no schema could be matched. "
            f"Scores: {scores}. Pass --input-schema explicitly."
        )

    sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    best_name, best_score = sorted_scores[0]

    # Margin check only applies when ≥2 schemas scored above zero.
    # If only one schema scored, it wins unambiguously regardless of the absolute score.
    non_zero = [(n, s) for n, s in sorted_scores if s > 0.0]
    if len(non_zero) > 1:
        _, runner_up_score = non_zero[1]
        if best_score - runner_up_score < _AUTO_MIN_MARGIN:
            raise SchemaDetectionError(
                f"Schema auto-detection is ambiguous (scores: {scores}). "
                "Pass --input-schema explicitly."
            )

    return best_name


def _dispatch_to_adapter(
    schema: str,
    loaded: _RawLoad,
    path: Path,
    settings: PyskindoseSettings | None,
) -> InputAdapterResult | list[InputAdapterResult]:
    """Run the adapter selected for *schema* and return its result.

    Validates the per-schema ``settings`` requirement (the vendor adapters need
    a PyskindoseSettings for manufacturer/model lookup) and dispatches to the
    matching adapter's ``adapt``. Stub vendors raise NotImplementedError with
    implementation guidance; an unrecognised schema raises ValueError.
    """
    if schema == "normalized":
        return normalized_adapter.adapt(loaded, original_filename=path.name)
    if schema in ("generic_rdsr_like", "radimetrics", "dosetrack"):
        if settings is None:
            raise ValueError(
                f"settings is required for {schema} schema "
                "(needed by rdsr_normalizer for manufacturer/model lookup)."
            )
        if schema == "generic_rdsr_like":
            return generic_rdsr_adapter.adapt(loaded, original_filename=path.name, settings=settings)
        if schema == "radimetrics":
            return radimetrics_adapter.adapt(loaded, original_filename=path.name, settings=settings)
        return dosetrack_adapter.adapt(loaded, original_filename=path.name, settings=settings)
    if schema in stubs.STUB_VENDORS:
        stubs.raise_not_implemented(schema)
    raise ValueError(
        f"Unknown schema {schema!r}. Supported: {_SUPPORTED_SCHEMAS!r}."
    )


@overload
def read_and_normalize_input(
    file_path: str | Path,
    *,
    input_schema: Literal[
        "generic_rdsr_like", "radimetrics", "dosetrack",
        "qaelum", "dosemonitor", "dosewatch",
    ],
    sheet_name: str | int = ...,
    settings: PyskindoseSettings | None = ...,
) -> InputAdapterResult:
    """Load and normalize a known vendor tabular schema (overload)."""
    ...

@overload
def read_and_normalize_input(
    file_path: str | Path,
    *,
    input_schema: Literal["normalized", "auto"] | None = ...,
    sheet_name: str | int = ...,
    settings: PyskindoseSettings | None = ...,
) -> InputAdapterResult | list[InputAdapterResult]:
    """Load and normalize a normalized/auto tabular schema (overload)."""
    ...

@overload
def read_and_normalize_input(
    file_path: str | Path,
    *,
    input_schema: str | None = ...,
    sheet_name: str | int = ...,
    settings: PyskindoseSettings | None = ...,
) -> InputAdapterResult | list[InputAdapterResult]:
    """Load and normalize a tabular input file (overload)."""
    ...

def read_and_normalize_input(
    file_path: str | Path,
    *,
    input_schema: str | None = None,
    sheet_name: str | int = 0,
    settings: PyskindoseSettings | None = None,
) -> InputAdapterResult | list[InputAdapterResult]:
    """Load a tabular file and return a normalized InputAdapterResult.

    Returns a list when the file contains multiple study identifiers and the
    selected adapter supports splitting (currently: ``"normalized"`` schema).
    Callers must handle both the single and list cases.

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

    result = _dispatch_to_adapter(schema, loaded, path, settings)

    # Propagate sheet_name into provenance for Excel files
    if suffix in (".xlsx", ".xlsm"):
        if isinstance(result, list):
            for r in result:
                r.provenance.sheet_name = sheet_name
        else:
            result.provenance.sheet_name = sheet_name

    return result
