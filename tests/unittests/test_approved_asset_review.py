"""Tests for exact-hash scanner triage through the approved asset inventory."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts.approved_asset_review import is_hash_pinned_approved


def write_inventory(root: Path, asset: Path, *, dicom: bool = False) -> None:
    relative = asset.relative_to(root)
    entry = {
        "path": relative.as_posix(),
        "sha256": hashlib.sha256(asset.read_bytes()).hexdigest(),
        "kind": "dicom" if dicom else "image",
        "review": {"status": "approved", "reviewer": "KG", "reviewed_on": "2026-07-16"},
    }
    if dicom:
        entry["dicom_review"] = {
            "direct_identifiers_reviewed": True,
            "private_tags_reviewed": True,
            "burned_in_text_reviewed": True,
        }
    inventory = root / "dev-docs" / "approved_asset_inventory.json"
    inventory.parent.mkdir(exist_ok=True)
    inventory.write_text(json.dumps({"version": 1, "assets": [entry]}), encoding="utf-8")


def test_approval_requires_exact_current_hash(tmp_path: Path) -> None:
    asset = tmp_path / "image.png"
    asset.write_bytes(b"reviewed")
    write_inventory(tmp_path, asset)

    assert is_hash_pinned_approved(tmp_path, Path("image.png"))

    asset.write_bytes(b"changed")
    assert not is_hash_pinned_approved(tmp_path, Path("image.png"))


def test_dicom_approval_requires_specific_review_checklist(tmp_path: Path) -> None:
    asset = tmp_path / "fixture.dcm"
    asset.write_bytes(b"synthetic")
    write_inventory(tmp_path, asset, dicom=False)

    assert not is_hash_pinned_approved(tmp_path, Path("fixture.dcm"), require_dicom_review=True)

    write_inventory(tmp_path, asset, dicom=True)
    assert is_hash_pinned_approved(tmp_path, Path("fixture.dcm"), require_dicom_review=True)
