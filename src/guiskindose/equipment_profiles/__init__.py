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

from guiskindose.equipment_profiles.bundled import (
    BundledCoordinateSet,
    bundled_coordinate_set,
    bundled_profile_id,
)
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
    FLAT_COLUMNS,
    FLAT_COLUMNS_BY_RECORD_TYPE,
    FLAT_PROMOTION_COLUMN,
    FLAT_REQUIRED_COLUMNS_BY_RECORD_TYPE,
    IMPLEMENTED_SOURCE_KINDS,
    MAX_AGGREGATE_ROWS,
    MAX_ALIASES,
    MAX_JSON_DEPTH,
    MAX_MODELS,
    MAX_PROFILES,
    MAX_REVISION,
    MAX_SHORT_TEXT,
    MAX_SOURCE_BYTES,
    MAX_SOURCE_TEXT,
    MAX_TRANSMISSION_ROWS,
    MAX_XLSX_MEMBER_BYTES,
    MAX_XLSX_SHEETS,
    RECORD_TYPES,
    RESOLUTION_COMPLETE,
    RESOLUTION_PARTIAL,
    SCHEMA_VERSION,
    SIGN_VALUES,
    SOURCE_KIND_CSV,
    SOURCE_KIND_JSON,
    SOURCE_KIND_MEMORY,
    SOURCE_KIND_TSV,
    SOURCE_KIND_XLSX,
    SOURCE_KINDS,
)
from guiskindose.equipment_profiles.csv_source import parse_csv_bytes, parse_csv_file
from guiskindose.equipment_profiles.errors import (
    RESERVED_CODES,
    EquipmentProfileError,
    ProfileErrorCode,
    error_codes,
    is_implemented_code,
)
from guiskindose.equipment_profiles.indexes import (
    CoordinateClaim,
    CoordinateIndex,
    CoordinateKey,
    IndexedProfile,
    ProfileIndexes,
    TransmissionIndex,
    TransmissionKey,
    TransmissionNode,
    build_profile_indexes,
)
from guiskindose.equipment_profiles.json_source import (
    ParsedDocument,
    parse_json_bytes,
    parse_json_file,
    parse_memory_document,
)
from guiskindose.equipment_profiles.keys import (
    clean_identity_text,
    is_wildcard_model,
    normalize_manufacturer_key,
    normalize_model_key,
)
from guiskindose.equipment_profiles.loading import (
    ProfileSet,
    combine_documents,
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
from guiskindose.equipment_profiles.profile_store import (
    STORE_FILENAME,
    ProfileStore,
    default_store_path,
)
from guiskindose.equipment_profiles.resolver import (
    CoordinateResolution,
    ExamCoordinateIdentity,
    NoticeEntry,
    ResolutionNotice,
    resolve_coordinate_leaves,
)
from guiskindose.equipment_profiles.store_schema import (
    MAX_LIST_LIMIT,
    MAX_REVISIONS_PER_PROFILE,
    MAX_STORE_RECORDS,
    utc_now_iso,
)
from guiskindose.equipment_profiles.store_types import (
    STORE_SCHEMA_VERSION,
    STORE_SOURCE_KIND,
    SelectedRevision,
    StoredRecord,
    StoredRevision,
    StoreSnapshot,
    store_source_hash,
)
from guiskindose.equipment_profiles.tsv_source import parse_tsv_bytes, parse_tsv_file
from guiskindose.equipment_profiles.validation import validate_document
from guiskindose.equipment_profiles.vendor_aliases import (
    GE_MANUFACTURER_ALIASES,
    MANUFACTURER_ALIASES_BY_SETTINGS_KEY,
    aliases_for_settings_key,
)
from guiskindose.equipment_profiles.xlsx_source import parse_xlsx_bytes, parse_xlsx_file

__all__ = [
    # Constants
    "ACQUISITION_PLANES",
    "COORDINATE_BLOCKS",
    "COORDINATE_LEAF_COUNT",
    "EVIDENCE_STATUSES",
    "FLAT_COLUMNS",
    "FLAT_COLUMNS_BY_RECORD_TYPE",
    "FLAT_PROMOTION_COLUMN",
    "FLAT_REQUIRED_COLUMNS_BY_RECORD_TYPE",
    "GE_MANUFACTURER_ALIASES",
    "IMPLEMENTED_SOURCE_KINDS",
    # Errors
    "MANUFACTURER_ALIASES_BY_SETTINGS_KEY",
    "MAX_AGGREGATE_ROWS",
    "MAX_ALIASES",
    "MAX_JSON_DEPTH",
    "MAX_LIST_LIMIT",
    "MAX_MODELS",
    "MAX_PROFILES",
    "MAX_REVISION",
    "MAX_REVISIONS_PER_PROFILE",
    "MAX_SHORT_TEXT",
    "MAX_SOURCE_BYTES",
    "MAX_SOURCE_TEXT",
    "MAX_STORE_RECORDS",
    "MAX_TRANSMISSION_ROWS",
    "MAX_XLSX_MEMBER_BYTES",
    "MAX_XLSX_SHEETS",
    "RECORD_TYPES",
    "RESERVED_CODES",
    "RESOLUTION_COMPLETE",
    "RESOLUTION_PARTIAL",
    "SCHEMA_VERSION",
    "SIGN_VALUES",
    "SOURCE_KINDS",
    "SOURCE_KIND_CSV",
    "SOURCE_KIND_JSON",
    "SOURCE_KIND_MEMORY",
    "SOURCE_KIND_TSV",
    "SOURCE_KIND_XLSX",
    "STORE_FILENAME",
    "STORE_SCHEMA_VERSION",
    "STORE_SOURCE_KIND",
    "UNSUPPORTED_CAPABILITIES",
    "BundledCoordinateSet",
    # Indexes
    "CoordinateClaim",
    "CoordinateIndex",
    "CoordinateKey",
    # Matches
    "CoordinateMatchRecord",
    "CoordinateResolution",
    # Models
    "Coordinates",
    "EquipmentProfileError",
    "ExamCoordinateIdentity",
    "IndexedProfile",
    "LeafProvenance",
    "MatchedInputKey",
    "NoticeEntry",
    # Parsing and loading
    "ParsedDocument",
    "Profile",
    "ProfileErrorCode",
    "ProfileIndexes",
    "ProfileSet",
    "ProfileStore",
    "Provenance",
    "ResolutionNotice",
    "RotationDirection",
    "SelectedRevision",
    "StoreSnapshot",
    "StoredRecord",
    "StoredRevision",
    "TranslationDirection",
    "TranslationOffset",
    "TransmissionIndex",
    "TransmissionKey",
    "TransmissionNode",
    "TransmissionRow",
    "active_set_hash",
    "aliases_for_settings_key",
    "build_leaf_provenance",
    "build_profile_indexes",
    "bundled_coordinate_set",
    "bundled_profile_id",
    # Canonical form and hashes
    "canonical_json_bytes",
    "canonical_profile_dict",
    # Capability gate
    "check_initial_capabilities",
    "clean_identity_text",
    "collect_identity_collisions",
    "combine_documents",
    "coordinate_leaf_values",
    "default_store_path",
    "error_codes",
    "first_unsupported_capability",
    "is_implemented_code",
    # Keys
    "is_wildcard_model",
    "normalize_manufacturer_key",
    "normalize_model_key",
    "order_leaf_provenance",
    "parse_csv_bytes",
    "parse_csv_file",
    "parse_json_bytes",
    "parse_json_file",
    "parse_memory_document",
    "parse_tsv_bytes",
    "parse_tsv_file",
    "parse_xlsx_bytes",
    "parse_xlsx_file",
    "profile_hash",
    "resolve_coordinate_leaves",
    "source_bytes_hash",
    "store_source_hash",
    "supported_profiles",
    "utc_now_iso",
    "validate_document",
    # Validation and conflicts
    "validate_profile_set",
]
