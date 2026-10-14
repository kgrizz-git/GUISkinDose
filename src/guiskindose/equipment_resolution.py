"""Runtime bridge: custom equipment-profile sessions into dose calculation (API slice).

Import-before-load only. When a frozen :class:`EquipmentProfileSession` is
bound on settings, raw exams resolve their homogeneous maker/model identity
in two phases around validation and zero-dose-row filtering — the effective
field-size mode lands before required-concept checks, and the published
record carries the final retained count — then all 15 effective leaves land
together before any geometry or field-size calculation. Nothing here mutates
bundled profile lists, attaches provenance to settings, or touches
already-loaded frames, the GUI, the CLI, or the export catalog.

Trust boundary: a :class:`EquipmentApplicationReceipt` is the only proof of
application. It binds the immutable record to the session hash, the canonical
identity, the retained count, and the effective settings materialized at
normalization time. Analysis validates the binding (session, identity, count,
live settings, record shape) before any single- or multi-exam calculation;
a bare :class:`CoordinateResolution` is never accepted as proof on its own.
"""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass, replace
from typing import Any

from guiskindose.equipment_profiles.bundled import bundled_coordinate_set
from guiskindose.equipment_profiles.constants import (
    MATCH_LEVEL_DEFAULT,
    MATCH_LEVEL_EXACT,
    MATCH_LEVEL_WILDCARD,
    MATCH_SOURCE_BUNDLED,
    MATCH_SOURCE_CUSTOM,
    MATCH_SOURCE_DEFAULT,
    SOURCE_KINDS,
)
from guiskindose.equipment_profiles.matches import (
    CoordinateMatchRecord,
    LeafProvenance,
    MatchedInputKey,
)
from guiskindose.equipment_profiles.preparation import prepare_bundled_context
from guiskindose.equipment_profiles.resolver import (
    LEAF_ORDER,
    CoordinateResolution,
    ExamCoordinateIdentity,
    NoticeEntry,
    ResolutionNotice,
    resolve_with_prepared,
)
from guiskindose.equipment_profiles.session import EquipmentProfileSession
from guiskindose.exam_identity import canonical_identity_pairs

__all__ = [
    "EquipmentApplicationReceipt",
    "apply_resolution_to_settings",
    "begin_session_application",
    "bind_receipt_frame",
    "check_session_input_compatible",
    "finalize_session_application",
    "receipt_to_mapping",
    "resolve_exam_coordinates",
    "restore_receipt_to_settings",
    "validate_application_receipt",
    "validate_receipt_binding",
]

#: Input schemas that already carry transformed geometry and therefore can
#: never take a coordinate session (closed vocabulary for diagnostics).
_PRETRANSFORMED_SCHEMAS = ("normalized", "preparsed_json")

#: Lowercase hex content hashes, as in the profile core.
_HEX_64_RE = re.compile(r"\A[0-9a-f]{64}\Z")

#: Canonical leaf paths, for record-shape validation at the boundary.
_LEAF_PATHS = frozenset(LEAF_ORDER)

#: Closed source/level vocabularies for record-shape validation.
_SOURCES = (MATCH_SOURCE_CUSTOM, MATCH_SOURCE_BUNDLED, MATCH_SOURCE_DEFAULT)
_LEVELS = (MATCH_LEVEL_EXACT, MATCH_LEVEL_WILDCARD, MATCH_LEVEL_DEFAULT)
_NOTICE_KINDS = ("complete", "partial")
_SETTINGS_MISMATCH = "Live normalization settings no longer match the proven resolution."


@dataclass(frozen=True, slots=True, repr=False)
class EquipmentApplicationReceipt:
    """Proof that a session resolved against one retained exam frame.

    Binds the immutable record to the session hash used, the canonical
    identity resolved, the final retained event count, the raw and matched
    identity spellings, and nothing else. The repr shows the event count and
    the closed-vocabulary method only — never keys, IDs, labels, or hashes.
    """

    resolution: CoordinateResolution
    session_hash: str
    maker_key: str
    model_key: str
    event_count: int
    input_maker: str
    input_model: str
    matched_maker: str
    matched_model: str
    frame_hash: str = ""

    @property
    def method(self) -> str:
        """Closed-vocabulary selection method for summaries."""
        return "Matched" if self.resolution.record.source in ("custom", "bundled") else "Fallback"

    def __repr__(self) -> str:
        return f"EquipmentApplicationReceipt(events={self.event_count!r}, method={self.method!r})"


