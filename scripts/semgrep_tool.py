#!/usr/bin/env python3
"""Resolve a pinned, isolated Semgrep invocation.

Semgrep is deliberately **not** a project dependency. Its own requirements are
tightly pinned (`click<8.2`, `mcp==1.23.3`, `pyjwt[crypto]~=2.13.0`), and while
it sat in the ``dev`` extra those pins held four transitive advisories
unfixable in the shared lock — every `[tool.uv.audit]` suppression the project
carried traced back to this one package. Semgrep is only ever run as a CLI, never
imported, so running it as an isolated tool removes the constraint entirely
without losing the scanner.

The pinned version is read from ``dev-docs/privacy_tool_inventory.json``, which
is already the tracked source of truth for scanner versions and is validated by
``scripts/render_privacy_tool_inventory.py --check``. Keeping the pin there means
the hook, the workflows, and the published inventory cannot drift apart.

Follows the ``uvx --from 'phi-scan==0.7.0'`` pattern already used for the PHI
scanner (``.github/workflows/phi-scan.yml``, ``scripts/privacy_admission.py``).
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path
from typing import Final

INVENTORY_PATH: Final = Path("dev-docs/privacy_tool_inventory.json")
_TOOL_ID: Final = "semgrep"
_TOOL_ID_KEY: Final = "id"

# Set by the weekly `ci-latest` probe to run the newest Semgrep instead of the pin.
# Nothing auto-bumps this pin (it is intentionally outside uv.lock, so Dependabot's
# pip ecosystem cannot see it), so that probe is what surfaces drift and upstream
# breakage; a human then bumps the inventory version.
#
# Honoured ONLY in CI. Locally it would be an unaudited way to run an arbitrary
# scanner version through the same blocking gates, which is the opposite of the
# point; a developer wanting to try a new release can run uvx directly.
UNPINNED_ENV: Final = "GUISKINDOSE_SEMGREP_UNPINNED"
_CI_ENV_VARS: Final = ("CI", "GITHUB_ACTIONS")
_TRUTHY: Final = frozenset({"1", "true", "yes", "on"})


def _is_truthy(value: object) -> bool:
    return value is not None and str(value).strip().lower() in _TRUTHY


def unpinned_probe_requested(environ: object = None) -> bool:
    """Whether the drift probe asked for the newest Semgrep, and may have it."""
    source = os.environ if environ is None else environ
    get = source.get  # type: ignore[union-attr]
    if not _is_truthy(get(UNPINNED_ENV)):
        return False
    return any(_is_truthy(get(name)) for name in _CI_ENV_VARS)


class SemgrepUnavailableError(RuntimeError):
    """Neither an isolated nor an installed Semgrep could be resolved.

    Raised rather than falling back to "skip the scan": a security gate that
    quietly does nothing is worse than one that fails.
    """


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def pinned_version(root: Path | None = None) -> str:
    """Semgrep version recorded in the privacy tool inventory."""
    base = repo_root() if root is None else root
    payload = json.loads((base / INVENTORY_PATH).read_text(encoding="utf-8"))
    for tool in payload.get("tools", []):
        if isinstance(tool, dict) and tool.get(_TOOL_ID_KEY) == _TOOL_ID:
            version = tool.get("version")
            if isinstance(version, str) and version.strip():
                return version.strip()
            raise SemgrepUnavailableError("inventory entry for semgrep has no version")
    raise SemgrepUnavailableError("no semgrep entry in the privacy tool inventory")


def tool_environment(environ: dict[str, str] | None = None) -> dict[str, str]:
    """Environment for the isolated tool, with the project's interpreter pin removed.

    `.envrc` exports ``UV_PYTHON`` to pin the *project* to 3.14, and ``uvx`` honours it —
    so without this the local blocking gate would run Semgrep on whatever the project
    pins while CI runs it on the runner default. The day a Semgrep release drops that
    interpreter, every direnv developer's pre-push gate breaks and CI stays green. Let
    uv pick an interpreter Semgrep actually supports instead.
    """
    source = dict(os.environ if environ is None else environ)
    source.pop("UV_PYTHON", None)
    return source


def semgrep_argv(args: list[str], *, root: Path | None = None) -> list[str]:
    """Command that runs the pinned Semgrep with ``args``.

    Prefers an isolated ``uvx`` run so the version matches CI exactly. Falls back
    to a Semgrep already on ``PATH`` only when ``uvx`` is missing, and says so on
    stderr — an unpinned local binary may disagree with the gate that runs in CI.
    """
    uvx = shutil.which("uvx")
    if uvx is not None:
        if unpinned_probe_requested():
            print(
                f"NOTE: {UNPINNED_ENV} is set in CI; running the latest Semgrep instead "
                "of the pinned version (weekly drift probe).",
                file=sys.stderr,
            )
            return [uvx, "semgrep", *args]
        if _is_truthy(os.environ.get(UNPINNED_ENV)):
            print(
                f"WARNING: ignoring {UNPINNED_ENV} outside CI; the pinned version is "
                "what the blocking gates use. Run uvx directly to try another release.",
                file=sys.stderr,
            )
        return [uvx, "--from", f"semgrep=={pinned_version(root)}", "semgrep", *args]
    installed = shutil.which("semgrep")
    if installed is not None:
        print(
            "WARNING: uvx not found; using the semgrep on PATH, whose version is not pinned and may differ from CI.",
            file=sys.stderr,
        )
        return [installed, *args]
    raise SemgrepUnavailableError("semgrep is not a project dependency; install uv (for uvx) or semgrep itself")
