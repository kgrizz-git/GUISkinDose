"""Shared exact-hash approval checks for advisory scanner triage."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

INVENTORY_PATH = Path("dev-docs/approved_asset_inventory.json")
DICOM_REVIEW_FIELDS = (
    "direct_identifiers_reviewed",
    "private_tags_reviewed",
    "burned_in_text_reviewed",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def approved_asset_entry(root: Path, relative: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads((root / INVENTORY_PATH).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    assets = payload.get("assets") if isinstance(payload, dict) else None
    if not isinstance(assets, list):
        return None
    normalized = relative.as_posix()
    for item in assets:
        if isinstance(item, dict) and item.get("path") == normalized:
            return item
    return None


def is_hash_pinned_approved(root: Path, relative: Path, *, require_dicom_review: bool = False) -> bool:
    entry = approved_asset_entry(root, relative)
    target = root / relative
    if entry is None or not target.is_file() or entry.get("sha256") != sha256(target):
        return False
    review = entry.get("review")
    if not isinstance(review, dict):
        return False
    if review.get("status") != "approved" or not review.get("reviewer") or not review.get("reviewed_on"):
        return False
    if not require_dicom_review:
        return True
    dicom_review = entry.get("dicom_review")
    return isinstance(dicom_review, dict) and all(dicom_review.get(field) is True for field in DICOM_REVIEW_FIELDS)
