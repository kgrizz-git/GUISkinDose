"""Full-v1 structural validation: a parsed document mapping to immutable canonical profiles.

Validation is deliberately strict. It rejects unknown keys at every level, treats ``null`` as a structural
error rather than as omission, refuses booleans where numbers are required and numbers where booleans are
required, rejects non-finite numbers and out-of-range values, requires strict calendar dates, and never
echoes an unknown user key into an error. Every rejection is a value-free :class:`EquipmentProfileError`.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from datetime import date
from typing import Any

from guiskindose.equipment_profiles.constants import (
    ACQUISITION_PLANES,
    AXIS_FIELDS,
    DETECTOR_SIDE_LENGTH,
    DETECTOR_SIDE_LENGTH_MAX,
    DETECTOR_SIDE_LENGTH_MIN_EXCLUSIVE,
    ENVELOPE_KEYS,
    EVIDENCE_STATUSES,
    FIELD_SIZE_MODE,
    FIELD_SIZE_MODES,
    FILTRATION_MMAL_MAX,
    FILTRATION_MMCU_MAX,
    K_PATIENT_SUPPORT_MAX,
    K_PATIENT_SUPPORT_MIN_EXCLUSIVE,
    KVP_MAX,
    KVP_MIN_EXCLUSIVE,
    MAX_ALIASES,
    MAX_LONG_TEXT,
    MAX_MODELS,
    MAX_PROFILES,
    MAX_SHORT_TEXT,
    MAX_SOURCE_TEXT,
    MAX_TRANSMISSION_ROWS,
    OFFSET_MAX,
    OFFSET_MIN,
    PLANE_WILDCARD,
    PROFILE_ID_PATTERN,
    PROFILE_KEYS,
    PROVENANCE_KEYS,
    ROTATION_LEAVES,
    SCHEMA_VERSION,
    SIGN_VALUES,
    SWAP_LATERAL_LONGITUDINAL,
    TRANSLATION_DIRECTION,
    TRANSLATION_OFFSET,
    TRANSMISSION_KEYS,
)
from guiskindose.equipment_profiles.errors import EquipmentProfileError, ProfileErrorCode
from guiskindose.equipment_profiles.keys import is_wildcard_model, normalize_manufacturer_key, normalize_model_key
from guiskindose.equipment_profiles.models import (
    Coordinates,
    Profile,
    Provenance,
    RotationDirection,
    TranslationDirection,
    TranslationOffset,
    TransmissionRow,
)

_DATE_PATTERN = re.compile(r"\A\d{4}-\d{2}-\d{2}\Z")
_PROFILE_ID_RE = re.compile(r"\A" + PROFILE_ID_PATTERN + r"\Z")

#: The six coordinate block names, in canonical documentation order.
COORDINATE_BLOCK_NAMES = (
    TRANSLATION_OFFSET,
    TRANSLATION_DIRECTION,
    "rotation_direction",
    SWAP_LATERAL_LONGITUDINAL,
    FIELD_SIZE_MODE,
    DETECTOR_SIDE_LENGTH,
)

#: Rotation leaf JSON key spelling, derived from the shared leaf table.
_ROTATION_KEYS = tuple(json_name for _field_name, json_name in ROTATION_LEAVES)


def _reject_null(value: Any, field_path: tuple[str, ...], source_kind: str) -> None:
    if value is None:
        raise EquipmentProfileError(ProfileErrorCode.INVALID_TYPE, source_kind=source_kind, field_path=field_path)


def _require_mapping(
    value: Any,
    field_path: tuple[str, ...],
    source_kind: str,
    *,
    code: ProfileErrorCode = ProfileErrorCode.INVALID_TYPE,
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise EquipmentProfileError(code, source_kind=source_kind, field_path=field_path)
    return value


def _require_sequence(value: Any, field_path: tuple[str, ...], source_kind: str) -> Sequence[Any]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise EquipmentProfileError(ProfileErrorCode.INVALID_TYPE, source_kind=source_kind, field_path=field_path)
    return value


def _reject_unknown_keys(
    raw: Mapping[str, Any],
    allowed: frozenset[str],
    field_path: tuple[str, ...],
    source_kind: str,
) -> None:
    for key in raw:
        if key not in allowed:
            raise EquipmentProfileError(
                ProfileErrorCode.UNKNOWN_FIELD,
                source_kind=source_kind,
                field_path=field_path,
            )


def _require_text(
    value: Any,
    field_path: tuple[str, ...],
    source_kind: str,
    *,
    max_length: int,
    allow_blank: bool,
) -> str:
    if not isinstance(value, str):
        raise EquipmentProfileError(ProfileErrorCode.INVALID_TYPE, source_kind=source_kind, field_path=field_path)
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        raise EquipmentProfileError(
            ProfileErrorCode.UNSUPPORTED_SOURCE_ENCODING, source_kind=source_kind, field_path=field_path
        ) from None
    if not allow_blank and not value:
        raise EquipmentProfileError(
            ProfileErrorCode.BLANK_REQUIRED_CELL, source_kind=source_kind, field_path=field_path
        )
    if len(value) > max_length:
        raise EquipmentProfileError(
            ProfileErrorCode.VALUE_OUT_OF_RANGE, source_kind=source_kind, field_path=field_path, count=max_length
        )
    return value


def _optional_text(
    value: Any,
    field_path: tuple[str, ...],
    source_kind: str,
    *,
    max_length: int,
) -> str | None:
    _reject_null(value, field_path, source_kind)
    text = _require_text(value, field_path, source_kind, max_length=max_length, allow_blank=True)
    return text or None


def _require_bool(value: Any, field_path: tuple[str, ...], source_kind: str) -> bool:
    if not isinstance(value, bool):
        raise EquipmentProfileError(ProfileErrorCode.INVALID_TYPE, source_kind=source_kind, field_path=field_path)
    return value


def _require_number(value: Any, field_path: tuple[str, ...], source_kind: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise EquipmentProfileError(ProfileErrorCode.INVALID_NUMBER, source_kind=source_kind, field_path=field_path)
    try:
        result = float(value)
    except (OverflowError, ValueError):
        # A JSON integer or a Python int too large for a double overflows here; it is not a finite number.
        raise EquipmentProfileError(
            ProfileErrorCode.INVALID_NUMBER, source_kind=source_kind, field_path=field_path
        ) from None
    if math.isnan(result) or result in (float("inf"), float("-inf")):
        raise EquipmentProfileError(ProfileErrorCode.INVALID_NUMBER, source_kind=source_kind, field_path=field_path)
    # Negative zero normalizes to +0.0 by exact IEEE addition (no comparison):
    # adding zero is exact for finite values and maps -0.0 to +0.0.
    return result + 0.0


def _require_range(
    value: float,
    field_path: tuple[str, ...],
    source_kind: str,
    *,
    minimum: float,
    maximum: float,
    exclusive_minimum: bool = False,
) -> float:
    if value < minimum or value > maximum:
        raise EquipmentProfileError(ProfileErrorCode.VALUE_OUT_OF_RANGE, source_kind=source_kind, field_path=field_path)
    if exclusive_minimum and value == minimum:
        raise EquipmentProfileError(
            ProfileErrorCode.VALUE_OUT_OF_RANGE, source_kind=source_kind, field_path=field_path
        )
    return value


def _require_enum(value: Any, allowed: tuple[str, ...], field_path: tuple[str, ...], source_kind: str) -> str:
    if not isinstance(value, str) or value not in allowed:
        raise EquipmentProfileError(ProfileErrorCode.INVALID_ENUM, source_kind=source_kind, field_path=field_path)
    return value


def validate_document(document: Any, *, source_kind: str) -> tuple[Profile, ...]:
    """Validate a whole document envelope and return its immutable profiles."""
    envelope = _require_mapping(
        document, (), source_kind, code=ProfileErrorCode.MALFORMED_JSON
    )
    _reject_unknown_keys(envelope, ENVELOPE_KEYS, (), source_kind)
    version = envelope.get("schema_version")
    if isinstance(version, bool) or not isinstance(version, int) or version != SCHEMA_VERSION:
        raise EquipmentProfileError(
            ProfileErrorCode.UNSUPPORTED_SCHEMA_VERSION,
            source_kind=source_kind,
            field_path=("schema_version",),
            count=SCHEMA_VERSION,
        )
    profiles = _require_sequence(envelope.get("profiles"), ("profiles",), source_kind)
    if not profiles:
        raise EquipmentProfileError(ProfileErrorCode.EMPTY_SOURCE, source_kind=source_kind, field_path=("profiles",))
    if len(profiles) > MAX_PROFILES:
        raise EquipmentProfileError(
            ProfileErrorCode.PROFILE_LIMIT_EXCEEDED, source_kind=source_kind, count=len(profiles)
        )
    return tuple(
        _validate_profile(raw, index, source_kind) for index, raw in enumerate(profiles)
    )


def _validate_profile(raw: Any, index: int, source_kind: str) -> Profile:
    mapping = _require_mapping(raw, (), source_kind)
    _reject_unknown_keys(mapping, PROFILE_KEYS, (), source_kind)
    context = _ProfileContext(source_kind, index)
    profile_id = _validate_profile_id(mapping.get("profile_id"), context)
    manufacturer = _validate_manufacturer(mapping.get("manufacturer"), context)
    models = _validate_models(mapping.get("models"), context)
    alias_context = _AliasContext(models, context)
    manufacturer_aliases = _validate_manufacturer_aliases(mapping, alias_context)
    model_aliases = _validate_model_aliases(mapping, alias_context)
    coordinates = _validate_coordinates(mapping, context)
    transmission = _validate_transmission(mapping, models, context)
    promote = _validate_promotion(mapping, models, context)
    if coordinates is None and not transmission:
        raise context.error(ProfileErrorCode.EMPTY_DOMAIN, ())
    return Profile(
        profile_id=profile_id,
        manufacturer=manufacturer,
        models=models,
        manufacturer_aliases=manufacturer_aliases,
        model_aliases=model_aliases,
        provenance=_validate_provenance(mapping, context),
        coordinates=coordinates,
        transmission=transmission,
        promote_coordinate_wildcard=promote,
    )


class _ProfileContext:
    """Row-level context shared by one profile's field validators."""

    __slots__ = ("index", "source_kind")

    def __init__(self, source_kind: str, index: int) -> None:
        self.source_kind = source_kind
        self.index = index

    def at(self, *path: str) -> tuple[str, ...]:
        return tuple(path)

    def error(self, code: ProfileErrorCode, field_path: tuple[str, ...], count: int | None = None) -> EquipmentProfileError:
        return EquipmentProfileError(
            code, source_kind=self.source_kind, field_path=field_path, row_index=self.index, count=count
        )


