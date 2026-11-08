"""Safe phantom-pack zip install into the per-user library."""

from __future__ import annotations

import logging
import os
import secrets
import shutil
import stat
import sys
import zipfile
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import IO

from guiskindose.phantom_library import (
    _path_is_library_link,
    shipped_mesh_stl_path,
    user_library_dir_for_platform,
)
from guiskindose.phantom_pack import (
    PhantomPackError,
    parse_pack_manifest,
    validate_manifest_for_install,
    verify_manifest_pin,
    verify_member_bytes,
)
from guiskindose.phantom_pack_lock import (
    LibraryInstallLock,
    LibraryInstallLockBusy,
    install_process_lock,
)
from guiskindose.privacy import safe_error_event

_LOG = logging.getLogger(__name__)

_MAX_MEMBERS = 128
_MAX_COMPRESSED_BYTES = 80 * 1024 * 1024
_MAX_MEMBER_BYTES = 8 * 1024 * 1024
_MAX_DECOMPRESSED_TOTAL = 80 * 1024 * 1024
_MAX_COMPRESSION_RATIO = 100
_READ_CHUNK = 64 * 1024
_EOCD_SEARCH_MAX = 65557
_MAX_CENTRAL_DIRECTORY_BYTES = 1024 * 1024
_BAD_ARCHIVE = "This phantom pack archive is not valid."
_BAD_ARCHIVE_MEMBER = "This phantom pack archive is not valid."
_INSTALL_FAILED = "Phantom pack install failed."
_LIBRARY_SYMLINK = "The phantom library path cannot be a symbolic link."
_LIBRARY_BUSY = "Another phantom pack install is already in progress."

_OPERATION_INSTALL = "phantom_pack_install"


@dataclass(frozen=True, slots=True)
class InstallResult:
    """Outcome counts only (no paths)."""

    installed: int
    skipped_shipped: int
    installed_stems: tuple[str, ...] = ()


def _reject_archive(exc: BaseException | None = None) -> None:
    if exc is not None:
        safe_error_event(_LOG, _OPERATION_INSTALL, exc)
    raise PhantomPackError(_BAD_ARCHIVE)


def _reject_member(exc: BaseException | None = None) -> None:
    if exc is not None:
        safe_error_event(_LOG, _OPERATION_INSTALL, exc)
    raise PhantomPackError(_BAD_ARCHIVE_MEMBER)


def _reject_install(exc: BaseException | None = None) -> None:
    if exc is not None:
        safe_error_event(_LOG, _OPERATION_INSTALL, exc)
    raise PhantomPackError(_INSTALL_FAILED)


def classify_member_name(name: str) -> str:
    """Return ``manifest``, a validated stem, or raise."""
    if not name or name.startswith("/") or "\\" in name:
        _reject_member()
    parts = name.split("/")
    if len(parts) != 1:
        _reject_member()
    if parts[0] in (".", ".."):
        _reject_member()
    if ":" in parts[0]:
        _reject_member()
    base = parts[0]
    if base == "manifest.json":
        return "manifest"
    if not base.endswith(".stl"):
        _reject_member()
    from guiskindose.phantom_pack import is_allowed_pack_stem

    stem = base[: -len(".stl")]
    if not is_allowed_pack_stem(stem):
        _reject_member()
    return stem


def _validate_zip_info(info: zipfile.ZipInfo) -> None:
    """Reject directories, links, encrypted members, and compression other than stored or deflated."""
    if info.is_dir():
        _reject_member()
    if info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
        _reject_member()
    if stat.S_ISLNK(info.external_attr >> 16):
        _reject_member()
    if info.flag_bits & 0x1:
        _reject_member()


