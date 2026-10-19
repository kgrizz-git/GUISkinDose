"""Atomic, private, Git-aware writes for clinical and derived exports."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path


class UnsafeOutputPathError(ValueError):
    """Raised when an export destination violates the write policy."""


def _run_git(argv: list[str]) -> subprocess.CompletedProcess[str] | None:
    """Run a git command; return None if the git executable cannot be spawned.

    Args:
        argv: Full argument vector starting with ``git``.

    Returns:
        The completed process, or None on ``OSError`` (for example, Git is not installed).
        Inherited ``GIT_DIR``, ``GIT_WORK_TREE``, and ``GIT_INDEX_FILE`` are removed so
        the command uses the ``-C`` directory. On Windows, a non-zero
        ``CREATE_NO_WINDOW`` flag hides the console flash.
    """
    # GIT_DIR, GIT_WORK_TREE, and GIT_INDEX_FILE would point this check at
    # some other checkout. Drop them so -C selects the destination's repo.
    env = os.environ.copy()
    for name in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"):
        env.pop(name, None)
    no_window = int(getattr(subprocess, "CREATE_NO_WINDOW", 0) or 0)
    try:
        if no_window:
            return subprocess.run(
                argv,
                check=False,
                capture_output=True,
                text=True,
                creationflags=no_window,
                env=env,
            )
        return subprocess.run(argv, check=False, capture_output=True, text=True, env=env)
    except OSError:
        return None


def _existing_parent(path: Path) -> Path:
    parent = path.parent.resolve()
    if not parent.is_dir():
        raise UnsafeOutputPathError("export_parent_missing")
    return parent


def _git_root(parent: Path) -> Path | None:
    result = _run_git(["git", "-C", str(parent), "rev-parse", "--show-toplevel"])
    if result is None:
        return None
    if result.returncode != 0:
        return None
    value = result.stdout.strip()
    return Path(value).resolve() if value else None


def _validate_checkout_destination(target: Path, root: Path, *, allow_ignored_checkout: bool) -> None:
    """Reject tracked or non-ignored destinations under a Git checkout."""
    try:
        relative = target.relative_to(root)
    except ValueError:
        return
    rel = relative.as_posix()
    tracked_result = _run_git(
        ["git", "-C", str(root), "ls-files", "--error-unmatch", "--", rel],
    )
    if tracked_result is None:
        # Git unavailable: do not block exports on machines without git (e.g. portable builds).
        return
    tracked = tracked_result.returncode == 0
    if tracked:
        raise UnsafeOutputPathError("export_tracked_path_forbidden")
    ignored_result = _run_git(
        ["git", "-C", str(root), "check-ignore", "-q", "--", rel],
    )
    if ignored_result is None:
        return
    ignored = ignored_result.returncode == 0
    if not (allow_ignored_checkout and ignored):
        raise UnsafeOutputPathError("export_checkout_path_forbidden")


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

    # A frozen app has no checkout to protect and must not spawn git.
    if not getattr(sys, "frozen", False):
        root = _git_root(parent)
        if root is not None:
            _validate_checkout_destination(target, root, allow_ignored_checkout=allow_ignored_checkout)
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
    fd, temporary_name = tempfile.mkstemp(prefix=".guiskindose-export-", dir=target.parent)
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
