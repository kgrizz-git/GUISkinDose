"""Guard coordinated gate-tool versions and the two independent uv update scopes."""

import json
import tomllib
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]


def test_ruff_lock_and_complexity_versions_agree() -> None:
    """The scoring baseline must move with the locked analyzer."""
    lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    locked_ruff = next(package["version"] for package in lock["package"] if package["name"] == "ruff")
    caps = json.loads((ROOT / "dev-docs/complexity_caps.json").read_text(encoding="utf-8"))
    assert caps["tool_version"] == locked_ruff


@pytest.mark.parametrize(
    ("hook_id", "command"),
    [("ruff", "ruff check --force-exclude"), ("bandit", "bandit"), ("shellcheck", "shellcheck")],
)
def test_python_gate_hooks_use_the_project_lock(hook_id: str, command: str) -> None:
    config = yaml.safe_load((ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8"))
    hooks = [hook for repo in config["repos"] for hook in repo["hooks"] if hook["id"] == hook_id]
    assert len(hooks) == 1
    assert hooks[0]["entry"] == f"uv run --locked --extra dev --extra gui {command}"
    assert hooks[0]["language"] == "system"
    if hook_id == "ruff":
        assert hooks[0]["args"] == ["--fix"]
        assert hooks[0]["files"] == "^(src|tests)/"
        assert hooks[0]["types_or"] == ["python", "pyi", "jupyter"]
    if hook_id == "bandit":
        assert hooks[0]["args"] == ["-c", "pyproject.toml", "--severity-level", "medium"]
        assert hooks[0]["files"] == "^(src/guiskindose|scripts)/"


def test_dependabot_uses_uv_and_preserves_the_scanner_pin() -> None:
    config = yaml.safe_load((ROOT / ".github/dependabot.yml").read_text(encoding="utf-8"))
    entries = {(entry["package-ecosystem"], entry["directory"]): entry for entry in config["updates"]}
    assert set(entries) == {("uv", "/"), ("uv", "/tools/semgrep"), ("github-actions", "/")}
    root = entries["uv", "/"]
    scanner = entries["uv", "/tools/semgrep"]
    assert root["versioning-strategy"] == "increase-if-necessary"
    assert "ruff" in root["groups"]["python-minor-and-patch"]["exclude-patterns"]
    assert scanner["versioning-strategy"] == "lockfile-only"
    assert scanner["allow"] == [{"dependency-type": "all"}]
    assert scanner["ignore"] == [{"dependency-name": "semgrep"}]
