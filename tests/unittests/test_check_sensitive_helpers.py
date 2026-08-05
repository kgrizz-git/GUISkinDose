"""Direct regression tests for sensitive-content format reader helpers."""

from __future__ import annotations

from scripts.check_sensitive_helpers import cell_data_mappings


def test_cell_data_mappings_yields_attachments_before_outputs() -> None:
    cell = {
        "attachments": {"first": {"image/png": "attachment"}, "ignored": "not-a-map"},
        "outputs": [
            {"data": {"image/jpeg": "output"}},
            {"data": "not-a-map"},
            "not-an-output",
        ],
    }

    assert list(cell_data_mappings(cell)) == [
        {"image/png": "attachment"},
        {"image/jpeg": "output"},
    ]


def test_cell_data_mappings_skips_malformed_cells() -> None:
    assert list(cell_data_mappings("not-a-cell")) == []
