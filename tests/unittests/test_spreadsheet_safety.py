"""Tests for spreadsheet formula-injection neutralization (CWE-1236)."""

from __future__ import annotations

import io

import pandas as pd
import pytest
from openpyxl import load_workbook

from mypyskindose.spreadsheet_safety import neutralize_dataframe, neutralize_spreadsheet_value


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ('=HYPERLINK("https://attacker.example","open")', '\'=HYPERLINK("https://attacker.example","open")'),
        ("+cmd|' /C calc'!A0", "'+cmd|' /C calc'!A0"),
        ("-2+3+cmd|' /C calc'!A0", "'-2+3+cmd|' /C calc'!A0"),
        ("@SUM(1+1)", "'@SUM(1+1)"),
        ("\tbeacon", "'\tbeacon"),
        ("\rbeacon", "'\rbeacon"),
        ("normal text", "normal text"),
        ("", ""),
    ],
)
def test_neutralize_spreadsheet_value_prefixes(raw: str, expected: str) -> None:
    assert neutralize_spreadsheet_value(raw) == expected


def test_neutralize_spreadsheet_value_preserves_non_strings() -> None:
    assert neutralize_spreadsheet_value(42) == 42
    assert neutralize_spreadsheet_value(None) is None


def test_neutralize_dataframe_only_touches_object_columns() -> None:
    df = pd.DataFrame(
        {
            "VendorNote": ['=HYPERLINK("x","y")', "ok"],
            "kVp": [80.0, 90.0],
        }
    )
    safe = neutralize_dataframe(df)
    assert safe.loc[0, "VendorNote"].startswith("'")
    assert safe.loc[1, "VendorNote"] == "ok"
    assert safe["kVp"].tolist() == [80.0, 90.0]
    assert df.loc[0, "VendorNote"].startswith("=")


def test_neutralized_xlsx_export_is_not_formula_cell() -> None:
    payload = '=HYPERLINK("https://attacker.example/beacon","open")'
    safe_df = neutralize_dataframe(pd.DataFrame([{"VendorNote": payload}]))
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        safe_df.to_excel(writer, index=False)
    buf.seek(0)
    ws = load_workbook(buf)["Sheet1"]
    cell = ws["A2"]
    assert cell.data_type == "s"
    assert cell.value.startswith("'")
