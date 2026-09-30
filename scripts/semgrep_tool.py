#!/usr/bin/env python3
"""Resolve a pinned, hash-locked, isolated Semgrep invocation.

Semgrep is deliberately **not** a project dependency. Its own requirements are
tightly pinned (`click<8.2`, `mcp==1.23.3`, `pyjwt[crypto]~=2.13.0`), and while
it sat in the ``dev`` extra those pins held four transitive advisories
unfixable in the shared lock — every `[tool.uv.audit]` suppression the project
carried traced back to this one package. Semgrep is only ever run as a CLI, never
imported, so running it as an isolated tool removes the constraint entirely
without losing the scanner.

Isolation alone would cost integrity, though: ``uvx --from semgrep==<pin>`` fixes
the scanner's own version but re-resolves its ~68 transitive dependencies on every
run, with no recorded hashes. So the preferred invocation is a ``uv run --locked``
against ``tools/semgrep/``, a standalone mini-project whose ``uv.lock`` pins every
transitive package to an exact version and sha256 — restoring what ``uv sync
--locked`` provided before Semgrep left the root lock. ``uvx`` remains a fallback.

The version of record is ``dev-docs/privacy_tool_inventory.json``, already the
tracked source of truth for scanner versions and validated by
``scripts/render_privacy_tool_inventory.py --check``. ``tools/semgrep/pyproject.toml``
must repeat the pin because uv needs a literal requirement; the two are checked
against each other by ``tests/unittests/test_semgrep_tool.py``.

Follows the ``uvx --from 'phi-scan==0.7.0'`` pattern already used for the PHI
scanner (``.github/workflows/phi-scan.yml``, ``scripts/privacy_admission.py``).
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
_TOOL_ID: Final = "semgrep"
_TOOL_ID_KEY: Final = "id"

# Standalone uv project carrying the hash-locked scanner environment. Not a workspace
# member of the root project: joining the workspace would merge these dependencies back
# into the root resolution and undo the isolation.
TOOL_PROJECT: Final = Path("tools/semgrep")
_TOOL_LOCK: Final = "uv.lock"
_TOOL_MANIFEST: Final = "pyproject.toml"

# Kept inside the tool project rather than under `tmp/`: pytest's write-containment
# snapshot in tests/conftest.py prunes directories named `.venv` at any depth, but not
# `tmp/`, and tests/unittests/test_privacy_semgrep_rules.py runs the scanner.
_TOOL_ENV_DIRNAME: Final = ".venv"

# Set by the weekly `ci-latest` probe to run the newest Semgrep instead of the pin.
# Nothing auto-bumps this pin (it is intentionally outside the root uv.lock, and
# `.github/dependabot.yml` scopes the pip ecosystem to `directory: /`, so Dependabot
# sees neither lock), so that probe is what surfaces drift and upstream breakage; a
# human then bumps the inventory version and relocks tools/semgrep.
#
# Honoured ONLY in CI. Locally it would be an unaudited way to run an arbitrary
# scanner version through the same blocking gates, which is the opposite of the
# point; a developer wanting to try a new release can run uvx directly.
UNPINNED_ENV: Final = "GUISKINDOSE_SEMGREP_UNPINNED"
_CI_ENV_VARS: Final = ("CI", "GITHUB_ACTIONS")
_TRUTHY: Final = frozenset({"1", "true", "yes", "on"})

_VERSION_PROBE_TIMEOUT_S: Final = 60


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


def in_ci(environ: object = None) -> bool:
    source = os.environ if environ is None else environ
    get = source.get  # type: ignore[union-attr]
    return any(_is_truthy(get(name)) for name in _CI_ENV_VARS)


def tool_manifest_pin(project: Path) -> str | None:
    """Semgrep version literal declared by the tool project, or None if unreadable."""
    try:
        text = (project / _TOOL_MANIFEST).read_text(encoding="utf-8")
    except OSError:
        return None
    match = re.search(r"semgrep==([A-Za-z0-9][A-Za-z0-9._+-]*)", text)
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

    ``UV_PYTHON`` pins the *project* to 3.14 and uv honours it — so without this the
    local blocking gate would run Semgrep on whatever the project pins while CI ran it
    on the runner default. The day a Semgrep release drops that interpreter, every
    direnv developer's pre-push gate breaks and CI stays green.

    ``UV_PROJECT_ENVIRONMENT`` points at the project's own ``.venv``. Left in place,
    ``uv run --project tools/semgrep`` would install Semgrep and its pinned
    dependencies straight into the environment this change exists to keep them out of.
    """
    source = dict(os.environ if environ is None else environ)
    source.pop("UV_PYTHON", None)
    source.pop("VIRTUAL_ENV", None)
    base = repo_root() if root is None else root
    source["UV_PROJECT_ENVIRONMENT"] = str(base / TOOL_PROJECT / _TOOL_ENV_DIRNAME)
    return source


def installed_version(executable: str) -> str | None:
    """Version reported by a Semgrep executable, or None if it cannot be read."""
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
    if completed.returncode != 0:
        return None
    return completed.stdout.strip().splitlines()[0].strip() if completed.stdout.strip() else None


