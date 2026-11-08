"""Safe phantom pack zip install."""

from __future__ import annotations

import io
import logging
import os
import stat
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest

from guiskindose.phantom_pack import PhantomPackError, canonical_manifest_bytes
from guiskindose.phantom_pack_install import InstallResult, install_phantom_pack
from tests.unittests.phantom_pack_test_helpers import manifest_for_files, pack_zip_bytes, tiny_stl_body


def _pin_for(manifest: dict) -> str:
    from guiskindose.phantom_pack import manifest_sha256

    return manifest_sha256(manifest)


def _install(
    raw: bytes,
    *,
    shipped: Path,
    library: Path,
    manifest: dict,
    app_version: str = "1.1.1",
) -> InstallResult:
    shipped.mkdir(parents=True, exist_ok=True)
    return install_phantom_pack(
        io.BytesIO(raw),
        user_library_dir=library,
        shipped_dir=shipped,
        expected_manifest_sha256=_pin_for(manifest),
        app_version=app_version,
    )


def test_installs_into_user_library(tmp_path: Path) -> None:
    shipped = tmp_path / "shipped"
    library = tmp_path / "library"
    body = tiny_stl_body()
    files = {"senior_male": body}
    manifest = manifest_for_files(files)
    result = _install(pack_zip_bytes(manifest, files), shipped=shipped, library=library, manifest=manifest)
    assert result.installed == 1
    assert (library / "senior_male.stl").read_bytes() == body
    assert not any(shipped.glob("*.stl"))


def test_creates_library_with_mode(tmp_path: Path) -> None:
    shipped = tmp_path / "shipped"
    library = tmp_path / "library"
    body = tiny_stl_body()
    files = {"senior_male": body}
    manifest = manifest_for_files(files)
    _install(pack_zip_bytes(manifest, files), shipped=shipped, library=library, manifest=manifest)
    assert library.is_dir()
    if os.name == "posix" and hasattr(stat, "S_IRWXU"):
        assert library.stat().st_mode & 0o777 == 0o700


def test_second_install_replaces_without_stage_leftovers(tmp_path: Path) -> None:
    shipped = tmp_path / "shipped"
    library = tmp_path / "library"
    body = tiny_stl_body()
    files = {"senior_male": body}
    manifest = manifest_for_files(files)
    raw = pack_zip_bytes(manifest, files)
    _install(raw, shipped=shipped, library=library, manifest=manifest)
    body2 = body + b"#"
    files2 = {"senior_male": body2}
    manifest2 = manifest_for_files(files2)
    raw2 = pack_zip_bytes(manifest2, files2)
    _install(raw2, shipped=shipped, library=library, manifest=manifest2)
    assert (library / "senior_male.stl").read_bytes() == body2
    assert not any(p.name.startswith(".incoming-") for p in library.iterdir())
    assert not any(library.glob("*.backup-*"))


def test_tampered_bytes_leave_previous_file(tmp_path: Path) -> None:
    shipped = tmp_path / "shipped"
    library = tmp_path / "library"
    body = tiny_stl_body()
    files = {"senior_male": body}
    manifest = manifest_for_files(files)
    _install(pack_zip_bytes(manifest, files), shipped=shipped, library=library, manifest=manifest)
    bad_manifest = manifest_for_files({"senior_male": body})
    bad_manifest["files"][0]["sha256"] = "f" * 64
    bad_raw = pack_zip_bytes(bad_manifest, files)
    with pytest.raises(PhantomPackError):
        _install(bad_raw, shipped=shipped, library=library, manifest=bad_manifest)
    assert (library / "senior_male.stl").read_bytes() == body


