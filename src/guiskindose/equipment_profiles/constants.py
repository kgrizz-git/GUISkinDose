"""Fixed bounds, vocabularies, and allowlisted field names for equipment profiles.

Everything here is a closed constant set. The schema contract in
``dev-docs/EQUIPMENT_PROFILE_SCHEMA.md`` is the implementation contract; this module is where those numbers
and vocabularies live so no other module has to invent one.

This module is stdlib-only by design: the core package must not import normalization, dose, GUI, or any
third-party dependency.
"""

from __future__ import annotations

# --- Document envelope -------------------------------------------------------------

SCHEMA_VERSION = 1

#: Root envelope keys. Nothing else exists at the root.
ENVELOPE_KEYS = frozenset({"schema_version", "profiles"})

#: Profile keys. Anything else is ``unknown_field``.
PROFILE_KEYS = frozenset(
    {
        "profile_id",
        "manufacturer",
        "models",
        "manufacturer_aliases",
        "model_aliases",
        "provenance",
        "coordinates",
        "transmission",
        "promote_coordinate_wildcard",
    }
)

PROVENANCE_KEYS = frozenset({"source", "notes"})

#: Provenance text keys (shared with the transmission row ``source``/``comment`` fields).
PROVENANCE_TEXT_KEYS = ("source", "notes")

#: Transmission row keys. Anything else is ``unknown_field``.
TRANSMISSION_KEYS = frozenset(
    {
        "device_model",
        "acquisition_plane",
        "kvp_kv",
        "filtration_added_mmcu",
        "filtration_added_mmal",
        "k_patient_support",
        "evidence_status",
        "source",
        "date",
        "comment",
    }
)

# --- Coordinate blocks and leaves ---------------------------------------------------

TRANSLATION_OFFSET = "translation_offset"
TRANSLATION_DIRECTION = "translation_direction"
ROTATION_DIRECTION = "rotation_direction"
SWAP_LATERAL_LONGITUDINAL = "swap_lateral_longitudinal"
FIELD_SIZE_MODE = "field_size_mode"
DETECTOR_SIDE_LENGTH = "detector_side_length"

#: The six coordinate blocks, in canonical documentation order.
COORDINATE_BLOCKS = (
    TRANSLATION_OFFSET,
    TRANSLATION_DIRECTION,
    ROTATION_DIRECTION,
    SWAP_LATERAL_LONGITUDINAL,
    FIELD_SIZE_MODE,
    DETECTOR_SIDE_LENGTH,
)

#: Common axis field names shared by the offset and direction blocks.
AXIS_FIELDS = ("x", "y", "z")

#: Rotation leaf field names (lower-cased) paired with their JSON key spelling.
ROTATION_LEAVES = (
    ("ap1", "Ap1"),
    ("ap2", "Ap2"),
    ("ap3", "Ap3"),
    ("at1", "At1"),
    ("at2", "At2"),
    ("at3", "At3"),
)

#: Total leaf count of a fully specified coordinate profile.
COORDINATE_LEAF_COUNT = 3 + 3 + len(ROTATION_LEAVES) + 3

SIGN_VALUES = ("+", "-")
FIELD_SIZE_MODES = ("CFA", "ASD")

# --- Transmission vocabulary ---------------------------------------------------------

ACQUISITION_PLANES = ("Single Plane", "Plane A", "Plane B")
EVIDENCE_STATUSES = ("measured", "estimated")
PLANE_WILDCARD = "*"

# --- Bounds --------------------------------------------------------------------------

#: Maximum source file bytes for any accepted source format.
MAX_SOURCE_BYTES = 8 * 1024 * 1024

#: Maximum aggregate logical rows across every source in one load.
MAX_AGGREGATE_ROWS = 10_000

#: Maximum profile objects per document and per load.
MAX_PROFILES = 64

#: Maximum source requests (files, memory documents, store snapshots combined)
#: per session assembly. Each file/memory source already yields at least one
#: profile, so profile/row ceilings bind content; this binds request fan-out
#: (including empty snapshots, which carry provenance but no profiles).
MAX_SOURCES = 64

#: Maximum store revision number accepted as index entry context. Matches the store's rowid ceiling without
#: importing store internals; the index core never touches SQLite.
MAX_REVISION = 2**63 - 1

#: Maximum canonical model keys per profile.
MAX_MODELS = 32

#: Maximum coordinate leaves per profile (one per allowed leaf).
MAX_COORDINATE_LEAVES = COORDINATE_LEAF_COUNT

#: Maximum transmission rows per profile.
MAX_TRANSMISSION_ROWS = 2_000

#: Maximum alias entries per alias collection.
MAX_ALIASES = 16

#: Maximum JSON nesting depth.
MAX_JSON_DEPTH = 16

