"""Phantom pack manifest validation."""

from __future__ import annotations

import hashlib

import pytest

from guiskindose.phantom_pack import (
    PhantomPackError,
    canonical_manifest_bytes,
    parse_pack_manifest,
    validate_manifest_for_install,
    verify_pack_signature,
)
from tests.unittests.phantom_pack_test_helpers import manifest_for_files, tiny_stl_body


def test_verify_pack_signature_rejects_present() -> None:
    with pytest.raises(PhantomPackError, match="Signed phantom packs"):
        verify_pack_signature({"signature": "abcd"})


def test_duplicate_top_level_keys_rejected() -> None:
    raw = b'{"format": 1, "format": 2, "pack_version": "1.1.1", "app_versions": ["1.1.1"], "files": []}'
    with pytest.raises(PhantomPackError):
        parse_pack_manifest(raw)


def test_bad_format_version_and_stem_rules() -> None:
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
        raw = canonical_manifest_bytes(manifest)
        parsed = parse_pack_manifest(raw)
        with pytest.raises(PhantomPackError):
            validate_manifest_for_install(parsed, app_version="1.1.1")
    with pytest.raises(PhantomPackError):
        validate_manifest_for_install(
            parse_pack_manifest(canonical_manifest_bytes(manifest_for_files({"not_a_catalog": body}))),
            app_version="1.1.1",
        )


def test_byte_and_hash_mismatch() -> None:
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
    manifest = manifest_for_files({"senior_male": tiny_stl_body()})
    manifest["extra"] = 1
    with pytest.raises(PhantomPackError):
        parse_pack_manifest(canonical_manifest_bytes(manifest))


def test_injected_hash_round_trip() -> None:
    body = tiny_stl_body()
    manifest = manifest_for_files({"senior_male": body}, app_version="1.1.1")
    digest = hashlib.sha256(canonical_manifest_bytes(manifest)).hexdigest()
    assert len(digest) == 64
    parsed = parse_pack_manifest(canonical_manifest_bytes(manifest))
    validate_manifest_for_install(parsed, app_version="1.1.1")