@pytest.mark.parametrize(
    "builder",
    [
        "symlink",
        "absolute",
        "dotdot",
        "directory",
        "casefold",
        "alias_stem",
        "demo_stem",
        "overflow_count",
        "oversize_stream",
    ],
)
def test_rejects_bad_archives(tmp_path: Path, builder: str, monkeypatch: pytest.MonkeyPatch) -> None:
    shipped = tmp_path / "shipped"
    library = tmp_path / "library"
    body = tiny_stl_body()
    buf = io.BytesIO()
    if builder == "overflow_count":
        with zipfile.ZipFile(buf, "w") as zf:
            for index in range(129):
                zf.writestr(f"m{index}.txt", b"x")
        raw = buf.getvalue()
        manifest = manifest_for_files({"senior_male": body})
        with pytest.raises(PhantomPackError):
            _install(raw, shipped=shipped, library=library, manifest=manifest)
        return

    files = {"senior_male": body}
    manifest = manifest_for_files(files)
    if builder == "symlink":
        with zipfile.ZipFile(buf, "w") as zf:
            info = zipfile.ZipInfo("senior_male.stl")
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            zf.writestr(info, body)
            zf.writestr("manifest.json", canonical_manifest_bytes(manifest))
    elif builder == "absolute":
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("/senior_male.stl", body)
            zf.writestr("manifest.json", canonical_manifest_bytes(manifest))
    elif builder == "dotdot":
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("../senior_male.stl", body)
            zf.writestr("manifest.json", canonical_manifest_bytes(manifest))
    elif builder == "directory":
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("nested/", b"")
            zf.writestr("manifest.json", canonical_manifest_bytes(manifest))
    elif builder == "casefold":
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("Senior_Male.stl", body)
            zf.writestr("senior_male.stl", body)
            zf.writestr("manifest.json", canonical_manifest_bytes(manifest))
    elif builder == "alias_stem":
        manifest = manifest_for_files({"pediatric_5y_male": body})
        files = {"pediatric_5y_male": body}
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("pediatric_5y_male.stl", body)
            zf.writestr("manifest.json", canonical_manifest_bytes(manifest))
    elif builder == "demo_stem":
        manifest = manifest_for_files({"demo_cosmic_buddha": body})
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("demo_cosmic_buddha.stl", body)
            zf.writestr("manifest.json", canonical_manifest_bytes(manifest))
    elif builder == "oversize_stream":
        from guiskindose.phantom_pack_install import _MAX_MEMBER_BYTES

        big = b"x" * (_MAX_MEMBER_BYTES + 128)
        manifest = manifest_for_files({"senior_male": big})
        raw = pack_zip_bytes(manifest, {"senior_male": big}, compression=zipfile.ZIP_STORED)
        original_infolist = zipfile.ZipFile.infolist

        def _lying_infolist(self: zipfile.ZipFile) -> list[zipfile.ZipInfo]:
            items = original_infolist(self)
            for info in items:
                if info.filename.endswith(".stl"):
                    info.file_size = 64
            return items

        monkeypatch.setattr(zipfile.ZipFile, "infolist", _lying_infolist)
        with pytest.raises(PhantomPackError):
            _install(raw, shipped=shipped, library=library, manifest=manifest)
        return
    raw = buf.getvalue()
    with pytest.raises(PhantomPackError):
        _install(raw, shipped=shipped, library=library, manifest=manifest)
    assert not (library / "senior_male.stl").exists()


def test_skip_shipped_install_other(tmp_path: Path) -> None:
    shipped = tmp_path / "shipped"
    library = tmp_path / "library"
    body = tiny_stl_body()
    shipped.mkdir(parents=True, exist_ok=True)
    (shipped / "adult_male.stl").write_bytes(b"keep")
    files = {"adult_male": body, "senior_male": body + b"2"}
    manifest = manifest_for_files(files)
    result = _install(pack_zip_bytes(manifest, files), shipped=shipped, library=library, manifest=manifest)
    assert result.skipped_shipped == 1
    assert result.installed == 1
    assert (shipped / "adult_male.stl").read_bytes() == b"keep"
    assert (library / "senior_male.stl").exists()
    assert not (library / "adult_male.stl").exists()


