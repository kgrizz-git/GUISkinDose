"""Unit tests for the GUI uploaded-temp-file lifecycle.

The GUI writes uploads to NamedTemporaryFile(delete=False) so the parser and the
XLSX sheet picker can read them. Since multi-exam Phase 2.1 the registry is
*accumulating*: each new upload is appended (previous files survive so multiple
exams can be loaded at once). Individual files are removed via remove_temp_upload
(when an exam is removed), all at once via clear_all_temp_uploads ("Clear all"),
and the atexit sweep removes whatever remains.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

pytest.importorskip("nicegui")

import mypyskindose.gui.upload_temp_files as temp_files


def _make_temp(suffix: str = ".csv") -> Path:
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(b"placeholder")
        return Path(tmp.name)


@pytest.fixture(autouse=True)
def _clean_registry():
    """Each test starts and ends with an empty registry and no leaked files."""
    temp_files.cleanup_temp_uploads()
    yield
    temp_files.cleanup_temp_uploads()


def test_register_tracks_current_upload():
    path = _make_temp()
    temp_files.register_temp_upload(path)
    assert path in temp_files._uploaded_temp_files
    assert path.exists()


def test_create_temp_upload_uses_private_random_session_storage():
    source_name = "PATIENT-SENTINEL-12345.dcm"
    path = temp_files.create_temp_upload(b"synthetic", suffix=Path(source_name).suffix)

    assert source_name not in str(path)
    assert path.name.startswith("upload-")
    assert path.parent.name.startswith("session-")
    assert path.read_bytes() == b"synthetic"
    if os.name == "posix":
        assert path.stat().st_mode & 0o777 == 0o600
        assert path.parent.stat().st_mode & 0o777 == 0o700


def test_register_accumulates_uploads():
    first = _make_temp()
    second = _make_temp()
    temp_files.register_temp_upload(first)
    temp_files.register_temp_upload(second)

    assert first.exists(), "previous upload temp file should survive (accumulating)"
    assert second.exists(), "current upload temp file should survive"
    assert temp_files._uploaded_temp_files == [first, second]


def test_remove_temp_upload_deletes_one():
    first = _make_temp()
    second = _make_temp()
    temp_files.register_temp_upload(first)
    temp_files.register_temp_upload(second)

    temp_files.remove_temp_upload(first)

    assert not first.exists(), "removed exam's temp file should be deleted"
    assert second.exists(), "other exam's temp file should be untouched"
    assert temp_files._uploaded_temp_files == [second]


def test_remove_temp_upload_ignores_unregistered_source_file(tmp_path: Path):
    source = tmp_path / "source.dcm"
    source.write_bytes(b"not a temp upload")

    temp_files.remove_temp_upload(source)

    assert source.exists(), "unregistered source files must not be deleted"
    assert temp_files._uploaded_temp_files == []


def test_clear_all_temp_uploads_removes_everything():
    first = _make_temp()
    second = _make_temp()
    temp_files.register_temp_upload(first)
    temp_files.register_temp_upload(second)

    temp_files.clear_all_temp_uploads()

    assert not first.exists()
    assert not second.exists()
    assert temp_files._uploaded_temp_files == []


def test_atexit_sweep_removes_remaining():
    path = _make_temp()
    temp_files.register_temp_upload(path)
    assert path.exists()

    temp_files.cleanup_temp_uploads()

    assert not path.exists()
    assert temp_files._uploaded_temp_files == []


def test_cleanup_tolerates_already_deleted_file():
    path = _make_temp()
    temp_files.register_temp_upload(path)
    path.unlink()

    temp_files.cleanup_temp_uploads()
    assert temp_files._uploaded_temp_files == []


def test_remove_temp_upload_tolerates_already_deleted():
    first = _make_temp()
    temp_files.register_temp_upload(first)
    first.unlink()

    temp_files.remove_temp_upload(first)

    assert temp_files._uploaded_temp_files == []