def _validate_profile_id(value: Any, context: _ProfileContext) -> str:
    path = context.at("profile_id")
    _reject_null(value, path, context.source_kind)
    text = _require_text(value, path, context.source_kind, max_length=MAX_SHORT_TEXT, allow_blank=False)
    if not _PROFILE_ID_RE.match(text):
        raise context.error(ProfileErrorCode.INVALID_PROFILE_ID, path)
    return text


def _validate_manufacturer(value: Any, context: _ProfileContext) -> str:
    path = context.at("manufacturer")
    _reject_null(value, path, context.source_kind)
    text = _require_text(value, path, context.source_kind, max_length=MAX_SHORT_TEXT, allow_blank=False)
    if is_wildcard_model(text):
        raise context.error(ProfileErrorCode.INVALID_MANUFACTURER, path)
    if not normalize_manufacturer_key(text):
        raise context.error(ProfileErrorCode.INVALID_MANUFACTURER, path)
    return text


def _validate_models(value: Any, context: _ProfileContext) -> tuple[str, ...]:
    path = context.at("models")
    _reject_null(value, path, context.source_kind)
    items = _require_sequence(value, path, context.source_kind)
    if not items:
        raise context.error(ProfileErrorCode.INVALID_MODEL_LIST, path)
    if len(items) > MAX_MODELS:
        raise context.error(ProfileErrorCode.MODEL_LIMIT_EXCEEDED, path, count=len(items))
    models: list[str] = []
    seen: set[str] = set()
    for item in items:
        _reject_null(item, path, context.source_kind)
        text = _require_text(item, path, context.source_kind, max_length=MAX_SHORT_TEXT, allow_blank=False)
        # Only the exact ``"*"`` spelling (whitespace-tolerant) is the wildcard; it is canonicalized to that
        # spelling so the wildcard is never stored as a literal model name.
        canonical = PLANE_WILDCARD if is_wildcard_model(text) else text
        key = normalize_model_key(canonical)
        if not key:
            raise context.error(ProfileErrorCode.INVALID_MODEL_LIST, path)
        if key in seen:
            raise context.error(ProfileErrorCode.INVALID_MODEL_LIST, path)
        seen.add(key)
        models.append(canonical)
    if PLANE_WILDCARD in models and models != [PLANE_WILDCARD]:
        raise context.error(ProfileErrorCode.WILDCARD_NOT_PERMITTED, path)
    return tuple(models)