def test_all_shipped_skipped_no_library_copy(tmp_path: Path) -> None:
    shipped = tmp_path / "shipped"
    library = tmp_path / "library"
    body = tiny_stl_body()
    shipped.mkdir(parents=True, exist_ok=True)
    (shipped / "senior_male.stl").write_bytes(body)
    files = {"senior_male": body}
    manifest = manifest_for_files(files)
    result = _install(pack_zip_bytes(manifest, files), shipped=shipped, library=library, manifest=manifest)
    assert result.skipped_shipped == 1
    assert result.installed == 0
    assert not (library / "senior_male.stl").exists()


def test_rollback_removes_stem_added_this_install(tmp_path: Path) -> None:
    shipped = tmp_path / "shipped"
    library = tmp_path / "library"
    library.mkdir()
    body = tiny_stl_body()
    files = {"junior_male": body, "senior_male": body + b"2"}
    manifest = manifest_for_files(files)
    calls = {"count": 0}
    original_replace = Path.replace

    def flaky_replace(self: Path, target: Path) -> None:
        calls["count"] += 1
        if calls["count"] == 2:
            raise PermissionError("blocked")
        original_replace(self, target)

    raw = pack_zip_bytes(manifest, files)
    with patch.object(Path, "replace", flaky_replace), pytest.raises(PhantomPackError):
        _install(raw, shipped=shipped, library=library, manifest=manifest)
    assert not (library / "junior_male.stl").exists()
    assert not (library / "senior_male.stl").exists()


def test_mid_replace_rollback(tmp_path: Path) -> None:
    shipped = tmp_path / "shipped"
    library = tmp_path / "library"
    body = tiny_stl_body()
    library.mkdir()
    (library / "junior_male.stl").write_bytes(b"original-junior")
    files = {"junior_male": body, "senior_male": body + b"new"}
    manifest = manifest_for_files(files)
    calls = {"count": 0}
    original_replace = Path.replace

    def flaky_replace(self: Path, target: Path) -> None:
        calls["count"] += 1
        if calls["count"] == 2:
            raise PermissionError("blocked")
        original_replace(self, target)

    raw = pack_zip_bytes(manifest, files)
    with patch.object(Path, "replace", flaky_replace), pytest.raises(PhantomPackError):
        _install(raw, shipped=shipped, library=library, manifest=manifest)
    assert (library / "junior_male.stl").read_bytes() == b"original-junior"
    assert not (library / "senior_male.stl").exists()
    assert not any(p.name.startswith(".incoming-") for p in library.iterdir())
    assert not any(library.glob("*.backup-*"))


def test_failure_logs_contain_no_paths(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    shipped = tmp_path / "shipped"
    library = tmp_path / "library"
    tag = tmp_path.name
    empty_manifest = manifest_for_files({})
    with caplog.at_level(logging.DEBUG), pytest.raises(PhantomPackError) as info:
        _install(b"not-a-zip", shipped=shipped, library=library, manifest=empty_manifest)
    assert tag not in caplog.text
    assert tag not in str(info.value)


def test_rejects_bad_crc_stored_member(tmp_path: Path) -> None:
    shipped = tmp_path / "shipped"
    library = tmp_path / "library"
    body = tiny_stl_body()
    manifest = manifest_for_files({"senior_male": body})
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_STORED) as zf:
        zf.writestr("senior_male.stl", body)
        zf.writestr("manifest.json", canonical_manifest_bytes(manifest))
    corrupted = bytearray(buf.getvalue())
    marker = corrupted.find(b"solid")
    assert marker >= 0
    corrupted[marker] ^= 0xFF
    bad_raw = bytes(corrupted)
    with pytest.raises(PhantomPackError):
        _install(bad_raw, shipped=shipped, library=library, manifest=manifest)


def test_rejects_unsupported_compression(tmp_path: Path) -> None:
    shipped = tmp_path / "shipped"
    library = tmp_path / "library"
    body = tiny_stl_body()
    manifest = manifest_for_files({"senior_male": body})
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        info = zipfile.ZipInfo("senior_male.stl")
        info.compress_type = zipfile.ZIP_BZIP2
        zf.writestr(info, body)
        zf.writestr("manifest.json", canonical_manifest_bytes(manifest))
    raw = buf.getvalue()
    with pytest.raises(PhantomPackError):
        _install(raw, shipped=shipped, library=library, manifest=manifest)


