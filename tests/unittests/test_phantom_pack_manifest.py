"""Phantom pack manifest validation."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from guiskindose.phantom_pack import (
    PhantomPackError,
    canonical_manifest_bytes,
    parse_pack_manifest,
    validate_manifest_for_install,
    verify_pack_signature,
)
from tests.unittests.phantom_pack_test_helpers import manifest_for_files, pack_zip_bytes, tiny_stl_body


def test_verify_pack_signature_rejects_present() -> None:
    """Exercise verify pack signature rejects present."""
    with pytest.raises(PhantomPackError, match="Signed phantom packs"):
        verify_pack_signature({"signature": "abcd"})


def test_duplicate_top_level_keys_rejected() -> None:
    """Exercise duplicate top level keys rejected."""
    raw = b'{"format": 1, "format": 2, "pack_version": "1.1.1", "app_versions": ["1.1.1"], "files": []}'
    with pytest.raises(PhantomPackError):
        parse_pack_manifest(raw)


def test_bad_format_version_and_stem_rules() -> None:
    """Exercise bad format version and stem rules."""
    body = tiny_stl_body()
    base = manifest_for_files({"senior_male": body})
    cases = [
        {**base, "format": 2},
        {**base, "app_versions": ["9.9.9"]},
        manifest_for_files({"pediatric_5y_male": body}),
        manifest_for_files({"demo_cosmic_buddha": body}),
        manifest_for_files({"adult_male_reduced_1000t": body}),
    ]
    for manifest in cases:
        parsed = parse_pack_manifest(canonical_manifest_bytes(manifest))
        with pytest.raises(PhantomPackError):
            validate_manifest_for_install(parsed, app_version="1.1.1")
    invalid_manifest = manifest_for_files({"not_a_catalog": body})
    invalid_parsed = parse_pack_manifest(canonical_manifest_bytes(invalid_manifest))
    with pytest.raises(PhantomPackError):
        validate_manifest_for_install(invalid_parsed, app_version="1.1.1")


def test_byte_and_hash_mismatch() -> None:
    """Exercise byte and hash mismatch."""
    body = tiny_stl_body()
    manifest = manifest_for_files({"senior_male": body})
    parsed = parse_pack_manifest(canonical_manifest_bytes(manifest))
    entries = validate_manifest_for_install(parsed, app_version="1.1.1")
    from guiskindose.phantom_pack import verify_member_bytes

    with pytest.raises(PhantomPackError):
        verify_member_bytes(body, expected_bytes=entries[0]["bytes"] + 1, expected_sha256=entries[0]["sha256"])
    manifest = manifest_for_files({"senior_male": body})
    manifest["files"][0]["sha256"] = "0" * 64
    parsed = parse_pack_manifest(canonical_manifest_bytes(manifest))
    entries = validate_manifest_for_install(parsed, app_version="1.1.1")
    from guiskindose.phantom_pack import verify_member_bytes

    with pytest.raises(PhantomPackError):
        verify_member_bytes(body, expected_bytes=entries[0]["bytes"], expected_sha256=entries[0]["sha256"])


def test_unknown_manifest_key_rejected() -> None:
    """Exercise unknown manifest key rejected."""
    manifest = manifest_for_files({"senior_male": tiny_stl_body()})
    manifest["extra"] = 1
    raw = canonical_manifest_bytes(manifest)
    with pytest.raises(PhantomPackError):
        parse_pack_manifest(raw)


def test_empty_pin_leaves_library_unchanged(tmp_path: Path) -> None:
    """Exercise empty pin leaves library unchanged."""
    import io

    from guiskindose.phantom_pack_install import install_phantom_pack

    shipped = tmp_path / "shipped"
    library = tmp_path / "library"
    body = tiny_stl_body()
    manifest = manifest_for_files({"senior_male": body})
    raw = pack_zip_bytes(manifest, {"senior_male": body})
    with pytest.raises(PhantomPackError):
        install_phantom_pack(
            io.BytesIO(raw),
            user_library_dir=library,
            shipped_dir=shipped,
            expected_manifest_sha256="",
            app_version="1.1.1",
        )
    assert not library.exists()


def test_mismatched_pin_leaves_library_unchanged(tmp_path: Path) -> None:
    """Exercise mismatched pin leaves library unchanged."""
    import io

    from guiskindose.phantom_pack_install import install_phantom_pack

    shipped = tmp_path / "shipped"
    library = tmp_path / "library"
    body = tiny_stl_body()
    manifest = manifest_for_files({"senior_male": body})
    raw = pack_zip_bytes(manifest, {"senior_male": body})
    with pytest.raises(PhantomPackError):
        install_phantom_pack(
            io.BytesIO(raw),
            user_library_dir=library,
            shipped_dir=shipped,
            expected_manifest_sha256="f" * 64,
            app_version="1.1.1",
        )
    assert not library.exists()


def test_injected_hash_round_trip() -> None:
    """Exercise injected hash round trip."""
    body = tiny_stl_body()
    manifest = manifest_for_files({"senior_male": body}, app_version="1.1.1")
    digest = hashlib.sha256(canonical_manifest_bytes(manifest)).hexdigest()
    assert len(digest) == 64
    parsed = parse_pack_manifest(canonical_manifest_bytes(manifest))
    validate_manifest_for_install(parsed, app_version="1.1.1")
