"""Two-root phantom library resolution."""

from __future__ import annotations

from pathlib import Path

import pytest

from guiskindose.phantom_mesh_names import (
    HumanMeshNotInstalledError,
    human_mesh_not_installed_message,
    prefer_reduced_preview_stem,
    resolve_human_mesh_stl_path,
)
from tests.unittests.phantom_pack_test_helpers import tiny_stl_body


def _write_stl(root: Path, stem: str, body: bytes | None = None) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / f"{stem}.stl").write_bytes(body or tiny_stl_body())


def test_user_library_resolves_when_shipped_missing(tmp_path: Path) -> None:
    shipped = tmp_path / "shipped"
    library = tmp_path / "library"
    _write_stl(library, "senior_male")
    path = resolve_human_mesh_stl_path(
        "senior_male",
        phantom_data_dir=shipped,
        user_library_dir=library,
    )
    assert path.is_relative_to(library.resolve())
    assert path.name == "senior_male.stl"


def test_shipped_wins_over_user_library(tmp_path: Path) -> None:
    shipped = tmp_path / "shipped"
    library = tmp_path / "library"
    _write_stl(shipped, "senior_male", b"shipped-bytes")
    _write_stl(library, "senior_male", b"user-bytes")
    path = resolve_human_mesh_stl_path(
        "senior_male",
        phantom_data_dir=shipped,
        user_library_dir=library,
    )
    assert path.read_bytes() == b"shipped-bytes"
    assert path.is_relative_to(shipped.resolve())


def test_missing_message_names_pack_without_paths(tmp_path: Path) -> None:
    shipped = tmp_path / "shipped"
    library = tmp_path / "library"
    shipped.mkdir()
    library.mkdir()
    message = human_mesh_not_installed_message(
        "senior_male",
        phantom_data_dir=shipped,
        user_library_dir=library,
    )
    assert message is not None
    assert "Senior Male" in message
    assert "senior_male" in message
    assert "phantom pack" in message.lower()
    assert str(shipped) not in message
    assert "/" not in message or "Full download" in message


def test_legacy_alias_still_resolves(tmp_path: Path) -> None:
    shipped = tmp_path / "shipped"
    _write_stl(shipped, "ped_5y_male")
    path = resolve_human_mesh_stl_path("pediatric_5y_male", phantom_data_dir=shipped, user_library_dir=None)
    assert path.name == "ped_5y_male.stl"


def test_preview_prefers_reduced_shipped_first(tmp_path: Path) -> None:
    shipped = tmp_path / "shipped"
    library = tmp_path / "library"
    _write_stl(shipped, "adult_male")
    _write_stl(library, "adult_male_reduced_3000t")
    assert prefer_reduced_preview_stem("adult_male", phantom_data_dir=shipped, user_library_dir=library) == (
        "adult_male_reduced_3000t"
    )
    _write_stl(shipped, "adult_male_reduced_3000t", b"ship-reduced")
    assert prefer_reduced_preview_stem("adult_male", phantom_data_dir=shipped, user_library_dir=library) == (
        "adult_male_reduced_3000t"
    )


