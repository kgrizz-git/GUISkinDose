#!/usr/bin/env python3
"""Write the "what caused it" section of the ci-latest tracking issue.

The ``latest-deps`` job in ``.github/workflows/ci-latest.yml`` tees each probe's output
into a log directory and ``pip freeze`` into ``freeze.txt``. This script turns those into
Markdown the issue step embeds:

* a log excerpt for every failed probe (pytest's FAILED/ERROR lines, otherwise the tail),
  labelled with the exit code, so the issue says *why* instead of only *which step*;
* the installed versions that differ from ``uv.lock``, direct dependencies first, which
  is what answers "was this an upstream release?". A failure with no direct-dependency
  drift is called out, since it usually means the probe environment rather than upstream.

Standard library only: it also runs when the unpinned install itself failed.
"""

from __future__ import annotations

import argparse
import re
import sys
import tomllib
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]

# Per-probe and whole-section caps keep the issue body far below GitHub's 65,536 limit.
MAX_EXCERPT_LINES = 40
MAX_LINE_CHARS = 300
MAX_SECTION_CHARS = 40_000
MAX_DIRECT_ROWS = 40

_ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
_EXIT_MARKER = re.compile(r"^\[exit code (\d+)\]$")
_REQUIREMENT_NAME = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")

# basedpyright/pyright exit codes: only 1 means the type check itself found problems.
_BASEDPYRIGHT_EXIT = {
    1: "type errors reported",
    2: "fatal error, basedpyright did not finish",
    3: "configuration error, basedpyright did not type-check anything",
    4: "invalid command line",
}


def normalize(name: str) -> str:
    """PEP 503 name normalization, so `typing_extensions` matches `typing-extensions`."""
    return re.sub(r"[-_.]+", "-", name).lower()


def locked_versions(lock_path: Path) -> dict[str, str]:
    lock = tomllib.loads(lock_path.read_text(encoding="utf-8"))
    return {normalize(pkg["name"]): pkg["version"] for pkg in lock.get("package", []) if "version" in pkg}


def direct_dependencies(pyproject_path: Path, extras: tuple[str, ...] = ("dev", "gui")) -> set[str]:
    project = tomllib.loads(pyproject_path.read_text(encoding="utf-8")).get("project", {})
    requirements = list(project.get("dependencies", []))
    for extra in extras:
        requirements += project.get("optional-dependencies", {}).get(extra, [])
    names = set()
    for requirement in requirements:
        match = _REQUIREMENT_NAME.match(requirement)
        if match:
            names.add(normalize(match.group(1)))
    return names


def installed_versions(freeze_text: str) -> dict[str, tuple[str, str]]:
    """Map normalized name -> (display name, version) for `name==version` lines."""
    installed = {}
    for line in freeze_text.splitlines():
        name, sep, version = line.strip().partition("==")
        if sep and name and version:
            installed[normalize(name)] = (name, version)
    return installed


def version_drift(
    installed: dict[str, tuple[str, str]], locked: dict[str, str], direct: set[str]
) -> tuple[list[tuple[str, str, str]], list[tuple[str, str, str]]]:
    """(direct, transitive) rows of (name, locked, installed); unlocked packages show "-"."""
    direct_rows, other_rows = [], []
    for key, (name, version) in sorted(installed.items()):
        pinned = locked.get(key, "-")
        if pinned == version:
            continue
        (direct_rows if key in direct else other_rows).append((name, pinned, version))
    return direct_rows, other_rows


def _clean(line: str, workspace: str) -> str:
    line = _ANSI.sub("", line.rstrip())
    if workspace:
        line = line.replace(workspace.rstrip("/") + "/", "")
    return line if len(line) <= MAX_LINE_CHARS else line[: MAX_LINE_CHARS - 3] + "..."