def _read_zip_body(zf: zipfile.ZipFile, info: zipfile.ZipInfo, *, running_total: int) -> bytes:
    """Read one member in chunks, enforcing the per-member and running totals on the bytes actually decompressed, not the header sizes."""
    buffer = bytearray()
    try:
        with zf.open(info, "r") as handle:
            while True:
                chunk = handle.read(_READ_CHUNK)
                if not chunk:
                    break
                buffer.extend(chunk)
                if len(buffer) > _MAX_MEMBER_BYTES:
                    _reject_member()
                if running_total + len(buffer) > _MAX_DECOMPRESSED_TOTAL:
                    _reject_member()
    except OSError as exc:
        _reject_install(exc)
    except (zipfile.BadZipFile, zlib.error, RuntimeError) as exc:
        _reject_member(exc)
    return bytes(buffer)


def read_member_with_cap(
    zf: zipfile.ZipFile,
    info: zipfile.ZipInfo,
    *,
    running_total: int,
) -> tuple[bytes, int]:
    """Read one member in chunks; return body and new running decompressed total."""
    _validate_zip_info(info)
    if info.file_size > _MAX_MEMBER_BYTES:
        _reject_member()
    if running_total + info.file_size > _MAX_DECOMPRESSED_TOTAL:
        _reject_member()
    if info.compress_size > 0 and info.file_size / info.compress_size > _MAX_COMPRESSION_RATIO:
        _reject_member()
    data = _read_zip_body(zf, info, running_total=running_total)
    if len(data) > _MAX_MEMBER_BYTES:
        _reject_member()
    return data, running_total + len(data)


def _scan_zip_members(zf: zipfile.ZipFile) -> tuple[bytes, dict[str, bytes]]:
    """Read the manifest and every STL body under the member, case, and size limits; return the raw manifest and bodies by stem."""
    names = zf.namelist()
    if len(names) > _MAX_MEMBERS:
        _reject_archive()
    lowered: dict[str, str] = {}
    for name in names:
        key = name.casefold()
        if key in lowered and lowered[key] != name:
            _reject_archive()
        lowered[key] = name
    manifest_bytes: bytes | None = None
    stl_bodies: dict[str, bytes] = {}
    running = 0
    seen_manifest = False
    for info in zf.infolist():
        kind = classify_member_name(info.filename)
        if kind == "manifest":
            if seen_manifest:
                _reject_archive()
            seen_manifest = True
            body, running = read_member_with_cap(zf, info, running_total=running)
            manifest_bytes = body
            continue
        body, running = read_member_with_cap(zf, info, running_total=running)
        if kind in stl_bodies:
            _reject_archive()
        stl_bodies[kind] = body
    if manifest_bytes is None:
        _reject_archive()
        raise AssertionError("unreachable")
    return manifest_bytes, stl_bodies


def _chmod_best_effort(path: Path, mode: int) -> None:
    try:
        os.chmod(path, mode)
    except OSError:
        return


def _prepare_library_root(user_library_dir: Path) -> tuple[Path, bool]:
    """Create library root when missing; refuse symlinks/junctions. Returns (root, created_new)."""
    if _path_is_library_link(user_library_dir, sys.platform):
        raise PhantomPackError(_LIBRARY_SYMLINK)
    created = False
    if not user_library_dir.exists():
        user_library_dir.mkdir(parents=True, exist_ok=True)
        _chmod_best_effort(user_library_dir, 0o700)
        created = True
    elif not user_library_dir.is_dir():
        raise PhantomPackError(_INSTALL_FAILED)
    return user_library_dir, created


def _unlink_link(path: Path) -> None:
    """Remove a symlink or junction itself, never its target."""
    try:
        path.unlink(missing_ok=True)
    except (IsADirectoryError, PermissionError):
        # A directory junction on Windows is removed with rmdir.
        path.rmdir()


def _safe_remove_path(path: Path) -> None:
    """Remove a file or empty tree without following symlinks."""
    try:
        if path.is_symlink() or _path_is_library_link(path, sys.platform):
            # A Windows junction is not a symlink to pathlib, so check reparse points too.
            _unlink_link(path)
            return
        if path.is_file():
            path.unlink(missing_ok=True)
            return
        if not path.is_dir():
            return
        for child in sorted(path.iterdir(), key=lambda p: p.name):
            _safe_remove_path(child)
        path.rmdir()
    except OSError as exc:
        safe_error_event(_LOG, _OPERATION_INSTALL, exc)


