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
from typing import Any, Literal, overload

import pandas as pd

from guiskindose.equipment_profiles.capture import CapturedCoordinates
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
            "manufacturer",
            "kvp",
            "acquisition_type",
            "acquisition_plane",
            "station_name",
            "stationname",
            "device_serial",
            "deviceserialnumber",
        }
    ),
    "generic_rdsr_like": frozenset(
        {"manufacturer", "kvp_kv", "stationname", "deviceserialnumber"}
    ),
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


def _pick_elected_schema(views: list[tuple[str, float, bool, int, bool]]) -> tuple[str, int]:
    """Return the elected schema name and its known-column hit count from *views*."""
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
    hits = next(hits for name, _score, _eligible, hits, _triggered in views if name == best_name)
    return best_name, hits


def _detect_schema_with_hits(loaded: _RawLoad) -> tuple[str, int]:
    """Return the elected schema and its known-column hit count for *loaded*."""
    return _pick_elected_schema(_schema_views(loaded.raw_df))


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
    return _detect_schema_with_hits(loaded)[0]


def _stamp_provenance(
    result: InputAdapterResult | list[InputAdapterResult],
    **fields: object,
) -> None:
    """Assign provenance attributes on one adapter result or each element of a list."""
    items = result if isinstance(result, list) else [result]
    for item in items:
        for key, value in fields.items():
            setattr(item.provenance, key, value)


def _dispatch_to_adapter(
    schema: str,
    loaded: _RawLoad,
    path: Path,
    settings: PyskindoseSettings | None,
    equipment_capture_context: CapturedCoordinates | None = None,
) -> InputAdapterResult | list[InputAdapterResult]:
    """Run the adapter selected for *schema* and return its result.

    Validates the per-schema ``settings`` requirement (the vendor adapters need
    a PyskindoseSettings for manufacturer/model lookup) and dispatches to the
    matching adapter's ``adapt``. Stub vendors raise NotImplementedError with
    implementation guidance; an unrecognised schema raises ValueError.
    """
    if schema == "normalized":
        from guiskindose.equipment_resolution import check_session_input_compatible

        check_session_input_compatible(
            schema="normalized",
            session=getattr(settings, "equipment_profile_session", None),
        )
        if equipment_capture_context is not None:
            from guiskindose.equipment_profiles.capture import (
                CODE_INVALID_EQUIPMENT_CAPTURE,
                CaptureError,
            )

            raise CaptureError(
                "Equipment capture replay needs raw vendor input, not normalized frames.",
                CODE_INVALID_EQUIPMENT_CAPTURE,
            )
        return normalized_adapter.adapt(loaded, original_filename=path.name)
    if schema in ("generic_rdsr_like", "radimetrics", "dosetrack"):
        if settings is None:
            raise ValueError(
                f"settings is required for {schema} schema (needed by rdsr_normalizer for manufacturer/model lookup)."
            )
        if schema == "generic_rdsr_like":
            return generic_rdsr_adapter.adapt(
                loaded, original_filename=path.name, settings=settings,
                equipment_capture_context=equipment_capture_context,
            )
        if schema == "radimetrics":
            return radimetrics_adapter.adapt(
                loaded, original_filename=path.name, settings=settings,
                equipment_capture_context=equipment_capture_context,
            )
        return dosetrack_adapter.adapt(
            loaded, original_filename=path.name, settings=settings,
            equipment_capture_context=equipment_capture_context,
        )
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
    equipment_capture_context: CapturedCoordinates | None = ...,
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
    equipment_capture_context: CapturedCoordinates | None = ...,
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
    equipment_capture_context: CapturedCoordinates | None = ...,
) -> InputAdapterResult | list[InputAdapterResult]:
    """Load and normalize a tabular input file (overload)."""


