"""Process-wide and per-library locks for phantom pack installs."""

from __future__ import annotations

import errno
import os
import sys
import threading
from pathlib import Path
from typing import Self

_INSTALL_MUTEX = threading.Lock()


class LibraryInstallLockBusy(OSError):
    """The per-library install lock file is already held."""


def install_process_lock():
    """Serialize in-process pack installs (e.g. multiple GUI sessions)."""
    return _INSTALL_MUTEX


def _lock_contention(exc: BaseException) -> bool:
    if isinstance(exc, BlockingIOError):
        return True
    if not isinstance(exc, OSError):
        return False
    if exc.errno in {errno.EAGAIN, errno.EWOULDBLOCK}:
        return True
    if sys.platform == "win32" and exc.errno in {errno.EACCES, 33, 36}:
        return True
    return False


class LibraryInstallLock:
    """Exclusive lock file under the user mesh library directory."""

    def __init__(self, library_root: Path) -> None:
        self._path = library_root / ".install.lock"
        self._handle: int | None = None

    def __enter__(self) -> Self:
        if not self._path.parent.is_dir():
            raise OSError("phantom library root is missing")
        if sys.platform == "win32":
            from guiskindose.phantom_library import _path_is_library_link

            if self._path.is_symlink() or (
                self._path.exists() and _path_is_library_link(self._path, "win32")
            ):
                raise OSError("install lock path is a link")
        follow_flag = getattr(os, "O_NOFOLLOW", 0)
        try:
            fd = os.open(self._path, os.O_RDWR | os.O_CREAT | follow_flag, 0o600)
        except OSError as exc:
            if _lock_contention(exc):
                raise LibraryInstallLockBusy(str(exc)) from exc
            raise
        try:
            if sys.platform == "win32":
                import msvcrt

                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self._handle = fd
            return self
        except OSError as exc:
            os.close(fd)
            if _lock_contention(exc):
                raise LibraryInstallLockBusy(str(exc)) from exc
            raise

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._handle is not None:
            try:
                if sys.platform == "win32":
                    import msvcrt

                    msvcrt.locking(self._handle, msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(self._handle, fcntl.LOCK_UN)
            finally:
                os.close(self._handle)
                self._handle = None