class _AliasContext:
    """Alias validation inputs shared by the manufacturer and model alias validators."""

    __slots__ = ("context", "models", "normalized_models")

    def __init__(self, models: tuple[str, ...], context: _ProfileContext) -> None:
        self.models = models
        self.context = context
        self.normalized_models = {normalize_model_key(model): model for model in models}


def _validate_manufacturer_aliases(mapping: Mapping[str, Any], alias_context: _AliasContext) -> tuple[str, ...]:
    context = alias_context.context
    path = context.at("manufacturer_aliases")
    if "manufacturer_aliases" not in mapping:
        return ()
    value = mapping["manufacturer_aliases"]
    _reject_null(value, path, context.source_kind)
    items = _require_sequence(value, path, context.source_kind)
    if len(items) > MAX_ALIASES:
        raise context.error(ProfileErrorCode.ALIAS_LIMIT_EXCEEDED, path, count=len(items))
    aliases: list[str] = []
    seen: set[str] = set()
    for item in items:
        _reject_null(item, path, context.source_kind)
        text = _require_text(item, path, context.source_kind, max_length=MAX_SHORT_TEXT, allow_blank=False)
        key = normalize_manufacturer_key(text)
        if not key or key in seen:
            raise context.error(ProfileErrorCode.ALIAS_AMBIGUOUS_TARGET, path)
        seen.add(key)
        aliases.append(text)
    return tuple(aliases)