def probe_excerpt(probe: str, log_text: str, workspace: str = "") -> tuple[int | None, list[str]]:
    """Return (exit code, excerpt lines) for one probe's log."""
    lines = [_clean(line, workspace) for line in log_text.splitlines()]
    exit_code = None
    if lines and (match := _EXIT_MARKER.match(lines[-1])):
        exit_code = int(match.group(1))
        lines = lines[:-1]
    lines = [line for line in lines if line.strip()]
    if probe == "pytest":
        failures = [line for line in lines if line.startswith(("FAILED ", "ERROR "))]
        if failures:
            shown = failures[:MAX_EXCERPT_LINES]
            if len(failures) > len(shown):
                shown.append(f"... {len(failures) - len(shown)} more")
            return exit_code, shown + lines[-1:]
    return exit_code, lines[-MAX_EXCERPT_LINES:]


def _exit_label(probe: str, exit_code: int | None) -> str:
    if exit_code is None:
        return "no exit code recorded"
    meaning = _BASEDPYRIGHT_EXIT.get(exit_code) if probe == "basedpyright" else None
    return f"exit code {exit_code}" + (f": {meaning}" if meaning else "")


def _excerpt_section(failed: list[str], log_dir: Path, workspace: str) -> list[str]:
    out = ["**What each failed step printed:**", ""]
    for probe in failed:
        log = log_dir / f"{probe}.log"
        if not log.is_file():
            out += [f"- **{probe}**: no log captured (see the run log).", ""]
            continue
        exit_code, excerpt = probe_excerpt(probe, log.read_text(encoding="utf-8", errors="replace"), workspace)
        body = "\n".join(excerpt).replace("```", "'''") or "(no output)"
        out += [
            f"<details><summary><b>{probe}</b> ({_exit_label(probe, exit_code)})</summary>",
            "",
            "```text",
            body,
            "```",
            "</details>",
            "",
        ]
    return out


def _drift_section(freeze: Path, lock: Path, pyproject: Path) -> list[str]:
    if not freeze.is_file():
        return ["**Versions vs `uv.lock`:** not available (the install did not finish).", ""]
    direct_rows, other_rows = version_drift(
        installed_versions(freeze.read_text(encoding="utf-8")), locked_versions(lock), direct_dependencies(pyproject)
    )
    out = [f"**Versions that differ from `uv.lock`:** {len(direct_rows)} direct, {len(other_rows)} transitive.", ""]
    if direct_rows:
        out += ["| Direct dependency | `uv.lock` | this run |", "|---|---|---|"]
        out += [f"| {name} | {pinned} | {version} |" for name, pinned, version in direct_rows[:MAX_DIRECT_ROWS]]
        if len(direct_rows) > MAX_DIRECT_ROWS:
            out.append(f"| ... {len(direct_rows) - MAX_DIRECT_ROWS} more | | |")
        out.append("")
    else:
        out += [
            "No direct dependency differs from `uv.lock`, so an upstream release is an unlikely cause.",
            "Check whether the failure is in how this workflow sets up its environment.",
            "",
        ]
    if other_rows:
        rows = ", ".join(f"{name} {pinned} → {version}" for name, pinned, version in other_rows)
        out += ["<details><summary>Transitive packages that differ</summary>", "", rows, "</details>", ""]
    return out


def build_report(
    failed: list[str], log_dir: Path, freeze: Path, lock: Path, pyproject: Path, workspace: str = ""
) -> str:
    text = "\n".join(_excerpt_section(failed, log_dir, workspace) + _drift_section(freeze, lock, pyproject))
    if len(text) > MAX_SECTION_CHARS:
        text = text[:MAX_SECTION_CHARS] + "\n\n(report truncated; see the run log)\n"
    return text


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write the failure section of the ci-latest tracking issue.")
    parser.add_argument("--log-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--failed", default="", help="comma-separated failed probe names")
    parser.add_argument("--workspace", default="", help="path prefix to strip from log lines")
    args = parser.parse_args(argv)
    failed = [name for name in args.failed.split(",") if name]
    report = build_report(
        failed,
        args.log_dir,
        args.log_dir / "freeze.txt",
        _REPO_ROOT / "uv.lock",
        _REPO_ROOT / "pyproject.toml",
        args.workspace,
    )
    args.out.write_text(report, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
