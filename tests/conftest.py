"""Top-level pytest configuration.

`pytest_plugins` must be declared in a top-level conftest — pytest no longer
allows it in nested conftests (it would silently affect the whole suite). The
NiceGUI test plugin provides the `user` fixture the GUI tests rely on, so it is
registered here, but only when NiceGUI (the `[gui]` extra) is installed. That
keeps the rest of the suite collectable without the GUI dependencies.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path

import pytest

pytest_plugins: list[str] = []

try:
    import nicegui  # noqa: F401
except ImportError:
    pass
else:
    pytest_plugins.append("nicegui.testing.user_plugin")


_REPO_ROOT = Path(__file__).resolve().parents[1]
_EXCLUDED_DIRS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    ".basedpyright",
    ".hypothesis",
    "node_modules",
    "build",
    "dist",
    "htmlcov",
    "site",
}
_EXCLUDED_FILENAMES = {
    # Finder owns these metadata files and may rewrite them while pytest runs.
    # They cannot contain application output or clinical fixture content.
    ".DS_Store",
}


def _is_excluded_artifact(path: Path) -> bool:
    """Ignore regenerable local artifacts that tests may create from committed inputs."""
    if path.name in _EXCLUDED_FILENAMES or path.name.startswith(".coverage"):
        return True
    # db_connect() auto-builds this SQLite cache from committed CSV tables; it is gitignored.
    if path.name == "corrections.db" or path.name.startswith("corrections.db-"):
        return True
    return False


def _digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _tracked_paths() -> set[Path]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=_REPO_ROOT,
        check=True,
        capture_output=True,
    )
    return {
        _REPO_ROOT / value.decode("utf-8")
        for value in result.stdout.split(b"\0")
        if value
    }


def _workspace_snapshot() -> tuple[dict[Path, str], dict[Path, str]]:
    tracked_paths = _tracked_paths()
    tracked = {path: _digest(path) for path in tracked_paths if path.is_file()}
    other: dict[Path, str] = {}
    for directory, dirnames, filenames in os.walk(_REPO_ROOT):
        dirnames[:] = [name for name in dirnames if name not in _EXCLUDED_DIRS]
        for filename in filenames:
            path = Path(directory) / filename
            if path not in tracked_paths and not _is_excluded_artifact(path):
                other[path] = _digest(path)
    return tracked, other


def _path_token(path: Path) -> str:
    relative = path.relative_to(_REPO_ROOT).as_posix().encode("utf-8")
    return hashlib.sha256(relative).hexdigest()[:12]


def pytest_sessionstart(session: pytest.Session) -> None:
    """Snapshot the checkout so tests cannot hide writes in an already-dirty tree."""
    try:
        session.config._privacy_workspace_snapshot = _workspace_snapshot()  # type: ignore[attr-defined]
    except (OSError, subprocess.SubprocessError):
        session.config._privacy_workspace_snapshot = None  # type: ignore[attr-defined]


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """Fail when tests changed tracked files or left new non-cache artifacts."""
    before = getattr(session.config, "_privacy_workspace_snapshot", None)
    if before is None:
        return
    try:
        after = _workspace_snapshot()
    except (OSError, subprocess.SubprocessError):
        session.exitstatus = pytest.ExitCode.TESTS_FAILED
        return

    changed = sorted(
        path
        for group_before, group_after in zip(before, after)
        for path in set(group_before) | set(group_after)
        if group_before.get(path) != group_after.get(path)
    )
    if not changed:
        return
    reporter = session.config.pluginmanager.get_plugin("terminalreporter")
    if reporter is not None:
        reporter.write_line(
            "ERROR: tests changed the checkout; value-safe path token(s): "
            + ", ".join(_path_token(path) for path in changed[:20]),
            red=True,
        )
    session.exitstatus = pytest.ExitCode.TESTS_FAILED