def _validate_model_aliases(mapping: Mapping[str, Any], alias_context: _AliasContext) -> tuple[tuple[str, str], ...]:
    context = alias_context.context
    path = context.at("model_aliases")
    if "model_aliases" not in mapping:
        return ()
    value = mapping["model_aliases"]
    _reject_null(value, path, context.source_kind)
    if isinstance(value, Mapping):
        return _validate_alias_map(value, alias_context)
    return _validate_alias_shorthand(value, alias_context)


def _validate_alias_map(
    value: Mapping[str, Any],
    alias_context: _AliasContext,
) -> tuple[tuple[str, str], ...]:
    context = alias_context.context
    path = context.at("model_aliases")
    if len(value) > MAX_ALIASES:
        raise context.error(ProfileErrorCode.ALIAS_LIMIT_EXCEEDED, path, count=len(value))
    pairs: list[tuple[str, str]] = []
    seen: set[str] = set()
    for alias, target in value.items():
        alias_text = _require_text(alias, path, context.source_kind, max_length=MAX_SHORT_TEXT, allow_blank=False)
        target_text = _require_text(target, path, context.source_kind, max_length=MAX_SHORT_TEXT, allow_blank=False)
        alias_key = normalize_model_key(alias_text)
        if not alias_key or alias_key in seen:
            raise context.error(ProfileErrorCode.ALIAS_AMBIGUOUS_TARGET, path)
        # The target resolves through the normalized key to the *listed* spelling, so a target written with an
        # equivalent normalized spelling canonicalizes to the same content as the single-model shorthand.
        resolved = alias_context.normalized_models.get(normalize_model_key(target_text))
        if resolved is None:
            raise context.error(ProfileErrorCode.ALIAS_TARGET_MISMATCH, path)
        _reject_alias_collides_with_a_different_model(alias_key, resolved, alias_context)
        seen.add(alias_key)
        pairs.append((alias_text, resolved))
    return tuple(pairs)


