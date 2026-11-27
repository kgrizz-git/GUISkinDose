"""Coverage for Data tab export helpers and table refresh."""

from __future__ import annotations

from typing import cast
from unittest.mock import AsyncMock, MagicMock

import pandas as pd
import pytest
from pydicom.valuerep import DSdecimal

pytest.importorskip("nicegui")

import orjson
from nicegui import ui

from guiskindose.export import failure_guidance as fg
from guiskindose.export.failure_guidance import ExportFailureKind
from guiskindose.gui.state import state
from guiskindose.gui.tabs import data as data_tab


@pytest.fixture(autouse=True)
def _reset_view_flags() -> None:
    state.view_raw = False
    state.rdsr_df = None
    state.rdsr_raw_df = None
    state.manufacturer = "TestMfr"
    state.model = "TestModel"
    state.normalization_method = "none"
    state.table_offset_x = 0.0
    state.table_offset_y = 0.0
    state.table_offset_z = 0.0


def test_export_metadata_includes_offsets() -> None:
    state.table_offset_x = 1.5
    meta = data_tab._export_metadata()
    assert list(meta.columns) == [
        "Manufacturer",
        "Model",
        "Normalization Method",
        "Table Offset X [cm]",
        "Table Offset Y [cm]",
        "Table Offset Z [cm]",
        "Export Type",
    ]
    assert float(meta.iloc[0]["Table Offset X [cm]"]) == 1.5
    assert meta.iloc[0]["Export Type"] == "Normalized"


def test_export_content_csv_and_txt() -> None:
    df = pd.DataFrame({"Tx": [1.0], "Ty": [2.0]})
    csv_bytes = data_tab._export_content(df, "csv")
    txt_bytes = data_tab._export_content(df, "txt")
    assert b"Tx" in csv_bytes
    assert b"METADATA" in txt_bytes
    assert b"Tx" in txt_bytes


def test_export_content_xlsx() -> None:
    df = pd.DataFrame({"Tz": [3.0]})
    xlsx_bytes = data_tab._export_content(df, "xlsx")
    assert isinstance(xlsx_bytes, bytes)
    assert len(xlsx_bytes) > 20


def test_refresh_raw_table_empty() -> None:
    table = MagicMock()
    data_tab._refresh_raw_table(table)
    assert table.columns == []
    assert table.rows == []
    cast(MagicMock, table.update).assert_called_once()


def test_refresh_raw_table_with_exam_column() -> None:
    state.rdsr_df = pd.DataFrame(
        {
            data_tab.EXAM_COLUMN: ["Exam A"],
            data_tab.EXAM_INDEX_COLUMN: [0],
            "Tx": [1.0],
        }
    )
    table = MagicMock()
    data_tab._refresh_raw_table(table)
    names = [c["name"] for c in table.columns]
    assert names[0] == data_tab.EXAM_COLUMN
    assert data_tab.EXAM_INDEX_COLUMN not in names
    assert len(table.rows) == 1
    cast(MagicMock, table.update).assert_called()


def test_refresh_raw_table_pydicom_native_rows_serialize() -> None:
    """Boundary regression: RAW pydicom natives must reach the table orjson-safe.

    Reverting ``data.py`` to bare ``to_dict("records")`` must fail this test:
    the socket emit serializes ``table.rows`` with orjson. Note ``DSdecimal``
    (not ``DSfloat``): ``to_dict`` self-converts float subclasses to plain
    floats, while ``DSdecimal``/``PersonName``/``Timestamp`` survive as exotic
    instances; production frames additionally carry nested ``DSfloat`` tuples
    (covered in the unit tests).
    """
    state.view_raw = True
    # dtype=object: without it pandas coerces DSdecimal to float64 at frame
    # construction and the test would pass even with the bug present.
    state.rdsr_raw_df = pd.DataFrame([{"dose": DSdecimal("12.5")}], dtype=object)
    table = MagicMock()
    data_tab._refresh_raw_table(table)
    assert len(table.rows) == 1
    orjson.dumps(table.rows)  # what the socket emit does; must not raise
    assert table.rows[0]["dose"] == 12.5
    cast(MagicMock, table.update).assert_called()


@pytest.mark.asyncio
async def test_local_export_warns_without_data(monkeypatch: pytest.MonkeyPatch) -> None:
    messages: list[str] = []
    monkeypatch.setattr(ui, "notify", lambda msg, **k: messages.append(str(msg)))
    state.rdsr_df = None
    await data_tab._local_export("csv")
    assert any("No data to export" in m for m in messages)


@pytest.mark.asyncio
async def test_local_export_browser_download(monkeypatch: pytest.MonkeyPatch) -> None:
    state.rdsr_df = pd.DataFrame({"Tx": [1.0]})
    downloaded: list[tuple] = []
    messages: list[str] = []
    monkeypatch.setattr(data_tab, "_is_native_mode", lambda: False)
    monkeypatch.setattr(data_tab, "_get_save_path", AsyncMock(return_value=None))
    monkeypatch.setattr(ui, "download", lambda content, name: downloaded.append((content, name)))
    monkeypatch.setattr(ui, "notify", lambda msg, **k: messages.append(str(msg)))

    await data_tab._local_export("csv")

    assert downloaded
    assert downloaded[0][1].endswith(".csv")
    assert any("Downloaded CSV" in m for m in messages)


@pytest.mark.asyncio
async def test_local_export_xlsx_preflight_shows_guidance_before_content(monkeypatch: pytest.MonkeyPatch) -> None:
    state.rdsr_df = pd.DataFrame({"Tx": [1.0]})
    shown: list = []
    get_save_path = AsyncMock(return_value=None)
    monkeypatch.setattr(data_tab, "show_export_failure_dialog", shown.append)
    monkeypatch.setattr(data_tab, "_get_save_path", get_save_path)
    monkeypatch.setattr(fg, "missing_backend", lambda fmt: "openpyxl" if fmt == "xlsx" else None)

    def _must_not_build(*_args, **_kwargs):
        raise AssertionError("preflight must report before content is built")

    monkeypatch.setattr(data_tab, "_export_content", _must_not_build)

    await data_tab._local_export("xlsx")  # must not raise

    get_save_path.assert_not_awaited()
    assert [failure.kind for failure in shown] == [ExportFailureKind.MISSING_PACKAGE]
    assert shown[0].command == "pip install openpyxl"


@pytest.mark.asyncio
async def test_local_export_content_import_failure_shows_guidance(monkeypatch: pytest.MonkeyPatch) -> None:
    """The post-preflight content build is still guarded (preflight can miss a damaged backend)."""
    state.rdsr_df = pd.DataFrame({"Tx": [1.0]})
    shown: list = []
    get_save_path = AsyncMock(return_value=None)
    monkeypatch.setattr(data_tab, "show_export_failure_dialog", shown.append)
    monkeypatch.setattr(data_tab, "_get_save_path", get_save_path)
    monkeypatch.setattr(fg, "missing_backend", lambda _fmt: None)

    def _boom(*_args, **_kwargs):
        raise ModuleNotFoundError("No module named 'openpyxl'")

    monkeypatch.setattr(data_tab, "_export_content", _boom)

    await data_tab._local_export("xlsx")  # must not raise

    get_save_path.assert_not_awaited()
    assert [failure.kind for failure in shown] == [ExportFailureKind.INCOMPLETE_INSTALL]