def test_failure_before_first_replace_leaves_library_root_with_lock(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    shipped = tmp_path / "shipped"
    library = tmp_path / "library"
    body = tiny_stl_body()
    files = {"senior_male": body}
    manifest = manifest_for_files(files)
    original_mkdir = Path.mkdir

    def fail_mkdir(self: Path, *args, **kwargs):
        if self.name.startswith(".incoming-"):
            raise OSError("no stage")
        return original_mkdir(self, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", fail_mkdir)
    assert not library.exists()
    raw = pack_zip_bytes(manifest, files)
    with pytest.raises(PhantomPackError):
        _install(raw, shipped=shipped, library=library, manifest=manifest)
    assert library.is_dir()
    assert [p.name for p in library.iterdir()] == [".install.lock"]


def test_accepts_members_with_regular_unix_mode(tmp_path: Path) -> None:
    """Zips written by ``ZipFile.write`` carry S_IFREG, which must not read as a symlink."""
    shipped = tmp_path / "shipped"
    shipped.mkdir()
    library = tmp_path / "lib"
    body = b"solid regular\nendsolid regular\n"
    manifest = manifest_for_files({"senior_male": body})
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        info = zipfile.ZipInfo("senior_male.stl")
        info.external_attr = (stat.S_IFREG | 0o644) << 16
        zf.writestr(info, body)
        zf.writestr("manifest.json", canonical_manifest_bytes(manifest))
    result = _install(buf.getvalue(), shipped=shipped, library=library, manifest=manifest)
    assert result.installed == 1
    assert (library / "senior_male.stl").read_bytes() == body


def test_orphan_backup_restored_when_destination_missing(tmp_path: Path) -> None:
    shipped = tmp_path / "shipped"
    library = tmp_path / "library"
    library.mkdir()
    restored_body = tiny_stl_body() + b"#orphan"
    (library / "missing_mesh.stl.backup-deadbeef").write_bytes(restored_body)
    body = tiny_stl_body()
    manifest = manifest_for_files({"senior_male": body})
    _install(pack_zip_bytes(manifest, {"senior_male": body}), shipped=shipped, library=library, manifest=manifest)
    assert (library / "missing_mesh.stl").read_bytes() == restored_body
    assert (library / "senior_male.stl").exists()


def test_sweep_unlinks_stale_incoming_symlink_without_touching_target(tmp_path: Path) -> None:
    from guiskindose.phantom_pack_install import _sweep_library_artifacts

    victim = tmp_path / "outside"
    victim.mkdir()
    keep = victim / "keep.txt"
    keep.write_bytes(b"stay")
    library = tmp_path / "library"
    library.mkdir()
    link = library / ".incoming-trap"
    link.symlink_to(victim)
    _sweep_library_artifacts(library)
    assert not link.exists()
    assert keep.read_bytes() == b"stay"


def test_stale_incoming_with_subdir_does_not_block_later_install(tmp_path: Path) -> None:
    from guiskindose.phantom_pack_install import _sweep_library_artifacts

    library = tmp_path / "library"
    stale = library / ".incoming-old"
    nested = stale / "nested"
    nested.mkdir(parents=True)
    _sweep_library_artifacts(library)
    shipped = tmp_path / "shipped"
    body = tiny_stl_body()
    manifest = manifest_for_files({"senior_male": body})
    result = _install(pack_zip_bytes(manifest, {"senior_male": body}), shipped=shipped, library=library, manifest=manifest)
    assert result.installed == 1


def test_source_stream_oserror_is_install_failed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from guiskindose.phantom_pack_install import _INSTALL_FAILED, install_phantom_pack

    def _broken_read(*_args, **_kwargs):
        raise OSError("broken stream")

    monkeypatch.setattr("guiskindose.phantom_pack_install._read_zip_body", _broken_read)

    shipped = tmp_path / "shipped"
    library = tmp_path / "library"
    body = tiny_stl_body()
    manifest = manifest_for_files({"senior_male": body})
    stream = io.BytesIO(pack_zip_bytes(manifest, {"senior_male": body}))
    pin = _pin_for(manifest)
    with pytest.raises(PhantomPackError, match=_INSTALL_FAILED):
        install_phantom_pack(
            stream,
            user_library_dir=library,
            shipped_dir=shipped,
            expected_manifest_sha256=pin,
            app_version="1.1.1",
        )


def test_non_directory_library_parent_install_failed(tmp_path: Path) -> None:
    from guiskindose.phantom_pack_install import _INSTALL_FAILED, install_phantom_pack

    shipped = tmp_path / "shipped"
    blocker = tmp_path / "blocker"
    blocker.write_bytes(b"not-a-dir")
    library = blocker / "phantoms"
    body = tiny_stl_body()
    manifest = manifest_for_files({"senior_male": body})
    stream = io.BytesIO(pack_zip_bytes(manifest, {"senior_male": body}))
    pin = _pin_for(manifest)
    with pytest.raises(PhantomPackError, match=_INSTALL_FAILED):
        install_phantom_pack(
            stream,
            user_library_dir=library,
            shipped_dir=shipped,
            expected_manifest_sha256=pin,
            app_version="1.1.1",
        )


@pytest.mark.skipif(os.name == "nt", reason="POSIX permissions")
def test_readonly_library_install_failed(tmp_path: Path) -> None:
    import os

    from guiskindose.phantom_pack_install import _INSTALL_FAILED, install_phantom_pack

    shipped = tmp_path / "shipped"
    library = tmp_path / "library"
    library.mkdir()
    os.chmod(library, 0o500)
    body = tiny_stl_body()
    manifest = manifest_for_files({"senior_male": body})
    stream = io.BytesIO(pack_zip_bytes(manifest, {"senior_male": body}))
    try:
        pin = _pin_for(manifest)
        with pytest.raises(PhantomPackError, match=_INSTALL_FAILED):
            install_phantom_pack(
                stream,
                user_library_dir=library,
                shipped_dir=shipped,
                expected_manifest_sha256=pin,
                app_version="1.1.1",
            )
    finally:
        os.chmod(library, 0o700)


def test_sweep_does_not_descend_into_a_junction(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A Windows junction looks like a plain directory to pathlib; its target's files must survive."""
    import guiskindose.phantom_pack_install as install_mod

    library = tmp_path / "library"
    junction = library / ".incoming-junction"
    junction.mkdir(parents=True)
    victim = junction / "keep.txt"
    victim.write_bytes(b"keep")
    real_check = install_mod._path_is_library_link
    monkeypatch.setattr(
        install_mod,
        "_path_is_library_link",
        lambda path, platform=None: path == junction or real_check(path, platform),
    )
    install_mod._sweep_incoming_dirs(library, keep_stage=None)
    assert victim.read_bytes() == b"keep"


def test_zip_eocd_member_count_rejected_before_zipfile(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import io
    import struct
    import zipfile

    from guiskindose.phantom_pack_install import install_phantom_pack

    # Minimal zip EOCD claiming 129 entries (invalid payload; must fail in pre-check).
    eocd = struct.pack("<4s4H2IH", b"PK\x05\x06", 0, 0, 129, 129, 0, 0, 0)
    payload = eocd

    def _fail_if_opened(*_args, **_kwargs):
        raise AssertionError("ZipFile should not be constructed")

    monkeypatch.setattr(zipfile.ZipFile, "__init__", _fail_if_opened)
    shipped = tmp_path / "shipped"
    library = tmp_path / "library"
    stream = io.BytesIO(payload)
    with pytest.raises(PhantomPackError):
        install_phantom_pack(
            stream,
            user_library_dir=library,
            shipped_dir=shipped,
            expected_manifest_sha256="a" * 64,
            app_version="1.1.1",
        )


def test_oversized_stream_rejected_before_zipfile(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import io
    import zipfile

    from guiskindose.phantom_pack_install import _MAX_COMPRESSED_BYTES, install_phantom_pack

    def _fail_if_opened(*_args, **_kwargs):
        raise AssertionError("ZipFile should not be constructed")

    monkeypatch.setattr(zipfile.ZipFile, "__init__", _fail_if_opened)
    shipped = tmp_path / "shipped"
    library = tmp_path / "library"
    stream = io.BytesIO(b"\x00" * (_MAX_COMPRESSED_BYTES + 1))
    with pytest.raises(PhantomPackError):
        install_phantom_pack(
            stream,
            user_library_dir=library,
            shipped_dir=shipped,
            expected_manifest_sha256="a" * 64,
            app_version="1.1.1",
        )


def test_read_zip_body_rejects_per_member_cap(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import zipfile

    from guiskindose.phantom_pack_install import _MAX_MEMBER_BYTES, _read_zip_body

    body = tiny_stl_body()
    manifest = manifest_for_files({"senior_male": body})
    raw = pack_zip_bytes(manifest, {"senior_male": body})

    class _HugeReader:
        def read(self, size: int = -1) -> bytes:
            return b"x" * (_MAX_MEMBER_BYTES + 1)

        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            return None

    def _open_lie(self, info, mode="r"):
        return _HugeReader()

    monkeypatch.setattr(zipfile.ZipFile, "open", _open_lie)
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        info = next(i for i in zf.infolist() if i.filename.endswith(".stl"))
        with pytest.raises(PhantomPackError):
            _read_zip_body(zf, info, running_total=0)


def test_read_zip_body_rejects_cumulative_cap(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import zipfile

    from guiskindose.phantom_pack_install import _MAX_DECOMPRESSED_TOTAL, _read_zip_body

    body = tiny_stl_body()
    manifest = manifest_for_files({"senior_male": body})
    raw = pack_zip_bytes(manifest, {"senior_male": body})

    class _ChunkReader:
        def read(self, size: int = -1) -> bytes:
            return b"x" * 65536

        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            return None

    def _open_lie(self, info, mode="r"):
        return _ChunkReader()

    monkeypatch.setattr(zipfile.ZipFile, "open", _open_lie)
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        info = next(i for i in zf.infolist() if i.filename.endswith(".stl"))
        with pytest.raises(PhantomPackError):
            _read_zip_body(zf, info, running_total=_MAX_DECOMPRESSED_TOTAL - 1)


def test_zip_signature_bytes_in_comment_do_not_reject_a_valid_pack(tmp_path: Path) -> None:
    """A valid pack whose comment and member data hold zip signature bytes still installs.

    Python's zipfile itself misreads an EOCD signature inside the comment, so the
    comment carries only the ZIP64 locator signature that the old check rejected.
    """
    shipped = tmp_path / "shipped"
    library = tmp_path / "library"
    body = tiny_stl_body()
    manifest = manifest_for_files({"senior_male": body})
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("senior_male.stl", body)
        zf.writestr("manifest.json", canonical_manifest_bytes(manifest))
        zf.comment = b"note PK\x06\x07 inside the comment"
    result = _install(buf.getvalue(), shipped=shipped, library=library, manifest=manifest)
    assert result.installed == 1


def test_tail_read_error_is_install_failed(tmp_path: Path) -> None:
    """An OSError while reading the archive tail gives the install-failed sentence."""
    from guiskindose.phantom_pack_install import _INSTALL_FAILED

    body = tiny_stl_body()
    manifest = manifest_for_files({"senior_male": body})
    raw = pack_zip_bytes(manifest, {"senior_male": body})

    class _BrokenRead(io.BytesIO):
        """Seekable stream whose read always fails."""

        def read(self, *_args: object) -> bytes:
            raise OSError("disk gone")

    pin = _pin_for(manifest)
    stream = _BrokenRead(raw)
    with pytest.raises(PhantomPackError, match=_INSTALL_FAILED):
        install_phantom_pack(
            stream,
            user_library_dir=tmp_path / "library",
            shipped_dir=tmp_path / "shipped",
            expected_manifest_sha256=pin,
            app_version="1.1.1",
        )
