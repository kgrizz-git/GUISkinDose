"""Unit tests for the GUI uploaded-temp-file lifecycle (refactor plan Phase 0.1).

The GUI writes uploads to NamedTemporaryFile(delete=False) so the parser and the
XLSX sheet picker can read them. These tests pin the cleanup contract: only the
current upload survives, each new upload deletes the prior one, and the atexit
sweep removes whatever remains.
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


def test_new_upload_deletes_previous():
    first = _make_temp()
    second = _make_temp()
    gui_app._register_temp_upload(first)
    gui_app._register_temp_upload(second)

    assert not first.exists(), "previous upload temp file should be deleted"
    assert second.exists(), "current upload temp file should survive"
    assert gui_app._uploaded_temp_files == [second]


def test_atexit_sweep_removes_remaining():
    path = _make_temp()
    gui_app._register_temp_upload(path)
    assert path.exists()

    gui_app._cleanup_temp_uploads()

    assert not path.exists()
    assert gui_app._uploaded_temp_files == []


def test_discard_temp_upload_removes_registered_file():
    path = _make_temp()
    gui_app._register_temp_upload(path)

    gui_app._discard_temp_upload(path)

    assert not path.exists()
    assert gui_app._uploaded_temp_files == []


def test_discard_temp_upload_tolerates_already_deleted_file():
    path = _make_temp()
    gui_app._register_temp_upload(path)
    path.unlink()

    gui_app._discard_temp_upload(path)

    assert gui_app._uploaded_temp_files == []


def test_discard_temp_upload_ignores_unregistered_file():
    path = _make_temp()

    gui_app._discard_temp_upload(path)

    assert path.exists()
    path.unlink()


def test_cleanup_tolerates_already_deleted_file():
    path = _make_temp()
    gui_app._register_temp_upload(path)
    path.unlink()  # simulate external deletion

    # Should not raise even though the tracked file is already gone.
    gui_app._cleanup_temp_uploads()
    assert gui_app._uploaded_temp_files == []


def test_register_tolerates_already_deleted_previous():
    first = _make_temp()
    gui_app._register_temp_upload(first)
    first.unlink()  # previous file vanishes before the next upload

    second = _make_temp()
    gui_app._register_temp_upload(second)  # must not raise

    assert gui_app._uploaded_temp_files == [second]
    assert second.exists()