def _session_or_none(settings: Any) -> EquipmentProfileSession | None:
    """Return the bound session, failing closed on a mis-typed attribute."""
    session = getattr(settings, "equipment_profile_session", None)
    if session is None:
        return None
    if not isinstance(session, EquipmentProfileSession):
        raise ValueError(
            "equipment_profile_session must be an EquipmentProfileSession or None, "
            f"not {type(session).__name__}."
        )
    return session


def check_session_input_compatible(*, schema: str, session: EquipmentProfileSession | None) -> None:
    """Refuse a nonempty coordinate session on pre-transformed input.

    The ``normalized`` tabular schema and preparsed ``.json`` frames already
    carry transformed geometry with no raw fields to re-derive from, so a
    session would either silently do nothing or normalize twice. Both fail
    closed with a value-free error instead. Empty sessions and raw inputs
    always pass through.
    """
    if session is None or len(session.profiles) == 0:
        return
    if schema not in _PRETRANSFORMED_SCHEMAS:
        return
    raise ValueError(
        f"Equipment-profile sessions require raw input; the {schema!r} schema carries "
        "pre-transformed geometry with no raw fields to re-derive. Load the raw DICOM "
        "or a raw-shaped tabular export instead."
    )


def _raw_identity(data_parsed: Any) -> tuple[str | None, str | None]:
    """First-row maker/model as text-or-missing (never stringified Nones)."""
    maker_column = data_parsed.get("Manufacturer")
    maker_value = maker_column.iloc[0] if maker_column is not None else None
    model_column = data_parsed.get("ManufacturerModelName")
    model_value = model_column.iloc[0] if model_column is not None else None
    maker = maker_value if isinstance(maker_value, str) else None
    model = model_value if isinstance(model_value, str) else None
    return maker, model


def resolve_exam_coordinates(
    *,
    manufacturer: str | None,
    model: str | None,
    event_count: int,
    session: EquipmentProfileSession,
    bundled_entries: list[dict[str, Any]],
) -> tuple[CoordinateResolution, str, str]:
    """Resolve one retained exam's identity against a session over bundled entries.

    The bundled entries (the live normalization list) compile fresh on every
    call, so resolution can never go stale; the session side stays exactly as
    assembled. Returns the resolution plus the selected source's (maker, model)
    display names, looked up by exact profile ID — custom names its profile,
    bundled names its entry exactly as runtime matching would, Default names
    itself. Raises value-free errors throughout.
    """
    bundled = prepare_bundled_context(bundled_coordinate_set(bundled_entries))
    resolution = resolve_with_prepared(
        identity=ExamCoordinateIdentity(
            manufacturer=manufacturer, model=model, event_count=event_count
        ),
        custom=session.prepared,
        bundled=bundled,
    )
    matched_maker, matched_model = _matched_names(resolution, session, bundled)
    return resolution, matched_maker, matched_model


def _matched_names(
    resolution: CoordinateResolution,
    session: EquipmentProfileSession,
    bundled: Any,
) -> tuple[str, str]:
    """(maker, model) display names of the selected source, by exact profile ID."""
    record = resolution.record
    entries = session.prepared.entries if record.source == "custom" else bundled.entries
    if record.source in ("custom", "bundled"):
        return _entry_names(entries, record.profile_id)
    return "Default", "Default"


def _entry_names(entries: Any, profile_id: str) -> tuple[str, str]:
    """Return permitted display names for an existing compiled entry."""
    for entry in entries:
        if entry.profile.profile_id == profile_id:
            return entry.profile.manufacturer, entry.profile.models[0]
    raise ValueError("Equipment-profile resolution names an unavailable entry.")