#: Maximum nodes visited by the bounded traversal that enforces the depth limit.
#: Derived from the document shape: one document holds at most ``MAX_AGGREGATE_ROWS``
#: logical rows, and each row contributes a bounded number of keys (profile field
#: model, coordinate leaves, or transmission row fields), so any valid document is
#: far below this. The cap keeps a hostile or accidentally enormous in-memory
#: mapping from being walked exhaustively before the row and profile limits are
#: checked, and is enforced *after* the cheap early list-length check.
MAX_TRAVERSAL_NODES = 250_000

#: Maximum XLSX sheets a workbook may offer for selection.
MAX_XLSX_SHEETS = 16

# --- XLSX container and worksheet preflight ---------------------------------------------
# A compressed upload may sit inside the 8 MiB byte cap and still inflate far past it, so the archive is
# preflighted by *streaming* real decompressed member bytes rather than trusting central-directory
# metadata, and the worksheet is counted from actual iteration rather than its declared dimension.

#: Ceiling for any single decompressed ZIP member.
MAX_XLSX_MEMBER_BYTES = 32 * 1024 * 1024

#: Ceiling for the sum of all decompressed members.
MAX_XLSX_TOTAL_INFLATED_BYTES = 64 * 1024 * 1024

#: Chunk used while streaming a member so a lying header cannot force one huge allocation.
XLSX_STREAM_CHUNK_BYTES = 64 * 1024

#: Row, column, and cell budgets enforced while counting an actual worksheet.
MAX_XLSX_PREFLIGHT_ROWS = 100_000
MAX_XLSX_PREFLIGHT_COLS = 512
MAX_XLSX_PREFLIGHT_CELLS = 2_000_000

#: OOXML worksheet part naming. Used only to locate parts inside the archive; sheet *selection* is resolved
#: from the workbook's own catalog, never from these names.
WORKSHEET_ENTRY_PREFIX = "xl/worksheets/"
WORKSHEET_ENTRY_SUFFIX = ".xml"

#: Maximum characters for short identity text (profile_id, manufacturer, model keys, aliases).
MAX_SHORT_TEXT = 64

#: Maximum characters for a provenance ``source`` value.
MAX_SOURCE_TEXT = 200

#: Maximum characters for bounded free text (``notes``, transmission ``comment``).
MAX_LONG_TEXT = 500

#: Accepted profile_id shape. Compared exactly, never case-folded.
PROFILE_ID_PATTERN = r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}"

# --- Numeric ranges (inclusive unless noted) ------------------------------------------

OFFSET_MIN = -1000.0
OFFSET_MAX = 1000.0
DETECTOR_SIDE_LENGTH_MIN_EXCLUSIVE = 0.0
DETECTOR_SIDE_LENGTH_MAX = 200.0
KVP_MIN_EXCLUSIVE = 0.0
KVP_MAX = 200.0
FILTRATION_MMCU_MAX = 100.0
FILTRATION_MMAL_MAX = 1000.0
K_PATIENT_SUPPORT_MIN_EXCLUSIVE = 0.0
K_PATIENT_SUPPORT_MAX = 1.0

# --- Source kinds ---------------------------------------------------------------------

SOURCE_KIND_JSON = "json"
SOURCE_KIND_MEMORY = "memory"
SOURCE_KIND_CSV = "csv"
SOURCE_KIND_TSV = "tsv"
SOURCE_KIND_XLSX = "xlsx"
SOURCE_KIND_GUI = "gui"
SOURCE_KIND_STORE = "store"

#: Source kinds with an implemented adapter in the current core slice.
IMPLEMENTED_SOURCE_KINDS = (
    SOURCE_KIND_JSON,
    SOURCE_KIND_MEMORY,
    SOURCE_KIND_CSV,
    SOURCE_KIND_TSV,
    SOURCE_KIND_XLSX,
)

#: Every documented source kind. The rest are reserved for their adapters.
SOURCE_KINDS = (
    SOURCE_KIND_JSON,
    SOURCE_KIND_MEMORY,
    SOURCE_KIND_CSV,
    SOURCE_KIND_TSV,
    SOURCE_KIND_XLSX,
    SOURCE_KIND_GUI,
    SOURCE_KIND_STORE,
)

#: File suffixes accepted by the implemented JSON file adapter.
JSON_SOURCE_SUFFIXES = (".json",)

#: File suffix -> source kind for the implemented tabular file adapters.
TABULAR_SUFFIX_TO_KIND = {
    ".csv": SOURCE_KIND_CSV,
    ".tsv": SOURCE_KIND_TSV,
}

#: File suffixes accepted by the implemented spreadsheet adapter.
XLSX_SOURCE_SUFFIXES = (".xlsx",)

# --- Flat tabular shape (RFC 4180-style single table) -----------------------------------

RECORD_TYPE_PROFILE = "profile"
RECORD_TYPE_COORDINATE = "coordinate"
RECORD_TYPE_TRANSMISSION = "transmission"

