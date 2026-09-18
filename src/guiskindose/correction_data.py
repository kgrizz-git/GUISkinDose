"""Packaged correction-data provider plus explicit-source resolution.

Default operation reads the authoritative CSVs under ``table_data/`` as
package resources — no SQLite bootstrap, no working-directory writes. An
explicitly configured SQLite path is served read-only through the Phase A
validators (legacy unversioned databases classify as ``legacy`` with full
content validation). All user-facing messages are value-free (never paths).
"""

from __future__ import annotations

import hashlib
import logging
import re
import threading
import warnings
from importlib import resources
from pathlib import Path

import pandas as pd

from guiskindose.correction_validation import (
    ColumnSpec,
    check_explicit_db,
)
from guiskindose.privacy import safe_warning

logger = logging.getLogger("guiskindose")

# Logical table name -> CSV path relative to table_data/.
_TABLE_FILES = {
    "hvl_combined": "hvl_tables/hvl_combined.csv",
    "correction_medium_and_backscatter": "correction_medium_and_backscatter.csv",
    "correction_table_and_pad_attenuation": "correction_table_and_pad_attenuation.csv",
    "device_info": "device_info.csv",
}

# Expected schema version for explicit DBs that carry a version table.
EXPLICIT_SCHEMA_VERSION = "1"

# Column specs + lookup keys for explicit-DB content validation. Keys were
# verified duplicate-free against the shipped data (hvl includes the anode
# slice; the runtime dedups it before lookup).
_EXPLICIT_SPECS: dict[str, list[ColumnSpec]] = {
    "hvl_combined": [
        ColumnSpec("kvp_kv", "float", (0.0, None)),
        ColumnSpec("filtration_inherent_mmal", "float", (0.0, None)),
        ColumnSpec("filtration_added_mmcu", "float", (0.0, None)),
        ColumnSpec("filtration_added_mmal", "float", (0.0, None)),
        ColumnSpec("anode_angle_deg", "float", (0.0, None)),
        ColumnSpec("hvl_mmal", "float", (0.0, None)),
    ],
    "correction_medium_and_backscatter": [
        ColumnSpec("kvp_kv", "float", (0.0, None)),
        ColumnSpec("filtration_inherent_mmal", "float", (0.0, None)),
        ColumnSpec("filtration_added_mmcu", "float", (0.0, None)),
        ColumnSpec("hvl_mmal", "float", (0.0, None)),
        ColumnSpec("h", "float", (0.0, None)),
        ColumnSpec("field_side_length_cm", "float", (0.0, None)),
        ColumnSpec("backscatter", "float", (0.0, None)),
        ColumnSpec("mu_en_quotient", "float", (0.0, None)),
    ],
    "correction_table_and_pad_attenuation": [
        ColumnSpec("kvp_kv", "float", (0.0, None)),
        ColumnSpec("filtration_added_mmcu", "float", (0.0, None)),
        ColumnSpec("filtration_added_mmal", "float", (0.0, None)),
        ColumnSpec("device_model", "string"),
        ColumnSpec("acquisition_plane", "string"),
        ColumnSpec("k_patient_support", "float", (0.0, None)),
        ColumnSpec("comment", "string"),
    ],
    "device_info": [
        ColumnSpec("DeviceObserverSerialNumber", "string"),
        ColumnSpec("Lab", "string"),
        ColumnSpec("DateMeasured", "string"),
        ColumnSpec("PadMaterial", "string"),
        ColumnSpec("PadThickness_mm", "float", (0.0, None)),
        ColumnSpec("Comment", "string"),
    ],
}
_EXPLICIT_KEYS: dict[str, tuple[str, ...]] = {
    "hvl_combined": ("kvp_kv", "filtration_inherent_mmal", "filtration_added_mmcu", "filtration_added_mmal", "anode_angle_deg"),
    "correction_medium_and_backscatter": ("field_side_length_cm", "kvp_kv", "hvl_mmal"),
    "correction_table_and_pad_attenuation": ("device_model", "acquisition_plane", "kvp_kv", "filtration_added_mmcu", "filtration_added_mmal"),
}

_DEFAULT_SENTINEL = "corrections.db"

_CACHE: dict[str, pd.DataFrame] = {}
_CACHE_LOCK = threading.Lock()
_HASH_CACHE: str | None = None

# Warning classes already emitted once per process (never paths).
_warned: set[str] = set()

_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _table_ref(name: str):
    return resources.files("guiskindose") / "table_data" / _TABLE_FILES[name]


def get_table(name: str) -> pd.DataFrame:
    """Packaged correction table as a DataFrame (deep copy per call).

    Tables are loaded once and cached; every caller gets an independent copy
    under a documented read-only contract (mutating the result never affects
    the cache). Raises :class:`KeyError` for unknown table names.
    """
    if name not in _TABLE_FILES:
        raise KeyError(f"Unknown correction table: {name!r}")
    cached = _CACHE.get(name)
    if cached is None:
        with _CACHE_LOCK:
            cached = _CACHE.get(name)
            if cached is None:
                with resources.as_file(_table_ref(name)) as path:
                    cached = pd.read_csv(path)
                _CACHE[name] = cached
    return cached.copy(deep=True)


