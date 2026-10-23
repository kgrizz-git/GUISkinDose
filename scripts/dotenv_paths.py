"""Locate the ``.env`` files the local Sonar helpers read.

``.env`` is gitignored, so a linked git worktree has none of its own. Without
this lookup the freshness gate silently turned itself off in a worktree and the
local scan could not find its token. A worktree's own ``.env`` still wins; the
main checkout's file only fills keys the worktree does not set.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

# Hook runners export these so child git targets the parent repository.
_GIT_DIR_OVERRIDE_VARS = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_INDEX_FILE",
    "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_COMMON_DIR",
    "GIT_NAMESPACE",
)


def main_checkout_root(root: Path) -> Path | None:
    """Return the main checkout when ``root`` is a linked worktree, else ``None``."""
    env = {key: value for key, value in os.environ.items() if key not in _GIT_DIR_OVERRIDE_VARS}
    try:
        common = subprocess.run(
            ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
            cwd=root,
            env=env,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None
    common_dir = Path(common)
    if common_dir.name != ".git":
        return None  # bare or unusual layout: no main working tree to borrow from
    main_root = common_dir.parent
    if main_root.resolve() == root.resolve():
        return None
    return main_root


def dotenv_candidates(root: Path) -> list[Path]:
    """Return ``.env`` paths in priority order: the checkout's own, then the main checkout's."""
    candidates = [root / ".env"]
    main_root = main_checkout_root(root)
    if main_root is not None:
        candidates.append(main_root / ".env")
    return candidates
