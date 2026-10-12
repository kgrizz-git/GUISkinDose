"""Captured-application preparation and confirmation for confirmed frames.

Second half of the capture story after :mod:`guiskindose.equipment_capture`:
given a validated :class:`CapturedCoordinates` authority and an already
confirmed normalized frame, build a candidate :class:`NormalizationSettings`
clone from the stored recipe and confirm it back against the capture. The
captured authority stays distinct from any live session throughout — nothing
here binds a session, opens profile files or stores, consults bundled data,
or replays raw normalization.

- :func:`prepare_captured_candidate` is pure: it validates the context,
  deep-copies the passed settings home, applies the full 15 stored leaf
  values plus captured input/matched labels, and refreshes the cached
  summary. The passed home, frame, and lists are never mutated.
- :func:`confirm_captured_application` verifies the frame's canonical input
  identity, final count, and portable geometry checksum against the context,
  then verifies all 15 live effective fields (plus labels) of the candidate
  against the capture. Only then does it publish a frozen
  :class:`CapturedApplicationReceipt` and the default-safe captured match
  mapping identical to the saved context. Any mismatch fails with
  value-free closed codes before any published state.

Baseline-normalized geometry that differs from the confirmed capture
rejects here; raw re-normalization and atomic commit belong to an explicit
later Phase 2/3 boundary. The capture checksum is a consistency check, not
authenticity — this module never claims full dose reproduction. Existing
live-session receipt validation is untouched.
"""

from __future__ import annotations

import copy
import hmac
import math
import re
from dataclasses import dataclass
from typing import Any

from guiskindose.equipment_capture import (
    capture_to_mapping,
    frame_geometry_rows,
    geometry_digest_v1,
)
from guiskindose.equipment_profiles.capture import (
    CODE_EQUIPMENT_GEOMETRY_MISMATCH,
    CODE_INVALID_EQUIPMENT_CAPTURE,
    CapturedCoordinates,
    CaptureError,
    validate_constructed_context,
)
from guiskindose.equipment_profiles.constants import MAX_AGGREGATE_ROWS, MAX_PROFILES, MAX_SHORT_TEXT
from guiskindose.equipment_profiles.keys import (
    normalize_manufacturer_key,
    normalize_model_key,
)
from guiskindose.exam_identity import canonical_identity_pairs
from guiskindose.input_adapters.models import InputAdapterResult
from guiskindose.privacy import opaque_exam_label
from guiskindose.settings.normalization_settings import NormalizationSettings
from guiskindose.settings.pyskindose_settings import PyskindoseSettings

_CAPTURE_SETTINGS_ERROR = "Equipment capture cannot be applied to these settings."


__all__ = [
    "CapturedApplicationReceipt",
    "check_captured_candidate",
    "check_captured_work_isolated",
    "confirm_captured_application",
    "prepare_captured_candidate",
    "prepare_replay_settings",
]

_SIGN_TO_INT = {"+": 1, "-": -1}
_MATCHED_SOURCES = ("custom", "bundled")


def check_captured_work_isolated(work_settings: Any, settings: Any) -> None:
    """Public isolation boundary for privately cloned capture work settings.

    Same established check as the preparation path: the working copy must
    share no mutable home (root, normalization, vectors, phantom, dimension,
    patient offset) with the caller-owned settings, verified before any
    setter runs. Closed ``CaptureError`` on violation.
    """
    _check_work_isolated(work_settings, settings)