def _validate_alias_shorthand(
    value: Any,
    alias_context: _AliasContext,
) -> tuple[tuple[str, str], ...]:
    context = alias_context.context
    path = context.at("model_aliases")
    items = _require_sequence(value, path, context.source_kind)
    # An empty collection always means "no aliases", for every profile shape: multi-model and wildcard
    # profiles are not made ambiguous by an explicitly empty list.
    if not items:
        return ()
    if len(items) > MAX_ALIASES:
        raise context.error(ProfileErrorCode.ALIAS_LIMIT_EXCEEDED, path, count=len(items))
    if len(alias_context.models) != 1 or is_wildcard_model(alias_context.models[0]):
        raise context.error(ProfileErrorCode.ALIAS_AMBIGUOUS_TARGET, path)
    target = alias_context.models[0]
    pairs: list[tuple[str, str]] = []
    seen: set[str] = set()
    for item in items:
        _reject_null(item, path, context.source_kind)
        text = _require_text(item, path, context.source_kind, max_length=MAX_SHORT_TEXT, allow_blank=False)
        key = normalize_model_key(text)
        if not key or key in seen:
            raise context.error(ProfileErrorCode.ALIAS_AMBIGUOUS_TARGET, path)
        _reject_alias_collides_with_a_different_model(key, target, alias_context)
        seen.add(key)
        pairs.append((text, target))
    return tuple(pairs)


def _reject_alias_collides_with_a_different_model(
    alias_key: str,
    resolved_target: str,
    alias_context: _AliasContext,
) -> None:
    """Reject an alias that would be indistinguishable from a canonical model pointing elsewhere.

    An alias whose normalized key equals a *listed* model's normalized key, but which resolves to a different
    model, cannot be matched unambiguously. An alias that collides with the very model it names is harmless.
    """
    listed = alias_context.normalized_models.get(alias_key)
    if listed is not None and listed != resolved_target:
        raise alias_context.context.error(
            ProfileErrorCode.ALIAS_AMBIGUOUS_TARGET, alias_context.context.at("model_aliases")
        )


def _validate_promotion(mapping: Mapping[str, Any], models: tuple[str, ...], context: _ProfileContext) -> bool:
    path = context.at("promote_coordinate_wildcard")
    if "promote_coordinate_wildcard" not in mapping:
        return False
    flag = _require_bool(mapping["promote_coordinate_wildcard"], path, context.source_kind)
    if flag and models != ("*",):
        raise context.error(ProfileErrorCode.WILDCARD_NOT_PERMITTED, path)
    return flag


def _validate_provenance(mapping: Mapping[str, Any], context: _ProfileContext) -> Provenance | None:
    path = context.at("provenance")
    if "provenance" not in mapping:
        return None
    _reject_null(mapping["provenance"], path, context.source_kind)
    block = _require_mapping(mapping["provenance"], path, context.source_kind)
    _reject_unknown_keys(block, PROVENANCE_KEYS, path, context.source_kind)
    return Provenance(
        source=_text_from(block, "source", path, context, MAX_SOURCE_TEXT),
        notes=_text_from(block, "notes", path, context, MAX_LONG_TEXT),
    )


