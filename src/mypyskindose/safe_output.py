"""Atomic, private, Git-aware writes for clinical and derived exports."""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path


class UnsafeOutputPathError(ValueError):
    """Raised when an export destination violates the write policy."""


def _existing_parent(path: Path) -> Path:
    parent = path.parent.resolve()
    if not parent.is_dir():
        raise UnsafeOutputPathError("export_parent_missing")
    return parent


def _git_root(parent: Path) -> Path | None:
    result = subprocess.run(
        ["git", "-C", str(parent), "rev-parse", "--show-toplevel"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    value = result.stdout.strip()
    return Path(value).resolve() if value else None


def validate_output_path(
    path: str | Path,
    *,
    force: bool = False,
    allow_ignored_checkout: bool = False,
) -> Path:
    """Validate a destination without including it in any raised message."""
    requested = Path(path).expanduser()
    parent = _existing_parent(requested)
    target = parent / requested.name
    if not requested.name or requested.name in {".", ".."}:
        raise UnsafeOutputPathError("export_filename_invalid")
    if target.exists() and target.is_dir():
        raise UnsafeOutputPathError("export_destination_is_directory")
    if target.exists() and not force:
        raise UnsafeOutputPathError("export_destination_exists")

    root = _git_root(parent)
    if root is not None:
        try:
            relative = target.relative_to(root)
        except ValueError:
            relative = None
        if relative is not None:
            rel = relative.as_posix()
            tracked = subprocess.run(
                ["git", "-C", str(root), "ls-files", "--error-unmatch", "--", rel],
                check=False,
                capture_output=True,
            ).returncode == 0
            if tracked:
                raise UnsafeOutputPathError("export_tracked_path_forbidden")
            ignored = subprocess.run(
                ["git", "-C", str(root), "check-ignore", "-q", "--", rel],
                check=False,
                capture_output=True,
            ).returncode == 0
            if not (allow_ignored_checkout and ignored):
                raise UnsafeOutputPathError("export_checkout_path_forbidden")
    return target


def atomic_write_private(
    path: str | Path,
    data: bytes,
    *,
    force: bool = False,
    allow_ignored_checkout: bool = False,
) -> Path:
    """Publish complete bytes with owner-only permissions and no silent overwrite."""
    target = validate_output_path(
        path,
        force=force,
        allow_ignored_checkout=allow_ignored_checkout,
    )
    fd, temporary_name = tempfile.mkstemp(prefix=".mypyskindose-export-", dir=target.parent)
    temporary = Path(temporary_name)
    try:
        if os.name == "posix":
            os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if force:
            os.replace(temporary, target)
        else:
            try:
                os.link(temporary, target)
            except FileExistsError as exc:
                raise UnsafeOutputPathError("export_destination_exists") from exc
            temporary.unlink()
        return target
    finally:
        temporary.unlink(missing_ok=True)