def _check_work_isolated(work_settings: Any, settings: Any) -> None:
    """Require the working copy isolated from caller-owned mutable state.

    Covers the root home plus every mutable subhome the calculation path can
    touch: normalization settings, the three coordinate vectors, the phantom,
    its dimensions (rewritten by plot-mode geometry previews), and the patient
    offset (rewritten per exam). A self-returning ``__deepcopy__`` (or
    shared-child hooks) that rebinds the working copy to caller handles would
    let later assignment mutate the caller, so rejection happens before any
    setter runs. Ordinary subclasses that copy cleanly pass unchanged. This
    verifies handle isolation at handoff; it cannot restrain a hostile hook
    that mutates caller state during its own copy execution.
    """
    if not isinstance(work_settings, PyskindoseSettings):
        raise CaptureError(
            _CAPTURE_SETTINGS_ERROR,
            CODE_INVALID_EQUIPMENT_CAPTURE,
        )
    try:
        shared = (
            work_settings is settings
            or work_settings.normalization_settings is settings.normalization_settings
            or work_settings.normalization_settings.trans_offset
            is settings.normalization_settings.trans_offset
            or work_settings.normalization_settings.trans_dir
            is settings.normalization_settings.trans_dir
            or work_settings.normalization_settings.rot_dir
            is settings.normalization_settings.rot_dir
            or work_settings.phantom is settings.phantom
            or work_settings.phantom.dimension is settings.phantom.dimension
            or work_settings.phantom.patient_offset is settings.phantom.patient_offset
        )
    except AttributeError:
        raise CaptureError(
            _CAPTURE_SETTINGS_ERROR,
            CODE_INVALID_EQUIPMENT_CAPTURE,
        ) from None
    if shared:
        raise CaptureError(
            _CAPTURE_SETTINGS_ERROR,
            CODE_INVALID_EQUIPMENT_CAPTURE,
        )


def _validate_capture_contexts(
    exams: list[InputAdapterResult],
    contexts: Any,
) -> list[Any]:
    """Validate the capture-context argument shape before any calculation.

    Requires an exact builtin list or tuple with exactly one entry per exam
    (``None`` entries stay baseline), at most ``MAX_PROFILES`` entries, and at
    most ``MAX_AGGREGATE_ROWS`` aggregate retained events across the provided
    captures. Strings, mappings, generators, and other shapes fail closed, as
    do unsupported entry types. Exact builtin containers exclude custom
    iteration and length hooks; counts are also rechecked after copying.
    """
    if type(contexts) not in (list, tuple):
        raise CaptureError(
            "Equipment capture contexts must be a list or tuple aligned with the exams.",
            CODE_INVALID_EQUIPMENT_CAPTURE,
        )
    if len(contexts) != len(exams):
        raise CaptureError(
            "Equipment capture contexts must align positionally with the exams.",
            CODE_INVALID_EQUIPMENT_CAPTURE,
        )
    if len(contexts) > MAX_PROFILES:
        raise CaptureError(
            "Too many equipment capture contexts for one multi-exam run.",
            CODE_INVALID_EQUIPMENT_CAPTURE,
        )
    materialized: list[Any] = []
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
    if len(materialized) != len(exams):
        raise CaptureError(
            "Equipment capture contexts must align positionally with the exams.",
            CODE_INVALID_EQUIPMENT_CAPTURE,
        )
    _check_capture_event_total(materialized)
    return materialized


def _check_capture_event_total(materialized: list[Any]) -> None:
    """Bound aggregate retained events across the provided captures.

    Every entry is revalidated through the public constructor validator
    first, so constructor-bypassed shapes (forged counts, corrupt nesting)
    fail closed here instead of leaking raw errors from the sum.
    """
    total_events = 0
    for entry in materialized:
        if entry is not None:
            validate_constructed_context(entry)
            total_events += entry.event_count
            if total_events > MAX_AGGREGATE_ROWS:
                raise CaptureError(
                    "Too many captured events for one multi-exam run.",
                    CODE_INVALID_EQUIPMENT_CAPTURE,
                )


def _check_capture_baseline_request(contexts: Any, baselines: Any) -> None:
    """Refuse baseline snapshots without the captured-analysis authority path."""
    if contexts is None and baselines is not None:
        raise CaptureError(
            "Per-exam baseline snapshots need capture contexts.", CODE_INVALID_EQUIPMENT_CAPTURE
        )