def test_demo_not_from_user_library(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from guiskindose.gui import window_prefs

    shipped = tmp_path / "shipped"
    library = tmp_path / "library"
    shipped.mkdir()
    _write_stl(library, "demo_cosmic_buddha")
    monkeypatch.setattr(window_prefs, "show_demo_phantoms_enabled", lambda **_: True)
    with pytest.raises(ValueError, match="Unknown human mesh"):
        resolve_human_mesh_stl_path(
            "demo_cosmic_buddha",
            phantom_data_dir=shipped,
            user_library_dir=library,
            show_demo_phantoms=True,
        )


def test_demo_from_shipped_when_enabled(tmp_path: Path) -> None:
    shipped = tmp_path / "shipped"
    _write_stl(shipped, "demo_cosmic_buddha")
    path = resolve_human_mesh_stl_path(
        "demo_cosmic_buddha",
        phantom_data_dir=shipped,
        user_library_dir=None,
        show_demo_phantoms=True,
    )
    assert path.is_relative_to(shipped.resolve())


def test_demo_off_raises_value_error(tmp_path: Path) -> None:
    shipped = tmp_path / "shipped"
    _write_stl(shipped, "demo_cosmic_buddha")
    with pytest.raises(ValueError, match="Unknown human mesh"):
        resolve_human_mesh_stl_path(
            "demo_cosmic_buddha",
            phantom_data_dir=shipped,
            user_library_dir=None,
            show_demo_phantoms=False,
        )


def test_missing_clinical_raises_typed_error(tmp_path: Path) -> None:
    shipped = tmp_path / "shipped"
    shipped.mkdir()
    with pytest.raises(HumanMeshNotInstalledError):
        resolve_human_mesh_stl_path("senior_male", phantom_data_dir=shipped, user_library_dir=tmp_path / "lib")


def test_unknown_stem_is_value_error_not_missing(tmp_path: Path) -> None:
    shipped = tmp_path / "shipped"
    shipped.mkdir()
    with pytest.raises(ValueError, match="Unknown human mesh") as info:
        resolve_human_mesh_stl_path("not_a_catalog_mesh", phantom_data_dir=shipped, user_library_dir=None)
    assert not isinstance(info.value, HumanMeshNotInstalledError)


@pytest.mark.parametrize(
    ("platform", "environ", "expected_suffix"),
    [
        ("darwin", {}, ("Library", "Application Support", "GUISkinDose", "phantoms")),
        ("linux", {"XDG_DATA_HOME": "/xdg"}, ("guiskindose", "phantoms")),
        ("linux", {}, (".local", "share", "guiskindose", "phantoms")),
    ],
)
def test_user_library_dir_for_platform_posix(
    tmp_path: Path, platform: str, environ: dict[str, str], expected_suffix: tuple[str, ...]
) -> None:
    from guiskindose.phantom_library import user_library_dir_for_platform

    home = tmp_path / "home"
    home.mkdir()
    path = user_library_dir_for_platform(platform, environ=environ, home=home)
    if platform == "linux" and "XDG_DATA_HOME" in environ:
        assert path == Path(environ["XDG_DATA_HOME"]) / "guiskindose" / "phantoms"
    else:
        assert path == home.joinpath(*expected_suffix)


def test_user_library_dir_windows_localappdata(tmp_path: Path) -> None:
    from guiskindose.phantom_library import PhantomLibraryUnavailableError, user_library_dir_for_platform

    with pytest.raises(PhantomLibraryUnavailableError):
        user_library_dir_for_platform("win32", environ={}, home=tmp_path)
    resolved = user_library_dir_for_platform("win32", environ={"LOCALAPPDATA": str(tmp_path / "local")}, home=tmp_path)
    assert resolved.parts[-2:] == ("GUISkinDose", "phantoms")


def test_path_is_library_link_uses_injected_platform_via_ctypes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import os

    from guiskindose.phantom_library import _path_is_library_link

    link_root = tmp_path / "lib"
    link_root.mkdir()
    monkeypatch.delattr(os.path, "isjunction", raising=False)
    monkeypatch.setattr(
        "guiskindose.phantom_library._win32_file_attributes",
        lambda _p: 0x400,
    )
    assert _path_is_library_link(link_root, "win32")


def test_win32_file_attributes_seam_returns_false_on_attribute_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from guiskindose.phantom_library import _win32_has_reparse_point

    link_root = tmp_path / "lib"
    link_root.mkdir()

    def _boom(_p: Path) -> int:
        raise AttributeError("no windll")

    monkeypatch.setattr("guiskindose.phantom_library._win32_file_attributes", _boom)
    assert not _win32_has_reparse_point(link_root)


def test_demo_stl_in_user_library_alone_is_not_shipped_mesh(tmp_path: Path) -> None:
    from guiskindose.phantom_library import shipped_mesh_stl_path, user_library_mesh_stl_path

    shipped = tmp_path / "shipped"
    library = tmp_path / "lib"
    shipped.mkdir()
    library.mkdir()
    (library / "demo_cosmic_buddha.stl").write_bytes(b"solid t\nendsolid t\n")
    assert user_library_mesh_stl_path("demo_cosmic_buddha", user_library_dir=library) is not None
    assert shipped_mesh_stl_path("demo_cosmic_buddha", shipped_dir=shipped) is None


def test_reduced_companion_of_enabled_demo_resolves_from_shipped(tmp_path: Path) -> None:
    """A shipped _reduced_3000t of an enabled demo resolves; the user library still never serves demos."""
    shipped = tmp_path / "shipped"
    _write_stl(shipped, "demo_cosmic_buddha_reduced_3000t")
    path = resolve_human_mesh_stl_path(
        "demo_cosmic_buddha_reduced_3000t",
        phantom_data_dir=shipped,
        user_library_dir=None,
        show_demo_phantoms=True,
    )
    assert path.name == "demo_cosmic_buddha_reduced_3000t.stl"
    with pytest.raises(ValueError, match="Unknown human mesh"):
        resolve_human_mesh_stl_path(
            "demo_cosmic_buddha_reduced_3000t",
            phantom_data_dir=shipped,
            user_library_dir=None,
            show_demo_phantoms=False,
        )
