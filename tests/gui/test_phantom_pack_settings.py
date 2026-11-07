"""GUI phantom catalog and pack install."""

from __future__ import annotations

import importlib.util
import io
from pathlib import Path

import pytest

pytest.importorskip("nicegui")

from guiskindose.gui import helpers
from guiskindose.gui.helpers import get_human_mesh_options, mesh_stem_is_installed
from guiskindose.gui.state import state
from guiskindose.gui.tabs import settings as settings_tab

_helpers_path = Path(__file__).resolve().parents[1] / "unittests" / "phantom_pack_test_helpers.py"
_spec = importlib.util.spec_from_file_location("phantom_pack_test_helpers", _helpers_path)
assert _spec is not None
assert _spec.loader is not None
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
    def _shipped_dir() -> Path:
        return shipped

    monkeypatch.setattr("guiskindose.phantom_mesh_names.package_phantom_data_dir", _shipped_dir)
    monkeypatch.setattr("guiskindose.gui.tabs._phantom_catalog.package_phantom_data_dir", _shipped_dir)
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


def test_pack_install_from_bytes_clears_measurement_cache(two_root_dirs, monkeypatch: pytest.MonkeyPatch) -> None:
    from guiskindose import __version__
    from guiskindose.gui.tabs import _phantom_catalog as catalog
    from guiskindose.phantom_pack import manifest_sha256
    from guiskindose.phantom_pack_cli import install_phantom_pack_from_stream

    shipped, library = two_root_dirs
    body = tiny_stl_body()
    manifest = manifest_for_files({"junior_male": body}, app_version=__version__)
    pin = manifest_sha256(manifest)
    helpers._MESH_EXTENT_CACHE["junior_male"] = (1.0, 2.0, 3.0)
    helpers._MESH_TORSO_WIDTH_CACHE["junior_male"] = 4.0
    raw = pack_zip_bytes(manifest, {"junior_male": body})
    import guiskindose.phantom_pack_pin as pin_mod

    monkeypatch.setattr(pin_mod, "EXPECTED_PHANTOM_PACK_SHA256", pin)
    result = install_phantom_pack_from_stream(
        io.BytesIO(raw),
        expected_manifest_sha256=pin,
        app_version=__version__,
        user_library_dir=library,
        shipped_dir=shipped,
    )
    assert result.installed == 1
    section = catalog._PhantomCatalogSection(mesh_select=type("S", (), {"options": {}, "update": lambda self: None})(), on_change=lambda: None)
    section.status_label = type("L", (), {"set_text": lambda self, _t: None})()
    section.report_install_success(result)
    assert "junior_male" not in helpers._MESH_EXTENT_CACHE
    assert "junior_male" not in helpers._MESH_TORSO_WIDTH_CACHE


@pytest.mark.asyncio
async def test_catalog_upload_good_zip_production_wiring(two_root_dirs, monkeypatch) -> None:
    import guiskindose.phantom_pack_pin as pin_mod
    from guiskindose import __version__
    from guiskindose.gui.tabs import _phantom_catalog as catalog
    from guiskindose.phantom_pack import manifest_sha256

    shipped, library = two_root_dirs
    body = tiny_stl_body()
    manifest = manifest_for_files({"junior_male": body}, app_version=__version__)
    pin = manifest_sha256(manifest)
    raw = pack_zip_bytes(manifest, {"junior_male": body})
    monkeypatch.setattr(pin_mod, "EXPECTED_PHANTOM_PACK_SHA256", pin)
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
async def test_catalog_upload_tampered_zip_leaves_not_installed(two_root_dirs, monkeypatch) -> None:
    import guiskindose.phantom_pack_pin as pin_mod
    from guiskindose import __version__
    from guiskindose.gui.tabs import _phantom_catalog as catalog
    from guiskindose.phantom_pack import manifest_sha256

    shipped, library = two_root_dirs
    body = tiny_stl_body()
    manifest = manifest_for_files({"junior_male": body}, app_version=__version__)
    pin = manifest_sha256(manifest)
    raw = pack_zip_bytes(manifest, {"junior_male": body + b"#"})
    monkeypatch.setattr(pin_mod, "EXPECTED_PHANTOM_PACK_SHA256", pin)
    messages: list[str] = []
    monkeypatch.setattr(catalog.ui, "notify", lambda message, **_k: messages.append(str(message)))

    async def _io_bound(fn, *args, **kwargs):
        return fn(*args, **kwargs)

    monkeypatch.setattr(catalog.run, "io_bound", _io_bound)
    section = catalog._PhantomCatalogSection(mesh_select=type("S", (), {"options": {}, "update": lambda self: None})(), on_change=lambda: None)
    status_text: list[str] = []
    section.status_label = type("L", (), {"set_text": lambda self, text: status_text.append(str(text))})()

    class _Upload:
        async def iterate(self):
            yield raw

    await section.install_upload(type("E", (), {"file": _Upload()})())
    assert not mesh_stem_is_installed("junior_male", phantom_data_dir=shipped, user_library_dir=library)
    joined = " ".join(status_text + messages).lower()
    assert "install failed" in joined or "not valid" in joined
