"""Unit tests for UI-copy catalog packaging.

``copy_text()`` runs on every GUI page render, so the catalog must resolve
outside a source checkout too: the wheel ships a mirrored copy
(``scripts/sync_ui_copy.py``) that ``ui_copy`` prefers, with the repo
``dev-docs/`` source of truth as fallback.
"""

from __future__ import annotations

import filecmp
from pathlib import Path

from guiskindose.gui import ui_copy
from guiskindose.gui.ui_copy import copy_text

REPO_ROOT = Path(__file__).resolve().parents[2]
CANONICAL = REPO_ROOT / "dev-docs" / "ui_copy.json"
BUNDLED = Path(ui_copy.__file__).resolve().parent / "ui_copy.json"


def test_bundled_catalog_matches_canonical() -> None:
    """The packaged mirror must be byte-identical to the source of truth."""
    assert BUNDLED.is_file(), f"missing bundled catalog: {BUNDLED}"
    assert CANONICAL.is_file(), f"missing canonical catalog: {CANONICAL}"
    assert filecmp.cmp(str(CANONICAL), str(BUNDLED), shallow=False), (
        "bundled ui_copy.json drifted; run scripts/sync_ui_copy.py"
    )


def test_copy_text_resolves_privacy_notice() -> None:
    """The live onboarding notice must render through the packaged path."""
    assert copy_text("onboarding.privacy_notice")


def test_copy_text_falls_back_to_repo_catalog(monkeypatch) -> None:
    """Without the packaged copy, the repo source of truth is used."""

    class _Missing:
        def is_file(self) -> bool:
            return False

    monkeypatch.setattr(ui_copy, "_PACKAGED_CATALOG_TRAVERSABLE", _Missing())
    assert copy_text("onboarding.privacy_notice")
