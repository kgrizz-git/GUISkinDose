"""Catalog-backed UI copy helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[3]
_CATALOG = _REPO_ROOT / "dev-docs" / "ui_copy.json"


def _load_catalog() -> dict[str, Any]:
    data = json.loads(_CATALOG.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise KeyError("ui_copy.json")
    keys = data.get("keys")
    if not isinstance(keys, dict):
        raise KeyError("keys")
    return keys


def copy_text(key: str) -> str:
    """Return UI copy text for a catalog key."""
    keys = _load_catalog()
    item = keys.get(key)
    if not isinstance(item, dict):
        raise KeyError(key)
    text = item.get("text")
    if not isinstance(text, str) or not text:
        raise KeyError(key)
    return text
