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
    monkeypatch.setattr("guiskindose.phantom_pack_cli.__version__", "1.1.1")
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


def test_download_flag_installs_and_prints_counts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from guiskindose.phantom_pack_cli import run_cli_phantom_pack_download
    from guiskindose.phantom_pack_install import InstallResult

    monkeypatch.setattr("guiskindose.phantom_pack_cli.default_install_library_dir", lambda: tmp_path / "library")
    monkeypatch.setattr("guiskindose.phantom_mesh_names.package_phantom_data_dir", lambda: tmp_path / "shipped")
    monkeypatch.setattr(
        "guiskindose.phantom_pack_cli.download_release_pack",
        lambda **_kwargs: InstallResult(1, 0, ("senior_male",)),
    )
    code = run_cli_phantom_pack_download()
    out = capsys.readouterr()
    assert code == 0
    assert "Installed 1" in out.out
    assert str(tmp_path) not in out.out


def test_download_failure_prints_fixed_sentence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from guiskindose.phantom_pack_cli import run_cli_phantom_pack_download
    from guiskindose.phantom_pack_download import DOWNLOAD_OFFLINE, PhantomPackDownloadError

    monkeypatch.setattr("guiskindose.phantom_pack_cli.default_install_library_dir", lambda: tmp_path / "library")
    monkeypatch.setattr("guiskindose.phantom_mesh_names.package_phantom_data_dir", lambda: tmp_path / "shipped")

    def _offline(**_kwargs):
        raise PhantomPackDownloadError(DOWNLOAD_OFFLINE)

    monkeypatch.setattr("guiskindose.phantom_pack_cli.download_release_pack", _offline)
    code = run_cli_phantom_pack_download()
    err = capsys.readouterr().err
    assert code == 1
    assert DOWNLOAD_OFFLINE in err
    assert str(tmp_path) not in err


def test_download_cancel_exits_130(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from guiskindose.phantom_pack_cli import run_cli_phantom_pack_download
    from guiskindose.phantom_pack_download import (
        DOWNLOAD_CANCELLED,
        PhantomPackDownloadCancelled,
    )

    monkeypatch.setattr("guiskindose.phantom_pack_cli.default_install_library_dir", lambda: tmp_path / "library")
    monkeypatch.setattr("guiskindose.phantom_mesh_names.package_phantom_data_dir", lambda: tmp_path / "shipped")

    def _cancel(**_kwargs):
        raise PhantomPackDownloadCancelled(DOWNLOAD_CANCELLED)

    monkeypatch.setattr("guiskindose.phantom_pack_cli.download_release_pack", _cancel)
    code = run_cli_phantom_pack_download()
    assert code == 130
    assert DOWNLOAD_CANCELLED in capsys.readouterr().err


def test_download_keyboard_interrupt_cancels_and_exits_130(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from guiskindose.phantom_pack_cli import run_cli_phantom_pack_download
    from guiskindose.phantom_pack_download import DOWNLOAD_CANCELLED

    monkeypatch.setattr("guiskindose.phantom_pack_cli.default_install_library_dir", lambda: tmp_path / "library")
    monkeypatch.setattr("guiskindose.phantom_mesh_names.package_phantom_data_dir", lambda: tmp_path / "shipped")

    def _interrupt(**kwargs):
        kwargs["control"].cancel()
        raise KeyboardInterrupt

    monkeypatch.setattr("guiskindose.phantom_pack_cli.download_release_pack", _interrupt)
    code = run_cli_phantom_pack_download()
    assert code == 130
    assert DOWNLOAD_CANCELLED in capsys.readouterr().err


def test_gui_mode_refuses_pack_download(monkeypatch: pytest.MonkeyPatch) -> None:
    from guiskindose import __main__ as entry

    monkeypatch.setattr(sys, "argv", ["guiskindose", "--mode", "gui", "--download-phantom-pack"])
    with pytest.raises(SystemExit) as exc:
        entry.cli()
    assert exc.value.code == 1


def test_pack_flags_are_mutually_exclusive() -> None:
    from guiskindose.cli_args import get_argument_parser

    with pytest.raises(SystemExit) as exc:
        get_argument_parser(["--download-phantom-pack", "--install-phantom-pack", "pack.zip"])
    assert exc.value.code == 2


def test_download_keyboard_interrupt_during_install_reports_install_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from guiskindose.phantom_pack_cli import run_cli_phantom_pack_download
    from guiskindose.phantom_pack_download import DOWNLOAD_CANCELLED

    monkeypatch.setattr("guiskindose.phantom_pack_cli.default_install_library_dir", lambda: tmp_path / "library")
    monkeypatch.setattr("guiskindose.phantom_mesh_names.package_phantom_data_dir", lambda: tmp_path / "shipped")

    def _interrupt(**kwargs):
        kwargs["progress"].update(phase="installing")
        raise KeyboardInterrupt

    monkeypatch.setattr("guiskindose.phantom_pack_cli.download_release_pack", _interrupt)
    code = run_cli_phantom_pack_download()
    err = capsys.readouterr().err
    assert code == 130
    assert "installation was interrupted" in err
    assert DOWNLOAD_CANCELLED not in err