def _sweep_incoming_dirs(library_root: Path, *, keep_stage: Path | None) -> None:
    for incoming in library_root.glob(".incoming-*"):
        if keep_stage is not None and incoming == keep_stage:
            continue
        _safe_remove_path(incoming)


def _reconcile_orphan_backups(library_root: Path) -> None:
    """Restore backups whose mesh file is missing; delete stale backups otherwise."""
    for backup in library_root.glob("*.stl.backup-*"):
        if backup.is_symlink():
            backup.unlink(missing_ok=True)
            continue
        destination = library_root / backup.name.split(".backup-", 1)[0]
        if destination.exists() or destination.is_symlink():
            try:
                backup.unlink(missing_ok=True)
            except OSError as exc:
                safe_error_event(_LOG, _OPERATION_INSTALL, exc)
            continue
        try:
            backup.replace(destination)
        except OSError as exc:
            safe_error_event(_LOG, _OPERATION_INSTALL, exc)


def _sweep_library_artifacts(library_root: Path, *, keep_stage: Path | None = None) -> None:
    """Clear leftover install temps and reconcile orphan backups before a new install."""
    _sweep_incoming_dirs(library_root, keep_stage=keep_stage)
    _reconcile_orphan_backups(library_root)


def _stage_path(library_root: Path) -> Path:
    token = secrets.token_hex(8)
    return library_root / f".incoming-{token}"


def _create_publish_backup(destination: Path) -> Path:
    """Hard-link (or copy) an existing mesh file aside without removing the live path."""
    backup = destination.with_name(f"{destination.name}.backup-{secrets.token_hex(4)}")
    try:
        os.link(destination, backup)
    except OSError:
        shutil.copy2(destination, backup)
    return backup


def _publish_staged_file(
    stage_file: Path,
    destination: Path,
    *,
    backups: dict[Path, Path | None],
) -> None:
    """Move a staged STL over *destination* atomically, keeping a backup of any existing file in *backups* for rollback."""
    backup: Path | None = None
    if destination.exists():
        backup = _create_publish_backup(destination)
    try:
        stage_file.replace(destination)
    except OSError:
        # The original mesh is still in place, so only this install's backup goes.
        if backup is not None:
            backup.unlink(missing_ok=True)
        raise
    _chmod_best_effort(destination, 0o600)
    backups[destination] = backup


def _restore_backup(dest: Path, backup: Path | None, added: list[Path]) -> None:
    """Undo one publish: restore the backup over *dest*, or remove *dest* if this install created it."""
    try:
        if backup is not None and backup.exists():
            # replace() overwrites in one step, so the mesh is never missing.
            backup.replace(dest)
        elif backup is None and dest in added and dest.exists():
            dest.unlink(missing_ok=True)
    except OSError as exc:
        safe_error_event(_LOG, _OPERATION_INSTALL, exc)


def _remove_stage_dir(stage_dir: Path) -> None:
    _safe_remove_path(stage_dir)


def _delete_publish_backups(backups: dict[Path, Path | None]) -> None:
    for backup in backups.values():
        if backup is None or backup.is_symlink():
            continue
        try:
            backup.unlink(missing_ok=True)
        except OSError as exc:
            safe_error_event(_LOG, _OPERATION_INSTALL, exc)


def _rollback(
    *,
    backups: dict[Path, Path | None],
    added: list[Path],
    stage_dir: Path | None,
) -> None:
    """Undo every publish this install made and remove its stage directory. The library root and lock file stay."""
    for dest, backup in backups.items():
        _restore_backup(dest, backup, added)
    if stage_dir is not None and stage_dir.exists():
        _remove_stage_dir(stage_dir)