def _validate_capture_baselines(
    baselines: Any, contexts: list[Any]
) -> list[NormalizationSettings | None] | None:
    """Validate bounded positional snapshots; captured entries cannot supply one."""
    if baselines is None:
        return None
    if type(baselines) not in (list, tuple) or len(baselines) != len(contexts):
        raise _closed()
    if len(baselines) > MAX_PROFILES:
        raise _closed()
    for baseline, context in zip(baselines, contexts, strict=True):
        if baseline is not None and (context is not None or not isinstance(baseline, NormalizationSettings)):
            raise _closed()
    return list(baselines)


def _prepare_captured_exams(
    exams: list[InputAdapterResult],
    contexts: list[Any],
    settings: PyskindoseSettings,
    per_exam_offsets: list[list[float]] | None,
    downgrade_beam_warning: bool,
    per_exam_baselines: list[Any] | None = None,
) -> list[tuple[PyskindoseSettings, dict[str, Any] | None, list[float]]]:
    """Validate every provided capture before any exam produces output.

    Rejects any configured live session or per-exam live receipt first, then
    prebuilds each exam's final work settings — isolated private copy, stored
    recipe for captured exams, per-exam offsets and warning downgrade — and
    confirms each non-null capture against its own frame. Returns per-exam
    final work settings plus the stored match mapping (``None`` for baseline
    entries) plus the effective offset. A late failure raises before any
    phantom, plot, dose, or result production, so no partial output escapes.
    Opaque exam labels only.
    """
    if getattr(settings, "equipment_profile_session", None) is not None:
        raise CaptureError(
            "Captured equipment contexts cannot be combined with a live session.",
            CODE_INVALID_EQUIPMENT_CAPTURE,
        )
    for index, exam in enumerate(exams):
        if exam.equipment_receipt is not None:
            raise CaptureError(
                f"{opaque_exam_label(index)}: captured equipment contexts cannot be "
                "combined with a live receipt.",
                CODE_INVALID_EQUIPMENT_CAPTURE,
            )
    global_offset = [
        float(settings.phantom.patient_offset.d_lon),
        float(settings.phantom.patient_offset.d_ver),
        float(settings.phantom.patient_offset.d_lat),
    ]
    prepared: list[tuple[PyskindoseSettings, dict[str, Any] | None, list[float]]] = []
    for index, (exam, context) in enumerate(zip(exams, contexts, strict=True)):
        raw_offset = (
            per_exam_offsets[index]
            if per_exam_offsets and index < len(per_exam_offsets)
            else global_offset
        )
        if (
            not isinstance(raw_offset, (list, tuple))
            or len(raw_offset) != 3
            or not all(
                isinstance(value, (int, float))
                and not isinstance(value, bool)
                and math.isfinite(float(value))
                for value in raw_offset
            )
        ):
            raise CaptureError(
                f"{opaque_exam_label(index)}: captured multi-exam offsets must hold "
                "exactly 3 finite numeric values.",
                CODE_INVALID_EQUIPMENT_CAPTURE,
            )
        effective_offset = [float(value) for value in raw_offset]
        baseline = per_exam_baselines[index] if per_exam_baselines is not None else None
        prepared.append(
            _prepare_one_captured_exam(
                exam, context, settings, effective_offset, downgrade_beam_warning, baseline
            )
        )
    return prepared


