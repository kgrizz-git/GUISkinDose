"""Captured multi-file orchestration for the public API.

Implements the captured path behind ``analyze_multiple_input_files`` so that
entry point keeps its legacy behavior untouched: with one validated captured
authority (or ``None`` for a baseline exam) per explicit file position, every
raw input file is loaded through the shared no-calculation seam, and only
then does the existing multi-exam capture path calculate. Non-null captured
entries never touch bundled profiles, the store, or the live resolver — not
even when those are broken — and calculation still reads its usual mesh and
physics assets. Null entries intentionally normalize through the standard
live baseline path (bundled/default selection, no session, receipts
stripped), so each null result matches its own individual baseline run.

Bounds (not authentication): each capture verifies recipe, geometry,
identity, and count — never full raw or dose content hashes. At most 64
explicit paths and contexts and 10_000 aggregate retained normalized events
per run (source bytes are not bounded — the bound counts loaded frames,
including null ones). Capture mode takes explicit paths only: no glob
expansion, no existence probes, no reads before every authority is
validated. Every non-null context plus authority conflicts are fully
validated before any source I/O, positionally with no guessing; a bad later
source or context leaves no partial output because calculation runs only
after all loads succeed. Multi-study splits refuse closed in capture mode —
including null entries — so one file always yields one exam; preparsed JSON
refuses for every entry (raw-exam-only invariant). ``plot_setup`` mode
refuses through the same conflict check as the single-file path.
"""

from __future__ import annotations

import copy
import logging
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from guiskindose import constants as c
from guiskindose.analyze_data import analyze_multiple_exams
from guiskindose.equipment_captured_input import (
    load_captured_exam,
    reject_captured_options_conflict,
    shielded_settings_for_capture,
)
from guiskindose.equipment_confirmation import check_captured_work_isolated
from guiskindose.equipment_profiles.capture import (
    CODE_INVALID_EQUIPMENT_CAPTURE,
    CapturedCoordinates,
    CaptureError,
    validate_constructed_context,
)
from guiskindose.equipment_profiles.constants import MAX_AGGREGATE_ROWS, MAX_PROFILES
from guiskindose.format_export_data import MultiExamResult
from guiskindose.helpers.parse_settings_to_settings_class import (
    parse_settings_to_settings_class,
)
from guiskindose.input_adapters.models import InputAdapterResult
from guiskindose.settings import PyskindoseSettings
from guiskindose.settings.normalization_settings import NormalizationSettings

logger = logging.getLogger(__name__)

__all__ = ["analyze_captured_multiple_input_files", "resolve_input_paths"]


def resolve_input_paths(file_paths: Sequence[str | Path]) -> list[Path]:
    """Expand missing glob paths, preserving the established input ordering."""
    resolved: list[Path] = []
    for file_path in file_paths:
        path = Path(file_path)
        if not path.exists() and ("*" in str(path) or "?" in str(path)):
            resolved.extend(sorted(path.parent.glob(path.name)))
        else:
            resolved.append(path)
    return resolved


def _materialize_capture_paths(file_paths: Any) -> list[Path]:
    """Require explicit capture paths without touching the filesystem.

    Capture mode takes an exact builtin list or tuple of explicit ``str`` /
    ``Path`` entries (at most ``MAX_PROFILES``); generators, mappings, bare
    strings, non-path entries, and glob syntax fail closed with no path
    echo. Pure string checks and ``Path`` construction only: no existence
    probes, no glob expansion, no reads.
    """
    if type(file_paths) not in (list, tuple):
        raise CaptureError(
            "Equipment capture file paths must be a list or tuple of explicit paths.",
            CODE_INVALID_EQUIPMENT_CAPTURE,
        )
    if len(file_paths) > MAX_PROFILES:
        raise CaptureError("Too many captured input files.", CODE_INVALID_EQUIPMENT_CAPTURE)
    materialized: list[Path] = []
    for entry in file_paths:
        if len(materialized) >= MAX_PROFILES:
            raise CaptureError(
                "Too many input files for one captured multi-exam run.",
                CODE_INVALID_EQUIPMENT_CAPTURE,
            )
        materialized.append(_capture_path(entry))
    return materialized


