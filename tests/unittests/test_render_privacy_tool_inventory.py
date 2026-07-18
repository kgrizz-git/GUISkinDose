"""Tests for the privacy-tool inventory contract."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.render_privacy_tool_inventory import render, validate


def test_repository_tool_inventory_covers_every_conditional_scanner() -> None:
    root = Path(__file__).resolve().parents[2]
    inventory = json.loads((root / "dev-docs/privacy_tool_inventory.json").read_text(encoding="utf-8"))
    policy = json.loads((root / "dev-docs/privacy_admission_policy.json").read_text(encoding="utf-8"))

    assert validate(inventory, policy) == []
    assert "ExifTool" in render(inventory)


def test_unknown_scanner_tool_is_rejected() -> None:
    inventory = {
        "version": 1,
        "tools": [
            {
                "id": "known",
                "name": "Known",
                "status": "active",
                "version": "1",
                "version_source": "test",
                "execution": "local",
                "role": "test",
                "output_policy": "suppressed",
                "source": "https://example.invalid/tool",
            }
        ],
    }
    policy = {"scanners": [{"id": "scan", "tool_ids": ["missing"]}]}

    assert validate(inventory, policy) == ["scanner scan references unknown tool missing"]