def _prepare_one_captured_exam(
    exam: InputAdapterResult,
    context: Any,
    settings: PyskindoseSettings,
    effective_offset: list[float],
    downgrade_beam_warning: bool,
    baseline: Any = None,
) -> tuple[PyskindoseSettings, dict[str, Any] | None, list[float]]:
    """Prebuild one exam's final isolated work settings plus stored match.

    Exactly one private copy per exam: isolation (root, normalization,
    vectors, phantom, dimension, patient offset) is verified before any
    recipe, offset, or warning lands, so shared-copy hooks cannot funnel
    caller handles into the calculation. Null entries take the same isolated
    path without a recipe; with a private baseline snapshot they install
    their own baseline instead of inheriting shared last-load state. No
    fake capture, session, receipt, or canonical match is attached to nulls.
    """
    try:
        work_settings = copy.deepcopy(settings)
    except Exception:
        # Untrusted boundary: the caller owns the settings graph.
        raise CaptureError(
            _CAPTURE_SETTINGS_ERROR,
            CODE_INVALID_EQUIPMENT_CAPTURE,
        ) from None
    _check_work_isolated(work_settings, settings)
    if context is None:
        stored_match = None
        if baseline is not None:
            if not isinstance(baseline, NormalizationSettings):
                raise CaptureError(
                    _CAPTURE_SETTINGS_ERROR,
                    CODE_INVALID_EQUIPMENT_CAPTURE,
                )
            try:
                cloned_baseline = copy.deepcopy(baseline)
            except Exception:
                raise _closed() from None
            _candidate_home(cloned_baseline)
            _check_clone_isolated(cloned_baseline, baseline)
            work_settings.normalization_settings = cloned_baseline
            _check_work_isolated(work_settings, settings)
    else:
        candidate = prepare_captured_candidate(context=context, norm=work_settings.normalization_settings)
        work_settings.normalization_settings = candidate
        _, stored_match = confirm_captured_application(
            context=context, frame=exam.normalized_data, candidate=candidate
        )
    _apply_exam_offset(work_settings, effective_offset, downgrade_beam_warning)
    return work_settings, stored_match, effective_offset


def _apply_exam_offset(
    work_settings: PyskindoseSettings, effective_offset: list[float], downgrade_beam_warning: bool
) -> None:
    """Apply one exam's offset and warning downgrade onto isolated work settings."""
    try:
        patient_offset = work_settings.phantom.patient_offset
        patient_offset.d_lon, patient_offset.d_ver, patient_offset.d_lat = effective_offset
    except AttributeError:
        raise CaptureError(
            _CAPTURE_SETTINGS_ERROR,
            CODE_INVALID_EQUIPMENT_CAPTURE,
        ) from None
    if downgrade_beam_warning:
        work_settings.beam_miss_warn = "summary"

_HEX_64 = re.compile(r"\A[0-9a-f]{64}\Z")


def _closed() -> CaptureError:
    """Closed-vocabulary preparation/confirmation failure (never echoes state)."""
    return CaptureError(
        "Equipment capture cannot be applied to this candidate.",
        CODE_INVALID_EQUIPMENT_CAPTURE,
    )


def _recipe_value(context: CapturedCoordinates, dotted_path: str) -> Any:
    """One stored effective value by dotted leaf path."""
    for leaf in context.fields:
        if leaf.field == dotted_path:
            return leaf.value
    raise _closed()


def _validated_context(context: Any) -> CapturedCoordinates:
    """Require a fully valid captured authority."""
    if type(context) is not CapturedCoordinates:
        raise _closed()
    try:
        validate_constructed_context(context)
    except CaptureError:
        raise
    except (TypeError, AttributeError):
        raise _closed() from None
    return context


def prepare_replay_settings(*, context: Any, settings: PyskindoseSettings) -> PyskindoseSettings:
    """Clone caller settings with isolation verified, then apply the captured recipe.

    Returns the private working clone (never the caller's home) carrying the
    full 15 stored leaves, captured labels, method flag, and refreshed summary
    into raw normalization. No session is bound, no source is opened, and
    nothing is re-resolved: the recipe is captured history, not fresh
    verification. The caller passes the clone to the capture-aware normalizer,
    which must skip live bundled selection itself.
    """
    checked = _validated_context(context)
    if getattr(settings, "equipment_profile_session", None) is not None:
        raise _closed()
    try:
        work_settings = copy.deepcopy(settings)
    except Exception:
        # Untrusted boundary: the caller owns the settings graph.
        raise _closed() from None
    _check_work_isolated(work_settings, settings)
    candidate = prepare_captured_candidate(context=checked, norm=work_settings.normalization_settings)
    work_settings.normalization_settings = candidate
    return work_settings


def _candidate_home(norm: Any) -> NormalizationSettings:
    """Require a normalization settings home to clone."""
    if not isinstance(norm, NormalizationSettings):
        raise _closed()
    return norm