#: The only accepted ``record_type`` values.
RECORD_TYPES = (RECORD_TYPE_PROFILE, RECORD_TYPE_COORDINATE, RECORD_TYPE_TRANSMISSION)

#: Columns of the flat tabular table, in packaged-example order. Exactly these are required.
FLAT_COLUMNS = (
    "record_type",
    "profile_id",
    "manufacturer",
    "models",
    "manufacturer_aliases",
    "model_aliases",
    "source",
    "notes",
    "field",
    "value",
    "device_model",
    "acquisition_plane",
    "kvp_kv",
    "filtration_added_mmcu",
    "filtration_added_mmal",
    "k_patient_support",
    "evidence_status",
    "date",
    "comment",
)

#: The optional profile-row column; when present the header holds these plus ``FLAT_COLUMNS``.
FLAT_PROMOTION_COLUMN = "promote_coordinate_wildcard"

#: Column names an error field path may use for a tabular source: the flat columns, the optional
#: promotion column, and the three ``record_type`` tokens. Nothing else, so no raw cell content leaks.
FLAT_FIELD_PATH_VOCABULARY = frozenset(
    set(FLAT_COLUMNS) | {FLAT_PROMOTION_COLUMN} | set(RECORD_TYPES)
)

#: Which flat columns may carry a value on each ``record_type``. Every other column must be blank on that row.
#: ``record_type`` and ``profile_id`` are applicable to every row type.
FLAT_COLUMNS_BY_RECORD_TYPE: dict[str, frozenset[str]] = {
    RECORD_TYPE_PROFILE: frozenset(
        {"record_type", "profile_id", "manufacturer", "models", "manufacturer_aliases",
         "model_aliases", "source", "notes", FLAT_PROMOTION_COLUMN}
    ),
    RECORD_TYPE_COORDINATE: frozenset({"record_type", "profile_id", "field", "value"}),
    RECORD_TYPE_TRANSMISSION: frozenset(
        {"record_type", "profile_id", "source", "device_model", "acquisition_plane", "kvp_kv",
         "filtration_added_mmcu", "filtration_added_mmal", "k_patient_support",
         "evidence_status", "date", "comment"}
    ),
}

#: Columns that must be non-blank on their record type. Anything else may be blank.
FLAT_REQUIRED_COLUMNS_BY_RECORD_TYPE: dict[str, frozenset[str]] = {
    RECORD_TYPE_PROFILE: frozenset({"record_type", "profile_id", "manufacturer", "models"}),
    RECORD_TYPE_COORDINATE: frozenset({"record_type", "profile_id", "field", "value"}),
    RECORD_TYPE_TRANSMISSION: frozenset(
        {"record_type", "profile_id", "device_model", "acquisition_plane", "kvp_kv",
         "filtration_added_mmcu", "filtration_added_mmal", "k_patient_support", "evidence_status"}
    ),
}

#: Columns where a blank cell is explicitly not "zero"/"absent" and is an error.
FLAT_BLANK_DISALLOWED_COLUMNS = frozenset({"filtration_added_mmcu", "filtration_added_mmal"})

#: Separator for flat list cells (models and alias lists). Only lists use it; JSON map cells do not.
FLAT_LIST_SEPARATOR = "|"

#: Strict boolean lexical forms for flat boolean cells. Nothing else is accepted.
FLAT_BOOLEAN_TRUE = "true"
FLAT_BOOLEAN_FALSE = "false"
FLAT_BOOLEAN_TOKENS = (FLAT_BOOLEAN_TRUE, FLAT_BOOLEAN_FALSE)

# --- Match-record vocabularies ----------------------------------------------------------

MATCH_DOMAIN_COORDINATE = "coordinate"
MATCH_SOURCE_CUSTOM = "custom"
MATCH_SOURCE_BUNDLED = "bundled"
MATCH_SOURCE_DEFAULT = "default"
MATCH_LEVEL_EXACT = "exact"
MATCH_LEVEL_WILDCARD = "wildcard"
MATCH_LEVEL_DEFAULT = "default"

#: Resolution notice kinds: every leaf came from the selected candidate
#: (`complete`), or at least one leaf was inherited from a lower candidate
#: (`partial`).
RESOLUTION_COMPLETE = "complete"
RESOLUTION_PARTIAL = "partial"

# --- Capability tokens (closed vocabulary used by the initial activation gate) ----------

CAPABILITY_MANUFACTURER_ALIAS = "manufacturer_alias"
CAPABILITY_MODEL_ALIAS = "model_alias"
CAPABILITY_MODEL_WILDCARD = "model_wildcard"
CAPABILITY_COORDINATE_WILDCARD_PROMOTION = "coordinate_wildcard_promotion"
CAPABILITY_TRANSMISSION_DOMAIN = "transmission_domain"
