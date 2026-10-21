"""The ci-latest tracking issue explains *why* a probe failed, not only which step."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from scripts import ci_latest_report as report

ROOT = Path(__file__).resolve().parents[2]

NODE = shutil.which("node")
NODE_TIMEOUT_SECONDS = 60

LOCK = """
[[package]]
name = "numpy"
version = "2.4.6"

[[package]]
name = "typing-extensions"
version = "4.15.0"

[[package]]
name = "basedpyright"
version = "1.40.2"
"""

PYPROJECT = """
[project]
dependencies = ["numpy >= 2.2.4"]
[project.optional-dependencies]
dev = ["basedpyright>=1.30"]
gui = []
"""


def _fixture(tmp_path: Path, freeze: str, logs: dict[str, str]) -> tuple[Path, Path, Path]:
    lock = tmp_path / "uv.lock"
    lock.write_text(LOCK, encoding="utf-8")
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(PYPROJECT, encoding="utf-8")
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    (log_dir / "freeze.txt").write_text(freeze, encoding="utf-8")
    for name, text in logs.items():
        (log_dir / f"{name}.log").write_text(text, encoding="utf-8")
    return log_dir, lock, pyproject


def test_basedpyright_configuration_failure_is_not_reported_as_type_errors(tmp_path: Path) -> None:
    freeze = "-e git+https://example.invalid/repo@abc#egg=guiskindose\nnumpy==2.4.6\nbasedpyright==1.40.2\n"
    log = "venv .venv subdirectory not found in venv path /work/repo.\n0 errors, 0 warnings, 0 notes\n[exit code 3]\n"
    log_dir, lock, pyproject = _fixture(tmp_path, freeze, {"basedpyright": log})
    text = report.build_report(["basedpyright"], log_dir, log_dir / "freeze.txt", lock, pyproject)
    assert "exit code 3: configuration error" in text
    assert "venv .venv subdirectory not found" in text
    assert "[exit code 3]" not in text
    assert "Nothing differs from `uv.lock`" in text


def test_pytest_excerpt_lists_failures_and_the_summary_line(tmp_path: Path) -> None:
    log = "\n".join(
        ["\x1b[31m....F....\x1b[0m", "/work/repo/tests/test_a.py:3: AssertionError"]
        + [f"FAILED tests/test_a.py::test_{i} - AssertionError" for i in range(report.MAX_EXCERPT_LINES + 5)]
        + ["45 failed, 10 passed in 1.00s", "[exit code 1]"]
    )
    log_dir, lock, pyproject = _fixture(tmp_path, "numpy==2.5.0\n", {"pytest": log})
    text = report.build_report(["pytest"], log_dir, log_dir / "freeze.txt", lock, pyproject, "/work/repo")
    assert "(exit code 1)" in text
    assert "FAILED tests/test_a.py::test_0 - AssertionError" in text
    assert "... 5 more" in text
    assert "45 failed, 10 passed" in text
    assert "\x1b[" not in text


def test_transitive_only_drift_is_not_dismissed_as_environment(tmp_path: Path) -> None:
    log_dir, lock, pyproject = _fixture(tmp_path, "numpy==2.4.6\ntyping_extensions==4.16.0\n", {})
    text = report.build_report([], log_dir, log_dir / "freeze.txt", lock, pyproject)
    assert "but the transitive packages below do" in text
    assert "unlikely cause" not in text


def test_absolute_paths_are_collapsed_but_test_ids_kept(tmp_path: Path) -> None:
    log = (
        "FAILED tests/unittests/test_a.py::test_x - CalledProcessError: Command '['/opt/tool/1.0/bin/uv', 'run']'\n"
        "E   OSError: /tmp/pytest-of-runner/pytest-0/x/out.json not found\n"
        "[exit code 1]\n"
    )
    log_dir, lock, pyproject = _fixture(tmp_path, "", {"pytest": log})
    _, excerpt = report.probe_excerpt("pytest", log)
    assert excerpt[0].startswith("FAILED tests/unittests/test_a.py::test_x")
    assert "'.../uv'" in excerpt[0]
    assert "/opt/tool" not in excerpt[0]
    text = report.build_report(["pytest"], log_dir, log_dir / "freeze.txt", lock, pyproject)
    assert "/opt/tool" not in text


def test_marker_after_unterminated_output_is_still_read() -> None:
    # The workflow writes printf '\n[exit code %s]\n', so a last line without "\n" stays apart.
    exit_code, excerpt = report.probe_excerpt("basedpyright", "partial line\n[exit code 3]\n")
    assert exit_code == 3
    assert excerpt == ["partial line"]


def test_pytest_captured_log_errors_are_not_listed_as_failures() -> None:
    log = "ERROR    guiskindose.io:io.py:12 could not read\nFAILED tests/t.py::test_a - boom\n1 failed\n"
    _, excerpt = report.probe_excerpt("pytest", log)
    assert excerpt == ["FAILED tests/t.py::test_a - boom", "1 failed"]


def test_every_probe_and_the_drift_section_survive_large_logs(tmp_path: Path) -> None:
    probes = ["install", "basedpyright", "gui_placement", "semgrep_owasp", "semgrep_privacy", "pytest"]
    big = "\n".join(f"FAILED tests/t.py::test_{i} - " + "x" * 400 for i in range(60)) + "\n[exit code 1]\n"
    log_dir, lock, pyproject = _fixture(tmp_path, "numpy==2.5.0\n", dict.fromkeys(probes, big))
    text = report.build_report(probes, log_dir, log_dir / "freeze.txt", lock, pyproject)
    assert all(f"<b>{probe}</b>" in text for probe in probes)
    assert "| numpy | 2.4.6 | 2.5.0 |" in text
    assert text.count("```text") * 2 == text.count("```")
    assert len(text) < 50_000


def test_drift_puts_direct_dependencies_in_a_table(tmp_path: Path) -> None:
    freeze = "numpy==2.5.0\ntyping_extensions==4.16.0\nbasedpyright==1.40.2\nnew-pkg==1.0\n"
    log_dir, lock, pyproject = _fixture(tmp_path, freeze, {})
    text = report.build_report(["install"], log_dir, log_dir / "freeze.txt", lock, pyproject)
    assert "1 direct, 2 transitive" in text
    assert "| numpy | 2.4.6 | 2.5.0 |" in text
    assert "typing_extensions 4.15.0 → 4.16.0" in text
    assert "new-pkg - → 1.0" in text
    assert "basedpyright" not in text
    assert "**install**: no log captured" in text


def test_missing_freeze_and_oversized_logs_stay_bounded(tmp_path: Path) -> None:
    log = "\n".join("x" * 1000 for _ in range(500)) + "\n[exit code 2]\n"
    log_dir, lock, pyproject = _fixture(tmp_path, "", {"semgrep_owasp": log})
    (log_dir / "freeze.txt").unlink()
    text = report.build_report(["semgrep_owasp"], log_dir, log_dir / "freeze.txt", lock, pyproject)
    assert "not available (the install did not finish)" in text
    assert len(text) <= report.MAX_PROBE_CHARS + 1_000
    assert "... (cut; see the run log)" in text


def _run_issue_step(report_path: Path | None, issues: list[dict]) -> list[dict]:
    workflow = yaml.safe_load((ROOT / ".github/workflows/ci-latest.yml").read_text(encoding="utf-8"))
    steps = {step.get("name"): step for step in workflow["jobs"]["latest-deps"]["steps"]}
    step = steps["Open issue and notify on failure"]
    assert step["env"]["REPORT_PATH"] == "${{ runner.temp }}/ci-latest/report.md"
    harness = r"""