def prepare_captured_candidate(*, context: Any, norm: Any) -> NormalizationSettings:
    """Build a candidate settings clone carrying the captured recipe.

    Pure function of its inputs: the passed home is deep-copied before any
    setter runs, so a failure (or success) never mutates the caller's
    settings. Applies the full 15 stored leaves, captured input/matched
    labels, the derived method flag, and a refreshed cached summary.
    """
    checked = _validated_context(context)
    home = _candidate_home(norm)
    try:
        candidate = copy.deepcopy(home)
    except Exception:
        # Untrusted boundary: the caller owns the entire object graph, so any
        # copy failure (including hostile __deepcopy__/__reduce__ hooks) is a
        # closed rejection, never a raw cause.
        raise _closed() from None
    _check_clone_isolated(candidate, home)
    _apply_recipe(candidate, checked)
    _apply_labels(candidate, checked)
    try:
        candidate.update_attrs_str()
    except (AttributeError, TypeError, ValueError):
        raise _closed() from None
    return candidate


def _check_clone_isolated(candidate: Any, home: Any) -> None:
    """Require the clone and its mutable settings homes to share no handles.

    A hostile subclass (or nested ``__deepcopy__`` returning ``self``) that
    rebinds the candidate to caller-owned mutable state fails here, before
    any setter runs — ordinary classes deep-copy cleanly and are unaffected.
    """
    try:
        shared = (
            candidate is home
            or candidate.trans_offset is home.trans_offset
            or candidate.trans_dir is home.trans_dir
            or candidate.rot_dir is home.rot_dir
        )
    except AttributeError:
        raise _closed() from None
    if shared:
        raise _closed()


def _apply_recipe(candidate: NormalizationSettings, context: CapturedCoordinates) -> None:
    """Apply the 15 stored leaves to the clone via public setters."""
    try:
        candidate.trans_offset.update_translation_offset(
            {
                axis: _recipe_value(context, f"translation_offset.{axis}")
                for axis in ("x", "y", "z")
            }
        )
        candidate.trans_dir.update_translation_direction(
            {
                axis: _recipe_value(context, f"translation_direction.{axis}")
                for axis in ("x", "y", "z")
            }
        )
        candidate.rot_dir.update_rotation_direction(
            {key: _recipe_value(context, f"rotation_direction.{key}") for key in ("Ap1", "Ap2", "Ap3", "At1", "At2", "At3")}
        )
        candidate.field_size_mode = _recipe_value(context, "field_size_mode")
        candidate.detector_side_length = _recipe_value(context, "detector_side_length")
        candidate.swap_lateral_longitudinal = _recipe_value(context, "swap_lateral_longitudinal")
    except (AttributeError, TypeError, ValueError, KeyError):
        raise _closed() from None


def _apply_labels(candidate: NormalizationSettings, context: CapturedCoordinates) -> None:
    """Apply captured identity labels and the derived method flag."""
    try:
        candidate.input_manufacturer = context.input_identity.manufacturer or ""
        candidate.input_model = context.input_identity.model or ""
        matched_maker = context.matched_identity.manufacturer
        matched_model = context.matched_identity.model
        if matched_maker is None or matched_model is None:
            raise _closed()
        candidate.matched_manufacturer = matched_maker
        candidate.matched_model = matched_model
        candidate.normalization_method = "Matched" if context.source in _MATCHED_SOURCES else "Fallback"
    except (AttributeError, TypeError):
        raise _closed() from None


@dataclass(frozen=True, slots=True, repr=False)
class CapturedApplicationReceipt:
    """Frozen proof that one capture confirmed against one frame and candidate.

    Binds the capture and geometry checksums, the final event count, the
    canonical identity keys, and the closed-vocabulary method. The repr shows
    the method and counts only — never hashes or keys.

    This receipt describes the verified result of :func:`confirm_captured_application`;
    its freely constructible fields are not independent authenticity. Future
    consumers must validate the context and frame through confirmation — never
    trust a hand-built receipt alone.
    """

    capture_hash: str
    geometry_hash: str
    event_count: int
    maker_key: str
    model_key: str
    method: str

    def __post_init__(self) -> None:
        try:
            _check_receipt_shape(
                self.capture_hash,
                self.geometry_hash,
                self.event_count,
                self.maker_key,
                self.model_key,
                self.method,
            )
        except CaptureError:
            raise
        except (TypeError, AttributeError):
            raise _closed() from None

    def __repr__(self) -> str:
        return f"CapturedApplicationReceipt(method={self.method!r}, events={self.event_count!r})"


