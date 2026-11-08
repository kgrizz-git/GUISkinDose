"""Headless CLI for installing a phantom pack zip."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import IO

from guiskindose import __version__, phantom_mesh_names
from guiskindose.phantom_library import (
    _WINDOWS_LIBRARY_UNAVAILABLE,
    PhantomLibraryUnavailableError,
)
from guiskindose.phantom_pack import PhantomPackError
from guiskindose.phantom_pack_install import InstallResult, install_phantom_pack

_CLI_SUCCESS = (
    "Phantom pack install finished. Installed {installed} clinical mesh(es); "
    "skipped {skipped_shipped} already bundled with this build."
)

_CLI_FAILURE = "Phantom pack install could not finish."


def phantom_pack_cli_args_present(args: object) -> bool:
    """True when ``--install-phantom-pack`` was passed."""
    return getattr(args, "install_phantom_pack", None) is not None


def install_phantom_pack_from_stream(
    source: IO[bytes],
    *,
    expected_manifest_sha256: str | None = None,
    app_version: str | None = None,
    user_library_dir: Path | None = None,
    shipped_dir: Path | None = None,
) -> InstallResult:
    """Install from an open binary stream; optional overrides for tests."""
    import guiskindose.phantom_pack_pin as phantom_pack_pin_module

    pin = (
        phantom_pack_pin_module.EXPECTED_PHANTOM_PACK_SHA256
        if expected_manifest_sha256 is None
        else expected_manifest_sha256
    )
    version = __version__ if app_version is None else app_version
    from guiskindose.phantom_pack_install import default_install_library_dir

    library = default_install_library_dir() if user_library_dir is None else user_library_dir
    shipped = phantom_mesh_names.package_phantom_data_dir() if shipped_dir is None else shipped_dir
    return install_phantom_pack(
        source,
        user_library_dir=library,
        shipped_dir=shipped.resolve(),
        expected_manifest_sha256=pin,
        app_version=version,
    )


def run_cli_phantom_pack_install(pack_path: Path) -> int:
    """Open *pack_path*, install, print counts. Never prints the path."""
    try:
        with pack_path.open("rb") as handle:
            result = install_phantom_pack_from_stream(handle)
    except PhantomPackError as exc:
        print(exc.user_message(), file=sys.stderr)
        return 1
    except PhantomLibraryUnavailableError:
        print(_WINDOWS_LIBRARY_UNAVAILABLE, file=sys.stderr)
        return 1
    except OSError:
        print(_CLI_FAILURE, file=sys.stderr)
        return 1
    print(_CLI_SUCCESS.format(installed=result.installed, skipped_shipped=result.skipped_shipped))
    return 0
