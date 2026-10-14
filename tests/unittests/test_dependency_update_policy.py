"""Guard coordinated gate-tool versions and the two independent uv update scopes."""

import json
import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_ruff_lock_hook_and_complexity_versions_agree() -> None:
    """A dependency-only Ruff bump must not leave local hooks on the previous analyzer."""
    lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    locked_ruff = next(package["version"] for package in lock["package"] if package["name"] == "ruff")
    hooks = (ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8")
    match = re.search(r"repo: https://github.com/astral-sh/ruff-pre-commit\s+rev: v([^\s]+)", hooks)
    assert match is not None
    assert match.group(1) == locked_ruff
    caps = json.loads((ROOT / "dev-docs/complexity_caps.json").read_text(encoding="utf-8"))
    assert caps["tool_version"] == locked_ruff


def test_dependabot_uses_uv_and_preserves_the_scanner_pin() -> None:
    config = (ROOT / ".github/dependabot.yml").read_text(encoding="utf-8")
    entries = config.split("  - package-ecosystem: ")[1:]
    root = next(entry for entry in entries if "    directory: /\n" in entry)
    scanner = next(entry for entry in entries if "    directory: /tools/semgrep\n" in entry)
    assert root.startswith("uv\n")
    assert "versioning-strategy: increase-if-necessary" in root
    assert "exclude-patterns:" in root
    assert '- "ruff"' in root
    assert scanner.startswith("uv\n")
    assert "versioning-strategy: lockfile-only" in scanner
    assert "dependency-type: all" in scanner
    assert "ignore:\n      - dependency-name: semgrep" in scanner