def _text_from(
    block: Mapping[str, Any], key: str, parent: tuple[str, ...], context: _ProfileContext, max_length: int
) -> str | None:
    if key not in block:
        return None
    field_path = (*parent, key)
    _reject_null(block[key], field_path, context.source_kind)
    text = _require_text(block[key], field_path, context.source_kind, max_length=max_length, allow_blank=True)
    return text or None


def _validate_coordinates(mapping: Mapping[str, Any], context: _ProfileContext) -> Coordinates | None:
    path = context.at("coordinates")
    if "coordinates" not in mapping:
        return None
    _reject_null(mapping["coordinates"], path, context.source_kind)
    block = _require_mapping(mapping["coordinates"], path, context.source_kind)
    _reject_unknown_keys(block, frozenset(COORDINATE_BLOCK_NAMES), path, context.source_kind)
    coordinates = Coordinates(
        translation_offset=_validate_axis_numbers(block, TRANSLATION_OFFSET, context),
        translation_direction=_validate_axis_signs(block, TRANSLATION_DIRECTION, context),
        rotation_direction=_validate_rotation_signs(block, context),
        swap_lateral_longitudinal=_validate_swap(block, context),
        field_size_mode=_validate_field_size_mode(block, context),
        detector_side_length=_validate_detector_side_length(block, context),
    )
    if coordinates.is_empty():
        raise context.error(ProfileErrorCode.EMPTY_COORDINATE_BLOCK, path)
    return coordinates


def _nested_block(
    block: Mapping[str, Any], name: str, allowed: tuple[str, ...], context: _ProfileContext
) -> Mapping[str, Any] | None:
    path = context.at("coordinates", name)
    if name not in block:
        return None
    _reject_null(block[name], path, context.source_kind)
    nested = _require_mapping(block[name], path, context.source_kind)
    _reject_unknown_keys(nested, frozenset(allowed), path, context.source_kind)
    return nested


def _validate_axis_numbers(
    block: Mapping[str, Any], name: str, context: _ProfileContext
) -> TranslationOffset | None:
    nested = _nested_block(block, name, AXIS_FIELDS, context)
    if nested is None:
        return None
    values: dict[str, float] = {}
    for axis in AXIS_FIELDS:
        path = context.at("coordinates", name, axis)
        if axis not in nested:
            continue
        _reject_null(nested[axis], path, context.source_kind)
        number = _require_number(nested[axis], path, context.source_kind)
        values[axis] = _require_range(number, path, context.source_kind, minimum=OFFSET_MIN, maximum=OFFSET_MAX)
    if not values:
        raise context.error(ProfileErrorCode.EMPTY_COORDINATE_BLOCK, context.at("coordinates", name))
    return TranslationOffset(**values)


def _validate_axis_signs(
    block: Mapping[str, Any], name: str, context: _ProfileContext
) -> TranslationDirection | None:
    nested = _nested_block(block, name, AXIS_FIELDS, context)
    if nested is None:
        return None
    values: dict[str, str] = {}
    for axis in AXIS_FIELDS:
        path = context.at("coordinates", name, axis)
        if axis not in nested:
            continue
        _reject_null(nested[axis], path, context.source_kind)
        values[axis] = _require_enum(nested[axis], SIGN_VALUES, path, context.source_kind)
    if not values:
        raise context.error(ProfileErrorCode.EMPTY_COORDINATE_BLOCK, context.at("coordinates", name))
    return TranslationDirection(**values)


