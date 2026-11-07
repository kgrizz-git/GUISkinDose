"""CLI phantom pack install."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from guiskindose.phantom_pack_cli import (
    run_cli_phantom_pack_install,
)
from tests.unittests.phantom_pack_test_helpers import manifest_for_files, pack_zip_bytes, tiny_stl_body


def test_headless_cli_install_via_entry(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from guiskindose import __main__ as entry

    shipped = tmp_path / "shipped"
    library = tmp_path / "library"
    shipped.mkdir()
    body = tiny_stl_body()
    manifest = manifest_for_files({"senior_male": body})
    from guiskindose.phantom_pack import manifest_sha256

    pin = manifest_sha256(manifest)
    zip_path = tmp_path / "pack.zip"
    zip_path.write_bytes(pack_zip_bytes(manifest, {"senior_male": body}))
    monkeypatch.setattr("guiskindose.phantom_pack_pin.EXPECTED_PHANTOM_PACK_SHA256", pin)
    monkeypatch.setattr("guiskindose.phantom_mesh_names.package_phantom_data_dir", lambda: shipped)
    monkeypatch.setattr("guiskindose.phantom_pack_install.default_install_library_dir", lambda: library)
    monkeypatch.setattr(sys, "argv", ["guiskindose", "--install-phantom-pack", str(zip_path)])
    with pytest.raises(SystemExit) as exc:
        entry.cli()
    assert exc.value.code == 0
    assert "Installed 1" in capsys.readouterr().out


def test_gui_mode_refuses_pack_install(monkeypatch: pytest.MonkeyPatch) -> None:
    from guiskindose import __main__ as entry

    argv = ["guiskindose", "--mode", "gui", "--install-phantom-pack", "pack.zip"]
    monkeypatch.setattr(sys, "argv", argv)
    with pytest.raises(SystemExit) as exc:
        entry.cli()
    assert exc.value.code == 1


def test_install_without_file_path_prints_counts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    shipped = tmp_path / "shipped"
    library = tmp_path / "library"
    shipped.mkdir()
    body = tiny_stl_body()
    manifest = manifest_for_files({"senior_male": body})
    from guiskindose.phantom_pack import manifest_sha256

    pin = manifest_sha256(manifest)
    zip_path = tmp_path / "pack.zip"
    zip_path.write_bytes(pack_zip_bytes(manifest, {"senior_male": body}))
    monkeypatch.setattr("guiskindose.phantom_pack_pin.EXPECTED_PHANTOM_PACK_SHA256", pin)
    monkeypatch.setattr("guiskindose.__version__", "1.1.1")
    monkeypatch.setattr("guiskindose.phantom_pack_install.default_install_library_dir", lambda: library)
    monkeypatch.setattr("guiskindose.phantom_mesh_names.package_phantom_data_dir", lambda: shipped)
    code = run_cli_phantom_pack_install(zip_path)
    out = capsys.readouterr()
    assert code == 0
    assert "Installed 1" in out.out or "installed 1" in out.out.lower()
    assert str(zip_path) not in out.out
    assert str(zip_path) not in out.err


def test_install_library_unavailable_prints_fixed_sentence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from guiskindose.phantom_library import _WINDOWS_LIBRARY_UNAVAILABLE, PhantomLibraryUnavailableError

    zip_path = tmp_path / "pack.zip"
    zip_path.write_bytes(b"not used")
    monkeypatch.setattr(
        "guiskindose.phantom_pack_cli.install_phantom_pack_from_stream",
        lambda *_a, **_k: (_ for _ in ()).throw(PhantomLibraryUnavailableError(_WINDOWS_LIBRARY_UNAVAILABLE)),
    )
    code = run_cli_phantom_pack_install(zip_path)
    err = capsys.readouterr().err
    assert code == 1
    assert _WINDOWS_LIBRARY_UNAVAILABLE in err


def test_bad_zip_user_message_no_path(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    bad = tmp_path / "bad.zip"
    bad.write_bytes(b"not a zip")
    code = run_cli_phantom_pack_install(bad)
    err = capsys.readouterr().err
    assert code == 1
    assert str(bad) not in err


def test_missing_mesh_headless_uses_install_hint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from guiskindose import load_settings_example_json
    from guiskindose.phantom_class import Phantom
    from guiskindose.phantom_mesh_names import HumanMeshNotInstalledError
    from guiskindose.settings import PyskindoseSettings

    shipped = tmp_path / "shipped"
    shipped.mkdir()
    (shipped / "adult_male.stl").write_bytes(tiny_stl_body())
    monkeypatch.setattr("guiskindose.phantom_mesh_names.package_phantom_data_dir", lambda: shipped)
    monkeypatch.setattr(
        "guiskindose.phantom_library.default_user_library_dir",
        lambda: tmp_path / "library",
    )
    dims = PyskindoseSettings(settings=load_settings_example_json()).phantom.dimension
    with pytest.raises(HumanMeshNotInstalledError) as info:
        Phantom(phantom_model="human", phantom_dim=dims, human_mesh="senior_male")
    assert "phantom pack" in str(info.value).lower()