def _capture_path(entry: Any) -> Path:
    """Coerce one explicit path without filesystem probes or raw-value errors."""
    try:
        if isinstance(entry, Path):
            text = str(entry)
        elif isinstance(entry, str):
            text = entry
        else:
            raise CaptureError(
                "Equipment capture file paths must be explicit str or Path entries.",
                CODE_INVALID_EQUIPMENT_CAPTURE,
            )
        if any(char in text for char in "*?["):
            raise CaptureError(
                "Equipment capture file paths must be explicit paths, not globs.",
                CODE_INVALID_EQUIPMENT_CAPTURE,
            )
        return Path(text)
    except CaptureError:
        raise
    except Exception:
        raise CaptureError(
            "Equipment capture file paths must be explicit str or Path entries.",
            CODE_INVALID_EQUIPMENT_CAPTURE,
        ) from None


def _materialize_capture_contexts(contexts: Any, exam_count: int) -> list[CapturedCoordinates | None]:
    """Check container shape and entry types with positional alignment.

    Requires an exact builtin list or tuple (no custom iteration or length
    hooks) with exactly one ``CapturedCoordinates`` or ``None`` entry per
    exam position and at most ``MAX_PROFILES`` entries; counts are rechecked
    after copying.
    """
    if type(contexts) not in (list, tuple):
        raise CaptureError(
            "Equipment capture contexts must be a list or tuple aligned with the exams.",
            CODE_INVALID_EQUIPMENT_CAPTURE,
        )
    if len(contexts) > MAX_PROFILES:
        raise CaptureError("Too many equipment capture contexts.", CODE_INVALID_EQUIPMENT_CAPTURE)
    materialized: list[CapturedCoordinates | None] = []
    for entry in contexts:
        if len(materialized) >= MAX_PROFILES:
            raise CaptureError(
                "Too many equipment capture contexts for one multi-exam run.",
                CODE_INVALID_EQUIPMENT_CAPTURE,
            )
        if entry is not None and type(entry) is not CapturedCoordinates:
            raise CaptureError(
                "Equipment capture contexts must be CapturedCoordinates or None entries.",
                CODE_INVALID_EQUIPMENT_CAPTURE,
            )
        materialized.append(entry)
    if len(materialized) != exam_count:
        raise CaptureError(
            "Equipment capture contexts must align positionally with the exams.",
            CODE_INVALID_EQUIPMENT_CAPTURE,
        )
    return materialized


def _check_capture_authorities(
    materialized: list[CapturedCoordinates | None],
    settings: PyskindoseSettings,
) -> None:
    """Reject live authority and bound aggregate events before any source I/O.

    A bound live session fails closed — even for an all-null list, which
    still requests capture-mode rules — as does ``plot_setup`` mode. Every
    non-null entry is revalidated through the public constructor validator so
    forged counts fail closed, with at most ``MAX_AGGREGATE_ROWS`` aggregate
    retained events across the provided captures.
    """
    if getattr(settings, "equipment_profile_session", None) is not None:
        raise CaptureError(
            "Captured equipment contexts cannot be combined with a live session.",
            CODE_INVALID_EQUIPMENT_CAPTURE,
        )
    if settings.mode == c.MODE_PLOT_SETUP:
        raise CaptureError(
            "Equipment capture replay needs a raw input exam, not plot setup.",
            CODE_INVALID_EQUIPMENT_CAPTURE,
        )
    total_events = 0
    for entry in materialized:
        if entry is not None:
            try:
                validate_constructed_context(entry)
            except CaptureError:
                raise
            except Exception:
                raise CaptureError(
                    "Equipment capture contexts must hold validated authorities.",
                    CODE_INVALID_EQUIPMENT_CAPTURE,
                ) from None
            total_events += entry.event_count
            if total_events > MAX_AGGREGATE_ROWS:
                raise CaptureError(
                    "Too many captured events for one multi-exam run.",
                    CODE_INVALID_EQUIPMENT_CAPTURE,
                )


def _prevalidate_capture_contexts(
    contexts: Any,
    exam_count: int,
    settings: PyskindoseSettings,
) -> list[CapturedCoordinates | None]:
    """Fully validate every capture authority before any source I/O."""
    materialized = _materialize_capture_contexts(contexts, exam_count)
    _check_capture_authorities(materialized, settings)
    return materialized


