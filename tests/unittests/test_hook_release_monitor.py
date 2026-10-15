"""Execute the metadata-only hook monitor with an offline GitHub API double."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
NODE = shutil.which("node")
# Include cold process startup and runner contention, particularly on Windows.
NODE_TIMEOUT_SECONDS = 60
pytestmark = pytest.mark.skipif(NODE is None, reason="Node.js is needed for the GitHub-script reproduction")


def _run_monitor(latest: str, pinned: str = "v8.30.1", issues: list | None = None, *, step: int = 0) -> dict:
    workflow = yaml.safe_load((ROOT / ".github/workflows/ci-latest.yml").read_text(encoding="utf-8"))
    job = workflow["jobs"]["hook-release-monitor"]
    assert job["if"] == "github.ref == 'refs/heads/main'"
    assert len(job["steps"]) == 2
    assert all(item["uses"].startswith("actions/github-script@") for item in job["steps"])
    assert job["steps"][1]["if"] == "failure() && steps.hook_release_check.outcome == 'failure'"
    script = job["steps"][step]["with"]["script"]
    fixture = {"latest": latest, "pinned": pinned, "issues": issues or []}
    harness = r"""
const fs = require('fs');
const {script, fixture} = JSON.parse(fs.readFileSync(0, 'utf8'));
const calls = [];
const context = {repo: {owner: 'synthetic-owner', repo: 'synthetic-repo'}, sha: 'synthetic-sha',
  serverUrl: 'https://github.com', runId: 42};
const configText = `repos:\n  - repo: https://github.com/gitleaks/gitleaks\n    rev: ${fixture.pinned}\n`;
const github = {rest: {
  repos: {
    getContent: async () => ({data: {type: 'file', encoding: 'base64', content: Buffer.from(configText).toString('base64')}}),
    getLatestRelease: async () => ({data: {tag_name: fixture.latest}}),
  },
  issues: {
    listForRepo: () => {},
    update: async args => {calls.push({operation: 'update', ...args});},
    create: async args => {calls.push({operation: 'create', ...args});},
  },
}, paginate: async () => fixture.issues};
const core = {info: () => {}};
const AsyncFunction = Object.getPrototypeOf(async function(){}).constructor;
new AsyncFunction('github', 'context', 'core', script)(github, context, core)
  .then(() => process.stdout.write(JSON.stringify({calls})))
  .catch(error => process.stdout.write(JSON.stringify({calls, error: error.message})));
"""
    assert NODE is not None
    result = subprocess.run(
        [NODE, "-e", harness],
        input=json.dumps({"script": script, "fixture": fixture}),
        capture_output=True, text=True, check=True, timeout=NODE_TIMEOUT_SECONDS,
    )
    return json.loads(result.stdout)


def test_new_release_opens_one_actionable_issue() -> None:
    result = _run_monitor("v8.31.0")
    assert "error" not in result
    assert len(result["calls"]) == 1
    call = result["calls"][0]
    assert call["operation"] == "create"
    assert "v8.30.1" in call["body"]
    assert "v8.31.0" in call["body"]
    assert "pre-commit autoupdate --repo https://github.com/gitleaks/gitleaks" in call["body"]


def test_existing_issue_is_updated_without_creating_another() -> None:
    issue = {"number": 12, "user": {"login": "github-actions[bot]"},
             "body": "<!-- gitleaks-hook-version-drift --> outdated details"}
    result = _run_monitor("v8.31.0", issues=[issue])
    assert result["calls"][0]["operation"] == "update"
    assert result["calls"][0]["issue_number"] == 12
    assert len(result["calls"]) == 1
    updated = {"number": 12, "user": {"login": "github-actions[bot]"}, "body": result["calls"][0]["body"]}
    assert _run_monitor("v8.31.0", issues=[updated])["calls"] == []


@pytest.mark.parametrize("latest", ["v8.30.1", "v8.29.9", "v8.9.99"])
def test_current_or_newer_pin_closes_only_matching_issues(latest: str) -> None:
    issues = [
        {"number": 12, "user": {"login": "github-actions[bot]"}, "body": "<!-- gitleaks-hook-version-drift -->"},
        {"number": 13, "body": "unrelated issue"},
        {"number": 14, "body": "<!-- gitleaks-hook-version-drift -->", "pull_request": {}},
        {"number": 15, "user": {"login": "synthetic-human"}, "body": "<!-- gitleaks-hook-version-drift -->"},
    ]
    result = _run_monitor(latest, issues=issues)
    assert result["calls"] == [{
        "operation": "update", "owner": "synthetic-owner", "repo": "synthetic-repo",
        "issue_number": 12, "state": "closed", "state_reason": "completed",
    }]


@pytest.mark.parametrize(("latest", "pinned"), [("v8.31.0-private", "v8.30.1"), ("v8.31.0", "malformed")])
def test_malformed_metadata_fails_before_issue_writes(latest: str, pinned: str) -> None:
    result = _run_monitor(latest, pinned)
    assert "error" in result
    assert result["calls"] == []
    assert "private" not in result["error"]


def test_monitor_consolidates_duplicates_and_closes_its_resolved_failure() -> None:
    bot = {"login": "github-actions[bot]"}
    issues = [
        {"number": 12, "user": bot, "body": "<!-- gitleaks-hook-version-drift -->"},
        {"number": 13, "user": bot, "body": "<!-- gitleaks-hook-version-drift --> duplicate"},
        {"number": 14, "user": bot, "body": "<!-- gitleaks-hook-monitor-failure -->"},
    ]
    calls = _run_monitor("v8.31.0", issues=issues)["calls"]
    assert [call["issue_number"] for call in calls] == [14, 12, 13]
    assert calls[0]["state"] == "closed"
    assert "body" in calls[1]
    assert calls[2]["state"] == "closed"


def test_failure_report_is_actionable_and_deduplicated() -> None:
    result = _run_monitor("invalid-private-tag", step=1)
    assert len(result["calls"]) == 1
    call = result["calls"][0]
    assert call["operation"] == "create"
    assert "invalid-private-tag" not in call["body"]
    assert "rerunning ci-latest on main" in call["body"]
    existing = {"number": 12, "user": {"login": "github-actions[bot]"}, "body": call["body"]}
    assert _run_monitor("invalid-private-tag", issues=[existing], step=1)["calls"] == []