const fs = require('fs');
const {script, env, issues} = JSON.parse(fs.readFileSync(0, 'utf8'));
Object.assign(process.env, env);
const calls = [];
const context = {repo: {owner: 'synthetic-owner', repo: 'synthetic-repo'}, sha: 'synthetic-sha',
  serverUrl: 'https://github.com', runId: 42};
const github = {rest: {issues: {
  listForRepo: () => {},
  create: async args => { calls.push({operation: 'create', ...args}); return {data: {number: 7}}; },
  createComment: async args => { calls.push({operation: 'comment', ...args}); },
}}, paginate: async () => issues};
const core = {info: () => {}};
const AsyncFunction = Object.getPrototypeOf(async function(){}).constructor;
new AsyncFunction('github', 'context', 'core', 'require', script)(github, context, core, require)
  .then(() => process.stdout.write(JSON.stringify({calls})))
  .catch(error => process.stdout.write(JSON.stringify({calls, error: error.message})));
"""
    env = {
        "BASEDPRIGHT_OUTCOME": "failure",
        "PYTEST_OUTCOME": "success",
        "REPORT_PATH": str(report_path) if report_path else "/nonexistent/report.md",
    }
    assert NODE is not None
    result = subprocess.run(
        [NODE, "-e", harness],
        input=json.dumps({"script": step["with"]["script"], "env": env, "issues": issues}),
        capture_output=True,
        text=True,
        check=True,
        timeout=NODE_TIMEOUT_SECONDS,
    )
    parsed = json.loads(result.stdout)
    assert "error" not in parsed, parsed.get("error")
    return parsed["calls"]


@pytest.mark.skipif(NODE is None, reason="Node.js is needed for the GitHub-script reproduction")
def test_issue_embeds_the_report_and_comments_on_an_existing_issue(tmp_path: Path) -> None:
    report_path = tmp_path / "report.md"
    report_path.write_text("SYNTHETIC-REPORT exit code 3: configuration error", encoding="utf-8")
    calls = _run_issue_step(report_path, [])
    assert [call["operation"] for call in calls] == ["create"]
    assert "SYNTHETIC-REPORT" in calls[0]["body"]
    assert "**basedpyright**" in calls[0]["body"]
    assert "two Mondays running" in calls[0]["body"]
    existing = [{"number": 9, "body": calls[0]["body"]}]
    calls = _run_issue_step(report_path, existing)
    assert [(call["operation"], call["issue_number"]) for call in calls] == [("comment", 9)]


@pytest.mark.skipif(NODE is None, reason="Node.js is needed for the GitHub-script reproduction")
def test_issue_is_still_filed_when_the_report_is_missing() -> None:
    calls = _run_issue_step(None, [])
    assert "failure summary was not generated" in calls[0]["body"]


def test_every_probe_can_open_and_close_the_issue() -> None:
    """A probe missing from one condition either never reports or closes the issue while red."""
    workflow = yaml.safe_load((ROOT / ".github/workflows/ci-latest.yml").read_text(encoding="utf-8"))
    steps = workflow["jobs"]["latest-deps"]["steps"]
    probes = [step["id"] for step in steps if step.get("continue-on-error") and step.get("id") != "report"]
    assert {"pytest", "floors_install", "floors_pytest"} <= set(probes)
    by_name = {step.get("name"): step for step in steps}
    report = next(step for step in steps if step.get("id") == "report")
    opener = by_name["Open issue and notify on failure"]
    closer = by_name["Close ci-latest tracking issues on success"]
    for probe in probes:
        assert f"steps.{probe}.outcome == 'failure'" in report["if"]
        assert f"steps.{probe}.outcome == 'failure'" in opener["if"]
        assert f"steps.{probe}.outcome == 'success'" in closer["if"]
        assert f"{probe}=${{{{ steps.{probe}.outcome }}}}" in report["env"]["OUTCOMES"]
        assert f"['{probe}', process.env." in opener["with"]["script"]
        assert f"{probe}: {{" in opener["with"]["script"]