def _validate_zip_archive_stream(source: IO[bytes]) -> None:
    """Bound zip size and central-directory metadata before ``ZipFile`` is constructed."""
    if not hasattr(source, "seek") or not hasattr(source, "tell") or not hasattr(source, "read"):
        return
    compressed_size = 0
    try:
        source.seek(0, os.SEEK_END)
        compressed_size = source.tell()
        source.seek(0)
    except OSError as exc:
        _reject_install(exc)
    if compressed_size > _MAX_COMPRESSED_BYTES:
        _reject_archive()
    tail_start = max(0, compressed_size - _EOCD_SEARCH_MAX)
    tail = b""
    try:
        source.seek(tail_start)
        tail = source.read()
        source.seek(0)
    except OSError as exc:
        _reject_install(exc)
    eocd_idx = _find_eocd(tail)
    if eocd_idx is None:
        _reject_archive()
        return
    eocd = tail[eocd_idx : eocd_idx + 22]
    total_entries = int.from_bytes(eocd[10:12], "little")
    cd_size = int.from_bytes(eocd[12:16], "little")
    cd_offset = int.from_bytes(eocd[16:20], "little")
    # 0xFFFF / 0xFFFFFFFF mean the real values live in a ZIP64 record, which packs never need.
    if total_entries == 0xFFFF or cd_size == 0xFFFFFFFF or cd_offset == 0xFFFFFFFF:
        _reject_archive()
    if total_entries > _MAX_MEMBERS or cd_size > _MAX_CENTRAL_DIRECTORY_BYTES:
        _reject_archive()
    # The central directory must sit before the EOCD, so the counts cannot understate it.
    if cd_offset + cd_size != tail_start + eocd_idx:
        _reject_archive()


def _find_eocd(tail: bytes) -> int | None:
    """Return the offset of the real end-of-central-directory record in *tail*.

    The record is 22 bytes plus its comment, and it ends the file. A signature
    that only appears inside the comment or a member's data does not line up
    with the end, so it is skipped.
    """
    pos = tail.rfind(b"PK\x05\x06")
    while pos >= 0:
        if pos + 22 <= len(tail):
            comment_len = int.from_bytes(tail[pos + 20 : pos + 22], "little")
            if pos + 22 + comment_len == len(tail):
                return pos
        pos = tail.rfind(b"PK\x05\x06", 0, pos)
    return None

def _plan_install(
    zf: zipfile.ZipFile,
    *,
    shipped_dir: Path,
    expected_manifest_sha256: str,
    app_version: str,
) -> tuple[list[tuple[str, bytes]], int]:
    """Verify the pin, manifest, and every member's size and hash; return the meshes to install and the count skipped because they ship."""
    manifest_raw, stl_bodies = _scan_zip_members(zf)
    manifest = parse_pack_manifest(manifest_raw)
    verify_manifest_pin(manifest, expected_manifest_sha256)
    entries = validate_manifest_for_install(manifest, app_version=app_version)
    manifest_stems = {entry["stem"] for entry in entries}
    if any(entry["stem"] not in stl_bodies for entry in entries):
        _reject_archive()
    if any(stem not in manifest_stems for stem in stl_bodies):
        _reject_archive()
    to_install: list[tuple[str, bytes]] = []
    skipped = 0
    for entry in entries:
        stem = entry["stem"]
        body = stl_bodies[stem]
        verify_member_bytes(body, expected_bytes=entry["bytes"], expected_sha256=entry["sha256"])
        if shipped_mesh_stl_path(stem, shipped_dir=shipped_dir) is not None:
            skipped += 1
            continue
        to_install.append((stem, body))
    return to_install, skipped


def _publish_all(
    to_install: list[tuple[str, bytes]],
    *,
    library_root: Path,
    stage_dir: Path,
    backups: dict[Path, Path | None],
    added: list[Path],
) -> None:
    """Stage and publish each mesh, recording backups and new files for rollback."""
    stage_dir.mkdir()
    for stem, body in to_install:
        staged = stage_dir / f"{stem}.stl"
        staged.write_bytes(body)
        destination = library_root / f"{stem}.stl"
        was_new = not destination.exists()
        _publish_staged_file(staged, destination, backups=backups)
        if was_new:
            added.append(destination)
    for child in sorted(stage_dir.iterdir(), key=lambda p: p.name):
        child.unlink(missing_ok=True)
    stage_dir.rmdir()