def clear_cache() -> None:
    """Drop cached tables and the packaged hash (tests only)."""
    global _HASH_CACHE
    with _CACHE_LOCK:
        _CACHE.clear()
        _HASH_CACHE = None


def packaged_source_hash() -> str:
    """SHA-256 identifying the packaged runtime correction content.

    Over each ``runtime_lookup`` manifest table in manifest order: filename +
    NUL + raw CSV bytes. Build inputs and provenance-only tables cannot affect
    results and are excluded. Cached lazily.
    """
    global _HASH_CACHE
    if _HASH_CACHE is None:
        with _CACHE_LOCK:
            if _HASH_CACHE is None:
                digest = hashlib.sha256()
                for name in ("hvl_combined", "correction_medium_and_backscatter", "correction_table_and_pad_attenuation"):
                    ref = _table_ref(name)
                    digest.update(name.encode("utf-8") + b"\0" + ref.read_bytes())
                _HASH_CACHE = digest.hexdigest()
    return _HASH_CACHE


def _warn_once(cls: str, code: str, message: str, *, emit_warnings: bool) -> None:
    if not emit_warnings:
        return
    with _CACHE_LOCK:
        if cls in _warned:
            return
        _warned.add(cls)
    safe_warning(logger, code)
    logger.warning(message)
    warnings.warn(message, DeprecationWarning, stacklevel=3)


def reset_warnings() -> None:
    """Clear once-per-process warning state (tests only)."""
    _warned.clear()


def _ignored_db_present() -> bool:
    return (Path.cwd() / _DEFAULT_SENTINEL).is_file()


def resolve_corrections_source(value: object, *, emit_warnings: bool = True) -> tuple[str, Path | None]:
    """Classify a ``corrections_db_path`` value without touching the filesystem DB.

    Returns ``("packaged", None)`` for the default (unset/``None``/empty/
    whitespace/``"corrections.db"``) and ``("explicit", path)`` for anything
    else. Note the spelling is exact: ``"./corrections.db"`` (or any other
    relative spelling) classifies as explicit, not as the sentinel.
    Non-default paths warn once per process (value-free) and are honored
    read-only downstream. ``~``-leading paths are rejected with a migration
    hint (SQLite expansion differs by OS). Emits an additional diagnostic when
    a ``corrections.db`` file in the process working directory is detected but
    deliberately ignored (repo-root files are no longer probed: the GUI root
    discovery was removed, so only CWD is checked).
    """
    text = "" if value is None else str(value).strip()
    if not text or text == _DEFAULT_SENTINEL:
        if _ignored_db_present():
            _warn_once(
                "ignored-db",
                "ignored_db_detected",
                "A corrections.db file was detected in the working directory and will be ignored; packaged correction data is used.",
                emit_warnings=emit_warnings,
            )
        return "packaged", None
    if text.startswith("~"):
        raise ValueError("Paths starting with '~' are not expanded; pass an absolute database path.")
    path = Path(text)
    if not path.is_absolute():
        _warn_once(
            "relative-deprecated",
            "relative_db_deprecated",
            "Relative correction-database paths are deprecated; pass an absolute path. The path is honored read-only for now.",
            emit_warnings=emit_warnings,
        )
    else:
        _warn_once(
            "explicit",
            "explicit_db_source",
            "A non-default correction-data source is configured and will be read read-only; packaged correction data is recommended.",
            emit_warnings=emit_warnings,
        )
    return "explicit", path


class CorrectionDataError(Exception):
    """Raised when an explicit correction-data source fails validation."""


def explicit_table(db_path: Path, table: str) -> pd.DataFrame:
    """One validated table from an explicit legacy SQLite database.

    Runs the Phase A validators under the legacy policy (unversioned bootstrap
    DBs accepted with full content validation) and raises
    :class:`CorrectionDataError` with a value-free message on any error-grade
    finding. Only the requested table (plus the schema version, when present)
    is validated: partial databases stay usable for the operations they cover.
    Never writes.
    """
    specs = {table: _EXPLICIT_SPECS[table]}
    keys = {table: _EXPLICIT_KEYS[table]} if table in _EXPLICIT_KEYS else {}
    issues = check_explicit_db(
        db_path,
        expected_version=EXPLICIT_SCHEMA_VERSION,
        table_specs=specs,
        table_keys=keys,
        legacy_unversioned=True,
    )
    errors = [issue for issue in issues if issue.severity == "error"]
    if errors:
        first = errors[0]
        raise CorrectionDataError(
            f"Explicit correction database failed validation: {first.code} on table {first.table!r} column {first.column!r}."
        )
    return _read_explicit_table(db_path, table)


def _read_explicit_table(db_path: Path, table: str) -> pd.DataFrame:
    import sqlite3

    if not _IDENTIFIER_RE.match(table):
        raise CorrectionDataError("Refusing to read table with unsafe name (value-free).")
    conn = sqlite3.connect(f"{db_path.resolve().as_uri()}?mode=ro", uri=True)
    try:
        return pd.read_sql_query(f'SELECT * FROM "{table}"', conn)  # nosec B608
    finally:
        conn.close()
