#!/usr/bin/env python3
"""Resolve the isolated Presidio / image-advisory scanner environment.

The scanners need a spaCy model that is only published as a direct github.com wheel URL.
That URL used to sit in the root lock (a dependency group) and broke every Dependabot root
refresh, so it now lives in the standalone uv project ``tools/privacy-scan/``. This module
is the one place that knows how to launch a script inside that project's own ``.venv``.

Like ``tools/semgrep``, the project is deliberately not a workspace member of the root.
"""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Final

TOOL_PROJECT: Final = Path("tools/privacy-scan")
_TOOL_ENV_DIRNAME: Final = ".venv"


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def tool_environment(environ: Mapping[str, str] | None = None, *, root: Path | None = None) -> dict[str, str]:
    """Return ``environ`` with uv's project settings redirected to the tool project.

    ``.envrc`` exports ``UV_PYTHON`` and ``UV_PROJECT_ENVIRONMENT`` (and activates a
    ``VIRTUAL_ENV``) for the root project. Left in place they would make
    ``uv run --project tools/privacy-scan`` use the root ``.venv``.
    """
    source = dict(os.environ if environ is None else environ)
    source.pop("UV_PYTHON", None)
    source.pop("VIRTUAL_ENV", None)
    base = repo_root() if root is None else root
    source["UV_PROJECT_ENVIRONMENT"] = str(base / TOOL_PROJECT / _TOOL_ENV_DIRNAME)
    return source


def script_argv(script: str | Path, args: Sequence[str] = (), *, root: Path | None = None) -> list[str]:
    """Build ``uv run --project <tool> --no-sync python <script> <args>``."""
    base = repo_root() if root is None else root
    return ["uv", "run", "--project", str(base / TOOL_PROJECT), "--no-sync", "python", str(script), *args]
