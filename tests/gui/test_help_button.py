"""Focused behavior tests for the reusable GUI help button."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from guiskindose.gui.components.help_button import HelpButton


@pytest.fixture(autouse=True)
def _skip_ui_construction():
    """Keep content-loading tests independent of a live NiceGUI client."""
    with patch.object(HelpButton, "_create_button"):
        yield


def test_inline_content_is_retained() -> None:
    button = HelpButton("Inline", content="# Inline help")

    assert button.content == "# Inline help"


def test_content_path_loads_bundled_help() -> None:
    button = HelpButton("Workflow", content_path="calculation_workflow.md")

    assert button.content.startswith("# Running Dose Calculations")


def test_missing_content_inputs_raise_existing_value_error() -> None:
    with pytest.raises(ValueError, match="Either content or content_path must be provided"):
        HelpButton("Missing")


def test_missing_content_path_raises_file_not_found() -> None:
    with pytest.raises(FileNotFoundError, match="Help file not found"):
        HelpButton("Missing", content_path="not-a-help-file.md")


def test_inline_content_takes_precedence_over_content_path() -> None:
    button = HelpButton("Inline wins", content="# Inline help", content_path="not-a-help-file.md")

    assert button.content == "# Inline help"