def _probe_argv(uvx: str | None, args: list[str]) -> list[str]:
    """Unpinned drift probe: deliberately the newest release, or nothing."""
    if uvx is None:
        # Falling through to the pinned paths here would be worse than failing: the probe
        # exists to answer "has the pin drifted behind upstream?", and a run that quietly
        # scanned the pinned version instead would answer "no" whatever upstream did. Same
        # failure mode as the skip-when-missing this module removed.
        raise SemgrepUnavailableError(
            f"{UNPINNED_ENV} requested the newest Semgrep, but uvx is unavailable; "
            "install uv in the probe workflow instead of silently probing the pin"
        )
    print(
        f"NOTE: {UNPINNED_ENV} is set in CI; running the latest Semgrep instead "
        "of the pinned version (weekly drift probe).",
        file=sys.stderr,
    )
    return [uvx, "semgrep", *args]


def _locked_argv(uv: str, project: Path, version: str, args: list[str]) -> list[str]:
    """Strongest tier: exact versions and sha256 hashes for the whole dependency tree."""
    declared = tool_manifest_pin(project)
    if declared != version:
        # `--locked` compares the tool manifest against its own lock and never reads the
        # inventory, so without this an inventory-only bump gates green on the previous
        # scanner and fails later in pytest — advisory exactly where it matters most.
        raise SemgrepUnavailableError(
            f"the inventory pins semgrep {version} but {TOOL_PROJECT}/pyproject.toml declares "
            f"{declared or 'no version'}; update both, then run: uv lock --project {TOOL_PROJECT}"
        )
    # --locked then refuses to proceed if uv.lock is stale rather than silently
    # re-resolving, which is the whole point of having the lock.
    return [uv, "run", "--locked", "--project", str(project), "semgrep", *args]


def _uvx_argv(uvx: str, project: Path | None, version: str, args: list[str]) -> list[str]:
    """Middle tier: the right scanner version, with an unverified dependency tree."""
    if project is None:
        detail = (
            f"{TOOL_PROJECT} is missing or has no uv.lock, so the scanner's dependency tree cannot be hash-verified"
        )
        # Locally this is a stale or partial checkout, and degrading to version-only
        # isolation beats blocking the push. In CI it means the tracked lock did not
        # arrive, and a warning would be invisible in a green log.
        if in_ci():
            raise SemgrepUnavailableError(f"{detail}; a CI checkout must include it")
        print(f"WARNING: {detail}; running the pinned version without it.", file=sys.stderr)
    return [uvx, "--from", f"semgrep=={version}", "semgrep", *args]


def _path_argv(base: Path, version: str, args: list[str]) -> list[str]:
    """Weakest tier: whatever is on PATH, accepted only at the pinned version."""
    installed = shutil.which("semgrep")
    if installed is None:
        raise SemgrepUnavailableError("semgrep is not a project dependency; install uv (for uvx) or semgrep itself")
    # `.envrc` puts the project venv on PATH and `tool_environment()` does not sanitise
    # PATH, so a semgrep left behind by the leak fixed earlier on this branch would
    # otherwise satisfy the version check below: right version, wrong environment.
    if Path(installed).resolve().is_relative_to((base / ".venv").resolve()):
        raise SemgrepUnavailableError(
            "the only semgrep on PATH lives in the project virtual environment, which means "
            "the scanner leaked into it; remove it and install uv"
        )
    reported = installed_version(installed)
    if reported != version:
        raise SemgrepUnavailableError(
            f"the semgrep on PATH reports {reported or 'an unreadable version'}, "
            f"but the gate is pinned to {version}; install uv so the pinned tool can be used"
        )
    print(
        "WARNING: uv not found; using the semgrep on PATH. Its version matches the pin, "
        "but its dependencies are not the hash-locked ones.",
        file=sys.stderr,
    )
    return [installed, *args]


def semgrep_argv(args: list[str], *, root: Path | None = None) -> list[str]:
    """Command that runs the pinned Semgrep with ``args``.

    Preference order, strongest first: a hash-locked ``uv run --locked`` against
    ``tools/semgrep``; an isolated ``uvx --from semgrep==<pin>`` (right version,
    unverified dependency tree); a Semgrep already on ``PATH``, which is accepted only
    when it reports the pinned version, because an unpinned local binary that disagrees
    with CI makes the gate advisory without saying so. Every tier either returns a command
    that runs the pinned scanner or raises; none of them degrades to running nothing.
    """
    base = repo_root() if root is None else root
    uv = shutil.which("uv")
    uvx = shutil.which("uvx")

    if unpinned_probe_requested():
        return _probe_argv(uvx, args)
    # Reached only when the probe was not honoured, i.e. the flag is set outside CI.
    if _is_truthy(os.environ.get(UNPINNED_ENV)):
        print(
            f"WARNING: ignoring {UNPINNED_ENV} outside CI; the pinned version is "
            "what the blocking gates use. Run uvx directly to try another release.",
            file=sys.stderr,
        )

    # Read the inventory on every tier, the locked one included: it is the version of record.
    version = pinned_version(base)
    project = locked_tool_project(base)
    if uv is not None and project is not None:
        return _locked_argv(uv, project, version, args)
    if uvx is not None:
        return _uvx_argv(uvx, project, version, args)
    return _path_argv(base, version, args)