def _apply_record_to_settings(
    resolution: CoordinateResolution,
    norm: Any,
    *,
    input_maker: str,
    input_model: str,
    matched_maker: str,
    matched_model: str,
) -> None:
    """Apply all 15 effective leaves plus summary labels to live settings.

    Uses the existing coordinate setters without touching baseline profile
    lists, then refreshes the cached summary string. Every call rewrites every
    field, so reused settings objects cannot retain stale offsets, signs,
    swap, labels, or summaries from a previous exam.
    """
    values = {leaf.field: leaf.value for leaf in resolution.record.fields}
    norm.trans_offset.update_translation_offset(
        {axis: values[f"translation_offset.{axis}"] for axis in ("x", "y", "z")}
    )
    norm.trans_dir.update_translation_direction(
        {axis: values[f"translation_direction.{axis}"] for axis in ("x", "y", "z")}
    )
    norm.rot_dir.update_rotation_direction(
        {key: values[f"rotation_direction.{key}"] for key in ("Ap1", "Ap2", "Ap3", "At1", "At2", "At3")}
    )
    norm.field_size_mode = values["field_size_mode"]
    norm.detector_side_length = values["detector_side_length"]
    norm.swap_lateral_longitudinal = bool(values["swap_lateral_longitudinal"])
    norm.input_manufacturer = input_maker
    norm.input_model = input_model
    norm.matched_manufacturer = matched_maker
    norm.matched_model = matched_model
    norm.normalization_method = (
        "Matched" if resolution.record.source in ("custom", "bundled") else "Fallback"
    )
    norm.update_attrs_str()


def apply_resolution_to_settings(
    resolution: CoordinateResolution,
    norm: Any,
    *,
    input_maker: str,
    input_model: str,
    matched_maker: str,
    matched_model: str,
) -> None:
    """Apply a resolution to live settings (see :func:`_apply_record_to_settings`)."""
    _apply_record_to_settings(
        resolution,
        norm,
        input_maker=input_maker,
        input_model=input_model,
        matched_maker=matched_maker,
        matched_model=matched_model,
    )


def restore_receipt_to_settings(receipt: EquipmentApplicationReceipt, norm: Any) -> None:
    """Re-apply a validated receipt's effective values to live settings.

    Used per exam before calculation when settings objects are shared across
    exams: each exam restores exactly what its own receipt proved, so detector
    size, field-size mode, swap, signs, offsets, and labels can never leak
    from a sibling exam. Idempotent.
    """
    if not isinstance(receipt, EquipmentApplicationReceipt):
        raise ValueError(
            "Equipment-profile receipt must be an EquipmentApplicationReceipt, "
            f"not {type(receipt).__name__}."
        )
    _apply_record_to_settings(
        receipt.resolution,
        norm,
        input_maker=receipt.input_maker,
        input_model=receipt.input_model,
        matched_maker=receipt.matched_maker,
        matched_model=receipt.matched_model,
    )


def begin_session_application(*, data_parsed: Any, settings: Any) -> bool:
    """Phase 1 (pre-filter): resolve with the pre-filter count and apply everything.

    Runs after bundled selection but before required-concept validation, so
    enforcement sees the effective custom field-size mode. Returns whether a
    session applied; the published record always comes from phase 2.
    """
    session = _session_or_none(settings)
    if session is None or len(session.profiles) == 0:
        return False
    if len(data_parsed) == 0:
        raise ValueError("No irradiation events remain for the equipment-profile application.")
    norm = settings.normalization_settings
    maker, model = _raw_identity(data_parsed)
    resolution, matched_maker, matched_model = resolve_exam_coordinates(
        manufacturer=maker,
        model=model,
        event_count=len(data_parsed),
        session=session,
        bundled_entries=norm.normalization_settings_list,
    )
    apply_resolution_to_settings(
        resolution,
        norm,
        input_maker=maker or "",
        input_model=model or "",
        matched_maker=matched_maker,
        matched_model=matched_model,
    )
    return True


