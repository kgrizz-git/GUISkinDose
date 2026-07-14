"""Tests for the tracked-content and approved-asset admission gate."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.check_sensitive_content import is_probably_binary, run_checks, sha256


def _write_policy(root: Path, assets: list[dict[str, object]]) -> None:
    docs = root / "dev-docs"
    docs.mkdir()
    (docs / "approved_asset_inventory.json").write_text(
        json.dumps({"version": 1, "assets": assets}), encoding="utf-8"
    )
    (docs / "sensitive_content_allowlist.json").write_text(
        json.dumps({"version": 1, "allowed_findings": []}), encoding="utf-8"
    )


def _asset_entry(root: Path, path: str, *, status: str = "approved") -> dict[str, object]:
    return {
        "path": path,
        "sha256": sha256(root / path),
        "kind": "image",
        "purpose": "Test fixture",
        "review": {"status": status, "reviewer": "tester", "reviewed_on": "2026-07-13"},
    }


def test_approved_asset_passes(tmp_path: Path) -> None:
    asset = tmp_path / "diagram.png"
    asset.write_bytes(b"not a real image, but a hash-pinned asset")
    _write_policy(tmp_path, [_asset_entry(tmp_path, "diagram.png")])

    assert run_checks(tmp_path, paths=["diagram.png"]) == []


def test_missing_or_changed_asset_fails(tmp_path: Path) -> None:
    asset = tmp_path / "diagram.png"
    asset.write_bytes(b"first version")
    entry = _asset_entry(tmp_path, "diagram.png")
    _write_policy(tmp_path, [entry])
    asset.write_bytes(b"changed version")
    (tmp_path / "new.dcm").write_bytes(b"new opaque input")

    findings = run_checks(tmp_path, paths=["diagram.png", "new.dcm"])
    assert {(finding.path, finding.rule) for finding in findings} == {
        ("diagram.png", "ASSET_HASH_NOT_APPROVED"),
        ("new.dcm", "ASSET_NOT_IN_APPROVED_INVENTORY"),
    }


def test_pending_baseline_becomes_error_in_strict_mode(tmp_path: Path) -> None:
    asset = tmp_path / "diagram.png"
    asset.write_bytes(b"baseline")
    _write_policy(tmp_path, [_asset_entry(tmp_path, "diagram.png", status="pending")])

    advisory = run_checks(tmp_path, paths=["diagram.png"])
    strict = run_checks(tmp_path, paths=["diagram.png"], require_approved_assets=True)
    assert [(finding.rule, finding.level) for finding in advisory] == [("ASSET_MANUAL_REVIEW_PENDING", "warning")]
    assert [(finding.rule, finding.level) for finding in strict] == [("ASSET_MANUAL_REVIEW_PENDING", "error")]


def test_sensitive_text_is_reported_without_echoing_value(tmp_path: Path) -> None:
    text = tmp_path / "notes.txt"
    text.write_text("contact=" + "person" + "@hospital.test\n", encoding="utf-8")
    _write_policy(tmp_path, [])

    findings = run_checks(tmp_path, paths=["notes.txt"])
    assert [(finding.path, finding.rule, finding.location) for finding in findings] == [
        ("notes.txt", "EMAIL_ADDRESS", "1")
    ]
    assert "person" not in findings[0].render()


def test_extensionless_file_requires_an_inventory_entry(tmp_path: Path) -> None:
    extensionless = tmp_path / "possible_dicom"
    extensionless.write_bytes(b"opaque input")
    _write_policy(tmp_path, [])

    findings = run_checks(tmp_path, paths=["possible_dicom"])
    assert [(finding.path, finding.rule) for finding in findings] == [
        ("possible_dicom", "ASSET_NOT_IN_APPROVED_INVENTORY")
    ]


def test_utf8_character_split_at_binary_sample_boundary_is_not_binary(tmp_path: Path) -> None:
    markdown = tmp_path / "notes.md"
    markdown.write_bytes(b"a" * 8191 + "—".encode("utf-8"))

    assert is_probably_binary(markdown) is False