def _load_captured_multi_exam(
    path: Path,
    context: CapturedCoordinates | None,
    *,
    settings_obj: PyskindoseSettings,
    input_schema: str | None,
    sheet_name: str | int,
    import_options: Any | None,
) -> tuple[InputAdapterResult, NormalizationSettings | None]:
    """Load one capture-mode file with its private baseline snapshot.

    Captured entries load on the shared shielded settings (the loader works
    on an internal private copy); null entries load on an explicit private
    per-file copy whose post-load normalization is snapshotted, so each null
    exam keeps its own baseline instead of inheriting the last load. No fake
    capture, session, receipt, or canonical match is attached to nulls.
    """
    if context is None:
        try:
            file_settings = copy.deepcopy(settings_obj)
            check_captured_work_isolated(file_settings, settings_obj)
            exam = load_captured_exam(
                path, settings=file_settings, input_schema=input_schema, sheet_name=sheet_name,
                import_options=import_options, context=context,
            )
            baseline = copy.deepcopy(file_settings.normalization_settings)
        except CaptureError:
            raise
        except Exception:
            raise CaptureError(
                "Equipment capture cannot use these settings.",
                CODE_INVALID_EQUIPMENT_CAPTURE,
            ) from None
        return exam, baseline
    return (
        load_captured_exam(
            path, settings=settings_obj, input_schema=input_schema, sheet_name=sheet_name,
            import_options=import_options, context=context,
        ),
        None,
    )


def analyze_captured_multiple_input_files(
    file_paths: Sequence[str | Path],
    settings: str | dict | PyskindoseSettings | None = None,
    *,
    input_schema: str | None = None,
    sheet_name: str | int = 0,
    per_exam_offsets: list[list[float]] | None = None,
    import_options: Any | None = None,
    equipment_capture_contexts: list[CapturedCoordinates | None]
    | tuple[CapturedCoordinates | None, ...]
    | None = None,
) -> MultiExamResult:
    """Load every raw input file under per-file captures, then calculate once.

    Takes caller settings (shielded when caller-owned, then parsed; HTML
    output forces to dict exactly like the legacy multi path). Explicit file
    paths only — no glob resolution, no existence probes: every authority is
    validated before any filesystem read. Each file loads through the shared
    capture seam — captured files confirm against their own authority, null
    files load the live baseline on a private copy with a per-exam snapshot —
    and multi-study splits refuse closed so alignment cannot slip. Set import
    options on any non-tabular path fail closed before any read; all-false
    options stay accepted everywhere. Retained normalized events accumulate
    across loaded frames (nulls included) against the aggregate cap before
    the next load. Only after every load succeeds do the confirmed exams
    calculate through the existing multi-exam capture path with isolated
    per-exam recipes, baselines, offsets, and output matches; null entries
    stay baseline. Never collects or passes a live receipt.
    """
    if isinstance(settings, PyskindoseSettings):
        settings = shielded_settings_for_capture(settings)
    settings_obj = parse_settings_to_settings_class(settings=settings)

    if settings_obj.output_format == "html":
        logger.warning("HTML output format is not supported for multi-exam runs. Forcing to dict.")
        settings_obj.output_format = "dict"

    resolved_paths = _materialize_capture_paths(file_paths)
    contexts = _prevalidate_capture_contexts(equipment_capture_contexts, len(resolved_paths), settings_obj)

    for path in resolved_paths:
        reject_captured_options_conflict(path, import_options)

    all_exams: list[InputAdapterResult] = []
    baselines: list[NormalizationSettings | None] = []
    retained = 0
    for path, context in zip(resolved_paths, contexts, strict=True):
        exam, baseline = _load_captured_multi_exam(
            path, context, settings_obj=settings_obj, input_schema=input_schema,
            sheet_name=sheet_name, import_options=import_options,
        )
        all_exams.append(exam)
        baselines.append(baseline)
        retained += len(exam.normalized_data)
        if retained > MAX_AGGREGATE_ROWS:
            raise CaptureError(
                "Too many loaded events for one multi-exam run.",
                CODE_INVALID_EQUIPMENT_CAPTURE,
            )

    return analyze_multiple_exams(
        all_exams, settings_obj, per_exam_offsets=per_exam_offsets,
        equipment_capture_contexts=contexts, per_exam_baselines=baselines,
    )
