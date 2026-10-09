"""Route tabular input files to the correct schema adapter.

Auto-detection scores each known schema by header recall, then elects one only
when the header has a distinctive marker for that source and at least
``_AUTO_MIN_HITS`` of that source's known columns. One known column asks the
user to choose a schema. DICOM RDSR files
(``.dcm``) never reach this module. Qaelum, DoseMonitor, and DoseWatch can be
named explicitly and raise ``NotImplementedError``. The user-facing description
is ``docs/source/gui_help/input_formats.md``; the maintainer description is
``dev-docs/INPUT_SCHEMA_DETECTION.md``.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Literal, overload

import pandas as pd

from guiskindose.input_adapters import dosetrack as dosetrack_adapter
from guiskindose.input_adapters import generic_rdsr as generic_rdsr_adapter
from guiskindose.input_adapters import normalized as normalized_adapter
from guiskindose.input_adapters import radimetrics as radimetrics_adapter
from guiskindose.input_adapters import stubs
from guiskindose.input_adapters.column_mapper import _normalize_str, detect_header_row
from guiskindose.input_adapters.dosetrack import DOSETRACK_COLUMN_NAMES
from guiskindose.input_adapters.generic_rdsr import GENERIC_RDSR_COLUMN_NAMES
from guiskindose.input_adapters.import_options import (
    TABULAR_SUFFIXES,
    TabularImportOptions,
    apply_tabular_import_coordinate_options,
)
from guiskindose.input_adapters.models import InputAdapterResult
from guiskindose.input_adapters.normalized import NORMALIZED_HEADER_NAMES
from guiskindose.input_adapters.radimetrics import RADIMETRICS_COLUMN_NAMES
from guiskindose.input_adapters.tabular_loader import _RawLoad, load

if TYPE_CHECKING:
    from guiskindose.settings import PyskindoseSettings


class SchemaDetectionError(ValueError):
    """Auto-detection could not pick a schema.

    Raised when no schema matches, when the only overlap is shared column names
    with no distinctive marker, when a marker is present but fewer than
    ``_AUTO_MIN_HITS`` known columns match, or when two eligible schemas are
    within ``_AUTO_MIN_MARGIN``. Subclasses ValueError so existing
    ``except ValueError`` / ``pytest.raises`` callers keep working. The GUI
    catches this specifically and asks the user to choose a schema instead of
    showing a traceback.
    """


# Schemas marked (stub) are wired for explicit selection but raise NotImplementedError
# until a real export fixture is available to build the column map.
_SUPPORTED_SCHEMAS = (
    "normalized",
    "generic_rdsr_like",
    "radimetrics",
    "dosetrack",
    "qaelum",  # stub — needs real export fixture
    "dosemonitor",  # stub — needs real export fixture
    "dosewatch",  # stub — needs real export fixture
    "auto",
)
_AUTO_MIN_MARGIN = 0.20  # required score gap between best and runner-up
_AUTO_MIN_HITS = 2  # known columns required before auto-detect elects a schema

# Ordered list of (schema_name, known_names) used for auto-detection scoring.
_SCHEMA_KNOWN_NAMES: list[tuple[str, frozenset[str]]] = [
    ("normalized", NORMALIZED_HEADER_NAMES),
    ("generic_rdsr_like", GENERIC_RDSR_COLUMN_NAMES),
    ("radimetrics", RADIMETRICS_COLUMN_NAMES),
    ("dosetrack", DOSETRACK_COLUMN_NAMES),
]

# Fingerprint names that must not elect a schema by themselves. They are common
# outside that export, or shared with another fingerprint, and still count
# toward recall. Radimetrics is omitted: its plain-English older-export names
# are most of the fingerprint, so eligibility is a trigger substring instead.
_TRIGGER_EXCLUSIONS: dict[str, frozenset[str]] = {
    "normalized": frozenset(
        {
            "model",
            "kvp",
            "acquisition_type",
            "acquisition_plane",
            "station_name",
            "stationname",
            "device_serial",
            "deviceserialnumber",
        }
    ),
    "generic_rdsr_like": frozenset({"manufacturer", "kvp_kv"}),
    "dosetrack": frozenset(
        {
            "air kerma (mgy)",
            "positioner primary angle (deg)",
            "positioner secondary angle (deg)",
            "distance source to detector (mm)",
            "distance source to isocenter (mm)",
            "table longitudinal position (mm)",
            "table lateral position (mm)",
            "table height position (mm)",
            "collimated field area (m2)",
            "filter material",
        }
    ),
}

# Markers for a Bayer Radimetrics header in the exports we have seen (older
# underscore form and newer bracketed units). "(rf)" is not a bare substring:
# the cell text through "(rf)" must be the start of a known Radimetrics column,
# so "Modality (RF)" does not count. "dap (total)" and "reference point dose
# (total)" still match as substrings. "device" and a bare "reference point dose"
# are not markers.
_RADIMETRICS_TRIGGER_SUBSTRINGS: frozenset[str] = frozenset(
    {
        "(rf)",
        "dap (total)",
        "reference point dose (total)",
    }
)


def _normalized_name_set(names: frozenset[str]) -> frozenset[str]:
    """Return *names* collapsed the same way header cells are compared."""
    return frozenset(_normalize_str(name) for name in names)


# Known Radimetrics columns that contain "(rf)". A header cell counts as an
# (rf) marker only when its text through "(rf)" is the start of one of these.
_RADIMETRICS_RF_COLUMNS: frozenset[str] = frozenset(
    name for name in _normalized_name_set(RADIMETRICS_COLUMN_NAMES) if "(rf)" in name
)


def _trigger_names(schema: str, known_names: frozenset[str]) -> frozenset[str]:
    """Fingerprint names that may elect *schema* after dropping shared or weak ones."""
    excluded = _normalized_name_set(_TRIGGER_EXCLUSIONS.get(schema, frozenset()))
    return _normalized_name_set(known_names) - excluded


_SCHEMA_TRIGGERS: dict[str, frozenset[str]] = {
    name: _trigger_names(name, known) for name, known in _SCHEMA_KNOWN_NAMES if name != "radimetrics"
}


def _header_cells(raw_df: pd.DataFrame, known_names: frozenset[str]) -> set[str]:
    """Return normalized cells of the best header row, or an empty set."""
    try:
        idx = detect_header_row(raw_df, known_names, min_score=1)
    except ValueError:
        return set()
    row = raw_df.iloc[idx]
    return {_normalize_str(str(cell)) for cell in row if pd.notna(cell) and str(cell).strip()}


def _hit_count(cells: set[str], known_names: frozenset[str]) -> int:
    """Return how many normalized *known_names* appear exactly in *cells*."""
    if not cells or not known_names:
        return 0
    known_norm = _normalized_name_set(known_names)
    return sum(1 for name in known_norm if name in cells)


def _recall(cells: set[str], known_names: frozenset[str]) -> float:
    """Return the fraction of *known_names* present in *cells*.

    Recall, not precision: a wide export that carries every known name plus
    dozens of unrelated columns still scores 1.0. Precision fell as the file
    got wider and made a full match look tied with a single stray column.
    """
    known_norm = _normalized_name_set(known_names)
    if not known_norm:
        return 0.0
    return _hit_count(cells, known_names) / len(known_norm)


def _score_schema(raw_df: pd.DataFrame, known_names: frozenset[str]) -> float:
    """Return how well *known_names* match the best header row in *raw_df*."""
    return _recall(_header_cells(raw_df, known_names), known_names)


def _rf_column_stem(cell: str) -> str | None:
    """Return *cell* through ``(rf)``, or None when that marker is absent.

    *cell* is already normalized. The stem is the column identity: ``primary
    angle (rf)`` from ``primary angle (rf) [°]``.
    """
    marker = "(rf)"
    end = cell.find(marker)
    if end < 0:
        return None
    return cell[: end + len(marker)].strip()


def _cell_matches_known_rf_column(cell: str) -> bool:
    """Return True when *cell* starts with a known Radimetrics ``(rf)`` column."""
    stem = _rf_column_stem(cell)
    if stem is None:
        return False
    return any(column.startswith(stem) for column in _RADIMETRICS_RF_COLUMNS)


def _cell_has_radimetrics_trigger(cell: str) -> bool:
    """Return True when *cell* is a Radimetrics-specific marker.

    ``(rf)`` counts only on a known Radimetrics column, so ``Modality (RF)``
    does not. ``dap (total)`` and ``reference point dose (total)`` still match
    as substrings, including when a unit follows them.
    """
    if _cell_matches_known_rf_column(cell):
        return True
    other_markers = _RADIMETRICS_TRIGGER_SUBSTRINGS - {"(rf)"}
    return any(token in cell for token in other_markers)


def _radimetrics_triggered(cells: set[str]) -> bool:
    """Return True when any header cell carries a Radimetrics marker."""
    return any(_cell_has_radimetrics_trigger(cell) for cell in cells)


def _is_triggered(name: str, cells: set[str]) -> bool:
    """Return True when *cells* are specific enough to elect *name*."""
    if name == "radimetrics":
        return _radimetrics_triggered(cells)
    return bool(cells & _SCHEMA_TRIGGERS[name])


def _schema_views(raw_df: pd.DataFrame) -> list[tuple[str, float, bool, int, bool]]:
    """Return (schema, recall, eligible, hits, triggered) for every scored schema.

    Eligible means the header has that schema's marker and at least
    ``_AUTO_MIN_HITS`` of its known columns. A marker alone is not eligible.
    """
    views: list[tuple[str, float, bool, int, bool]] = []
    for name, known in _SCHEMA_KNOWN_NAMES:
        cells = _header_cells(raw_df, known)
        hits = _hit_count(cells, known)
        triggered = _is_triggered(name, cells)
        eligible = triggered and hits >= _AUTO_MIN_HITS
        views.append((name, _recall(cells, known), eligible, hits, triggered))
    return views


def _no_schema_message(views: list[tuple[str, float, bool, int, bool]]) -> str:
    """Explain a failed auto-detection without echoing header text."""
    scores = {name: score for name, score, _eligible, _hits, _triggered in views}
    if not max(scores.values(), default=0):
        return f"Schema auto-detection: no schema could be matched. Scores: {scores}. Pass --input-schema explicitly."
    thin = [name for name, _score, _eligible, hits, triggered in views if triggered and hits < _AUTO_MIN_HITS]
    if thin:
        matched = ", ".join(thin)
        return (
            "Schema auto-detection: a distinctive marker matched "
            f"{matched}, but fewer than {_AUTO_MIN_HITS} known columns were present. "
            f"Scores: {scores}. Pass --input-schema explicitly."
        )
    return (
        "Schema auto-detection: headers overlapped known schemas but none had a "
        f"distinctive marker. Scores: {scores}. Pass --input-schema explicitly."
    )


def _detect_schema(loaded: _RawLoad) -> str:
    """Return the eligible schema with the best recall.

    A schema whose header only shares ordinary names (for example ``Device`` or
    ``kVp``) is not eligible, even if it is the only schema with a non-zero
    recall. A distinctive marker with fewer than ``_AUTO_MIN_HITS`` known
    columns is not eligible either; the caller asks the user to choose.
    Among eligible schemas, the leader must beat the runner-up by
    ``_AUTO_MIN_MARGIN``.

    Raises SchemaDetectionError when nothing is eligible or the top two
    eligible schemas are within the margin.
    """
    views = _schema_views(loaded.raw_df)
    scores = {name: score for name, score, _eligible, _hits, _triggered in views}
    eligible = [(name, score) for name, score, is_eligible, _hits, _triggered in views if is_eligible]
    if not eligible:
        raise SchemaDetectionError(_no_schema_message(views))

    eligible.sort(key=lambda item: item[1], reverse=True)
    best_name, best_score = eligible[0]
    if len(eligible) > 1 and best_score - eligible[1][1] < _AUTO_MIN_MARGIN:
        raise SchemaDetectionError(
            f"Schema auto-detection is ambiguous (scores: {scores}). Pass --input-schema explicitly."
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
                f"settings is required for {schema} schema (needed by rdsr_normalizer for manufacturer/model lookup)."
            )
        if schema == "generic_rdsr_like":
            return generic_rdsr_adapter.adapt(loaded, original_filename=path.name, settings=settings)
        if schema == "radimetrics":
            return radimetrics_adapter.adapt(loaded, original_filename=path.name, settings=settings)
        return dosetrack_adapter.adapt(loaded, original_filename=path.name, settings=settings)
    if schema in stubs.STUB_VENDORS:
        stubs.raise_not_implemented(schema)
    raise ValueError(f"Unknown schema {schema!r}. Supported: {_SUPPORTED_SCHEMAS!r}.")


def _apply_import_options_to_result(
    result: InputAdapterResult,
    import_options: TabularImportOptions | None,
) -> None:
    """Assign post-normalization coordinate overrides to one adapter result."""
    result.normalized_data = apply_tabular_import_coordinate_options(
        result.normalized_data,
        result.provenance.schema_name,
        import_options,
    )


def _apply_import_options_to_results(
    result: InputAdapterResult | list[InputAdapterResult],
    import_options: TabularImportOptions | None,
) -> InputAdapterResult | list[InputAdapterResult]:
    """Apply import options to a single result or each element of a multi-study list."""
    if isinstance(result, list):
        for item in result:
            _apply_import_options_to_result(item, import_options)
        return result
    _apply_import_options_to_result(result, import_options)
    return result


@overload
def read_and_normalize_input(
    file_path: str | Path,
    *,
    input_schema: Literal[
        "generic_rdsr_like",
        "radimetrics",
        "dosetrack",
        "qaelum",
        "dosemonitor",
        "dosewatch",
    ],
    sheet_name: str | int = ...,
    settings: PyskindoseSettings | None = ...,
    import_options: TabularImportOptions | None = ...,
) -> InputAdapterResult:
    """Load and normalize a known vendor tabular schema (overload)."""


@overload
def read_and_normalize_input(
    file_path: str | Path,
    *,
    input_schema: Literal["normalized", "auto"] | None = ...,
    sheet_name: str | int = ...,
    settings: PyskindoseSettings | None = ...,
    import_options: TabularImportOptions | None = ...,
) -> InputAdapterResult | list[InputAdapterResult]:
    """Load and normalize a normalized/auto tabular schema (overload)."""


@overload
def read_and_normalize_input(
    file_path: str | Path,
    *,
    input_schema: str | None = ...,
    sheet_name: str | int = ...,
    settings: PyskindoseSettings | None = ...,
    import_options: TabularImportOptions | None = ...,
) -> InputAdapterResult | list[InputAdapterResult]:
    """Load and normalize a tabular input file (overload)."""


def read_and_normalize_input(
    file_path: str | Path,
    *,
    input_schema: str | None = None,
    sheet_name: str | int = 0,
    settings: PyskindoseSettings | None = None,
    import_options: TabularImportOptions | None = None,
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
        Use ``"auto"`` to score each known schema and pick the best match.
        A schema is eligible only when the header has a distinctive marker
        for that source and at least ``_AUTO_MIN_HITS`` of its known columns.
        One known column raises SchemaDetectionError so the caller can ask
        the user to choose. A clear margin is required when two are eligible.
        Raises ValueError when nothing is eligible or the result is ambiguous.
    sheet_name:
        Sheet name or 0-based index for Excel files (ignored for CSV/TSV).
    settings:
        Required when *input_schema* is ``"generic_rdsr_like"`` or when
        ``"auto"`` resolves to that schema.
    import_options:
        Optional post-normalization coordinate overrides (``Tx``↔``Tz`` swap,
        ``Ap1``/``Ap2`` negation). Applied per result using that result's
        ``provenance.schema_name``. ``None`` and all-false options leave
        numeric values unchanged vs omitting the argument.

    Raises
    ------
    ValueError
        On unsupported suffix, unknown schema, ambiguous auto-detection, or
        data validation failures from the selected adapter.
    """
    path = Path(file_path)
    suffix = path.suffix.lower()

    if suffix not in TABULAR_SUFFIXES:
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

    return _apply_import_options_to_results(result, import_options)
