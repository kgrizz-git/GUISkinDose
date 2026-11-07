"""Safe phantom-pack zip install into the per-user library."""

from __future__ import annotations

import logging
import os
import secrets
import stat
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from guiskindose.phantom_library import shipped_mesh_stl_path, user_library_dir_for_platform
from guiskindose.phantom_pack import (
    PhantomPackError,
    parse_pack_manifest,
    validate_manifest_for_install,
    verify_manifest_pin,
    verify_member_bytes,
)
from guiskindose.privacy import safe_error_event

_LOG = logging.getLogger(__name__)

_MAX_MEMBERS = 128
_MAX_COMPRESSED_BYTES = 80 * 1024 * 1024
_MAX_MEMBER_BYTES = 8 * 1024 * 1024
_MAX_DECOMPRESSED_TOTAL = 80 * 1024 * 1024
_MAX_COMPRESSION_RATIO = 100
_READ_CHUNK = 64 * 1024

_BAD_ARCHIVE = "This phantom pack archive is not valid."
_BAD_ARCHIVE_MEMBER = "This phantom pack archive is not valid."
_INSTALL_FAILED = "Phantom pack install failed."
_LIBRARY_SYMLINK = "The phantom library path cannot be a symbolic link."
_LIBRARY_MODE_FAILED = "Phantom pack install failed."

_OPERATION_INSTALL = "phantom_pack_install"


@dataclass(frozen=True, slots=True)
class InstallResult:
    """Outcome counts only (no paths)."""

    installed: int
    skipped_shipped: int


def _reject_archive(exc: BaseException | None = None) -> None:
    if exc is not None:
        safe_error_event(_LOG, _OPERATION_INSTALL, exc)
    raise PhantomPackError(_BAD_ARCHIVE)


def _reject_member(exc: BaseException | None = None) -> None:
    if exc is not None:
        safe_error_event(_LOG, _OPERATION_INSTALL, exc)
    raise PhantomPackError(_BAD_ARCHIVE_MEMBER)


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
    if info.is_dir():
        _reject_member()
    # S_IFLNK shares a bit with S_IFREG, so test the file type, not a bit mask.
    if stat.S_ISLNK(info.external_attr >> 16):
        _reject_member()
    if info.flag_bits & 0x1:
        _reject_member()


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
    buffer = bytearray()
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
    data = bytes(buffer)
    if len(data) > _MAX_MEMBER_BYTES:
        _reject_member()
    return data, running_total + len(data)


def _scan_zip_members(zf: zipfile.ZipFile) -> tuple[bytes, dict[str, bytes]]:
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
    """Create library root when missing; refuse symlinks. Returns (root, created_new)."""
    if user_library_dir.is_symlink():
        raise PhantomPackError(_LIBRARY_SYMLINK)
    created = False
    if not user_library_dir.exists():
        user_library_dir.mkdir(parents=True, exist_ok=True)
        _chmod_best_effort(user_library_dir, 0o700)
        created = True
    elif not user_library_dir.is_dir():
        raise PhantomPackError(_INSTALL_FAILED)
    elif user_library_dir.is_symlink():
        raise PhantomPackError(_LIBRARY_SYMLINK)
    return user_library_dir, created


def _stage_path(library_root: Path) -> Path:
    token = secrets.token_hex(8)
    return library_root / f".incoming-{token}"


def _publish_staged_file(
    stage_file: Path,
    destination: Path,
    *,
    backups: dict[Path, Path | None],
) -> None:
    backup: Path | None = None
    if destination.exists():
        backup = destination.with_name(f"{destination.name}.backup-{secrets.token_hex(4)}")
        destination.replace(backup)
    try:
        stage_file.replace(destination)
    except OSError:
        if backup is not None and backup.exists():
            if destination.exists():
                destination.unlink(missing_ok=True)
            backup.replace(destination)
        raise
    _chmod_best_effort(destination, 0o600)
    backups[destination] = backup


