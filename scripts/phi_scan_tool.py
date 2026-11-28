#!/usr/bin/env python3
"""Resolve a pinned, hash-locked, isolated phi-scan invocation.

phi-scan is deliberately **not** a project dependency. It is only ever run as a CLI,
never imported, so it lives in its own environment like the other privacy scanners.

Isolation alone would cost integrity: ``uvx --from phi-scan==<pin>`` fixes the
scanner's own version but re-resolves its 38 transitive dependencies on every run,
with no recorded hashes. The preferred invocation is therefore a ``uv run --locked``
against ``tools/phi-scan/``, a standalone mini-project whose ``uv.lock`` pins every
transitive package to an exact version and sha256. ``uvx`` remains a local fallback;
in CI it is refused, because a green CI log would hide the fact that the scanner ran
with an unverified dependency tree.

The version of record is ``dev-docs/privacy_tool_inventory.json``, the tracked source
of truth for scanner versions. ``tools/phi-scan/pyproject.toml`` must repeat the pin
because uv needs a literal requirement; the two are checked against each other by
``tests/unittests/test_phi_scan_tool.py`` and at gate time by ``phi_scan_argv``.

All invocations are argument lists with :mod:`pathlib` paths, never shell strings, so
the resolver behaves the same on Windows, macOS, and Linux.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Final

INVENTORY_PATH: Final = Path("dev-docs/privacy_tool_inventory.json")
_TOOL_ID: Final = "phi-scan"
_TOOL_ID_KEY: Final = "id"

# Standalone uv project carrying the hash-locked scanner environment. Not a workspace
# member of the root project: joining the workspace would merge these dependencies back
# into the root resolution and undo the isolation.
TOOL_PROJECT: Final = Path("tools/phi-scan")
EXECUTABLE: Final = "phi-scan"
_TOOL_LOCK: Final = "uv.lock"
_TOOL_MANIFEST: Final = "pyproject.toml"
_TOOL_ENV_DIRNAME: Final = ".venv"

_VERSION_PROBE_TIMEOUT_S: Final = 60
_CI_ENV_VARS: Final = ("CI", "GITHUB_ACTIONS")
_TRUTHY: Final = frozenset({"1", "true", "yes", "on"})


class PhiScanUnavailableError(RuntimeError):
    """Neither an isolated nor an installed phi-scan could be resolved.

    Raised rather than falling back to "skip the scan": a privacy gate that quietly
    does nothing is worse than one that fails.
    """


def _is_truthy(value: object) -> bool:
    return value is not None and str(value).strip().lower() in _TRUTHY


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def pinned_version(root: Path | None = None) -> str:
    """phi-scan version recorded in the privacy tool inventory."""
    base = repo_root() if root is None else root
    payload = json.loads((base / INVENTORY_PATH).read_text(encoding="utf-8"))
    for tool in payload.get("tools", []):
        if isinstance(tool, dict) and tool.get(_TOOL_ID_KEY) == _TOOL_ID:
            version = tool.get("version")
            if isinstance(version, str) and version.strip():
                return version.strip()
            raise PhiScanUnavailableError("inventory entry for phi-scan has no version")
    raise PhiScanUnavailableError("no phi-scan entry in the privacy tool inventory")


def in_ci(environ: object = None) -> bool:
    source = os.environ if environ is None else environ
    get = source.get  # type: ignore[union-attr]
    return any(_is_truthy(get(name)) for name in _CI_ENV_VARS)


def tool_manifest_pin(project: Path) -> str | None:
    """phi-scan version literal declared by the tool project, or None if unreadable."""
    try:
        text = (project / _TOOL_MANIFEST).read_text(encoding="utf-8")
    except OSError:
        return None
    match = re.search(r'"(?:phi-scan|phi_scan)==([A-Za-z0-9][A-Za-z0-9._+-]*)"', text)
    return match.group(1) if match else None


def locked_tool_project(root: Path | None = None) -> Path | None:
    """The hash-locked tool project, or None if this checkout has no usable one."""
    base = repo_root() if root is None else root
    project = base / TOOL_PROJECT
    if (project / _TOOL_MANIFEST).is_file() and (project / _TOOL_LOCK).is_file():
        return project
    return None


def tool_environment(environ: dict[str, str] | None = None, *, root: Path | None = None) -> dict[str, str]:
    """Environment for the isolated tool, with the project's uv settings redirected.

    Two `.envrc` exports would otherwise leak into the scanner run:

    ``UV_PYTHON`` pins the *project* to 3.14 and uv honours it. phi-scan needs >=3.12 so
    that value happens to work today, but inheriting it would make the local gate follow
    the project pin while CI used its own interpreter.

    ``UV_PROJECT_ENVIRONMENT`` points at the project's own ``.venv``. Left in place,
    ``uv run --project tools/phi-scan`` would install phi-scan and its pinned
    dependencies straight into the environment this change exists to keep them out of.
    """
    source = dict(os.environ if environ is None else environ)
    source.pop("UV_PYTHON", None)
    source.pop("VIRTUAL_ENV", None)
    base = repo_root() if root is None else root
    source["UV_PROJECT_ENVIRONMENT"] = str(base / TOOL_PROJECT / _TOOL_ENV_DIRNAME)
    return source


def installed_version(executable: str) -> str | None:
    """Version reported by a phi-scan executable, or None if it cannot be read.

    phi-scan prints ``phi-scan 0.7.0`` (and may emit an NLP-extra warning on stderr),
    so the version is the last token on the first stdout line.
    """
    try:
        completed = subprocess.run(
            [executable, "--version"],
            check=False,
            capture_output=True,
            text=True,
            timeout=_VERSION_PROBE_TIMEOUT_S,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0 or not completed.stdout.strip():
        return None
    first_line = completed.stdout.strip().splitlines()[0].strip()
    return first_line.split()[-1] if first_line else None


def _locked_argv(uv: str, project: Path, version: str, args: list[str]) -> list[str]:
    """Strongest tier: exact versions and sha256 hashes for the whole dependency tree."""
    declared = tool_manifest_pin(project)
    if declared != version:
        # `--locked` compares the tool manifest against its own lock and never reads the
        # inventory, so without this an inventory-only bump gates green on the previous
        # scanner and fails later in pytest -- advisory exactly where it matters most.
        raise PhiScanUnavailableError(
            f"the inventory pins phi-scan {version} but {TOOL_PROJECT}/pyproject.toml declares "
            f"{declared or 'no version'}; update both, then run: uv lock --project {TOOL_PROJECT}"
        )
    # --locked then refuses to proceed if uv.lock is stale rather than silently
    # re-resolving, which is the whole point of having the lock.
    return [uv, "run", "--locked", "--project", str(project), EXECUTABLE, *args]


def _uvx_argv(uvx: str, project: Path | None, version: str, args: list[str]) -> list[str]:
    """Local fallback only: the right scanner version, with an unverified dependency tree."""
    if project is None:
        detail = (
            f"{TOOL_PROJECT} is missing or has no uv.lock, so the scanner's dependency tree cannot be hash-verified"
        )
        # Locally this is a stale or partial checkout, and degrading to version-only
        # isolation beats blocking a push. In CI it means the tracked lock did not
        # arrive, and a warning would be invisible in a green log.
        if in_ci():
            raise PhiScanUnavailableError(f"{detail}; a CI checkout must include it")
        print(f"WARNING: {detail}; running the pinned version without it.", file=sys.stderr)
    return [uvx, "--from", f"{EXECUTABLE}=={version}", EXECUTABLE, *args]


def _path_argv(base: Path, version: str, args: list[str]) -> list[str]:
    """Weakest tier: whatever is on PATH, accepted only at the pinned version."""
    installed = shutil.which(EXECUTABLE)
    if installed is None:
        raise PhiScanUnavailableError(
            "phi-scan is not a project dependency; install uv (for the locked tool project) or phi-scan itself"
        )
    # `.envrc` puts the project venv on PATH and `tool_environment()` does not sanitise
    # PATH, so a phi-scan left behind by a leak into the project environment would
    # otherwise satisfy the version check below: right version, wrong environment.
    if Path(installed).resolve().is_relative_to((base / ".venv").resolve()):
        raise PhiScanUnavailableError(
            "the only phi-scan on PATH lives in the project virtual environment, which means "
            "the scanner leaked into it; remove it and install uv"
        )
    reported = installed_version(installed)
    if reported != version:
        raise PhiScanUnavailableError(
            f"the phi-scan on PATH reports {reported or 'an unreadable version'}, "
            f"but the gate is pinned to {version}; install uv so the pinned tool can be used"
        )
    print(
        "WARNING: uv not found; using the phi-scan on PATH. Its version matches the pin, "
        "but its dependencies are not the hash-locked ones.",
        file=sys.stderr,
    )
    return [installed, *args]


def phi_scan_argv(args: list[str], *, root: Path | None = None) -> list[str]:
    """Command that runs the pinned phi-scan with ``args``.

    Preference order, strongest first: a hash-locked ``uv run --locked`` against
    ``tools/phi-scan``; a local-only ``uvx --from phi-scan==<pin>`` (right version,
    unverified dependency tree); a phi-scan already on ``PATH``, accepted only when it
    reports the pinned version. In CI the locked route is required: neither ``uvx`` nor
    ``PATH`` is accepted, so a missing lock or missing ``uv`` fails the run. Every tier
    either returns a command that runs the pinned scanner or raises; none of them
    degrades to running nothing.
    """
    base = repo_root() if root is None else root
    uv = shutil.which("uv")
    uvx = shutil.which("uvx")

    # Read the inventory on every tier, the locked one included: it is the version of record.
    version = pinned_version(base)
    project = locked_tool_project(base)
    if in_ci() and (project is None or uv is None):
        # In CI the lock route is the only acceptable one: an unverified dependency tree
        # (uvx) or an unpinned binary on PATH must fail the run, not pass quietly.
        detail = (
            f"{TOOL_PROJECT} is missing or has no uv.lock, so the scanner's dependency tree cannot be hash-verified"
            if project is None
            else "uv is not available, so the hash-locked scanner environment cannot run"
        )
        raise PhiScanUnavailableError(f"{detail}; a CI checkout must include it")
    if uv is not None and project is not None:
        return _locked_argv(uv, project, version, args)
    if uvx is not None:
        return _uvx_argv(uvx, project, version, args)
    return _path_argv(base, version, args)
