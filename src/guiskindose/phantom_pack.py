"""Phantom pack manifest validation and pack errors."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from guiskindose.phantom_mesh_names import (
    _LEGACY_REDUCED_SUFFIXES,
    DEMO_HUMAN_MESHES,
    GUI_HIDDEN_HUMAN_MESHES,
    HUMAN_MESH_ALIASES,
    is_clinical_catalog_stem,
    resolve_human_mesh_stem,
)
from guiskindose.privacy import UserFacingInputError

_MANIFEST_MAX_BYTES = 256 * 1024
_PACK_VERSION_MAX_LEN = 32

_PHANTOM_PACK_BAD_FORMAT = "This phantom pack manifest is not supported."
_PHANTOM_PACK_BAD_VERSION = "This phantom pack is not built for this GUISkinDose version."
_PHANTOM_PACK_DUPLICATE_KEYS = "This phantom pack manifest is invalid."
_PHANTOM_PACK_UNKNOWN_KEY = "This phantom pack manifest is invalid."
_PHANTOM_PACK_SIGNATURE_PRESENT = "Signed phantom packs are not supported in this version."
_PHANTOM_PACK_BAD_STEM = "This phantom pack lists a mesh that is not allowed."
_PHANTOM_PACK_BYTE_MISMATCH = "This phantom pack file size does not match the manifest."
_PHANTOM_PACK_HASH_MISMATCH = "This phantom pack file hash does not match the manifest."
_PHANTOM_PACK_PIN_MISMATCH = "This phantom pack manifest is not recognized."
_PHANTOM_PACK_EMPTY_PIN = "Phantom pack install is not configured for this build."

_ALLOWED_MANIFEST_KEYS = frozenset({"format", "pack_version", "app_versions", "files", "signature"})
_ALLOWED_FILE_KEYS = frozenset({"stem", "bytes", "sha256"})


class PhantomPackError(UserFacingInputError):
    """Manifest, pin, or archive validation failure for a phantom pack."""


def verify_pack_signature(manifest: dict[str, Any]) -> None:
    """Phase-3 seam: Phase 2 rejects any manifest that carries ``signature``."""
    if "signature" in manifest:
        raise PhantomPackError(_PHANTOM_PACK_SIGNATURE_PRESENT)


def canonical_manifest_bytes(manifest: dict[str, Any]) -> bytes:
    """UTF-8 manifest body with sorted keys and no insignificant whitespace."""
    cleaned = {k: v for k, v in manifest.items() if k != "signature"}
    return json.dumps(cleaned, sort_keys=True, separators=(",", ":")).encode("utf-8")


def manifest_sha256(manifest: dict[str, Any]) -> str:
    """Return lowercase hex SHA-256 of the canonical manifest bytes."""
    return hashlib.sha256(canonical_manifest_bytes(manifest)).hexdigest()


def verify_manifest_pin(manifest: dict[str, Any], expected_sha256: str) -> None:
    """Compare manifest hash to the expected pin (required for every install)."""
    if not expected_sha256:
        raise PhantomPackError(_PHANTOM_PACK_EMPTY_PIN)
    digest = manifest_sha256(manifest)
    if digest != expected_sha256.lower():
        raise PhantomPackError(_PHANTOM_PACK_PIN_MISMATCH)


def is_allowed_pack_stem(stem: str) -> bool:
    """True when *stem* may appear in a pack manifest entry."""
    if not stem or stem in HUMAN_MESH_ALIASES:
        return False
    if stem in DEMO_HUMAN_MESHES or stem in GUI_HIDDEN_HUMAN_MESHES:
        return False
    if any(stem.endswith(suffix) for suffix in _LEGACY_REDUCED_SUFFIXES):
        return False
    try:
        canonical = resolve_human_mesh_stem(stem)
    except ValueError:
        return False
    if canonical != stem:
        return False
    return is_clinical_catalog_stem(stem)


def _parse_manifest_object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """Parse manifest object pairs."""
    keys = [k for k, _ in pairs]
    if len(keys) != len(set(keys)):
        raise PhantomPackError(_PHANTOM_PACK_DUPLICATE_KEYS)
    if "format" in keys or "pack_version" in keys or "files" in keys:
        for key in keys:
            if key not in _ALLOWED_MANIFEST_KEYS:
                raise PhantomPackError(_PHANTOM_PACK_UNKNOWN_KEY)
    else:
        for key in keys:
            if key not in _ALLOWED_FILE_KEYS:
                raise PhantomPackError(_PHANTOM_PACK_UNKNOWN_KEY)
    return dict(pairs)


def parse_pack_manifest(raw: bytes) -> dict[str, Any]:
    """Parse and validate manifest JSON; raise :class:`PhantomPackError` on failure."""
    if len(raw) > _MANIFEST_MAX_BYTES:
        raise PhantomPackError(_PHANTOM_PACK_BAD_FORMAT)
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PhantomPackError(_PHANTOM_PACK_BAD_FORMAT) from exc
    try:
        manifest = json.loads(text, object_pairs_hook=_parse_manifest_object_pairs)
    except PhantomPackError:
        raise
    except (json.JSONDecodeError, ValueError, RecursionError) as exc:
        raise PhantomPackError(_PHANTOM_PACK_BAD_FORMAT) from exc
    if not isinstance(manifest, dict):
        raise PhantomPackError(_PHANTOM_PACK_BAD_FORMAT)
    return manifest


def _validate_manifest_top(manifest: dict[str, Any], app_version: str) -> None:
    """Validate manifest top."""
    verify_pack_signature(manifest)
    if manifest.get("format") != 1:
        raise PhantomPackError(_PHANTOM_PACK_BAD_FORMAT)
    pack_version = manifest.get("pack_version")
    if not isinstance(pack_version, str) or not pack_version or len(pack_version) > _PACK_VERSION_MAX_LEN:
        raise PhantomPackError(_PHANTOM_PACK_BAD_FORMAT)
    app_versions = manifest.get("app_versions")
    if not isinstance(app_versions, list) or not app_versions:
        raise PhantomPackError(_PHANTOM_PACK_BAD_VERSION)
    if not all(isinstance(v, str) and v for v in app_versions):
        raise PhantomPackError(_PHANTOM_PACK_BAD_VERSION)
    if app_version not in app_versions:
        raise PhantomPackError(_PHANTOM_PACK_BAD_VERSION)
    if pack_version not in app_versions:
        raise PhantomPackError(_PHANTOM_PACK_BAD_FORMAT)
    files = manifest.get("files")
    if not isinstance(files, list) or not files:
        raise PhantomPackError(_PHANTOM_PACK_BAD_FORMAT)


def _validate_file_entry(entry: Any) -> dict[str, Any]:
    """Validate file entry."""
    if not isinstance(entry, dict):
        raise PhantomPackError(_PHANTOM_PACK_BAD_FORMAT)
    for key in entry:
        if key not in _ALLOWED_FILE_KEYS:
            raise PhantomPackError(_PHANTOM_PACK_UNKNOWN_KEY)
    stem = entry.get("stem")
    nbytes = entry.get("bytes")
    digest = entry.get("sha256")
    if not isinstance(stem, str) or not isinstance(nbytes, int) or not isinstance(digest, str):
        raise PhantomPackError(_PHANTOM_PACK_BAD_FORMAT)
    if not is_allowed_pack_stem(stem):
        raise PhantomPackError(_PHANTOM_PACK_BAD_STEM)
    if nbytes < 0 or len(digest) != 64 or not all(c in "0123456789abcdef" for c in digest):
        raise PhantomPackError(_PHANTOM_PACK_BAD_FORMAT)
    return {"stem": stem, "bytes": nbytes, "sha256": digest}


def validate_manifest_for_install(manifest: dict[str, Any], *, app_version: str) -> list[dict[str, Any]]:
    """Validate manifest schema and return normalized file entries."""
    _validate_manifest_top(manifest, app_version)
    files_raw = manifest["files"]
    seen: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for entry in files_raw:
        item = _validate_file_entry(entry)
        stem = item["stem"]
        if stem in seen:
            raise PhantomPackError(_PHANTOM_PACK_BAD_STEM)
        seen.add(stem)
        normalized.append(item)
    return normalized


def verify_member_bytes(data: bytes, *, expected_bytes: int, expected_sha256: str) -> None:
    """Ensure decompressed member size and hash match the manifest entry."""
    if len(data) != expected_bytes:
        raise PhantomPackError(_PHANTOM_PACK_BYTE_MISMATCH)
    digest = hashlib.sha256(data).hexdigest()
    if digest != expected_sha256.lower():
        raise PhantomPackError(_PHANTOM_PACK_HASH_MISMATCH)