def _commit_install(
    to_install: list[tuple[str, bytes]],
    *,
    user_library_dir: Path,
    skipped: int,
) -> InstallResult:
    """Publish the planned meshes under the process lock and the library file lock, rolling back on any filesystem error."""
    if not to_install:
        return InstallResult(installed=0, skipped_shipped=skipped)
    stems = tuple(stem for stem, _ in to_install)
    library_root: Path | None = None
    stage_dir: Path | None = None
    backups: dict[Path, Path | None] = {}
    added: list[Path] = []
    failed = False
    with install_process_lock():
        try:
            library_root, _ = _prepare_library_root(user_library_dir)
        except PhantomPackError:
            raise
        except OSError as exc:
            safe_error_event(_LOG, _OPERATION_INSTALL, exc)
            raise PhantomPackError(_INSTALL_FAILED) from None
        try:
            with LibraryInstallLock(library_root):
                try:
                    stage_dir = _stage_path(library_root)
                    _sweep_library_artifacts(library_root, keep_stage=stage_dir)
                    _publish_all(to_install, library_root=library_root, stage_dir=stage_dir, backups=backups, added=added)
                    stage_dir = None
                    _delete_publish_backups(backups)
                except OSError as exc:
                    safe_error_event(_LOG, _OPERATION_INSTALL, exc)
                    _rollback(
                        backups=backups,
                        added=added,
                        stage_dir=stage_dir if stage_dir is not None and stage_dir.exists() else None,
                    )
                    failed = True
            if failed:
                raise PhantomPackError(_INSTALL_FAILED)
        except LibraryInstallLockBusy as exc:
            safe_error_event(_LOG, _OPERATION_INSTALL, exc)
            raise PhantomPackError(_LIBRARY_BUSY) from None
        except OSError as exc:
            safe_error_event(_LOG, _OPERATION_INSTALL, exc)
            raise PhantomPackError(_INSTALL_FAILED) from None
    return InstallResult(installed=len(to_install), skipped_shipped=skipped, installed_stems=stems)


def install_phantom_pack(
    source: IO[bytes],
    *,
    user_library_dir: Path,
    shipped_dir: Path,
    expected_manifest_sha256: str,
    app_version: str,
) -> InstallResult:
    """Install allow-listed STL members from an open pack zip stream."""
    _validate_zip_archive_stream(source)
    try:
        zf = zipfile.ZipFile(source)
    except OSError as exc:
        safe_error_event(_LOG, _OPERATION_INSTALL, exc)
        raise PhantomPackError(_INSTALL_FAILED) from None
    except (zipfile.BadZipFile, zlib.error, RuntimeError) as exc:
        safe_error_event(_LOG, _OPERATION_INSTALL, exc)
        raise PhantomPackError(_BAD_ARCHIVE) from None
    try:
        with zf:
            to_install, skipped = _plan_install(
                zf,
                shipped_dir=shipped_dir,
                expected_manifest_sha256=expected_manifest_sha256,
                app_version=app_version,
            )
            return _commit_install(to_install, user_library_dir=user_library_dir, skipped=skipped)
    except PhantomPackError:
        raise
    except KeyError as exc:
        safe_error_event(_LOG, _OPERATION_INSTALL, exc)
        raise PhantomPackError(_BAD_ARCHIVE) from None
    except OSError as exc:
        safe_error_event(_LOG, _OPERATION_INSTALL, exc)
        raise PhantomPackError(_INSTALL_FAILED) from None
    except (zipfile.BadZipFile, zlib.error, RuntimeError) as exc:
        safe_error_event(_LOG, _OPERATION_INSTALL, exc)
        raise PhantomPackError(_BAD_ARCHIVE) from None


def default_install_library_dir() -> Path:
    """Resolve the platform user-library directory for installs (raises when undefined)."""
    platform = "win32" if sys.platform == "win32" else sys.platform
    return user_library_dir_for_platform(platform)
