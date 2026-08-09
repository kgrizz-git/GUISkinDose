"""Private per-session storage and bounded cleanup for GUI uploads."""

from __future__ import annotations

import atexit
import logging
import os
import shutil
import tempfile
import time
from contextlib import suppress
from pathlib import Path

from mypyskindose.privacy import safe_error_event

_STALE_AFTER_SECONDS = 24 * 60 * 60
_ALLOWED_SUFFIXES = {".csv", ".dcm", ".dicom", ".tsv", ".xlsx", ".xlsm"}
_uploaded_temp_files: list[Path] = []
_session_dir: Path | None = None
logger = logging.getLogger(__name__)


def _private_base_dir() -> Path:
    base = Path(tempfile.gettempdir()) / "mypyskindose-uploads"
    base.mkdir(mode=0o700, parents=True, exist_ok=True)
    if os.name == "posix":
        base.chmod(0o700)
    return base


def cleanup_stale_sessions(*, now: float | None = None) -> int:
    """Remove expired app-owned session directories without logging paths."""
    base = _private_base_dir()
    cutoff = (time.time() if now is None else now) - _STALE_AFTER_SECONDS
    removed = 0
    for candidate in base.glob("session-*"):
        try:
            if candidate.is_dir() and candidate.stat().st_mtime < cutoff:
                shutil.rmtree(candidate)
                removed += 1
        except OSError as exc:
            safe_error_event(logger, "stale_upload_cleanup", exc, level=logging.DEBUG)
    return removed


def _ensure_session_dir() -> Path:
    global _session_dir
    if _session_dir is None:
        cleanup_stale_sessions()
        _session_dir = Path(tempfile.mkdtemp(prefix="session-", dir=_private_base_dir()))
        if os.name == "posix":
            _session_dir.chmod(0o700)
    return _session_dir


def create_temp_upload(data: bytes, *, suffix: str) -> Path:
    """Write an upload under a random name in the private session directory."""
    normalized_suffix = suffix.casefold() if suffix.casefold() in _ALLOWED_SUFFIXES else ".bin"
    fd, name = tempfile.mkstemp(prefix="upload-", suffix=normalized_suffix, dir=_ensure_session_dir())
    path = Path(name)
    try:
        if os.name == "posix":
            os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    except Exception:
        path.unlink(missing_ok=True)
        raise
    register_temp_upload(path)
    return path


def register_temp_upload(path: Path) -> None:
    """Track a temporary upload so remove/clear/shutdown can delete it."""
    _uploaded_temp_files.append(path)


def remove_temp_upload(path: Path) -> None:
    """Delete one registered upload; never delete an unregistered source file."""
    if path not in _uploaded_temp_files:
        return
    try:
        path.unlink(missing_ok=True)
    except OSError as exc:
        safe_error_event(logger, "temporary_upload_delete", exc, level=logging.DEBUG)
    _uploaded_temp_files.remove(path)


def clear_all_temp_uploads() -> None:
    """Delete and deregister all accumulated upload files."""
    while _uploaded_temp_files:
        remove_temp_upload(_uploaded_temp_files[-1])


@atexit.register
def cleanup_temp_uploads() -> None:
    """Remove remaining files and the private session directory."""
    global _session_dir
    clear_all_temp_uploads()
    if _session_dir is not None:
        with suppress(OSError):
            _session_dir.rmdir()
        _session_dir = None
