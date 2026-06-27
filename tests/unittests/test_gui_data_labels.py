"""Tests for GUI-only Data tab column labels."""

from __future__ import annotations

import pytest

pytest.importorskip("nicegui")

from mypyskindose.gui.tabs.data import display_column_label


def test_table_position_columns_get_display_aliases():
    assert display_column_label("Tx") == "Tx (X/LON)"
    assert display_column_label("Ty") == "Ty (Y/VER)"
    assert display_column_label("Tz") == "Tz (Z/LAT)"
    assert display_column_label("DoseRP_Gy") == "DoseRP_Gy"
