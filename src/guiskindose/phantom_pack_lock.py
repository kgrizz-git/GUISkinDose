"""Process-wide and per-library locks for phantom pack installs."""

from __future__ import annotations

import os
import sys
import threading
from pathlib import Path
from typing import Self

_INSTALL_MUTEX = threading.Lock()


def install_process_lock():
    """Serialize in-process pack installs (e.g. multiple GUI sessions)."""
    return _INSTALL_MUTEX


class LibraryInstallLock:
    """Exclusive lock file under the user mesh library directory."""

    def __init__(self, library_root: Path) -> None:
        self._path = library_root / ".install.lock"
        self._handle: int | None = None

    def __enter__(self) -> Self:
        if not self._path.parent.is_dir():
            raise OSError("phantom library root is missing")
        fd = os.open(self._path, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
        try:
            if sys.platform == "win32":
                import msvcrt

                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self._handle = fd
            return self
        except OSError:
            os.close(fd)
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
                # The lock file is left in place. Unlinking it would let a waiting
                # process lock the old inode while another creates a new file.
                os.close(self._handle)
                self._handle = None