def _check_receipt_shape(
    capture_hash: Any,
    geometry_hash: Any,
    event_count: Any,
    maker_key: Any,
    model_key: Any,
    method: Any,
) -> None:
    """Require exact receipt shapes; keys bounded before canonicalization.

    The method membership test runs only after the exact-builtin-string
    check, so hostile ``__eq__``/``__repr__`` payloads and string subclasses
    never reach comparison. Key lengths are bounded to the capture identity
    limit before the (linear-time) normalizers run.
    """
    if type(capture_hash) is not str or _HEX_64.match(capture_hash) is None:
        raise _closed()
    if type(geometry_hash) is not str or _HEX_64.match(geometry_hash) is None:
        raise _closed()
    if type(event_count) is not int:
        raise _closed()
    if not 1 <= event_count <= MAX_AGGREGATE_ROWS:
        raise _closed()
    if type(maker_key) is not str or len(maker_key) > MAX_SHORT_TEXT:
        raise _closed()
    if normalize_manufacturer_key(maker_key) != maker_key:
        raise _closed()
    if type(model_key) is not str or len(model_key) > MAX_SHORT_TEXT:
        raise _closed()
    if normalize_model_key(model_key) != model_key:
        raise _closed()
    if type(method) is not str or method not in ("Matched", "Fallback"):
        raise _closed()


def _frame_identity_keys(frame: Any) -> tuple[str, str]:
    """Canonical input-identity keys across all bounded retained rows.

    Uses the shared exam-identity semantics: spelling variants collapse to
    one pair while maker/model variation and known/unknown mixes stay
    distinct — so exactly one pair must remain, equal to the captured key.
    Missing artifacts map to empty keys, matching Default captures.
    """
    try:
        pairs = canonical_identity_pairs(frame)
    except (AttributeError, TypeError, ValueError):
        raise _closed() from None
    if len(pairs) != 1:
        raise _closed()
    maker, model = pairs[0]
    return maker or "", model or ""


