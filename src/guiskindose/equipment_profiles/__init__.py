"""Equipment-profile core: immutable canonical models, JSON/in-memory parsing, and the capability gate.

This package is the stdlib-only core described by ``dev-docs/EQUIPMENT_PROFILE_SCHEMA.md``. It contains no
application wiring: no dose, normalization, GUI, CLI, or store path reads from it, and nothing here applies a
profile to a calculation. Adapters for CSV/TSV/XLSX, the user store, and activation are later slices.

Typical use::

    from guiskindose.equipment_profiles import (
        parse_json_file, combine_documents, check_initial_capabilities,
    )

    document = parse_json_file("profiles.json")
    profile_set = combine_documents([document])
    check_initial_capabilities(profile_set.profiles, source_kind=document.source_kind)

Privacy: every failure is a value-free :class:`EquipmentProfileError` with a stable code. No raw user value,
unknown key, file path, note, station name, or serial number reaches an error or a ``repr``.
"""

from __future__ import annotations

from guiskindose.equipment_profiles.canonical import (
    active_set_hash,
    canonical_json_bytes,
    canonical_profile_dict,
    profile_hash,
    source_bytes_hash,
)
from guiskindose.equipment_profiles.capability import (
    UNSUPPORTED_CAPABILITIES,
    check_initial_capabilities,
    first_unsupported_capability,
    supported_profiles,
)
from guiskindose.equipment_profiles.conflicts import (
    collect_identity_collisions,
    validate_profile_set,
)
from guiskindose.equipment_profiles.constants import (
    ACQUISITION_PLANES,
    COORDINATE_BLOCKS,
    COORDINATE_LEAF_COUNT,
    EVIDENCE_STATUSES,
    MAX_AGGREGATE_ROWS,
    MAX_ALIASES,
    MAX_JSON_DEPTH,
    MAX_MODELS,
    MAX_PROFILES,
    MAX_SHORT_TEXT,
    MAX_SOURCE_BYTES,
    MAX_SOURCE_TEXT,
    MAX_TRANSMISSION_ROWS,
    MAX_XLSX_SHEETS,
    SCHEMA_VERSION,
    SIGN_VALUES,
    SOURCE_KIND_JSON,
    SOURCE_KIND_MEMORY,
    SOURCE_KINDS,
)
from guiskindose.equipment_profiles.errors import (
    RESERVED_CODES,
    EquipmentProfileError,
    ProfileErrorCode,
    error_codes,
    is_implemented_code,
)
from guiskindose.equipment_profiles.keys import (
    is_wildcard_model,
    normalize_manufacturer_key,
    normalize_model_key,
)
from guiskindose.equipment_profiles.loading import (
    ParsedDocument,
    ProfileSet,
    combine_documents,
    parse_json_bytes,
    parse_json_file,
    parse_memory_document,
)
from guiskindose.equipment_profiles.matches import (
    CoordinateMatchRecord,
    LeafProvenance,
    MatchedInputKey,
    build_leaf_provenance,
    order_leaf_provenance,
)
from guiskindose.equipment_profiles.models import (
    Coordinates,
    Profile,
    Provenance,
    RotationDirection,
    TranslationDirection,
    TranslationOffset,
    TransmissionRow,
    coordinate_leaf_values,
)
from guiskindose.equipment_profiles.validation import validate_document

__all__ = [
    # Constants
    "ACQUISITION_PLANES",
    "COORDINATE_BLOCKS",
    "COORDINATE_LEAF_COUNT",
    "EVIDENCE_STATUSES",
    "MAX_AGGREGATE_ROWS",
    "MAX_ALIASES",
    "MAX_JSON_DEPTH",
    "MAX_MODELS",
    "MAX_PROFILES",
    "MAX_SHORT_TEXT",
    "MAX_SOURCE_BYTES",
    "MAX_SOURCE_TEXT",
    "MAX_TRANSMISSION_ROWS",
    "MAX_XLSX_SHEETS",
    "RESERVED_CODES",
    "SCHEMA_VERSION",
    "SIGN_VALUES",
    "SOURCE_KINDS",
    "SOURCE_KIND_JSON",
    "SOURCE_KIND_MEMORY",
    "UNSUPPORTED_CAPABILITIES",
    # Matches
    "CoordinateMatchRecord",
    # Models
    "Coordinates",
    # Errors
    "EquipmentProfileError",
    "LeafProvenance",
    "MatchedInputKey",
    # Parsing and loading
    "ParsedDocument",
    "Profile",
    "ProfileErrorCode",
    "ProfileSet",
    "Provenance",
    "RotationDirection",
    "TranslationDirection",
    "TranslationOffset",
    "TransmissionRow",
    "active_set_hash",
    "build_leaf_provenance",
    # Canonical form and hashes
    "canonical_json_bytes",
    "canonical_profile_dict",
    # Capability gate
    "check_initial_capabilities",
    "collect_identity_collisions",
    "combine_documents",
    "coordinate_leaf_values",
    "error_codes",
    "first_unsupported_capability",
    "is_implemented_code",
    # Keys
    "is_wildcard_model",
    "normalize_manufacturer_key",
    "normalize_model_key",
    "order_leaf_provenance",
    "parse_json_bytes",
    "parse_json_file",
    "parse_memory_document",
    "profile_hash",
    "source_bytes_hash",
    "supported_profiles",
    "validate_document",
    # Validation and conflicts
    "validate_profile_set",
]
