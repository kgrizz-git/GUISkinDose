"""Tests for XLSX zip-bomb / cell-budget guards in tabular_loader."""

from __future__ import annotations

import zipfile
from pathlib import Path
from typing import Self

import pytest
from openpyxl import Workbook

from mypyskindose.input_adapters import tabular_loader
from mypyskindose.input_adapters.tabular_loader import (
    assert_xlsx_zip_within_budget,
    read_excel,
)


def _write_sheet(path: Path, rows: list[list[object]], sheet_title: str = "Sheet1") -> None:
    workbook = Workbook()
    worksheet = workbook.active
    assert worksheet is not None
    worksheet.title = sheet_title
    for row in rows:
        worksheet.append(row)
    workbook.save(path)


def test_read_excel_accepts_small_workbook(tmp_path: Path) -> None:
    path = tmp_path / "ok.xlsx"
    _write_sheet(path, [["kVp", "DAP"], ["80", "1.2"], ["90", "2.3"]])
    loaded = read_excel(path)
    assert loaded.raw_df.shape[0] >= 2
    assert loaded.delimiter is None


def test_assert_xlsx_zip_within_budget_rejects_large_member(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(tabular_loader, "MAX_XLSX_UNCOMPRESSED_MEMBER_BYTES", 32)
    monkeypatch.setattr(tabular_loader, "MAX_XLSX_UNCOMPRESSED_TOTAL_BYTES", 10_000)
    path = tmp_path / "member_bomb.xlsx"
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("xl/worksheets/sheet1.xml", "x" * 64)
    with pytest.raises(ValueError, match="uncompressed size"):
        assert_xlsx_zip_within_budget(path)


def test_assert_xlsx_zip_within_budget_rejects_large_total(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(tabular_loader, "MAX_XLSX_UNCOMPRESSED_MEMBER_BYTES", 100)
    monkeypatch.setattr(tabular_loader, "MAX_XLSX_UNCOMPRESSED_TOTAL_BYTES", 50)
    path = tmp_path / "total_bomb.xlsx"
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("xl/a.xml", "a" * 40)
        archive.writestr("xl/b.xml", "b" * 40)
    with pytest.raises(ValueError, match="uncompressed size"):
        assert_xlsx_zip_within_budget(path)


def test_read_excel_rejects_cell_budget_overflow(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(tabular_loader, "MAX_XLSX_CELLS", 4)
    monkeypatch.setattr(tabular_loader, "MAX_XLSX_ROWS", 100)
    monkeypatch.setattr(tabular_loader, "MAX_XLSX_COLS", 100)
    path = tmp_path / "wide.xlsx"
    _write_sheet(path, [["a", "b", "c"], ["1", "2", "3"], ["4", "5", "6"]])
    with pytest.raises(ValueError, match="cell budget"):
        read_excel(path)


def test_read_excel_rejects_row_budget_overflow(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(tabular_loader, "MAX_XLSX_ROWS", 2)
    monkeypatch.setattr(tabular_loader, "MAX_XLSX_CELLS", 10_000)
    path = tmp_path / "tall.xlsx"
    _write_sheet(path, [["h"], ["1"], ["2"], ["3"]])
    with pytest.raises(ValueError, match="number of rows"):
        read_excel(path)


def test_assert_xlsx_zip_within_budget_rejects_bad_zip(tmp_path: Path) -> None:
    path = tmp_path / "not.xlsx"
    path.write_text("not a zip", encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid Excel workbook"):
        assert_xlsx_zip_within_budget(path)


def test_assert_xlsx_zip_within_budget_rejects_underreported_inflate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Forged ZipInfo.file_size must not bypass the inflate-byte budget.

    CPython's ``zipfile`` may raise ``BadZipFile`` (CRC) when ``file_size`` is
    underreported; that is also a hard reject. When inflate proceeds, the
    streamed byte counter must still enforce the member budget.
    """
    monkeypatch.setattr(tabular_loader, "MAX_XLSX_UNCOMPRESSED_MEMBER_BYTES", 50)
    monkeypatch.setattr(tabular_loader, "MAX_XLSX_UNCOMPRESSED_TOTAL_BYTES", 10_000)
    path = tmp_path / "underreported.xlsx"
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("xl/worksheets/sheet1.xml", "z" * 200)

    real_zipfile = zipfile.ZipFile

    class LyingZipFile(real_zipfile):
        def infolist(self):  # type: ignore[override]
            infos = super().infolist()
            for info in infos:
                info.file_size = 10
            return infos

    monkeypatch.setattr(tabular_loader.zipfile, "ZipFile", LyingZipFile)
    with pytest.raises(ValueError, match=r"uncompressed size|Invalid Excel workbook"):
        assert_xlsx_zip_within_budget(path)


def test_count_decompressed_member_enforces_streamed_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Streamed inflate bytes are counted even when declared size looks small."""
    monkeypatch.setattr(tabular_loader, "MAX_XLSX_UNCOMPRESSED_MEMBER_BYTES", 50)
    monkeypatch.setattr(tabular_loader, "MAX_XLSX_UNCOMPRESSED_TOTAL_BYTES", 10_000)

    class _FakeMember:
        def __init__(self, payload: bytes) -> None:
            self._payload = payload
            self._offset = 0

        def read(self, size: int = -1) -> bytes:
            if self._offset >= len(self._payload):
                return b""
            if size < 0:
                size = len(self._payload) - self._offset
            chunk = self._payload[self._offset : self._offset + size]
            self._offset += len(chunk)
            return chunk

        def __enter__(self) -> Self:
            return self

        def __exit__(self, *args: object) -> None:
            return None

    class _FakeArchive:
        def open(self, info: zipfile.ZipInfo, mode: str = "r") -> _FakeMember:
            assert mode == "r"
            return _FakeMember(b"x" * 200)

    info = zipfile.ZipInfo("xl/worksheets/sheet1.xml")
    info.file_size = 10
    with pytest.raises(ValueError, match="uncompressed size"):
        tabular_loader._count_decompressed_member(_FakeArchive(), info, total_so_far=0)  # type: ignore[arg-type]