def _rollback(
    *,
    library_root: Path,
    created_root: bool,
    backups: dict[Path, Path | None],
    added: list[Path],
    stage_dir: Path | None,
) -> None:
    for dest, backup in backups.items():
        if backup is not None and backup.exists():
            if dest.exists():
                dest.unlink(missing_ok=True)
            backup.replace(dest)
        elif backup is None and dest in added and dest.exists():
            dest.unlink(missing_ok=True)
    if stage_dir is not None and stage_dir.exists():
        for child in stage_dir.iterdir():
            child.unlink(missing_ok=True)
        stage_dir.rmdir()
    if created_root and library_root.exists() and not any(library_root.iterdir()):
        library_root.rmdir()


def _check_compressed_limit(zf: zipfile.ZipFile) -> None:
    if zf.fp is None or not hasattr(zf.fp, "seek") or not hasattr(zf.fp, "tell"):
        return
    try:
        zf.fp.seek(0, os.SEEK_END)
        compressed_size = zf.fp.tell()
        zf.fp.seek(0)
        if compressed_size > _MAX_COMPRESSED_BYTES:
            _reject_archive()
    except OSError:
        return


def _plan_install(
    zf: zipfile.ZipFile,
    *,
    shipped_dir: Path,
    expected_manifest_sha256: str,
    app_version: str,
) -> tuple[list[tuple[str, bytes]], int]:
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


def _commit_install(
    to_install: list[tuple[str, bytes]],
    *,
    user_library_dir: Path,
    skipped: int,
) -> InstallResult:
    if not to_install:
        return InstallResult(installed=0, skipped_shipped=skipped)
    library_root, created_root = _prepare_library_root(user_library_dir)
    stage_dir = _stage_path(library_root)
    stage_dir.mkdir()
    backups: dict[Path, Path | None] = {}
    added: list[Path] = []
    try:
        for stem, body in to_install:
            staged = stage_dir / f"{stem}.stl"
            staged.write_bytes(body)
            destination = library_root / f"{stem}.stl"
            was_new = not destination.exists()
            _publish_staged_file(staged, destination, backups=backups)
            if was_new:
                added.append(destination)
        for child in stage_dir.iterdir():
            child.unlink(missing_ok=True)
        stage_dir.rmdir()
        for backup in backups.values():
            if backup is not None and backup.exists():
                backup.unlink()
    except (OSError, PermissionError) as exc:
        safe_error_event(_LOG, _OPERATION_INSTALL, exc)
        _rollback(
            library_root=library_root,
            created_root=created_root,
            backups=backups,
            added=added,
            stage_dir=stage_dir if stage_dir.exists() else None,
        )
        raise PhantomPackError(_INSTALL_FAILED) from None
    return InstallResult(installed=len(to_install), skipped_shipped=skipped)


def install_phantom_pack(
    source: BinaryIO,
    *,
    user_library_dir: Path,
    shipped_dir: Path,
    expected_manifest_sha256: str,
    app_version: str,
) -> InstallResult:
    """Install allow-listed STL members from an open pack zip stream."""
    try:
        zf = zipfile.ZipFile(source)
    except zipfile.BadZipFile as exc:
        safe_error_event(_LOG, _OPERATION_INSTALL, exc)
        raise PhantomPackError(_BAD_ARCHIVE) from None
    try:
        with zf:
            _check_compressed_limit(zf)
            to_install, skipped = _plan_install(
                zf,
                shipped_dir=shipped_dir,
                expected_manifest_sha256=expected_manifest_sha256,
                app_version=app_version,
            )
            return _commit_install(to_install, user_library_dir=user_library_dir, skipped=skipped)
    except KeyError as exc:
        safe_error_event(_LOG, _OPERATION_INSTALL, exc)
        raise PhantomPackError(_BAD_ARCHIVE) from None


def default_install_library_dir() -> Path:
    """Resolve the platform user-library directory for installs (raises when undefined)."""
    platform = "win32" if sys.platform == "win32" else sys.platform
    return user_library_dir_for_platform(platform)