def finalize_session_application(
    *, data_parsed: Any, settings: Any, applied: bool
) -> EquipmentApplicationReceipt | None:
    """Phase 2 (post-filter): publish the receipt for the final retained frame.

    Re-resolves when filtering dropped rows so the affected count is exact;
    fails closed when nothing was retained. Only this receipt may be
    published — never the provisional phase-1 record.
    """
    if not applied:
        return None
    session = _session_or_none(settings)
    if session is None or len(session.profiles) == 0:
        raise ValueError(
            "Custom equipment-profile state changed during normalization; refusing to publish."
        )
    retained = len(data_parsed)
    if retained == 0:
        raise ValueError(
            "A custom equipment-profile session is configured but no irradiation events "
            "were retained after validation; nothing to resolve."
        )
    norm = settings.normalization_settings
    maker, model = _raw_identity(data_parsed)
    resolution, matched_maker, matched_model = resolve_exam_coordinates(
        manufacturer=maker,
        model=model,
        event_count=retained,
        session=session,
        bundled_entries=norm.normalization_settings_list,
    )
    apply_resolution_to_settings(
        resolution,
        norm,
        input_maker=maker or "",
        input_model=model or "",
        matched_maker=matched_maker,
        matched_model=matched_model,
    )
    identity = ExamCoordinateIdentity(manufacturer=maker, model=model, event_count=retained)
    return EquipmentApplicationReceipt(
        resolution=resolution,
        session_hash=session.active_set_hash,
        maker_key=identity.manufacturer_key,
        model_key=identity.model_key,
        event_count=retained,
        input_maker=maker or "",
        input_model=model or "",
        matched_maker=matched_maker,
        matched_model=matched_model,
    )


def bind_receipt_frame(receipt: EquipmentApplicationReceipt, frame: Any) -> EquipmentApplicationReceipt:
    """Bind successful normalized geometry and its final retained count."""
    if len(frame) == 0:
        raise ValueError("No irradiation events remain for the equipment-profile application.")
    resolution = replace(
        receipt.resolution,
        record=replace(receipt.resolution.record, affected_event_count=len(frame)),
    )
    return EquipmentApplicationReceipt(
        resolution=resolution, session_hash=receipt.session_hash,
        maker_key=receipt.maker_key, model_key=receipt.model_key, event_count=len(frame),
        input_maker=receipt.input_maker, input_model=receipt.input_model,
        matched_maker=receipt.matched_maker, matched_model=receipt.matched_model,
        frame_hash=_geometry_hash(frame),
    )


def _geometry_hash(frame: Any) -> str:
    """Fingerprint normalized numeric geometry, excluding restricted identifiers."""
    import pandas as pd

    columns = ("Tx", "Ty", "Tz", "Ap1", "Ap2", "Ap3", "At1", "At2", "At3", "kVp", "DSL", "FS_lat", "FS_long", "DSD", "DSI", "DID", "DSIRP")
    if not all(column in frame.columns for column in columns):
        raise ValueError("Equipment-profile application requires complete normalized geometry.")
    try:
        values = pd.util.hash_pandas_object(frame.loc[:, list(columns)], index=False).to_numpy().tobytes()
    except (TypeError, ValueError):
        raise ValueError("Equipment-profile application holds invalid normalized geometry.") from None
    return hashlib.sha256(values).hexdigest()


def _check_text(value: Any, field: str) -> str:
    """Require a string field on a hand-built record; never echo the value."""
    if type(value) is not str:
        raise ValueError(f"Equipment-profile record field {field!r} must be text.")
    return value


def _check_hash(value: Any, field: str) -> str:
    """Require a lowercase hex content hash; never echo the value."""
    if type(value) is not str or _HEX_64_RE.match(value) is None:
        raise ValueError(f"Equipment-profile record field {field!r} must be a content hash.")
    return value


def _check_leaf(leaf: Any) -> None:
    """Validate one provenance leaf's shape and closed vocabularies."""
    if not isinstance(leaf, LeafProvenance):
        raise ValueError("Equipment-profile match fields must be leaf provenance records.")
    if type(leaf.field) is not str or leaf.field not in _LEAF_PATHS:
        raise ValueError("Equipment-profile match holds an unknown coordinate field.")
    _check_leaf_value(leaf.field, leaf.value)
    if leaf.source not in _SOURCES or leaf.level not in _LEVELS:
        raise ValueError("Equipment-profile match holds an unknown source or level.")
    _check_text(leaf.profile_id, "profile_id")
    if leaf.source_kind not in SOURCE_KINDS:
        raise ValueError("Equipment-profile match holds an unknown source kind.")
    _check_hash(leaf.profile_hash, "profile_hash")
    if leaf.revision is not None and (type(leaf.revision) is not int or leaf.revision < 1):
        raise ValueError("Equipment-profile match holds an invalid revision.")
    if type(leaf.inherited) is not bool:
        raise ValueError("Equipment-profile match holds an invalid inheritance flag.")