def read_and_normalize_input(
    file_path: str | Path,
    *,
    input_schema: str | None = None,
    sheet_name: str | int = 0,
    settings: PyskindoseSettings | None = None,
    import_options: TabularImportOptions | None = None,
    equipment_capture_context: CapturedCoordinates | None = None,
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
    equipment_capture_context:
        Validated captured-coordinate authority for offline replay of raw
        vendor schemas (``generic_rdsr_like``, ``radimetrics``, ``dosetrack``).
        Fully validated before any file load, with bound sessions rejected
        and settings required. The ``normalized`` schema refuses a capture
        (explicitly or auto-discovered); multi-study splits refuse rather
        than applying one capture to several frames. Final confirmation runs
        on the returned frame after import options; the result carries no
        live receipt.

    Provenance records ``detection_mode`` (``"auto"`` or ``"explicit"``) and,
    for auto loads only, ``matched_column_count`` (the winning schema's
    known-column hit count).

    Raises
    ------
    ValueError
        On unsupported suffix, unknown schema, ambiguous auto-detection, or
        data validation failures from the selected adapter.
    CaptureError
        On capture/shape conflicts: malformed contexts, missing settings,
        live sessions, normalized frames, or multi-study splits under capture.
    """
    if equipment_capture_context is None:
        return _read_and_normalize_input_impl(
            file_path, input_schema=input_schema, sheet_name=sheet_name,
            settings=settings, import_options=import_options,
        )
    from guiskindose.equipment_profiles.capture import CODE_INVALID_EQUIPMENT_CAPTURE, CaptureError

    try:
        return _read_and_normalize_input_impl(
            file_path, input_schema=input_schema, sheet_name=sheet_name,
            settings=settings, import_options=import_options,
            equipment_capture_context=equipment_capture_context,
        )
    except CaptureError:
        raise
    except (OSError, ValueError, TypeError, AttributeError, KeyError, OverflowError):
        raise CaptureError(
            "Equipment capture replay could not load or normalize raw tabular input.",
            CODE_INVALID_EQUIPMENT_CAPTURE,
        ) from None


def _read_and_normalize_input_impl(
    file_path: str | Path,
    *,
    input_schema: str | None = None,
    sheet_name: str | int = 0,
    settings: PyskindoseSettings | None = None,
    import_options: TabularImportOptions | None = None,
    equipment_capture_context: CapturedCoordinates | None = None,
) -> InputAdapterResult | list[InputAdapterResult]:
    """Shared pipeline; the public boundary closes capture-only failures."""
    if equipment_capture_context is not None:
        settings = _reject_captured_conflicts(settings, equipment_capture_context)
    path = Path(file_path)
    suffix = path.suffix.lower()

    if suffix not in TABULAR_SUFFIXES:
        if equipment_capture_context is not None:
            from guiskindose.equipment_profiles.capture import (
                CODE_INVALID_EQUIPMENT_CAPTURE,
                CaptureError,
            )

            raise CaptureError(
                "Equipment capture replay needs a raw tabular input file.",
                CODE_INVALID_EQUIPMENT_CAPTURE,
            )
        raise ValueError(
            f"Unsupported suffix {suffix!r}. "
            "The tabular adapter handles .csv, .tsv, .xlsx, .xlsm. "
            "For DICOM RDSR or JSON use read_and_normalise_rdsr_data()."
        )

    if equipment_capture_context is not None and (
        input_schema is None or input_schema == "normalized"
    ):
        # Explicit normalized refuses before any source I/O; auto detection
        # below may still read first to discover an unsupported normalized
        # frame, but never silently ignores the context.
        from guiskindose.equipment_profiles.capture import (
            CODE_INVALID_EQUIPMENT_CAPTURE,
            CaptureError,
        )

        raise CaptureError(
            "Equipment capture replay needs raw vendor input, not normalized frames.",
            CODE_INVALID_EQUIPMENT_CAPTURE,
        )

    loaded = load(path, sheet_name=sheet_name)

    is_auto = input_schema == "auto"
    schema = "normalized" if input_schema is None else input_schema
    matched_column_count: int | None = None

    if is_auto:
        schema, matched_column_count = _detect_schema_with_hits(loaded)

    if equipment_capture_context is not None and schema not in (
        "generic_rdsr_like",
        "radimetrics",
        "dosetrack",
    ):
        from guiskindose.equipment_profiles.capture import (
            CODE_INVALID_EQUIPMENT_CAPTURE,
            CaptureError,
        )

        raise CaptureError(
            "Equipment capture replay needs a raw vendor schema.",
            CODE_INVALID_EQUIPMENT_CAPTURE,
        )

    work_settings: Any = settings
    if equipment_capture_context is not None:
        # One preparation shared by dispatch and confirmation: the candidate
        # the pipeline normalizes with is the candidate confirmed later, so a
        # stale or muted clone cannot slip between the two.
        from guiskindose.equipment_confirmation import prepare_replay_settings

        narrowed: Any = settings
        work_settings = prepare_replay_settings(
            context=equipment_capture_context, settings=narrowed
        )
    result = _dispatch_to_adapter(schema, loaded, path, work_settings, equipment_capture_context)

    provenance_fields: dict[str, object] = {
        "detection_mode": "auto" if is_auto else "explicit",
        "matched_column_count": matched_column_count,
    }
    if suffix in (".xlsx", ".xlsm"):
        provenance_fields["sheet_name"] = sheet_name
    _stamp_provenance(result, **provenance_fields)

    _validate_live_receipts(result, settings)
    result = _apply_import_options_to_results(result, import_options)
    _rebind_live_receipts(result)
    if equipment_capture_context is not None:
        _confirm_captured_result(
            result, work_settings.normalization_settings, equipment_capture_context
        )
    return result


def _validate_live_receipts(
    result: InputAdapterResult | list[InputAdapterResult], settings: PyskindoseSettings | None
) -> None:
    """Verify existing authority before a sanctioned geometry transformation."""
    from guiskindose.equipment_resolution import receipt_to_mapping

    items = result if isinstance(result, list) else [result]
    for item in items:
        if item.equipment_receipt is None:
            continue
        if settings is None:
            raise ValueError("Equipment-profile receipts require configured settings.")
        receipt_to_mapping(receipt=item.equipment_receipt, frame=item.normalized_data, settings=settings)


def _rebind_live_receipts(result: InputAdapterResult | list[InputAdapterResult]) -> None:
    """Rebind genuine live receipts to the final post-options frame.

    The caller validates the original receipts before import options run.
    Import options transform geometry after the adapter binds its receipt, so
    without rebinding the recorded checksum describes a frame that no longer
    exists. Each receipt is rebound with the public bridge helper; results
    without receipts (including every capture replay) pass through untouched.
    """
    from guiskindose.equipment_resolution import bind_receipt_frame

    items = result if isinstance(result, list) else [result]
    for item in items:
        if item.equipment_receipt is not None:
            item.equipment_receipt = bind_receipt_frame(item.equipment_receipt, item.normalized_data)


def _reject_captured_conflicts(settings: Any, context: Any) -> PyskindoseSettings:
    """Fully validate a capture and reject authority conflicts before any I/O.

    A constructor-bypassed forgery fails here with zero file reads; a
    missing or mistyped settings home and bound live sessions fail on the
    same closed terms. Returns the narrowed settings home for dispatch.
    """
    from guiskindose.equipment_profiles.capture import (
        CODE_INVALID_EQUIPMENT_CAPTURE,
        CaptureError,
        validate_constructed_context,
    )

    try:
        validate_constructed_context(context)
    except (TypeError, AttributeError):
        raise CaptureError(
            "Equipment capture context must be a CapturedCoordinates or None.",
            CODE_INVALID_EQUIPMENT_CAPTURE,
        ) from None
    if not isinstance(settings, PyskindoseSettings):
        raise CaptureError(
            "Equipment capture replay needs settings for raw normalization.",
            CODE_INVALID_EQUIPMENT_CAPTURE,
        )
    if getattr(settings, "equipment_profile_session", None) is not None:
        raise CaptureError(
            "Equipment capture replay never resolves a live session.",
            CODE_INVALID_EQUIPMENT_CAPTURE,
        )
    return settings


def _confirm_captured_result(
    result: InputAdapterResult | list[InputAdapterResult], candidate: Any, context: Any
) -> None:
    """Confirm the returned frame after import options; result carries no receipt.

    Multi-study splits fail closed before any confirmation or publication —
    one capture is never applied to several frames. Confirms identity, count,
    geometry, and all 15 leaves on the actual returned frame against the
    pipeline's own applied candidate (threaded from dispatch, never
    re-prepared, so a muted clone cannot slip between the two). A live
    receipt on the result fails closed rather than returning mixed authority;
    nothing is published.
    """
    from guiskindose.equipment_confirmation import confirm_captured_application
    from guiskindose.equipment_profiles.capture import (
        CODE_INVALID_EQUIPMENT_CAPTURE,
        CaptureError,
    )

    if isinstance(result, list):
        raise CaptureError(
            "Equipment capture replay needs a single raw exam, not a multi-study split.",
            CODE_INVALID_EQUIPMENT_CAPTURE,
        )

    if result.equipment_receipt is not None:
        raise CaptureError(
            "Equipment capture replay never publishes receipt records.",
            CODE_INVALID_EQUIPMENT_CAPTURE,
        )
    confirm_captured_application(
        context=context,
        frame=result.normalized_data,
        candidate=candidate,
    )
