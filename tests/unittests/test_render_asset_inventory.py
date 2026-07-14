"""Tests for the generated human-readable sensitive-asset inventory."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.render_asset_inventory import MARKDOWN_RELATIVE_PATH, main, render_inventory_markdown


def _write_inventory(root: Path) -> None:
    docs = root / "dev-docs"
    docs.mkdir()
    (docs / "approved_asset_inventory.json").write_text(
        json.dumps(
            {
                "version": 1,
                "assets": [
                    {
                        "path": "figures/sample.png",
                        "sha256": "a" * 64,
                        "kind": "image",
                        "purpose": "Rendered example",
                        "review": {"status": "approved", "reviewer": "Reviewer", "reviewed_on": "2026-07-14"},
                    },
                    {
                        "path": "fixtures/example.dcm",
                        "sha256": "b" * 64,
                        "kind": "dicom",
                        "purpose": "Synthetic fixture",
                        "review": {"status": "pending", "reviewer": None, "reviewed_on": None},
                        "dicom_review": {
                            "direct_identifiers_reviewed": False,
                            "private_tags_reviewed": True,
                            "burned_in_text_reviewed": False,
                        },
                    },
                ],
            }
        ),
        encoding="utf-8",
    )


def test_render_links_assets_and_shows_review_state(tmp_path: Path) -> None:
    _write_inventory(tmp_path)

    rendered = render_inventory_markdown(tmp_path)

    assert "[`figures/sample.png`](../figures/sample.png)" in rendered
    assert "✅ Approved — Reviewer (2026-07-14)" in rendered
    assert "⏳ Pending manual review" in rendered
    assert "IDs ☐ · private ✓ · pixels ☐" in rendered
    assert "`aaaaaaaaaaaa`" in rendered
    assert "a" * 64 not in rendered


def test_check_detects_stale_or_matching_markdown(tmp_path: Path) -> None:
    _write_inventory(tmp_path)

    assert main(["--repo-root", str(tmp_path), "--check"]) == 1
    output = tmp_path / MARKDOWN_RELATIVE_PATH
    output.write_text(render_inventory_markdown(tmp_path), encoding="utf-8")
    assert main(["--repo-root", str(tmp_path), "--check"]) == 0