def _validate_rotation_signs(block: Mapping[str, Any], context: _ProfileContext) -> RotationDirection | None:
    name = "rotation_direction"
    nested = _nested_block(block, name, _ROTATION_KEYS, context)
    if nested is None:
        return None
    values: dict[str, str] = {}
    for field_name, json_name in ROTATION_LEAVES:
        path = context.at("coordinates", name, json_name)
        if json_name not in nested:
            continue
        _reject_null(nested[json_name], path, context.source_kind)
        values[field_name] = _require_enum(nested[json_name], SIGN_VALUES, path, context.source_kind)
    if not values:
        raise context.error(ProfileErrorCode.EMPTY_COORDINATE_BLOCK, context.at("coordinates", name))
    return RotationDirection(**values)


def _validate_swap(block: Mapping[str, Any], context: _ProfileContext) -> bool | None:
    name = SWAP_LATERAL_LONGITUDINAL
    if name not in block:
        return None
    path = context.at("coordinates", name)
    _reject_null(block[name], path, context.source_kind)
    return _require_bool(block[name], path, context.source_kind)


def _validate_field_size_mode(block: Mapping[str, Any], context: _ProfileContext) -> str | None:
    name = FIELD_SIZE_MODE
    if name not in block:
        return None
    path = context.at("coordinates", name)
    _reject_null(block[name], path, context.source_kind)
    return _require_enum(block[name], FIELD_SIZE_MODES, path, context.source_kind)


def _validate_detector_side_length(block: Mapping[str, Any], context: _ProfileContext) -> float | None:
    name = DETECTOR_SIDE_LENGTH
    if name not in block:
        return None
    path = context.at("coordinates", name)
    _reject_null(block[name], path, context.source_kind)
    number = _require_number(block[name], path, context.source_kind)
    return _require_range(
        number,
        path,
        context.source_kind,
        minimum=DETECTOR_SIDE_LENGTH_MIN_EXCLUSIVE,
        maximum=DETECTOR_SIDE_LENGTH_MAX,
        exclusive_minimum=True,
    )


def _validate_transmission(
    mapping: Mapping[str, Any], models: tuple[str, ...], context: _ProfileContext
) -> tuple[TransmissionRow, ...]:
    path = context.at("transmission")
    if "transmission" not in mapping:
        return ()
    _reject_null(mapping["transmission"], path, context.source_kind)
    items = _require_sequence(mapping["transmission"], path, context.source_kind)
    if len(items) > MAX_TRANSMISSION_ROWS:
        raise context.error(ProfileErrorCode.ROW_LIMIT_EXCEEDED, path, count=len(items))
    return tuple(_validate_transmission_row(raw, models, context) for raw in items)


def _require_text_field(
    mapping: Mapping[str, Any],
    key: str,
    parent: tuple[str, ...],
    context: _ProfileContext,
    *,
    max_length: int,
) -> str:
    """Read a required, non-blank, bounded string field, reporting absence distinctly."""
    field_path = (*parent, key)
    if key not in mapping:
        raise context.error(ProfileErrorCode.MISSING_REQUIRED_FIELD, field_path)
    _reject_null(mapping[key], field_path, context.source_kind)
    return _require_text(mapping[key], field_path, context.source_kind, max_length=max_length, allow_blank=False)


