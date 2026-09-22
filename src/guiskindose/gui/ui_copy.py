"""Catalog-backed UI copy helpers."""

from __future__ import annotations

import importlib.resources
import json
from pathlib import Path
from typing import Any

_PACKAGED_CATALOG_TRAVERSABLE = importlib.resources.files("guiskindose.gui").joinpath("ui_copy.json")
_REPO_ROOT = Path(__file__).resolve().parents[3]
_REPO_CATALOG = _REPO_ROOT / "dev-docs" / "ui_copy.json"


def _read_catalog_text() -> str:
    """Read the bundled catalog, falling back to the repo source of truth.

    The packaged copy (mirrored by ``scripts/sync_ui_copy.py``) is what ships
    in wheels, where ``dev-docs/`` does not exist. The repo fallback keeps
    exotic source layouts working and is byte-identical when in sync.
    """
    if _PACKAGED_CATALOG_TRAVERSABLE.is_file():
        return _PACKAGED_CATALOG_TRAVERSABLE.read_text(encoding="utf-8")
    return _REPO_CATALOG.read_text(encoding="utf-8")


def _load_catalog() -> dict[str, Any]:
    data = json.loads(_read_catalog_text())
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
