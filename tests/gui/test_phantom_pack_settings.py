"""GUI phantom catalog and pack install."""

from __future__ import annotations

import importlib.util
import io
from pathlib import Path

import pytest

pytest.importorskip("nicegui")

from guiskindose.gui.helpers import get_human_mesh_options, mesh_stem_is_installed
from guiskindose.gui.state import state
from guiskindose.gui.tabs import settings as settings_tab

_helpers_path = Path(__file__).resolve().parents[1] / "unittests" / "phantom_pack_test_helpers.py"
_spec = importlib.util.spec_from_file_location("phantom_pack_test_helpers", _helpers_path)
assert _spec is not None and _spec.loader is not None
_helpers = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_helpers)
manifest_for_files = _helpers.manifest_for_files
pack_zip_bytes = _helpers.pack_zip_bytes
tiny_stl_body = _helpers.tiny_stl_body

pytestmark = pytest.mark.nicegui_main_file("tests/gui/nicegui_main.py")


@pytest.fixture
def two_root_dirs(tmp_path, monkeypatch):
    shipped = tmp_path / "shipped"
    library = tmp_path / "library"
    shipped.mkdir()
    library.mkdir()
    (shipped / "adult_male.stl").write_bytes(tiny_stl_body())
    (library / "senior_male.stl").write_bytes(tiny_stl_body())
    monkeypatch.setattr("guiskindose.phantom_mesh_names.package_phantom_data_dir", lambda: shipped)
    monkeypatch.setattr(
        "guiskindose.phantom_library.default_user_library_dir",
        lambda: library,
    )
    monkeypatch.setattr(
        "guiskindose.phantom_pack_install.default_install_library_dir",
        lambda: library,
    )
    return shipped, library


def test_catalog_install_status_two_root(two_root_dirs) -> None:
    assert mesh_stem_is_installed("adult_male")
    assert mesh_stem_is_installed("senior_male")
    assert not mesh_stem_is_installed("junior_male")


def test_missing_catalog_stem_stays_selected(two_root_dirs, monkeypatch) -> None:
    options = get_human_mesh_options()
    monkeypatch.setattr(state, "human_mesh", "junior_male")
    note = settings_tab._select_installed_mesh(options)
    assert state.human_mesh == "junior_male"
    assert note is not None
    assert "phantom pack" in note.lower()


def test_pack_install_from_bytes(two_root_dirs) -> None:
    from guiskindose.phantom_pack import manifest_sha256
    from guiskindose.phantom_pack_cli import install_phantom_pack_from_stream

    shipped, library = two_root_dirs
    body = tiny_stl_body()
    manifest = manifest_for_files({"junior_male": body})
    pin = manifest_sha256(manifest)
    raw = pack_zip_bytes(manifest, {"junior_male": body})
    result = install_phantom_pack_from_stream(
        io.BytesIO(raw),
        expected_manifest_sha256=pin,
        app_version="1.1.1",
        user_library_dir=library,
        shipped_dir=shipped,
    )
    assert result.installed == 1
    assert mesh_stem_is_installed("junior_male")


@pytest.mark.asyncio
async def test_catalog_upload_good_zip_installs(two_root_dirs, monkeypatch) -> None:
    from guiskindose import __version__
    from guiskindose.gui.tabs import _phantom_catalog as catalog
    from guiskindose.phantom_pack import manifest_sha256

    shipped, library = two_root_dirs
    body = tiny_stl_body()
    manifest = manifest_for_files({"junior_male": body}, app_version=__version__)
    pin = manifest_sha256(manifest)
    raw = pack_zip_bytes(manifest, {"junior_male": body})
    from guiskindose.phantom_pack_cli import install_phantom_pack_from_stream as _install_stream

    def _install_bound(source, **_ignored):
        return _install_stream(
            source,
            expected_manifest_sha256=pin,
            app_version=__version__,
            user_library_dir=library,
            shipped_dir=shipped,
        )

    monkeypatch.setattr(catalog, "install_phantom_pack_from_stream", _install_bound)
    monkeypatch.setattr(catalog.ui, "notify", lambda *_a, **_k: None)

    async def _io_bound(fn, *args, **kwargs):
        return fn(*args, **kwargs)

    monkeypatch.setattr(catalog.run, "io_bound", _io_bound)
    section = catalog._PhantomCatalogSection(mesh_select=type("S", (), {"options": {}, "update": lambda self: None})(), on_change=lambda: None)
    section.status_label = type("L", (), {"set_text": lambda self, _t: None})()

    class _Upload:
        async def iterate(self):
            yield raw

    await section.install_upload(type("E", (), {"file": _Upload()})())
    assert mesh_stem_is_installed("junior_male", phantom_data_dir=shipped, user_library_dir=library)


@pytest.mark.asyncio
async def test_catalog_upload_tampered_zip_leaves_missing(two_root_dirs, monkeypatch) -> None:
    from guiskindose import __version__
    from guiskindose.gui.tabs import _phantom_catalog as catalog
    from guiskindose.phantom_pack import manifest_sha256

    shipped, library = two_root_dirs
    body = tiny_stl_body()
    manifest = manifest_for_files({"junior_male": body}, app_version=__version__)
    pin = manifest_sha256(manifest)
    raw = pack_zip_bytes(manifest, {"junior_male": body + b"#"})
    from guiskindose.phantom_pack_cli import install_phantom_pack_from_stream as _install_stream

    def _install_bound(source, **_ignored):
        return _install_stream(
            source,
            expected_manifest_sha256=pin,
            app_version=__version__,
            user_library_dir=library,
            shipped_dir=shipped,
        )

    monkeypatch.setattr("guiskindose.phantom_pack_cli.install_phantom_pack_from_stream", _install_bound)

    class _Upload:
        async def iterate(self):
            yield raw

    async def _io_bound(fn, *args, **kwargs):
        return fn(*args, **kwargs)

    monkeypatch.setattr(catalog.run, "io_bound", _io_bound)
    section = catalog._PhantomCatalogSection(mesh_select=type("S", (), {"options": {}, "update": lambda self: None})(), on_change=lambda: None)
    section.status_label = type("L", (), {"set_text": lambda self, _t: None})()
    await section.install_upload(type("E", (), {"file": _Upload()})())
    assert not mesh_stem_is_installed("junior_male", phantom_data_dir=shipped, user_library_dir=library)