def _check_number(value: Any) -> float:
    """Require a finite non-boolean number; no truthiness or coercion."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _closed()
    try:
        number = float(value)
    except OverflowError:
        raise _closed() from None
    if not math.isfinite(number):
        raise _closed()
    return number


def _check_offsets(candidate: NormalizationSettings, context: CapturedCoordinates) -> None:
    """Stored offsets must equal finite non-boolean live offsets exactly."""
    try:
        live = candidate.trans_offset
        for axis in ("x", "y", "z"):
            if _check_number(getattr(live, axis)) != _recipe_value(context, f"translation_offset.{axis}"):
                raise _closed()
    except AttributeError:
        raise _closed() from None


def _check_directions(candidate: NormalizationSettings, context: CapturedCoordinates) -> None:
    """Stored signs must equal exact +-1 live multipliers (booleans rejected)."""
    try:
        trans = candidate.trans_dir
        for axis in ("x", "y", "z"):
            value = getattr(trans, axis)
            if type(value) is not int or value not in (1, -1):
                raise _closed()
            if value != _SIGN_TO_INT[_recipe_value(context, f"translation_direction.{axis}")]:
                raise _closed()
        rot = candidate.rot_dir
        for key in ("Ap1", "Ap2", "Ap3", "At1", "At2", "At3"):
            value = getattr(rot, key)
            if type(value) is not int or value not in (1, -1):
                raise _closed()
            if value != _SIGN_TO_INT[_recipe_value(context, f"rotation_direction.{key}")]:
                raise _closed()
    except (AttributeError, KeyError):
        raise _closed() from None


def _check_modes_and_labels(candidate: NormalizationSettings, context: CapturedCoordinates) -> None:
    """Stored mode/size/swap/labels must equal exact-typed live values."""
    try:
        mode = candidate.field_size_mode
        if type(mode) is not str or mode != _recipe_value(context, "field_size_mode"):
            raise _closed()
        if _check_number(candidate.detector_side_length) != _recipe_value(context, "detector_side_length"):
            raise _closed()
        swap = candidate.swap_lateral_longitudinal
        if type(swap) is not bool or swap != _recipe_value(context, "swap_lateral_longitudinal"):
            raise _closed()
        _check_label(candidate.input_manufacturer, context.input_identity.manufacturer or "")
        _check_label(candidate.input_model, context.input_identity.model or "")
        _check_label(candidate.matched_manufacturer, context.matched_identity.manufacturer)
        _check_label(candidate.matched_model, context.matched_identity.model)
        expected = "Matched" if context.source in _MATCHED_SOURCES else "Fallback"
        if type(candidate.normalization_method) is not str or candidate.normalization_method != expected:
            raise _closed()
    except AttributeError:
        raise _closed() from None


def _check_label(live: Any, stored: Any) -> None:
    """Require an exact-string live label equal to its stored spelling."""
    if type(live) is not str or live != stored:
        raise _closed()


def check_captured_candidate(candidate: Any, context: Any) -> CapturedCoordinates:
    """Verify a candidate home carries the capture recipe and labels (no frame).

    Reusable precondition for raw normalization: the full 15 stored leaves,
    captured labels, and derived method flag must already match, so an
    unapplied home fails closed before any geometry runs. Frame identity,
    count, and geometry checks still belong to full confirmation later.
    """
    checked = _validated_context(context)
    if not isinstance(candidate, NormalizationSettings):
        raise _closed()
    _check_offsets(candidate, checked)
    _check_directions(candidate, checked)
    _check_modes_and_labels(candidate, checked)
    return checked


def confirm_captured_application(
    *, context: Any, frame: Any, candidate: Any
) -> tuple[CapturedApplicationReceipt, dict[str, Any]]:
    """Confirm a prepared candidate against its capture and frame.

    Verifies, in order: the context itself, the candidate home type, the
    frame's canonical input identity and final count, the portable geometry
    checksum, and all 15 live effective fields plus labels. Only then
    publishes the frozen receipt and the captured match mapping identical to
    the saved context. Nothing is mutated; failures precede all publication.
    """
    checked = _validated_context(context)
    if not isinstance(candidate, NormalizationSettings):
        raise _closed()
    try:
        retained = len(frame)
    except TypeError:
        raise _closed() from None
    if retained != checked.event_count:
        raise _closed()
    if _frame_identity_keys(frame) != checked.matched_input_key:
        raise _closed()
    try:
        digest = geometry_digest_v1(frame_geometry_rows(frame, retained))
    except CaptureError:
        raise
    except (TypeError, AttributeError, ValueError):
        raise _closed() from None
    if not hmac.compare_digest(digest, checked.geometry_hash):
        raise CaptureError(
            "Confirmed geometry does not match the captured checksum.",
            CODE_EQUIPMENT_GEOMETRY_MISMATCH,
        )
    _check_offsets(candidate, checked)
    _check_directions(candidate, checked)
    _check_modes_and_labels(candidate, checked)
    method = "Matched" if checked.source in _MATCHED_SOURCES else "Fallback"
    receipt = CapturedApplicationReceipt(
        capture_hash=checked.capture_hash,
        geometry_hash=checked.geometry_hash,
        event_count=checked.event_count,
        maker_key=checked.matched_input_key[0],
        model_key=checked.matched_input_key[1],
        method=method,
    )
    try:
        mapping = capture_to_mapping(checked)["match"]
    except (CaptureError, TypeError, AttributeError, KeyError):
        raise _closed() from None
    return receipt, mapping
