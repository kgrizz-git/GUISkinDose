"""Unit tests for the GUI uploaded-temp-file lifecycle.

The GUI writes uploads to NamedTemporaryFile(delete=False) so the parser and the
XLSX sheet picker can read them. Since multi-exam Phase 2.1 the registry is
*accumulating*: each new upload is appended (previous files survive so multiple
exams can be loaded at once). Individual files are removed via _remove_temp_upload
(when an exam is removed), all at once via _clear_all_temp_uploads ("Clear all"),
and the atexit sweep removes whatever remains.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

pytest.importorskip("nicegui")

import mypyskindose.gui.app as gui_app


def _make_temp(suffix: str = ".csv") -> Path:
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(b"placeholder")
        return Path(tmp.name)


@pytest.fixture(autouse=True)
def _clean_registry():
    """Each test starts and ends with an empty registry and no leaked files."""
    gui_app._cleanup_temp_uploads()
    yield
    gui_app._cleanup_temp_uploads()


def test_register_tracks_current_upload():
    path = _make_temp()
    gui_app._register_temp_upload(path)
    assert path in gui_app._uploaded_temp_files
    assert path.exists()


def test_register_accumulates_uploads():
    first = _make_temp()
    second = _make_temp()
    gui_app._register_temp_upload(first)
    gui_app._register_temp_upload(second)

    # Accumulating model: both files survive and both stay registered so several
    # exams can be loaded at once.
    assert first.exists(), "previous upload temp file should survive (accumulating)"
    assert second.exists(), "current upload temp file should survive"
    assert gui_app._uploaded_temp_files == [first, second]


def test_remove_temp_upload_deletes_one():
    first = _make_temp()
    second = _make_temp()
    gui_app._register_temp_upload(first)
    gui_app._register_temp_upload(second)

    gui_app._remove_temp_upload(first)

    assert not first.exists(), "removed exam's temp file should be deleted"
    assert second.exists(), "other exam's temp file should be untouched"
    assert gui_app._uploaded_temp_files == [second]


def test_clear_all_temp_uploads_removes_everything():
    first = _make_temp()
    second = _make_temp()
    gui_app._register_temp_upload(first)
    gui_app._register_temp_upload(second)

    gui_app._clear_all_temp_uploads()

    assert not first.exists()
    assert not second.exists()
    assert gui_app._uploaded_temp_files == []


def test_atexit_sweep_removes_remaining():
    path = _make_temp()
    gui_app._register_temp_upload(path)
    assert path.exists()

    gui_app._cleanup_temp_uploads()

    assert not path.exists()
    assert gui_app._uploaded_temp_files == []


def test_cleanup_tolerates_already_deleted_file():
    path = _make_temp()
    gui_app._register_temp_upload(path)
    path.unlink()  # simulate external deletion

    # Should not raise even though the tracked file is already gone.
    gui_app._cleanup_temp_uploads()
    assert gui_app._uploaded_temp_files == []


def test_remove_temp_upload_tolerates_already_deleted():
    first = _make_temp()
    gui_app._register_temp_upload(first)
    first.unlink()  # file vanishes externally before the explicit removal

    # Must not raise even though the tracked file is already gone, and must still
    # deregister it.
    gui_app._remove_temp_upload(first)

    assert gui_app._uploaded_temp_files == []
