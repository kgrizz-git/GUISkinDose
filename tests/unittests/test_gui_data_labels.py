"""Tests for GUI-only Data tab column labels."""

from __future__ import annotations

import pytest

pytest.importorskip("nicegui")

from mypyskindose.gui.tabs.data import display_column_label


def test_table_position_columns_get_display_aliases():
    assert display_column_label("Tx") == "Tx (X, DICOM LON, PT L-R)"
    assert display_column_label("Ty") == "Ty (Y, DICOM VER, PT A-P)"
    assert display_column_label("Tz") == "Tz (Z, DICOM LAT, PT S-I)"
    assert display_column_label("DoseRP_Gy") == "DoseRP_Gy"