def _check_leaf_value(field: str, value: Any) -> None:
    """Enforce the canonical scalar type for each coordinate leaf."""
    if field == "swap_lateral_longitudinal":
        valid = type(value) is bool
    elif field == "field_size_mode":
        valid = type(value) is str and value in ("CFA", "ASD")
    elif field.startswith(("translation_direction.", "rotation_direction.")):
        valid = type(value) is str and value in ("+", "-")
    else:
        valid = type(value) is float and math.isfinite(value)
    if not valid:
        raise ValueError("Equipment-profile match holds an invalid leaf value.")


def _check_notice(notice: Any) -> None:
    """Validate a notice's shape; entries name permitted fields only."""
    if not isinstance(notice, ResolutionNotice):
        raise ValueError("Equipment-profile match holds an invalid notice.")
    if notice.kind not in _NOTICE_KINDS:
        raise ValueError("Equipment-profile match holds an unknown notice kind.")
    if type(notice.entries) is not tuple:
        raise ValueError("Equipment-profile match holds invalid notice entries.")
    for item in notice.entries:
        if not isinstance(item, NoticeEntry):
            raise ValueError("Equipment-profile match holds an invalid notice entry.")
        if item.field not in _LEAF_PATHS:
            raise ValueError("Equipment-profile notice names an unknown field.")
        if item.source not in _SOURCES or item.level not in _LEVELS:
            raise ValueError("Equipment-profile notice names an unknown source or level.")
        _check_text(item.profile_id, "profile_id")
        _check_text(item.label, "label")
    if type(notice.text) is not str:
        raise ValueError("Equipment-profile match holds an invalid notice text.")


def _check_record_shape(resolution: Any) -> CoordinateResolution:
    """Validate a hand-built record's full shape before it may serialize."""
    if not isinstance(resolution, CoordinateResolution):
        raise ValueError(
            "Equipment-profile resolution must be a CoordinateResolution, "
            f"not {type(resolution).__name__}."
        )
    record = resolution.record
    if not isinstance(record, CoordinateMatchRecord):
        raise ValueError("Equipment-profile match holds an invalid record.")
    _check_text(record.profile_id, "profile_id")
    if record.source not in _SOURCES or record.level not in _LEVELS:
        raise ValueError("Equipment-profile match holds an unknown source or level.")
    if record.source_kind not in SOURCE_KINDS:
        raise ValueError("Equipment-profile match holds an unknown source kind.")
    _check_hash(record.profile_hash, "profile_hash")
    if not isinstance(record.matched_input_key, MatchedInputKey):
        raise ValueError("Equipment-profile match holds an invalid matched key.")
    _check_text(record.matched_input_key.manufacturer, "matched_input_key")
    _check_text(record.matched_input_key.model, "matched_input_key")
    if type(record.affected_event_count) is not int or record.affected_event_count < 0:
        raise ValueError("Equipment-profile match holds an invalid event count.")
    if type(record.fields) is not tuple or len(record.fields) != len(LEAF_ORDER):
        raise ValueError("Equipment-profile match must carry all 15 leaves.")
    if tuple(leaf.field for leaf in record.fields if isinstance(leaf, LeafProvenance)) != tuple(LEAF_ORDER):
        raise ValueError("Equipment-profile match leaves are out of order.")
    for leaf in record.fields:
        _check_leaf(leaf)
    _check_notice(resolution.notice)
    return resolution


def _check_custom_membership(resolution: CoordinateResolution, session: EquipmentProfileSession) -> None:
    """A custom match must name a profile the session actually holds."""
    if resolution.record.source != "custom":
        return
    if resolution.record.profile_id not in {entry.profile.profile_id for entry in session.prepared.entries}:
        raise ValueError(
            "Equipment-profile match names a custom profile the session does not hold."
        )