def _validate_transmission_row(raw: Any, models: tuple[str, ...], context: _ProfileContext) -> TransmissionRow:
    path = context.at("transmission")
    mapping = _require_mapping(raw, path, context.source_kind)
    _reject_unknown_keys(mapping, TRANSMISSION_KEYS, path, context.source_kind)
    # A transmission row must name an actual listed model: the wildcard is never a valid target.
    device_model = _require_text_field(mapping, "device_model", path, context, max_length=MAX_SHORT_TEXT)
    if device_model not in models or is_wildcard_model(device_model):
        raise context.error(ProfileErrorCode.ALIAS_TARGET_MISMATCH, (*path, "device_model"))
    kvp = _transmission_number(mapping, "kvp_kv", path, context, KVP_MIN_EXCLUSIVE, KVP_MAX, exclusive=True)
    mmcu = _transmission_number(mapping, "filtration_added_mmcu", path, context, 0.0, FILTRATION_MMCU_MAX)
    mmal = _transmission_number(mapping, "filtration_added_mmal", path, context, 0.0, FILTRATION_MMAL_MAX)
    factor = _transmission_number(
        mapping, "k_patient_support", path, context, K_PATIENT_SUPPORT_MIN_EXCLUSIVE, K_PATIENT_SUPPORT_MAX,
        exclusive=True,
    )
    evidence = _require_enum_field(mapping, "evidence_status", path, context, EVIDENCE_STATUSES)
    source = _required_when_measured(mapping, "source", evidence, context, path, MAX_SOURCE_TEXT)
    row_date = _validate_row_date(mapping, evidence, context, path)
    return TransmissionRow(
        device_model=device_model,
        acquisition_plane=_require_enum_field(mapping, "acquisition_plane", path, context, ACQUISITION_PLANES),
        kvp_kv=kvp,
        filtration_added_mmcu=mmcu,
        filtration_added_mmal=mmal,
        k_patient_support=factor,
        evidence_status=evidence,
        source=source,
        date=row_date,
        comment=_text_from(mapping, "comment", path, context, MAX_LONG_TEXT),
    )


def _require_enum_field(
    mapping: Mapping[str, Any],
    key: str,
    parent: tuple[str, ...],
    context: _ProfileContext,
    allowed: tuple[str, ...],
) -> str:
    field_path = (*parent, key)
    if key not in mapping:
        raise context.error(ProfileErrorCode.MISSING_REQUIRED_FIELD, field_path)
    _reject_null(mapping[key], field_path, context.source_kind)
    return _require_enum(mapping[key], allowed, field_path, context.source_kind)


def _transmission_number(
    mapping: Mapping[str, Any],
    key: str,
    path: tuple[str, ...],
    context: _ProfileContext,
    minimum: float,
    maximum: float,
    *,
    exclusive: bool = False,
) -> float:
    field_path = (*path, key)
    if key not in mapping:
        raise context.error(ProfileErrorCode.MISSING_REQUIRED_FIELD, field_path)
    _reject_null(mapping[key], field_path, context.source_kind)
    number = _require_number(mapping[key], field_path, context.source_kind)
    return _require_range(
        number, field_path, context.source_kind, minimum=minimum, maximum=maximum, exclusive_minimum=exclusive
    )


def _required_when_measured(
    mapping: Mapping[str, Any],
    key: str,
    evidence: str,
    context: _ProfileContext,
    path: tuple[str, ...],
    max_length: int,
) -> str | None:
    field_path = (*path, key)
    if key not in mapping:
        if evidence == "measured":
            raise context.error(ProfileErrorCode.MISSING_REQUIRED_FIELD, field_path)
        return None
    _reject_null(mapping[key], field_path, context.source_kind)
    text = _require_text(mapping[key], field_path, context.source_kind, max_length=max_length, allow_blank=True)
    if evidence == "measured" and not text.strip():
        raise context.error(ProfileErrorCode.BLANK_REQUIRED_CELL, field_path)
    return text or None


def _validate_row_date(
    mapping: Mapping[str, Any], evidence: str, context: _ProfileContext, path: tuple[str, ...]
) -> str | None:
    field_path = (*path, "date")
    if "date" not in mapping:
        if evidence == "measured":
            raise context.error(ProfileErrorCode.MISSING_REQUIRED_FIELD, field_path)
        return None
    _reject_null(mapping["date"], field_path, context.source_kind)
    text = _require_text(mapping["date"], field_path, context.source_kind, max_length=16, allow_blank=False)
    if not _DATE_PATTERN.match(text):
        raise context.error(ProfileErrorCode.INVALID_DATE, field_path)
    try:
        date(int(text[0:4]), int(text[5:7]), int(text[8:10]))
    except ValueError:
        raise context.error(ProfileErrorCode.INVALID_DATE, field_path) from None
    return text
