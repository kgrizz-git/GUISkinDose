"""End-to-end pack build script + install."""

from __future__ import annotations

import hashlib
from pathlib import Path

from guiskindose.phantom_pack import canonical_manifest_bytes
from guiskindose.phantom_pack_cli import install_phantom_pack_from_stream
from scripts.build_phantom_pack import build_pack_manifest, write_pack_zip
from tests.unittests.phantom_pack_test_helpers import tiny_stl_body

PHANTOM_DATA = Path(__file__).resolve().parents[2] / "src" / "guiskindose" / "phantom_data"


def test_build_script_zip_installs_via_installer(tmp_path: Path) -> None:
    """Exercise build script zip installs via installer."""
    shipped = tmp_path / "shipped"
    library = tmp_path / "library"
    shipped.mkdir()
    (shipped / "adult_male.stl").write_bytes(b"shipped\n")
    senior = PHANTOM_DATA / "senior_male.stl"
    if not senior.is_file():
        senior = tmp_path / "senior_male.stl"
        senior.write_bytes(tiny_stl_body())
    manifest = build_pack_manifest([senior], app_version="1.1.1")
    pin = hashlib.sha256(canonical_manifest_bytes(manifest)).hexdigest()
    zip_path = tmp_path / "pack.zip"
    write_pack_zip(manifest, [senior], zip_path)
    with zip_path.open("rb") as handle:
        result = install_phantom_pack_from_stream(
            handle,
            expected_manifest_sha256=pin,
            app_version="1.1.1",
            user_library_dir=library,
            shipped_dir=shipped,
        )
    assert result.installed == 1
    assert (library / "senior_male.stl").is_file()