def validate_receipt_binding(*, receipt: Any, frame: Any, settings: Any) -> EquipmentProfileSession:
    """Validate a receipt's binding except live-settings currency.

    Checks the receipt type, the session type and hash, the frame's canonical
    identity and retained count, and the record shape — all value-free. Skips
    the live-settings comparison, so multi-exam preflights can validate every
    exam up front while the shared settings object still holds another exam's
    values. Returns the validated session. Raises on the first breach.
    """
    if not isinstance(receipt, EquipmentApplicationReceipt):
        raise ValueError(
            "Equipment-profile receipt must be an EquipmentApplicationReceipt, "
            f"not {type(receipt).__name__}."
        )
    session = _session_or_none(settings)
    if session is None or len(session.profiles) == 0:
        raise ValueError(
            "Equipment-profile receipt has no configured session to validate against."
        )
    if receipt.session_hash != session.active_set_hash:
        raise ValueError(
            "Equipment-profile receipt was produced for a different session."
        )
    pairs = canonical_identity_pairs(frame)
    if len(pairs) != 1:
        raise ValueError(
            "Equipment-profile receipt needs a homogeneous exam frame."
        )
    maker_key, model_key = pairs[0]
    if (maker_key or "", model_key or "") != (receipt.maker_key, receipt.model_key):
        raise ValueError(
            "Equipment-profile receipt identity does not match the exam frame."
        )
    if len(frame) != receipt.event_count:
        raise ValueError(
            "Equipment-profile receipt event count does not match the exam frame."
        )
    _check_record_shape(receipt.resolution)
    _check_custom_membership(receipt.resolution, session)
    if receipt.frame_hash != _geometry_hash(frame):
        raise ValueError("Equipment-profile receipt geometry does not match the exam frame.")
    expected, matched_maker, matched_model = resolve_exam_coordinates(
        manufacturer=receipt.input_maker, model=receipt.input_model,
        event_count=receipt.event_count, session=session,
        bundled_entries=settings.normalization_settings.normalization_settings_list,
    )
    if receipt.resolution != expected or (receipt.matched_maker, receipt.matched_model) != (matched_maker, matched_model):
        raise ValueError("Equipment-profile receipt does not match the resolved session content.")
    return session


def validate_application_receipt(*, receipt: Any, frame: Any, settings: Any) -> EquipmentProfileSession:
    """Validate a receipt's full binding before any calculation using it.

    Binding checks plus the live-settings comparison: the settings object
    must still carry exactly what the receipt proved. Returns the validated
    session for downstream serialization. Raises on the first breach.
    """
    session = validate_receipt_binding(receipt=receipt, frame=frame, settings=settings)
    _check_norm_matches_receipt(receipt, settings.normalization_settings)
    return session


def receipt_to_mapping(*, receipt: Any, frame: Any, settings: Any) -> dict[str, Any]:
    """Validate a receipt's full binding, then serialize it for results."""
    session = validate_application_receipt(receipt=receipt, frame=frame, settings=settings)
    return _resolution_to_mapping(receipt.resolution, session)


def _leaf_effective_value(record: CoordinateResolution, dotted_path: str) -> Any:
    """Effective value of one leaf from a validated record."""
    for leaf in record.record.fields:
        if leaf.field == dotted_path:
            return leaf.value
    raise ValueError("Equipment-profile match is missing a coordinate field.")


def _sign_value(value: Any) -> int:
    """Map a direction sign to its multiplier, failing closed on anything else."""
    if value == "+":
        return 1
    if value == "-":
        return -1
    raise ValueError(_SETTINGS_MISMATCH)


def _check_norm_geometry(receipt: EquipmentApplicationReceipt, norm: Any) -> None:
    """Offsets, directions, and rotations must match the proven leaves exactly."""
    record = receipt.resolution
    try:
        for axis in ("x", "y", "z"):
            if getattr(norm.trans_offset, axis) != _leaf_effective_value(record, f"translation_offset.{axis}"):
                raise ValueError(_SETTINGS_MISMATCH)
        for axis in ("x", "y", "z"):
            if getattr(norm.trans_dir, axis) != _sign_value(
                _leaf_effective_value(record, f"translation_direction.{axis}")
            ):
                raise ValueError(_SETTINGS_MISMATCH)
        for key in ("Ap1", "Ap2", "Ap3", "At1", "At2", "At3"):
            if getattr(norm.rot_dir, key) != _sign_value(
                _leaf_effective_value(record, f"rotation_direction.{key}")
            ):
                raise ValueError(_SETTINGS_MISMATCH)
    except AttributeError:
        raise ValueError(
            _SETTINGS_MISMATCH
        ) from None


