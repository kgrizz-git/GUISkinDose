"""Uploaded temp-file lifecycle for the GUI (refactor plan Phase 3.3g).

Uploads are written to NamedTemporaryFile(delete=False) so the parser (and the
XLSX sheet picker, which re-reads the path on every sheet change) can read them.
The registry is accumulating: each new upload is appended so multiple exams can
be loaded at once. Individual files are removed via ``remove_temp_upload`` (when
an exam is removed), all at once via ``clear_all_temp_uploads`` ("Clear all"),
and the atexit sweep removes whatever remains at shutdown. Bundled example files
are never registered here, so they are never deleted.
"""

from __future__ import annotations

import atexit
from pathlib import Path

from mypyskindose.debug import dprint

_uploaded_temp_files: list[Path] = []


def register_temp_upload(path: Path) -> None:
    """Track a freshly written upload temp file (accumulating — does not delete others)."""
    _uploaded_temp_files.append(path)


def remove_temp_upload(path: Path) -> None:
    """Delete one specific temp file and deregister it (called when user removes an exam)."""
    try:
        path.unlink(missing_ok=True)
    except OSError as exc:
        dprint("GUI", f"Could not delete temp upload {path}: {exc}")
    try:
        _uploaded_temp_files.remove(path)
    except ValueError:
        pass


def clear_all_temp_uploads() -> None:
    """Delete and deregister all accumulated upload temp files."""
    while _uploaded_temp_files:
        old = _uploaded_temp_files.pop()
        try:
            old.unlink(missing_ok=True)
        except OSError:
            pass


@atexit.register
def cleanup_temp_uploads() -> None:
    """Remove any remaining upload temp files at process exit."""
    for path in _uploaded_temp_files:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
    _uploaded_temp_files.clear()
