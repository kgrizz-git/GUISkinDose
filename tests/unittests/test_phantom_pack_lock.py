"""Per-library and in-process phantom pack install locks."""

from __future__ import annotations

import os
import threading
from pathlib import Path

import pytest

from guiskindose.phantom_pack import PhantomPackError
from guiskindose.phantom_pack_install import _LIBRARY_BUSY, install_phantom_pack
from guiskindose.phantom_pack_lock import LibraryInstallLock, LibraryInstallLockBusy
from tests.unittests.phantom_pack_test_helpers import manifest_for_files, pack_zip_bytes, tiny_stl_body


def _pin_for(manifest: dict) -> str:
    """Pin for."""
    from guiskindose.phantom_pack import manifest_sha256

    return manifest_sha256(manifest)


def test_library_lock_refused_then_acquired(tmp_path: Path) -> None:
    """Exercise library lock refused then acquired."""
    library = tmp_path / "library"
    library.mkdir()
    first = LibraryInstallLock(library)
    first.__enter__()
    second = LibraryInstallLock(library)
    with pytest.raises(LibraryInstallLockBusy):
        second.__enter__()
    first.__exit__(None, None, None)
    with LibraryInstallLock(library):
        pass


def test_install_lock_file_persists(tmp_path: Path) -> None:
    """Exercise install lock file persists."""
    from guiskindose.phantom_pack_install import InstallResult, install_phantom_pack

    shipped = tmp_path / "shipped"
    library = tmp_path / "library"
    body = tiny_stl_body()
    manifest = manifest_for_files({"senior_male": body})
    raw = pack_zip_bytes(manifest, {"senior_male": body})
    result = install_phantom_pack(
        __import__("io").BytesIO(raw),
        user_library_dir=library,
        shipped_dir=shipped,
        expected_manifest_sha256=_pin_for(manifest),
        app_version="1.1.1",
    )
    assert isinstance(result, InstallResult)
    assert (library / ".install.lock").is_file()


@pytest.mark.skipif(not hasattr(os, "O_NOFOLLOW"), reason="O_NOFOLLOW required")
def test_symlinked_lock_path_refused_on_posix(tmp_path: Path) -> None:
    """Exercise symlinked lock path refused on posix."""
    library = tmp_path / "library"
    library.mkdir()
    real_lock = tmp_path / "real.lock"
    real_lock.write_bytes(b"x")
    (library / ".install.lock").symlink_to(real_lock)
    lock = LibraryInstallLock(library)
    with pytest.raises(OSError):
        lock.__enter__()


def test_concurrent_installs_serialized(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Exercise concurrent installs serialized."""
    import guiskindose.phantom_pack_install as install_mod

    shipped = tmp_path / "shipped"
    library = tmp_path / "library"
    body = tiny_stl_body()
    errors: list[BaseException] = []
    first_inside = threading.Event()
    release = threading.Event()
    original = install_mod._publish_all

    def _blocking_publish(*args, **kwargs):
        """Blocking publish."""
        first_inside.set()
        assert release.wait(timeout=10)
        return original(*args, **kwargs)

    monkeypatch.setattr(install_mod, "_publish_all", _blocking_publish)

    def _run(stem: str, done: threading.Event) -> None:
        """Run."""
        manifest = manifest_for_files({stem: body})
        raw = pack_zip_bytes(manifest, {stem: body})
        try:
            install_phantom_pack(
                __import__("io").BytesIO(raw),
                user_library_dir=library,
                shipped_dir=shipped,
                expected_manifest_sha256=_pin_for(manifest),
                app_version="1.1.1",
            )
        except BaseException as exc:
            errors.append(exc)
        finally:
            done.set()

    done1 = threading.Event()
    done2 = threading.Event()
    first = threading.Thread(target=_run, args=("junior_male", done1))
    second = threading.Thread(target=_run, args=("senior_male", done2))
    first.start()
    assert first_inside.wait(timeout=10)
    assert not done2.wait(timeout=0.2)
    release.set()
    first.join(timeout=30)
    second.start()
    second.join(timeout=30)
    assert not errors
    assert not first.is_alive()
    assert not second.is_alive()
    assert (library / "junior_male.stl").exists()
    assert (library / "senior_male.stl").exists()


@pytest.mark.skipif(os.name == "nt", reason="uses POSIX flock to hold the lock externally")
def test_external_lock_reports_busy(tmp_path: Path) -> None:
    """Exercise external lock reports busy."""
    import fcntl

    shipped = tmp_path / "shipped"
    library = tmp_path / "library"
    library.mkdir()
    lock_path = library / ".install.lock"
    fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
    fcntl.flock(fd, fcntl.LOCK_EX)
    try:
        body = tiny_stl_body()
        manifest = manifest_for_files({"senior_male": body})
        raw = pack_zip_bytes(manifest, {"senior_male": body})
        stream = __import__("io").BytesIO(raw)
        pin = _pin_for(manifest)
        with pytest.raises(PhantomPackError, match=_LIBRARY_BUSY):
            install_phantom_pack(
                stream,
                user_library_dir=library,
                shipped_dir=shipped,
                expected_manifest_sha256=pin,
                app_version="1.1.1",
            )
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