def _check_norm_modes(receipt: EquipmentApplicationReceipt, norm: Any) -> None:
    """Field-size mode, detector size, and swap must match the proven leaves."""
    record = receipt.resolution
    try:
        if norm.field_size_mode != _leaf_effective_value(record, "field_size_mode"):
            raise ValueError(_SETTINGS_MISMATCH)
        if norm.detector_side_length != _leaf_effective_value(record, "detector_side_length"):
            raise ValueError(_SETTINGS_MISMATCH)
        if bool(norm.swap_lateral_longitudinal) != bool(_leaf_effective_value(record, "swap_lateral_longitudinal")):
            raise ValueError(_SETTINGS_MISMATCH)
    except AttributeError:
        raise ValueError(
            _SETTINGS_MISMATCH
        ) from None


def _check_norm_labels(receipt: EquipmentApplicationReceipt, norm: Any) -> None:
    """Summary labels must match the proven receipt."""
    try:
        if norm.input_manufacturer != receipt.input_maker or norm.input_model != receipt.input_model:
            raise ValueError(_SETTINGS_MISMATCH)
        if norm.matched_manufacturer != receipt.matched_maker or norm.matched_model != receipt.matched_model:
            raise ValueError(_SETTINGS_MISMATCH)
    except AttributeError:
        raise ValueError(
            _SETTINGS_MISMATCH
        ) from None


def _check_norm_matches_receipt(receipt: EquipmentApplicationReceipt, norm: Any) -> None:
    """The live settings must still carry exactly what the receipt proved."""
    _check_norm_geometry(receipt, norm)
    _check_norm_modes(receipt, norm)
    _check_norm_labels(receipt, norm)


def _resolution_to_mapping(
    resolution: CoordinateResolution, session: EquipmentProfileSession | None
) -> dict[str, Any]:
    """Serialize one resolution plus session context into default-safe mappings.

    Validates the record shape first, so malformed records fail closed instead
    of leaking arbitrary payloads. Carries the match record, the
    complete/partial notice, the active-set hash, and the session provenance
    summary — identifiers, hashes, and counts only, never paths, notes, raw
    text, station, or serial values.
    """
    _check_record_shape(resolution)
    if session is not None:
        if not isinstance(session, EquipmentProfileSession):
            raise ValueError(
                "Equipment session must be an EquipmentProfileSession or None, "
                f"not {type(session).__name__}."
            )
        _check_custom_membership(resolution, session)
    record = resolution.record
    notice = resolution.notice
    mapping: dict[str, Any] = {
        "profile_id": record.profile_id,
        "source": record.source,
        "level": record.level,
        "source_kind": record.source_kind,
        "profile_hash": record.profile_hash,
        "revision": record.revision,
        "matched_input_key": record.matched_input_key.as_mapping(),
        "affected_event_count": record.affected_event_count,
        "fields": [
            {
                "field": leaf.field,
                "value": leaf.value,
                "source": leaf.source,
                "level": leaf.level,
                "profile_id": leaf.profile_id,
                "source_kind": leaf.source_kind,
                "profile_hash": leaf.profile_hash,
                "revision": leaf.revision,
                "inherited": leaf.inherited,
            }
            for leaf in record.fields
        ],
        "notice": {
            "kind": notice.kind,
            "entries": [
                {
                    "field": item.field,
                    "source": item.source,
                    "level": item.level,
                    "profile_id": item.profile_id,
                    "label": item.label,
                }
                for item in notice.entries
            ],
            "text": notice.text,
        },
    }
    if session is not None:
        mapping["active_set_hash"] = session.active_set_hash
        mapping["session"] = {
            "total_profiles": session.provenance.total_profiles,
            "total_rows": session.provenance.total_rows,
            "sources": [
                {
                    "kind": source.kind,
                    "format": source.format,
                    "source_hash": source.source_hash,
                    "profile_ids": list(source.profile_ids),
                    "revisions": [list(pair) for pair in source.revisions],
                    "profile_count": source.profile_count,
                    "logical_rows": source.logical_rows,
                }
                for source in session.provenance.sources
            ],
        }
    return mapping
