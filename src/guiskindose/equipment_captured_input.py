"""Single-file captured input orchestration for the public API.

Implements the captured path behind ``analyze_input_file`` and ``main`` so
those entry points keep their legacy behavior untouched: with a validated
captured-coordinate authority, one raw input file (DICOM or raw vendor
tabular) is loaded through the capture-aware loaders, confirmed, and
calculated — with no live session, no live receipt, and no bundled, store,
or profile-source contact. Calculation still reads its usual mesh and
physics assets.

Bounds (not authentication): the capture verifies recipe, geometry,
identity, and count — never full raw or dose content hashes. ``plot_setup``
mode refuses explicitly instead of ignoring the authority. Preparsed JSON,
normalized frames, and multi-study splits refuse closed.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pandas as pd

from guiskindose import constants as c
from guiskindose.analyze_data import analyze_data
from guiskindose.equipment_confirmation import check_captured_work_isolated
from guiskindose.equipment_profiles.capture import (
    CODE_INVALID_EQUIPMENT_CAPTURE,
    CapturedCoordinates,
    CaptureError,
    validate_constructed_context,
)
from guiskindose.input_adapters.import_options import TABULAR_SUFFIXES
from guiskindose.input_adapters.models import InputAdapterResult, InputProvenance
from guiskindose.settings import PyskindoseSettings

__all__ = [
    "analyze_captured_input_file",
    "analyze_captured_main_input",
    "load_captured_exam",
    "reject_captured_options_conflict",
    "shielded_settings_for_capture",
]


def shielded_settings_for_capture(settings: PyskindoseSettings) -> PyskindoseSettings:
    """Deepcopy caller settings so capture replay cannot mutate them.

    Plain dict/str inputs already produce fresh objects at init; only a
    caller-owned settings home needs shielding from output-format assignment.
    Beyond the root-identity guard, the full established isolation boundary
    applies: a self-returning ``__deepcopy__`` that shares nested
    normalization/phantom homes fails closed before any setter runs.
    """
    try:
        work = copy.deepcopy(settings)
    except Exception:
        raise CaptureError(
            "Equipment capture cannot use these settings.",
            CODE_INVALID_EQUIPMENT_CAPTURE,
        ) from None

    if not isinstance(work, PyskindoseSettings) or work is settings:
        raise CaptureError(
            "Equipment capture cannot use shared settings.",
            CODE_INVALID_EQUIPMENT_CAPTURE,
        )
    check_captured_work_isolated(work, settings)
    return work


def analyze_captured_main_input(
    file_path: str | None,
    settings: PyskindoseSettings,
    equipment_capture_context: CapturedCoordinates,
) -> Any:
    """Captured replay for the historical DICOM entry point.

    Refuses tabular sources before any I/O: the historical entry point
    carries no schema or import options, so tabular replay stays on
    ``analyze_input_file``. Everything else delegates with fixed schema
    and options.
    """
    if file_path is not None and Path(file_path).suffix.lower() in TABULAR_SUFFIXES:
        raise CaptureError(
            "Equipment capture replay through main needs a DICOM input file.",
            CODE_INVALID_EQUIPMENT_CAPTURE,
        )
    return analyze_captured_input_file(
        file_path, settings=settings, input_schema=None, sheet_name=0,
        import_options=None, equipment_capture_context=equipment_capture_context,
    )


def _reject_captured_input_conflicts(settings: PyskindoseSettings, context: Any) -> CapturedCoordinates:
    """Fully validate the capture and reject authority conflicts before any I/O.

    Returns the validated context for dispatch. A constructor-bypassed
    forgery, a non-settings home, a bound live session, or a source-free
    ``plot_setup`` mode all fail closed here with zero source reads.
    """
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
    if settings.mode == c.MODE_PLOT_SETUP:
        raise CaptureError(
            "Equipment capture replay needs a raw input exam, not plot setup.",
            CODE_INVALID_EQUIPMENT_CAPTURE,
        )
    return context


def analyze_captured_input_file(
    file_path: str | Path | None,
    *,
    settings: PyskindoseSettings,
    input_schema: str | None,
    sheet_name: str | int,
    import_options: Any | None,
    equipment_capture_context: CapturedCoordinates,
) -> Any:
    """Load one raw input file under a capture and calculate from it.

    Takes initialized settings (the caller owns output-format handling).
    DICOM sources go through the captured DICOM helper; tabular sources go
    through the captured registry with schema, sheet, and import options
    carried. Preparsed JSON, normalized frames, and multi-study splits fail
    closed; the confirmed frame calculates through ``analyze_data`` with the
    same capture. Never collects or passes a live receipt.
    """
    context = _reject_captured_input_conflicts(settings, equipment_capture_context)
    frame = load_captured_exam(
        file_path, settings=settings, input_schema=input_schema, sheet_name=sheet_name,
        import_options=import_options, context=context,
    ).normalized_data
    if not isinstance(frame, pd.DataFrame):
        raise CaptureError(
            "Equipment capture replay needs a single raw exam frame.",
            CODE_INVALID_EQUIPMENT_CAPTURE,
        )
    return analyze_data(frame, settings, equipment_capture_context=context)


def reject_captured_options_conflict(file_path: str | Path | None, import_options: Any | None) -> None:
    """Refuse set coordinate import options on a non-tabular path in capture mode.

    Same trigger as reject_import_options_for_non_tabular (flags set on a
    non-tabular path), closed for capture mode before any source read.
    All-false options stay accepted on every suffix.
    """
    if (
        import_options is not None
        and import_options.any_set()
        and (file_path is None or Path(file_path).suffix.lower() not in TABULAR_SUFFIXES)
    ):
        raise CaptureError(
            "Equipment capture replay needs tabular input for import options.",
            CODE_INVALID_EQUIPMENT_CAPTURE,
        )


def _dicom_exam_result(frame: pd.DataFrame, file_path: str | Path | None) -> InputAdapterResult:
    """Wrap a loaded DICOM frame as a receipt-free exam result.

    Mirrors the legacy multi-file DICOM construction: schema ``"rdsr"``, no
    warnings, no raw data, no live receipt.
    """
    if not isinstance(frame, pd.DataFrame):
        raise CaptureError(
            "Equipment capture replay needs a single raw exam frame.",
            CODE_INVALID_EQUIPMENT_CAPTURE,
        )
    provenance = InputProvenance(
        source_type="" if file_path is None else Path(file_path).suffix.lower().lstrip("."),
        schema_name="rdsr",
        original_filename="" if file_path is None else Path(file_path).name,
        header_row_index=0,
        detected_encoding="n/a",
        detected_delimiter=None,
        sheet_name=None,
        column_map={},
        unit_conversions={},
        warnings=[],
    )
    return InputAdapterResult(
        normalized_data=frame,
        raw_data=None,
        provenance=provenance,
        warnings=[],
        equipment_receipt=None,
    )


def load_captured_exam(
    file_path: str | Path | None,
    *,
    settings: PyskindoseSettings,
    input_schema: str | None,
    sheet_name: str | int,
    import_options: Any | None,
    context: CapturedCoordinates | None,
) -> InputAdapterResult:
    """Load one raw file in capture mode without calculating.

    A validated capture routes through the capture-aware loaders (confirming
    recipe, geometry, identity, and count); ``None`` loads the live baseline
    with any live receipt stripped. Callers validate the capture authority
    and session conflicts before any load. Multi-study splits refuse closed
    in capture mode — including null entries, so one file always yields one
    exam and positional alignment cannot slip. Preparsed JSON refuses before
    any read; unreadable or malformed sources neutralize to a closed error
    that never echoes filenames, paths, or library exceptions.
    """
    reject_captured_options_conflict(file_path, import_options)
    if file_path is not None and Path(file_path).suffix.lower() == ".json":
        raise CaptureError(
            "Equipment capture replay needs raw input, not preparsed JSON.",
            CODE_INVALID_EQUIPMENT_CAPTURE,
        )
    try:
        if file_path is None or Path(file_path).suffix.lower() not in TABULAR_SUFFIXES:
            from guiskindose.helpers.read_and_normalize_rdsr_data import (
                read_and_normalise_rdsr_data,
            )

            frame = read_and_normalise_rdsr_data(
                rdsr_filepath=None if file_path is None else str(file_path),
                settings=settings,
                equipment_capture_context=context,
            )
            return _dicom_exam_result(frame, file_path)
        from guiskindose.input_adapters.registry import read_and_normalize_input

        result = read_and_normalize_input(
            file_path,
            input_schema=input_schema,
            sheet_name=sheet_name,
            settings=settings,
            import_options=import_options,
            equipment_capture_context=context,
        )
        if isinstance(result, list):
            raise CaptureError(
                "Equipment capture replay needs a single raw exam, not a multi-study split.",
                CODE_INVALID_EQUIPMENT_CAPTURE,
            )
        result.equipment_receipt = None
        return result
    except CaptureError:
        raise
    except Exception:
        # Unreadable or malformed sources must not leak filenames, paths, or
        # library exceptions in capture mode.
        raise CaptureError(
            "Equipment capture replay failed closed while reading input.",
            CODE_INVALID_EQUIPMENT_CAPTURE,
        ) from None
